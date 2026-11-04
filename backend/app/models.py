from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Video(Base):
    __tablename__ = "videos"

    id: Mapped[int] = mapped_column(primary_key=True)
    original_name: Mapped[str] = mapped_column(String(255))
    path: Mapped[str] = mapped_column(String(500))
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    duration: Mapped[float] = mapped_column(Float, default=0)
    fps: Mapped[float] = mapped_column(Float, default=0)
    width: Mapped[int] = mapped_column(Integer, default=0)
    height: Mapped[int] = mapped_column(Integer, default=0)
    frame_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    jobs: Mapped[list["AnalysisJob"]] = relationship(back_populates="video", cascade="all, delete-orphan")


class Camera(Base):
    __tablename__ = "cameras"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    source_url: Mapped[str] = mapped_column(String(500))  # rtsp://..., http://..., or webcam index
    location: Mapped[str] = mapped_column(String(200), default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    jobs: Mapped[list["AnalysisJob"]] = relationship(back_populates="camera")


class AnalysisJob(Base):
    __tablename__ = "analysis_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    video_id: Mapped[int | None] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"), nullable=True, index=True)
    camera_id: Mapped[int | None] = mapped_column(ForeignKey("cameras.id", ondelete="SET NULL"), nullable=True, index=True)
    source: Mapped[str] = mapped_column(String(500))
    is_live: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)  # queued|running|completed|failed|stopped
    progress: Mapped[float] = mapped_column(Float, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    settings: Mapped[dict] = mapped_column(JSON, default=dict)
    output_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    reference_image: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # results
    duration: Mapped[float] = mapped_column(Float, default=0)
    frames_processed: Mapped[int] = mapped_column(Integer, default=0)
    processing_fps: Mapped[float] = mapped_column(Float, default=0)
    width: Mapped[int] = mapped_column(Integer, default=0)
    height: Mapped[int] = mapped_column(Integer, default=0)
    total_pedestrians: Mapped[int] = mapped_column(Integer, default=0)
    peak_count: Mapped[int] = mapped_column(Integer, default=0)
    average_count: Mapped[float] = mapped_column(Float, default=0)
    camera_motion: Mapped[float] = mapped_column(Float, default=0)
    heatmap: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    directions: Mapped[list | None] = mapped_column(JSON, nullable=True)
    speeds: Mapped[list | None] = mapped_column(JSON, nullable=True)
    crowd: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    relationships: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    pairs: Mapped[list | None] = mapped_column(JSON, nullable=True)

    video: Mapped[Video | None] = relationship(back_populates="jobs")
    camera: Mapped[Camera | None] = relationship(back_populates="jobs")
    tracks: Mapped[list["TrackRecord"]] = relationship(cascade="all, delete-orphan")
    following_events: Mapped[list["FollowingEvent"]] = relationship(cascade="all, delete-orphan")
    group_events: Mapped[list["GroupEvent"]] = relationship(cascade="all, delete-orphan")
    crowd_events: Mapped[list["CrowdEvent"]] = relationship(cascade="all, delete-orphan")


class TrackRecord(Base):
    __tablename__ = "tracks"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("analysis_jobs.id", ondelete="CASCADE"), index=True)
    track_id: Mapped[int] = mapped_column(Integer)
    first_seen: Mapped[float] = mapped_column(Float)
    last_seen: Mapped[float] = mapped_column(Float)
    hits: Mapped[int] = mapped_column(Integer)
    total_distance: Mapped[float] = mapped_column(Float)
    avg_speed: Mapped[float] = mapped_column(Float)
    direction: Mapped[float | None] = mapped_column(Float, nullable=True)
    path: Mapped[list] = mapped_column(JSON, default=list)


class FollowingEvent(Base):
    __tablename__ = "following_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("analysis_jobs.id", ondelete="CASCADE"), index=True)
    event_key: Mapped[str] = mapped_column(String(20))
    leader_id: Mapped[int] = mapped_column(Integer)
    follower_id: Mapped[int] = mapped_column(Integer)
    start_time: Mapped[float] = mapped_column(Float)
    end_time: Mapped[float] = mapped_column(Float)
    duration: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float, index=True)
    consistency: Mapped[float] = mapped_column(Float, default=0)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    classification: Mapped[str] = mapped_column(String(40), default="potential_following")
    status: Mapped[str] = mapped_column(String(20), default="new", index=True)  # new|confirmed|dismissed|reviewed
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    snapshot_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class GroupEvent(Base):
    __tablename__ = "group_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("analysis_jobs.id", ondelete="CASCADE"), index=True)
    group_key: Mapped[str] = mapped_column(String(20))
    members: Mapped[list] = mapped_column(JSON, default=list)
    all_members: Mapped[list] = mapped_column(JSON, default=list)
    max_size: Mapped[int] = mapped_column(Integer, default=0)
    start_time: Mapped[float] = mapped_column(Float)
    end_time: Mapped[float] = mapped_column(Float)
    duration: Mapped[float] = mapped_column(Float)
    history: Mapped[list] = mapped_column(JSON, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CrowdEvent(Base):
    __tablename__ = "crowd_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("analysis_jobs.id", ondelete="CASCADE"), index=True)
    event_key: Mapped[str] = mapped_column(String(20))
    crowd_type: Mapped[str] = mapped_column(String(20))  # overcrowding | congestion
    start_time: Mapped[float] = mapped_column(Float)
    end_time: Mapped[float] = mapped_column(Float)
    duration: Mapped[float] = mapped_column(Float)
    peak_count: Mapped[int] = mapped_column(Integer)
    peak_time: Mapped[float] = mapped_column(Float)
    location: Mapped[list | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="new", index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    snapshot_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
