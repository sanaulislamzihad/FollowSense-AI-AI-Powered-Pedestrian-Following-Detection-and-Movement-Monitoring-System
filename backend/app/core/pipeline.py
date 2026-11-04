"""End-to-end video analysis pipeline.

video/stream -> resize -> YOLO + tracker -> camera motion compensation -> track store
-> following engine / group tracker / crowd monitor -> annotated output + callbacks.

The pipeline is independent of the web app: the job manager passes callbacks to persist
events and push live updates, and ``scripts/analyze_video.py`` runs it from the CLI.
"""
from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import cv2
import numpy as np

from ..config import DetectionSettings
from .annotate import draw_frame
from .crowd import CrowdMonitor, MovementAccumulator
from .detector import PedestrianTracker
from .following import SEVERITY, EngineEvent, FollowingEngine, Relationship
from .motion import CameraMotionCompensator
from .tracks import TrackStore

MAX_SIDE = 1280  # frames are processed / written at most this large


def is_stream_source(source: str) -> bool:
    s = str(source).lower()
    return s.isdigit() or s.startswith(("rtsp://", "rtmp://", "http://", "https://", "udp://"))


def open_capture(source: str) -> cv2.VideoCapture:
    src = int(source) if str(source).isdigit() else str(source)
    cap = cv2.VideoCapture(src)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video source: {source}")
    return cap


class LatestFrameReader:
    """For live streams: read continuously in a thread and only keep the newest frame,
    so slow processing drops frames instead of accumulating latency."""

    def __init__(self, cap: cv2.VideoCapture):
        self.cap = cap
        self.frame = None
        self.seq = 0
        self.alive = True
        self.cond = threading.Condition()
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def _loop(self) -> None:
        failures = 0
        while self.alive:
            ok, frame = self.cap.read()
            if not ok:
                failures += 1
                if failures > 50:
                    break
                time.sleep(0.1)
                continue
            failures = 0
            with self.cond:
                self.frame, self.seq = frame, self.seq + 1
                self.cond.notify_all()
        self.alive = False
        with self.cond:
            self.cond.notify_all()

    def read(self, last_seq: int, timeout: float = 5.0):
        with self.cond:
            self.cond.wait_for(lambda: self.seq != last_seq or not self.alive, timeout=timeout)
            if self.seq == last_seq:
                return None, last_seq
            return self.frame, self.seq

    def stop(self) -> None:
        self.alive = False


class VideoWriter:
    """H.264 MP4 writer (browser playable) using the ffmpeg binary from imageio-ffmpeg."""

    def __init__(self, path: Path, width: int, height: int, fps: float):
        import imageio_ffmpeg

        self.gen = imageio_ffmpeg.write_frames(
            str(path), (width, height), fps=fps, codec="libx264", quality=None, bitrate=None,
            pix_fmt_in="bgr24", pix_fmt_out="yuv420p", macro_block_size=2,
            output_params=["-preset", "veryfast", "-crf", "26", "-movflags", "+faststart"],
        )
        self.gen.send(None)

    def write(self, frame: np.ndarray) -> None:
        self.gen.send(np.ascontiguousarray(frame))

    def close(self) -> None:
        try:
            self.gen.close()
        except Exception:  # noqa: BLE001
            pass


@dataclass
class Callbacks:
    on_event: Callable[[EngineEvent, np.ndarray, float], None] | None = None
    on_progress: Callable[[dict], None] | None = None
    on_frame: Callable[[np.ndarray, dict], None] | None = None


@dataclass
class AnalysisResult:
    duration: float = 0.0
    frames_processed: int = 0
    processing_fps: float = 0.0
    width: int = 0
    height: int = 0
    tracks: list = field(default_factory=list)
    heatmap: dict = field(default_factory=dict)
    directions: list = field(default_factory=list)
    speeds: list = field(default_factory=list)
    crowd: dict = field(default_factory=dict)
    relationships: dict = field(default_factory=dict)
    pairs: list = field(default_factory=list)
    camera_motion: float = 0.0
    stopped: bool = False


def _even(v: int) -> int:
    return v - (v % 2)


