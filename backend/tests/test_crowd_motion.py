import cv2
import numpy as np

from app.config import DetectionSettings
from app.core.crowd import CrowdMonitor, MovementAccumulator, find_clusters
from app.core.detector import make_tiles, merge_boxes
from app.core.motion import CameraMotionCompensator


def person(x, y, h=100):
    return (x - h * 0.2, y - h, x + h * 0.2, y)


def test_dense_cluster_detected_but_spread_people_are_not():
    s = DetectionSettings()
    dense = [person(500 + 30 * (i % 4), 500 + 30 * (i // 4)) for i in range(8)]
    spread = [person(100 + 140 * i, 900) for i in range(8)]  # 1.4 body heights apart
    boxes = dense + spread
    clusters = find_clusters(list(range(len(boxes))), boxes, s)
    assert len(clusters) == 1
    assert set(clusters[0].members) == set(range(8))


def test_overcrowding_alert_after_sustained_duration():
    s = DetectionSettings(crowd_critical_count=10, crowd_alert_min_duration_sec=2.0)
    mon = CrowdMonitor(s)
    events = []
    for f in range(60):  # 4 s at 15 fps with 12 people
        t = f / 15
        ids = list(range(12))
        events += mon.update(t, ids, [person(100 + 150 * i, 500) for i in ids])
    events += mon.finish()
    kinds = [(e.kind, e.action, e.payload["crowd_type"]) for e in events]
    assert ("crowd", "opened", "overcrowding") in kinds
    assert ("crowd", "closed", "overcrowding") in kinds
    assert mon.summary()["peak_count"] == 12


def test_heatmap_accumulates_points():
    acc = MovementAccumulator(640, 480, cols=32)
    acc.add_points(np.array([[10, 10], [10, 10], [600, 400]]))
    hm = acc.heatmap()
    assert hm["values"][0][0] == 1.0
    assert hm["rows"] == 24


def test_camera_motion_compensation_recovers_pan():
    rng = np.random.default_rng(0)
    base = (rng.random((600, 900)) * 255).astype(np.uint8)
    base = cv2.GaussianBlur(base, (7, 7), 2)
    base = cv2.cvtColor(base, cv2.COLOR_GRAY2BGR)
    cmc = CameraMotionCompensator(work_width=640)
    shift = 0
    for _ in range(6):  # camera pans: image content moves 8 px left per frame
        frame = base[:, shift:shift + 800].copy()
        cmc.update(frame, [])
        shift += 8
    # a static ground point seen at x=400 in the last frame was at x=400+40 in frame 0
    ref = cmc.to_reference([(400, 300)])[0]
    assert abs(ref[0] - 440) < 2.5 and abs(ref[1] - 300) < 2.5


def test_static_camera_stays_identity():
    rng = np.random.default_rng(1)
    frame = cv2.cvtColor((rng.random((480, 640)) * 255).astype(np.uint8), cv2.COLOR_GRAY2BGR)
    cmc = CameraMotionCompensator()
    for _ in range(5):
        cmc.update(frame, [])
    assert np.allclose(cmc.T, np.eye(3))


def test_tiles_cover_frame_and_merge_removes_duplicates():
    tiles = make_tiles(720, 1280, 640)
    assert tiles[0][:2] == (0, 0) and max(t[2] for t in tiles) == 720 and max(t[3] for t in tiles) == 1280
    boxes = np.array([[10, 10, 50, 110, 0.9, 0], [12, 12, 50, 108, 0.6, 0], [12, 60, 48, 108, 0.5, 0],
                      [300, 300, 340, 400, 0.8, 0]], np.float32)
    merged = merge_boxes(boxes, 0.5)
    assert len(merged) == 2
