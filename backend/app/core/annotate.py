"""Draws boxes, IDs, trajectories, following links, groups and crowd zones on frames."""
from __future__ import annotations

import colorsys

import cv2
import numpy as np

RED = (60, 60, 235)
ORANGE = (0, 150, 255)
GREEN = (90, 200, 60)
YELLOW = (0, 215, 255)
WHITE = (255, 255, 255)
DARK = (25, 25, 25)
LEVEL_COLORS = {"normal": GREEN, "elevated": YELLOW, "critical": RED}


def id_color(tid: int) -> tuple[int, int, int]:
    h = (tid * 0.61803398875) % 1.0
    r, g, b = colorsys.hsv_to_rgb(h, 0.65, 0.95)
    return int(b * 255), int(g * 255), int(r * 255)


def _label(img, text, x, y, color, scale=0.45):
    (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, 1)
    y = max(th + 4, int(y))
    cv2.rectangle(img, (int(x), y - th - 4), (int(x) + tw + 4, y), color, -1)
    cv2.putText(img, text, (int(x) + 2, y - 3), cv2.FONT_HERSHEY_SIMPLEX, scale, DARK, 1, cv2.LINE_AA)


def draw_frame(img: np.ndarray, *, detections, trajectories, follows, groups, clusters,
               hud: dict) -> np.ndarray:
    """
    detections:   [(tid, (x1,y1,x2,y2), conf)]
    trajectories: {tid: Nx2 array in frame coordinates}
    follows:      [(leader_id, follower_id, confidence)]
    groups:       {group_key: [tid, ...]}
    clusters:     [Cluster] congestion zones (frame coordinates)
    """
    out = img
    scale = max(0.4, min(out.shape[:2]) / 900)
    overlay = out.copy()
    for c in clusters:
        x1, y1, x2, y2 = map(int, c.bbox)
        cv2.rectangle(overlay, (x1, y1), (x2, y2), YELLOW, -1)
    if clusters:
        cv2.addWeighted(overlay, 0.18, out, 0.82, 0, out)
    for c in clusters:
        x1, y1, x2, y2 = map(int, c.bbox)
        cv2.rectangle(out, (x1, y1), (x2, y2), YELLOW, 2)
        _label(out, f"Congestion: {c.size} people", x1, y1 - 2, YELLOW, 0.5 * scale)

    for tid, pts in trajectories.items():
        if len(pts) >= 2:
            cv2.polylines(out, [pts.astype(np.int32).reshape(-1, 1, 2)], False, id_color(tid), 2, cv2.LINE_AA)

    by_id = {tid: box for tid, box, _ in detections}
    followers = {f: (l, c) for l, f, c in follows}
    leaders = {l for l, _, _ in follows}
    member_of = {m: g for g, ms in groups.items() for m in ms}

    for gkey, members in groups.items():
        feet = [((by_id[m][0] + by_id[m][2]) / 2, by_id[m][3]) for m in members if m in by_id]
        for i in range(len(feet) - 1):
            cv2.line(out, tuple(map(int, feet[i])), tuple(map(int, feet[i + 1])), GREEN, 2, cv2.LINE_AA)

    for tid, (x1, y1, x2, y2), conf in detections:
        color, thick, text = id_color(tid), 2, f"ID {tid}"
        if tid in followers:
            color, thick, text = RED, 3, f"ID {tid} FOLLOWING {followers[tid][0]}"
        elif tid in leaders:
            color, thick, text = ORANGE, 3, f"ID {tid} LEAD"
        elif tid in member_of:
            color, text = GREEN, f"ID {tid} {member_of[tid]}"
        cv2.rectangle(out, (int(x1), int(y1)), (int(x2), int(y2)), color, thick)
        _label(out, text, x1, y1 - 2, color, 0.42 * scale)

    for leader, follower, conf in follows:
        if leader in by_id and follower in by_id:
            lb, fb = by_id[leader], by_id[follower]
            p1 = (int((fb[0] + fb[2]) / 2), int((fb[1] + fb[3]) / 2))
            p2 = (int((lb[0] + lb[2]) / 2), int((lb[1] + lb[3]) / 2))
            cv2.arrowedLine(out, p1, p2, RED, 3, cv2.LINE_AA, tipLength=0.08)
            mid = ((p1[0] + p2[0]) // 2, (p1[1] + p2[1]) // 2)
            _label(out, f"{conf:.0%}", mid[0], mid[1], RED, 0.5 * scale)

    # HUD
    level = hud.get("level", "normal")
    lines = [
        f"t {hud.get('t', 0):6.1f}s",
        f"People {hud.get('count', 0)}",
        f"Crowd {level.upper()}",
        f"Following {len(follows)}",
        f"Groups {len(groups)}",
    ]
    fs = 0.55 * scale
    lh = int(26 * scale) + 4
    w = int(200 * scale) + 20
    cv2.rectangle(out, (8, 8), (8 + w, 8 + lh * len(lines) + 8), DARK, -1)
    for i, line in enumerate(lines):
        col = LEVEL_COLORS.get(level, WHITE) if line.startswith("Crowd") else (
            RED if line.startswith("Following") and follows else WHITE)
        cv2.putText(out, line, (16, 8 + lh * (i + 1)), cv2.FONT_HERSHEY_SIMPLEX, fs, col, 1, cv2.LINE_AA)
    return out