class VideoAnalyzer:
    def __init__(self, source: str, settings: DetectionSettings, *, model_path: str,
                 device: str = "", output_path: Path | None = None,
                 reference_image_path: Path | None = None,
                 callbacks: Callbacks | None = None, stop_event: threading.Event | None = None):
        self.source = str(source)
        self.s = settings
        self.model_path = model_path
        self.device = device
        self.output_path = output_path
        self.reference_image_path = reference_image_path
        self.cb = callbacks or Callbacks()
        self.stop_event = stop_event or threading.Event()
        self.is_stream = is_stream_source(self.source)

    def run(self) -> AnalysisResult:
        s = self.s
        cap = open_capture(self.source)
        fps = cap.get(cv2.CAP_PROP_FPS) or 0
        if not fps or fps > 240 or math.isnan(fps):
            fps = 25.0
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0) if not self.is_stream else 0
        stride = 1 if (self.is_stream or s.target_fps <= 0) else max(1, int(round(fps / s.target_fps)))
        eff_fps = fps / stride

        tracker = PedestrianTracker(s, self.model_path, self.device, eff_fps)
        store = TrackStore(stale_after_sec=s.occlusion_buffer_sec)
        engine = FollowingEngine(s)
        crowd = CrowdMonitor(s)
        cmc = CameraMotionCompensator(enabled=s.camera_motion_compensation)
        movement: MovementAccumulator | None = None
        writer: VideoWriter | None = None
        result = AnalysisResult()

        frame_idx, processed = -1, 0
        wall_start = time.monotonic()
        last_progress = 0.0
        t = 0.0
        follows_draw: list = []
        reader = LatestFrameReader(cap) if self.is_stream else None
        seq = 0
        try:
            while not self.stop_event.is_set():
                if reader:
                    frame, seq = reader.read(seq)
                    if frame is None:
                        if not reader.alive:
                            break
                        continue
                    frame_idx += 1
                else:
                    if not cap.grab():
                        break
                    frame_idx += 1
                    if frame_idx % stride:
                        continue
                    ok, frame = cap.retrieve()
                    if not ok or frame is None:
                        continue
                t = (time.monotonic() - wall_start) if self.is_stream else frame_idx / fps

                h0, w0 = frame.shape[:2]
                k = min(1.0, MAX_SIDE / max(h0, w0))
                W, H = _even(int(w0 * k)), _even(int(h0 * k))
                if (W, H) != (w0, h0):
                    frame = cv2.resize(frame, (W, H), interpolation=cv2.INTER_AREA)
                if movement is None:
                    result.width, result.height = W, H
                    movement = MovementAccumulator(W, H, s.heatmap_cols)
                    if self.reference_image_path:
                        cv2.imwrite(str(self.reference_image_path), frame)
                    if self.output_path:
                        writer = VideoWriter(self.output_path, W, H, eff_fps)

                dets = tracker(frame)
                boxes = [d[1] for d in dets]
                cmc.update(frame, boxes)
                feet = np.array([((b[0] + b[2]) / 2, b[3]) for b in boxes]).reshape(-1, 2)
                ref = cmc.to_reference(feet)
                store.update(t, frame_idx, dets, [tuple(p) for p in ref])
                movement.add_points(ref)

                visible = [d for d in dets if store.tracks[d[0]].hits >= s.min_track_hits]
                events: list[EngineEvent] = crowd.update(
                    t, [d[0] for d in visible], [d[1] for d in visible])

                if engine.due(t):
                    events += engine.step(store, t)
                    for tr in store.visible(s.min_track_hits):
                        v = tr.velocity_at(t, s.velocity_window_sec)
                        if v is not None:
                            sp = math.hypot(*v) / max(tr.mean_height(), 1)
                            if sp > s.min_moving_speed:
                                movement.add_velocity(v[0], v[1], sp)
                    store.prune(s.analysis_window_sec + s.max_lag_sec + 2)
                    follows_draw = [(st.leader_id, st.follower_id, engine._confidence(st))
                                    for st in engine.active_following()]

                # ---- annotate --------------------------------------------------
                trajectories = {}
                for tid, _, _ in visible:
                    obs = [o for o in store.tracks[tid].observations if t - o.t <= s.trajectory_history_sec]
                    if len(obs) >= 2:
                        trajectories[tid] = cmc.to_frame([(o.x, o.y) for o in obs])
                groups = {g.key: sorted(g.members) for g in engine.groups.groups.values()}
                hud = {"t": t, "count": crowd.count, "level": crowd.level}
                annotated = draw_frame(frame, detections=visible, trajectories=trajectories,
                                       follows=follows_draw, groups=groups,
                                       clusters=crowd.clusters, hud=hud)
                if writer:
                    writer.write(annotated)
                processed += 1

                for ev in events:
                    if self.cb.on_event:
                        self.cb.on_event(ev, annotated, t)

                status = {
                    "t": round(t, 2),
                    "frame": frame_idx,
                    "total_frames": total,
                    "progress": round(min(1.0, frame_idx / total), 4) if total else None,
                    "count": crowd.count,
                    "level": crowd.level,
                    "clusters": len(crowd.clusters),
                    "tracks_total": sum(1 for tr in store.tracks.values() if tr.hits >= s.min_track_hits),
                    "following_active": len(follows_draw),
                    "groups_active": len(groups),
                    "processing_fps": round(processed / max(time.monotonic() - wall_start, 1e-6), 2),
                }
                if self.cb.on_frame:
                    self.cb.on_frame(annotated, status)
                now = time.monotonic()
                if self.cb.on_progress and now - last_progress >= 1.0:
                    last_progress = now
                    self.cb.on_progress(status)
        finally:
            for ev in engine.finish(t) + crowd.finish():
                if self.cb.on_event:
                    self.cb.on_event(ev, None, t)
            if reader:
                reader.stop()
                reader.thread.join(timeout=3)
            cap.release()
            if writer:
                writer.close()
            tracker.close()

        result.stopped = self.stop_event.is_set()
        result.duration = round(t, 2)
        result.frames_processed = processed
        result.processing_fps = round(processed / max(time.monotonic() - wall_start, 1e-6), 2)
        result.camera_motion = round(cmc.total_shift, 1)
        result.crowd = crowd.summary()
        if movement:
            result.heatmap = movement.heatmap()
            result.heatmap["zones"] = movement.congestion_zones()
            result.directions = movement.direction_bins.tolist()
            result.speeds = movement.speed_samples[-5000:]
        result.tracks = self._track_summaries(store)
        result.relationships, result.pairs = self._relationship_summary(engine)
        return result

    def _track_summaries(self, store: TrackStore) -> list[dict]:
        out = []
        for tr in store.tracks.values():
            if tr.hits < self.s.min_track_hits:
                continue
            dur = max(tr.last_seen - tr.first_seen, 1e-6)
            direction = None
            if len(tr.path) >= 2:
                (_, x0, y0), (_, x1, y1) = tr.path[0], tr.path[-1]
                if math.hypot(x1 - x0, y1 - y0) > 5:
                    direction = round(math.degrees(math.atan2(-(y1 - y0), x1 - x0)) % 360, 1)
            out.append({
                "track_id": tr.track_id,
                "first_seen": round(tr.first_seen, 2),
                "last_seen": round(tr.last_seen, 2),
                "hits": tr.hits,
                "total_distance": round(tr.total_distance, 2),
                "avg_speed": round(tr.total_distance / dur, 3),
                "direction": direction,
                "path": tr.path,
            })
        return out

    @staticmethod
    def _relationship_summary(engine: FollowingEngine) -> tuple[dict, list]:
        counts = {r.value: 0 for r in Relationship}
        pairs = []
        for (a, b), summ in engine.pair_summary.items():
            c = summ["counts"]
            meaningful = {k: v for k, v in c.items() if k != Relationship.INSUFFICIENT.value}
            if c.get(Relationship.POTENTIAL_FOLLOWING.value, 0) >= 4:
                label = Relationship.POTENTIAL_FOLLOWING.value
            elif meaningful:
                label = max(meaningful, key=lambda k: (meaningful[k], SEVERITY[Relationship(k)]))
            else:
                label = Relationship.INSUFFICIENT.value
            counts[label] += 1
            pairs.append({"a": a, "b": b, "label": label, "max_score": round(summ["max_score"], 3)})
        return counts, pairs
