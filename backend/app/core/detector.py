"""Pedestrian detection (pretrained YOLO) + multi-object tracking (ByteTrack / BoT-SORT).

Crowded scenes contain many small, distant people that a single down-scaled YOLO pass
misses. In ``tiled`` mode the frame is additionally split into overlapping tiles that
are detected at full resolution (SAHI-style); all boxes are merged with NMS and then
handed to the tracker. The trackers are the ultralytics ByteTrack / BoT-SORT
implementations, driven directly so that we control which detections they receive.
"""
from __future__ import annotations

import numpy as np
import torch
from torchvision.ops import nms

from ..config import DetectionSettings

PERSON_CLASS = 0  # COCO "person"
LOW_CONF = 0.1  # low-score boxes feed ByteTrack's second association stage


def tracker_args(settings: DetectionSettings, effective_fps: float) -> dict:
    tracker = settings.tracker.lower().replace(".yaml", "")
    if tracker not in ("bytetrack", "botsort"):
        tracker = "bytetrack"
    high = max(LOW_CONF + 0.05, settings.confidence_threshold)
    args = {
        "tracker_type": tracker,
        "track_high_thresh": high,
        "track_low_thresh": LOW_CONF,
        "new_track_thresh": high + 0.05,
        "track_buffer": max(10, int(round(settings.occlusion_buffer_sec * effective_fps))),
        "match_thresh": 0.8,
        "fuse_score": True,
    }
    if tracker == "botsort":
        # Our own compensator stabilises analysis coordinates; BoT-SORT's GMC additionally
        # helps association when the camera moves.
        args.update({"gmc_method": "sparseOptFlow", "proximity_thresh": 0.5,
                     "appearance_thresh": 0.8, "with_reid": False, "model": "auto"})
    return args


def make_tiles(w: int, h: int, tile: int, overlap: float = 0.2) -> list[tuple[int, int, int, int]]:
    """Overlapping square-ish tiles covering the frame."""
    if max(w, h) <= tile:
        return []
    step = int(tile * (1 - overlap))
    xs = list(range(0, max(w - tile, 0) + 1, step)) or [0]
    ys = list(range(0, max(h - tile, 0) + 1, step)) or [0]
    if xs[-1] + tile < w:
        xs.append(max(w - tile, 0))
    if ys[-1] + tile < h:
        ys.append(max(h - tile, 0))
    return [(x, y, min(x + tile, w), min(y + tile, h)) for y in ys for x in xs]


def merge_boxes(boxes: np.ndarray, iou: float) -> np.ndarray:
    """NMS + suppression of boxes mostly contained in a higher-scoring box (tile seams)."""
    if len(boxes) == 0:
        return boxes
    t = torch.from_numpy(boxes[:, :4]).float()
    keep = nms(t, torch.from_numpy(boxes[:, 4]).float(), iou).numpy()
    b = boxes[keep]
    order = np.argsort(-b[:, 4])
    b = b[order]
    keep_mask = np.ones(len(b), bool)
    area = (b[:, 2] - b[:, 0]) * (b[:, 3] - b[:, 1])
    for i in range(len(b)):
        if not keep_mask[i]:
            continue
        xx1 = np.maximum(b[i, 0], b[i + 1:, 0])
        yy1 = np.maximum(b[i, 1], b[i + 1:, 1])
        xx2 = np.minimum(b[i, 2], b[i + 1:, 2])
        yy2 = np.minimum(b[i, 3], b[i + 1:, 3])
        inter = np.clip(xx2 - xx1, 0, None) * np.clip(yy2 - yy1, 0, None)
        contained = inter / np.maximum(area[i + 1:], 1e-6) > 0.75
        keep_mask[i + 1:] &= ~contained
    return b[keep_mask]


class PedestrianTracker:
    """One instance per video/stream (holds the tracker state)."""

    def __init__(self, settings: DetectionSettings, model_path: str, device: str = "",
                 effective_fps: float = 15.0):
        from ultralytics import YOLO
        from ultralytics.trackers.bot_sort import BOTSORT
        from ultralytics.trackers.byte_tracker import BYTETracker
        from ultralytics.utils import IterableSimpleNamespace

        self.s = settings
        self.model = YOLO(model_path)
        self.device = device or None
        args = IterableSimpleNamespace(**tracker_args(settings, effective_fps))
        self.tracker = BOTSORT(args) if args.tracker_type == "botsort" else BYTETracker(args)
        self.tiled = settings.detection_mode == "tiled"
        self.last_raw_count = 0

    def _predict(self, images: list[np.ndarray], imgsz: int):
        return self.model.predict(images, classes=[PERSON_CLASS], conf=LOW_CONF,
                                  iou=self.s.iou_threshold, imgsz=imgsz, device=self.device,
                                  verbose=False)

    def detect(self, frame: np.ndarray) -> np.ndarray:
        """Returns (N, 6) array [x1, y1, x2, y2, conf, cls]."""
        h, w = frame.shape[:2]
        parts = [self._predict([frame], self.s.image_size)[0].boxes.data.cpu().numpy()]
        if self.tiled:
            tiles = make_tiles(w, h, self.s.tile_size)
            if tiles:
                crops = [frame[y1:y2, x1:x2] for x1, y1, x2, y2 in tiles]
                for (x1, y1, _, _), res in zip(tiles, self._predict(crops, self.s.tile_size)):
                    d = res.boxes.data.cpu().numpy()
                    if len(d):
                        d = d.copy()
                        d[:, [0, 2]] += x1
                        d[:, [1, 3]] += y1
                        parts.append(d)
        boxes = np.concatenate([p for p in parts if len(p)], axis=0) if any(len(p) for p in parts) \
            else np.zeros((0, 6), np.float32)
        # drop tiny fragments (< 12 px tall) which are almost always noise
        boxes = boxes[(boxes[:, 3] - boxes[:, 1]) >= 12] if len(boxes) else boxes
        return merge_boxes(boxes, self.s.iou_threshold) if self.tiled else boxes

    def __call__(self, frame: np.ndarray) -> list[tuple[int, tuple[float, float, float, float], float]]:
        from ultralytics.engine.results import Boxes

        det = self.detect(frame)
        self.last_raw_count = int((det[:, 4] >= self.s.confidence_threshold).sum()) if len(det) else 0
        boxes = Boxes(torch.from_numpy(np.asarray(det, np.float32)).reshape(-1, 6), frame.shape[:2]).cpu().numpy()
        tracks = self.tracker.update(boxes, frame)
        out = []
        for row in tracks:
            x1, y1, x2, y2, tid, score = row[:6]
            out.append((int(tid), (float(x1), float(y1), float(x2), float(y2)), float(score)))
        return out

    def close(self) -> None:
        pass
