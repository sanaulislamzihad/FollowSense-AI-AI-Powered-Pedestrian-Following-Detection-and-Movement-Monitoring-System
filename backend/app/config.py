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
    confidence_threshold: float = 0.25
    iou_threshold: float = 0.5
    image_size: int = 1280  # larger input finds small / distant people in crowds
    detection_mode: str = "standard"  # standard | tiled (extra full-res tiles for dense crowds)
    tile_size: int = 640
    tracker: str = "bytetrack"  # bytetrack | botsort
    target_fps: float = 15.0  # frames analysed per second of video (0 = every frame)
    occlusion_buffer_sec: float = 3.0  # keep lost tracks alive this long (occlusions)
    min_track_hits: int = 3  # ignore tracks shorter than this many detections
    camera_motion_compensation: bool = True  # stabilise coordinates for moving / shaky cameras

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

    # --- crowd management ---
    crowd_warning_count: int = 25  # people in view -> "elevated" crowd level
    crowd_critical_count: int = 45  # people in view -> "critical" level / overcrowding alert
    congestion_distance: float = 0.9  # neighbours closer than this (body heights) form a cluster
    congestion_min_people: int = 6  # cluster size considered a congestion zone
    crowd_alert_min_duration_sec: float = 3.0

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
                if isinstance(default, bool):
                    clean[key] = value if isinstance(value, bool) else str(value).lower() in ("1", "true", "yes", "on")
                else:
                    clean[key] = type(default)(value)
            except (TypeError, ValueError):
                continue
        return cls(**clean)

    def to_dict(self) -> dict:
        return asdict(self)
