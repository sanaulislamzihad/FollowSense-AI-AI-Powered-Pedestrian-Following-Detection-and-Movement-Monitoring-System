"""Application configuration and default detection settings."""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class AppConfig(BaseSettings):
    """Environment driven configuration (prefix ``FS_``)."""

    model_config = SettingsConfigDict(env_prefix="FS_", env_file=".env", extra="ignore")

    # PostgreSQL in production, e.g. postgresql+psycopg2://user:pass@db:5432/followsense
    database_url: str = f"sqlite:///{(BASE_DIR / 'data' / 'followsense.db').as_posix()}"
    data_dir: Path = BASE_DIR / "data"
    yolo_model: str = "yolo11n.pt"
    device: str = ""  # "" = auto, "cpu", "0" ...
    max_parallel_jobs: int = 2
    cors_origins: str = "*"

    @property
    def upload_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def output_dir(self) -> Path:
        return self.data_dir / "outputs"

    @property
    def snapshot_dir(self) -> Path:
        return self.data_dir / "snapshots"

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.upload_dir, self.output_dir, self.snapshot_dir):
            d.mkdir(parents=True, exist_ok=True)


app_config = AppConfig()


@dataclass
class DetectionSettings:
    """Tunable thresholds used by the detection, tracking and following engines.

    Spatial values are expressed in *body heights* (the average bounding-box height
    of the people involved). This keeps thresholds roughly independent of camera
    resolution and of how far people are from the camera.
    """

    # --- detection / tracking ---
    confidence_threshold: float = 0.35
    iou_threshold: float = 0.5
    image_size: int = 640
    tracker: str = "bytetrack"  # bytetrack | botsort
    frame_stride: int = 1  # process every Nth frame (speed up on CPU)
    min_track_hits: int = 3  # ignore tracks shorter than this many detections

    # --- movement analysis ---
    velocity_window_sec: float = 0.6
    min_moving_speed: float = 0.15  # body heights / second
    trajectory_history_sec: float = 8.0

    # --- following detection ---
    analysis_window_sec: float = 4.0
    analysis_interval_sec: float = 0.25
    min_following_duration_sec: float = 5.0
    gap_tolerance_sec: float = 1.5
    follow_min_distance: float = 0.7
    follow_max_distance: float = 6.0
    direction_similarity_threshold: float = 0.8
    speed_consistency_threshold: float = 0.55
    trajectory_similarity_threshold: float = 0.5
    behind_ratio_threshold: float = 0.7
    min_lag_sec: float = 0.4
    max_lag_sec: float = 6.0
    min_alert_confidence: float = 0.5

    # --- group walking ---
    group_max_distance: float = 1.6
    min_group_duration_sec: float = 3.0

    # --- heatmap ---
    heatmap_cols: int = 64

    @classmethod
    def from_dict(cls, data: dict | None) -> "DetectionSettings":
        data = data or {}
        valid = {f.name: f.type for f in fields(cls)}
        clean = {}
        defaults = cls()
        for key, value in data.items():
            if key not in valid or value is None:
                continue
            default = getattr(defaults, key)
            try:
                clean[key] = type(default)(value)
            except (TypeError, ValueError):
                continue
        return cls(**clean)

    def to_dict(self) -> dict:
        return asdict(self)
