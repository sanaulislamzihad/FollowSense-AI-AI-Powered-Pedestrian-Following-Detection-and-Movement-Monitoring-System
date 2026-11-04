"""Server-side rendering of heatmaps and trajectory maps (used by the API and PDF reports)."""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from ..core.annotate import id_color


def _background(job) -> np.ndarray:
    w, h = job.width or 1280, job.height or 720
    if job.reference_image and Path(job.reference_image).exists():
        img = cv2.imread(job.reference_image)
        if img is not None:
            return cv2.resize(img, (w, h))
    return np.full((h, w, 3), 40, np.uint8)


def heatmap_image(job, alpha: float = 0.55) -> np.ndarray:
    base = _background(job)
    hm = job.heatmap or {}
    values = np.asarray(hm.get("values") or [[0]], np.float32)
    h, w = base.shape[:2]
    grid = cv2.resize(values, (w, h), interpolation=cv2.INTER_CUBIC)
    grid = cv2.GaussianBlur(grid, (0, 0), sigmaX=max(w, h) / 120)
    if grid.max() > 0:
        grid = grid / grid.max()
    grid = np.clip(grid, 0, 1)
    colored = cv2.applyColorMap((grid * 255).astype(np.uint8), cv2.COLORMAP_JET)
    mask = (grid > 0.05)[..., None]
    a = (alpha * np.clip(grid * 1.5, 0, 1))[..., None]
    dim = (base * 0.65).astype(np.uint8)
    out = np.where(mask, (dim * (1 - a) + colored * a).astype(np.uint8), dim)
    return out


def trajectory_image(job, tracks, highlight: set[int] | None = None) -> np.ndarray:
    base = (_background(job) * 0.55).astype(np.uint8)
    highlight = highlight or set()
    for tr in tracks:
        pts = np.array([[p[1], p[2]] for p in tr.path], np.int32)
        if len(pts) < 2:
            continue
        hot = tr.track_id in highlight
        color = (60, 60, 235) if hot else id_color(tr.track_id)
        cv2.polylines(base, [pts.reshape(-1, 1, 2)], False, color, 4 if hot else 2, cv2.LINE_AA)
        cv2.circle(base, tuple(pts[-1]), 5 if hot else 3, color, -1)
        if hot:
            cv2.putText(base, f"ID {tr.track_id}", tuple(pts[-1] + 6), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                        (255, 255, 255), 2, cv2.LINE_AA)
    return base


def encode_png(img: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".png", img)
    return buf.tobytes() if ok else b""


def encode_jpeg(img: np.ndarray, quality: int = 85) -> bytes:
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return buf.tobytes() if ok else b""
