from __future__ import annotations

from sqlalchemy.orm import Session

from ..config import DetectionSettings
from ..models import AppSetting

KEY = "detection"


def load_settings(db: Session) -> DetectionSettings:
    row = db.get(AppSetting, KEY)
    return DetectionSettings.from_dict(row.value if row else None)


def save_settings(db: Session, values: dict) -> DetectionSettings:
    current = load_settings(db).to_dict()
    current.update(values or {})
    settings = DetectionSettings.from_dict(current)
    row = db.get(AppSetting, KEY)
    if row is None:
        row = AppSetting(key=KEY, value=settings.to_dict())
        db.add(row)
    else:
        row.value = settings.to_dict()
    db.commit()
    return settings


def reset_settings(db: Session) -> DetectionSettings:
    row = db.get(AppSetting, KEY)
    if row is not None:
        db.delete(row)
        db.commit()
    return DetectionSettings()
