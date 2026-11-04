"""Background job manager: runs the analysis pipeline and persists its results."""
from __future__ import annotations

import logging
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

import cv2
import numpy as np

from ..config import DetectionSettings, app_config
from ..core.following import EngineEvent
from ..core.pipeline import Callbacks, VideoAnalyzer
from ..database import SessionLocal
from ..models import AnalysisJob, CrowdEvent, FollowingEvent, GroupEvent, TrackRecord, utcnow
from .realtime import hub

log = logging.getLogger(__name__)


@dataclass
class JobRuntime:
    job_id: int
    stop_event: threading.Event = field(default_factory=threading.Event)
    status: dict = field(default_factory=dict)
    jpeg: bytes | None = None
    frame_seq: int = 0
    viewers: int = 0
    cond: threading.Condition = field(default_factory=threading.Condition)
    db_ids: dict = field(default_factory=dict)  # engine event key -> DB row id
    last_db_progress: float = 0.0
    last_jpeg_time: float = 0.0
    done: bool = False


class JobManager:
    def __init__(self, max_workers: int = 2):
        self.executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="analysis")
        self.runtimes: dict[int, JobRuntime] = {}
        self.lock = threading.Lock()

    # ---------------------------------------------------------------- control
    def submit(self, job_id: int) -> None:
        with self.lock:
            rt = self.runtimes[job_id] = JobRuntime(job_id)
        self.executor.submit(self._run, rt)

    def stop(self, job_id: int) -> bool:
        rt = self.runtimes.get(job_id)
        if rt is None or rt.done:
            return False
        rt.stop_event.set()
        return True

    def runtime(self, job_id: int) -> JobRuntime | None:
        return self.runtimes.get(job_id)

    def recover(self) -> None:
        """Called at start-up: interrupted jobs fail, queued file jobs are re-queued."""
        with SessionLocal() as db:
            for job in db.query(AnalysisJob).filter(AnalysisJob.status.in_(["running", "queued"])).all():
                if job.status == "running" or job.is_live:
                    job.status, job.error = "failed", "Interrupted by server restart"
                    job.finished_at = utcnow()
                else:
                    self.submit(job.id)
            db.commit()

    def shutdown(self) -> None:
        for rt in self.runtimes.values():
            rt.stop_event.set()
        self.executor.shutdown(wait=False, cancel_futures=True)

    # ---------------------------------------------------------------- worker
    def _run(self, rt: JobRuntime) -> None:
        job_id = rt.job_id
        with SessionLocal() as db:
            job = db.get(AnalysisJob, job_id)
            if job is None:
                return
            if rt.stop_event.is_set():
                job.status = "stopped"
                db.commit()
                return
            job.status, job.started_at, job.progress = "running", utcnow(), 0.0
            db.commit()
            source, settings_dict = job.source, job.settings or {}
        hub.publish({"type": "job", "job_id": job_id, "status": "running"})

        settings = DetectionSettings.from_dict(settings_dict)
        out_path = app_config.output_dir / f"job_{job_id}.mp4"
        ref_path = app_config.output_dir / f"job_{job_id}_reference.jpg"
        analyzer = VideoAnalyzer(
            source, settings, model_path=app_config.yolo_model, device=app_config.device,
            output_path=out_path, reference_image_path=ref_path,
            callbacks=Callbacks(
                on_event=lambda ev, frame, t: self._on_event(rt, ev, frame),
                on_progress=lambda st: self._on_progress(rt, st),
                on_frame=lambda frame, st: self._on_frame(rt, frame, st),
            ),
            stop_event=rt.stop_event,
        )
        try:
            result = analyzer.run()
            self._save_result(job_id, result, out_path, ref_path)
        except Exception as exc:  # noqa: BLE001
            log.exception("job %s failed", job_id)
            with SessionLocal() as db:
                job = db.get(AnalysisJob, job_id)
                if job:
                    job.status, job.error, job.finished_at = "failed", f"{exc}\n{traceback.format_exc()[-1500:]}", utcnow()
                    db.commit()
            hub.publish({"type": "job", "job_id": job_id, "status": "failed", "error": str(exc)})
        finally:
            rt.done = True
            with rt.cond:
                rt.cond.notify_all()

    def _save_result(self, job_id: int, result, out_path, ref_path) -> None:
        with SessionLocal() as db:
            job = db.get(AnalysisJob, job_id)
            job.status = "stopped" if (result.stopped and not job.is_live) else "completed"
            job.progress = 1.0 if job.status == "completed" else job.progress
            job.finished_at = utcnow()
            job.output_path = str(out_path) if out_path.exists() else None
            job.reference_image = str(ref_path) if ref_path.exists() else None
            job.duration = result.duration
            job.frames_processed = result.frames_processed
            job.processing_fps = result.processing_fps
            job.width, job.height = result.width, result.height
            job.total_pedestrians = len(result.tracks)
            job.peak_count = result.crowd.get("peak_count", 0)
            job.average_count = result.crowd.get("average_count", 0)
            job.camera_motion = result.camera_motion
            job.heatmap = result.heatmap
            job.directions = result.directions
            job.speeds = result.speeds
            job.crowd = result.crowd
            job.relationships = result.relationships
            job.pairs = result.pairs
            db.query(TrackRecord).filter(TrackRecord.job_id == job_id).delete()
            db.add_all([TrackRecord(job_id=job_id, **{k: tr[k] for k in (
                "track_id", "first_seen", "last_seen", "hits", "total_distance", "avg_speed", "direction", "path")})
                for tr in result.tracks])
            db.commit()
            status = job.status
        hub.publish({"type": "job", "job_id": job_id, "status": status})

    # ---------------------------------------------------------------- callbacks
    def _on_progress(self, rt: JobRuntime, st: dict) -> None:
        rt.status = st
        hub.publish({"type": "progress", "job_id": rt.job_id, **st})
        now = time.monotonic()
        if now - rt.last_db_progress >= 3 and st.get("progress") is not None:
            rt.last_db_progress = now
            with SessionLocal() as db:
                job = db.get(AnalysisJob, rt.job_id)
                if job:
                    job.progress = st["progress"]
                    db.commit()

    def _on_frame(self, rt: JobRuntime, frame: np.ndarray, st: dict) -> None:
        rt.status = st
        now = time.monotonic()
        # Encode only when somebody watches the live view, at most ~12 fps.
        if rt.viewers <= 0 or now - rt.last_jpeg_time < 0.08:
            return
        rt.last_jpeg_time = now
        h, w = frame.shape[:2]
        k = min(1.0, 960 / max(h, w))
        img = cv2.resize(frame, (int(w * k), int(h * k))) if k < 1 else frame
        ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 72])
        if ok:
            with rt.cond:
                rt.jpeg, rt.frame_seq = buf.tobytes(), rt.frame_seq + 1
                rt.cond.notify_all()

    def _snapshot(self, rt: JobRuntime, key: str, frame) -> str | None:
        if frame is None:
            return None
        path = app_config.snapshot_dir / f"job_{rt.job_id}_{key}.jpg"
        cv2.imwrite(str(path), frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return str(path)

    def _on_event(self, rt: JobRuntime, ev: EngineEvent, frame) -> None:
        p = ev.payload
        try:
            with SessionLocal() as db:
                row_id = rt.db_ids.get(ev.key)
                row = None
                if ev.kind == "following":
                    row = db.get(FollowingEvent, row_id) if row_id else None
                    if row is None:
                        row = FollowingEvent(job_id=rt.job_id, event_key=ev.key, leader_id=p["leader_id"],
                                             follower_id=p["follower_id"],
                                             snapshot_path=self._snapshot(rt, ev.key, frame))
                        db.add(row)
                    for k in ("start_time", "end_time", "duration", "confidence", "consistency", "metrics"):
                        setattr(row, k, p[k])
                elif ev.kind == "group":
                    row = db.get(GroupEvent, row_id) if row_id else None
                    if row is None:
                        row = GroupEvent(job_id=rt.job_id, group_key=ev.key)
                        db.add(row)
                    for k in ("members", "all_members", "max_size", "start_time", "end_time", "duration", "history"):
                        setattr(row, k, p[k])
                elif ev.kind == "crowd":
                    row = db.get(CrowdEvent, row_id) if row_id else None
                    if row is None:
                        row = CrowdEvent(job_id=rt.job_id, event_key=ev.key, crowd_type=p["crowd_type"],
                                         snapshot_path=self._snapshot(rt, ev.key, frame))
                        db.add(row)
                    for k in ("start_time", "end_time", "duration", "peak_count", "peak_time", "location"):
                        setattr(row, k, p[k])
                if row is None:
                    return
                row.is_active = ev.action != "closed"
                db.commit()
                rt.db_ids[ev.key] = row.id
                event_id = row.id
        except Exception:  # noqa: BLE001
            log.exception("could not persist event %s", ev.key)
            return
        hub.publish({"type": "alert" if ev.action == "opened" and ev.kind != "group" else "event",
                     "kind": ev.kind, "action": ev.action, "job_id": rt.job_id,
                     "event_id": event_id, "key": ev.key, **p})


manager = JobManager(max_workers=app_config.max_parallel_jobs)
