"""Request bodies and response serialisers."""
from __future__ import annotations

from pydantic import BaseModel, Field

from .models import AnalysisJob, Camera, CrowdEvent, FollowingEvent, GroupEvent, Video


class JobCreate(BaseModel):
    video_id: int | None = None
    camera_id: int | None = None
    source: str | None = Field(None, description="RTSP/HTTP URL or webcam index for an ad-hoc live job")
    settings: dict = Field(default_factory=dict, description="per-job overrides of the saved settings")


class CameraIn(BaseModel):
    name: str
    source_url: str
    location: str = ""
    enabled: bool = True


class ReviewIn(BaseModel):
    status: str | None = Field(None, pattern="^(new|confirmed|dismissed|reviewed)$")
    notes: str | None = None


def video_out(v: Video, latest_job: AnalysisJob | None = None) -> dict:
    return {
        "id": v.id, "original_name": v.original_name, "size_bytes": v.size_bytes, "duration": v.duration,
        "fps": v.fps, "width": v.width, "height": v.height, "frame_count": v.frame_count,
        "created_at": v.created_at, "latest_job": job_out(latest_job, brief=True) if latest_job else None,
    }


def camera_out(c: Camera, live_job: AnalysisJob | None = None) -> dict:
    return {"id": c.id, "name": c.name, "source_url": c.source_url, "location": c.location,
            "enabled": c.enabled, "created_at": c.created_at,
            "live_job_id": live_job.id if live_job else None}


def job_out(j: AnalysisJob, brief: bool = False, runtime=None) -> dict:
    d = {
        "id": j.id, "video_id": j.video_id, "camera_id": j.camera_id, "is_live": j.is_live,
        "status": j.status, "progress": j.progress, "error": j.error, "created_at": j.created_at,
        "started_at": j.started_at, "finished_at": j.finished_at, "duration": j.duration,
        "total_pedestrians": j.total_pedestrians, "peak_count": j.peak_count, "average_count": j.average_count,
        "processing_fps": j.processing_fps, "frames_processed": j.frames_processed,
        "width": j.width, "height": j.height, "has_output": bool(j.output_path),
        "source_name": j.video.original_name if j.video else (j.camera.name if j.camera else j.source),
        "following_count": len(j.following_events), "crowd_alert_count": len(j.crowd_events),
        "group_count": len(j.group_events),
    }
    if runtime is not None and not runtime.done:
        d["live"] = runtime.status
    if not brief:
        d.update({"settings": j.settings, "relationships": j.relationships, "camera_motion": j.camera_motion})
    return d


def following_out(e: FollowingEvent) -> dict:
    return {
        "id": e.id, "job_id": e.job_id, "event_key": e.event_key, "leader_id": e.leader_id,
        "follower_id": e.follower_id, "start_time": e.start_time, "end_time": e.end_time,
        "duration": e.duration, "confidence": e.confidence, "consistency": e.consistency,
        "metrics": e.metrics, "classification": e.classification, "status": e.status,
        "is_active": e.is_active, "notes": e.notes, "has_snapshot": bool(e.snapshot_path),
        "created_at": e.created_at, "reviewed_at": e.reviewed_at,
    }


def group_out(g: GroupEvent) -> dict:
    return {"id": g.id, "job_id": g.job_id, "group_key": g.group_key, "members": g.members,
            "all_members": g.all_members, "max_size": g.max_size, "start_time": g.start_time,
            "end_time": g.end_time, "duration": g.duration, "history": g.history, "is_active": g.is_active}


def crowd_out(c: CrowdEvent) -> dict:
    return {"id": c.id, "job_id": c.job_id, "event_key": c.event_key, "crowd_type": c.crowd_type,
            "start_time": c.start_time, "end_time": c.end_time, "duration": c.duration,
            "peak_count": c.peak_count, "peak_time": c.peak_time, "location": c.location,
            "status": c.status, "is_active": c.is_active, "has_snapshot": bool(c.snapshot_path),
            "created_at": c.created_at}
