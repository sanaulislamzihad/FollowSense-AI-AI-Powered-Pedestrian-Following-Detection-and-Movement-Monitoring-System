"""Trajectory history management and per-track kinematics."""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field

import numpy as np


@dataclass
class Observation:
    t: float  # seconds since stream start
    frame: int
    x: float  # foot point (bottom-centre of the box), pixels
    y: float
    h: float  # box height, pixels (scale reference)
    box: tuple[float, float, float, float]
    conf: float


@dataclass
class Track:
    track_id: int
    observations: deque = field(default_factory=lambda: deque(maxlen=2000))
    hits: int = 0
    total_distance: float = 0.0  # body heights travelled
    first_seen: float = 0.0
    last_seen: float = 0.0
    # Long-term, down-sampled path kept for analytics (t, x, y)
    path: list = field(default_factory=list)

    @property
    def last(self) -> Observation:
        return self.observations[-1]

    def add(self, obs: Observation) -> None:
        if self.observations:
            prev = self.observations[-1]
            scale = max((prev.h + obs.h) / 2.0, 1.0)
            self.total_distance += math.hypot(obs.x - prev.x, obs.y - prev.y) / scale
        else:
            self.first_seen = obs.t
        self.observations.append(obs)
        self.hits += 1
        self.last_seen = obs.t
        if not self.path or obs.t - self.path[-1][0] >= 0.2:
            self.path.append((round(obs.t, 2), round(obs.x, 1), round(obs.y, 1)))

    # ---- kinematics -------------------------------------------------------
    def window(self, t_start: float, t_end: float) -> list[Observation]:
        return [o for o in self.observations if t_start <= o.t <= t_end]

    def mean_height(self, last_n: int = 15) -> float:
        obs = list(self.observations)[-last_n:]
        return float(np.mean([o.h for o in obs])) if obs else 1.0

    def velocity_at(self, t: float, window: float) -> tuple[float, float] | None:
        """Velocity (px/s) around time ``t`` estimated by least squares over ``window``."""
        pts = [o for o in self.observations if t - window <= o.t <= t + 1e-6]
        if len(pts) < 2 or pts[-1].t - pts[0].t < window * 0.4:
            return None
        ts = np.array([p.t for p in pts])
        xs = np.array([p.x for p in pts])
        ys = np.array([p.y for p in pts])
        ts = ts - ts.mean()
        denom = float((ts ** 2).sum())
        if denom <= 1e-9:
            return None
        return float((ts * (xs - xs.mean())).sum() / denom), float((ts * (ys - ys.mean())).sum() / denom)

    def speed(self, window: float) -> float:
        """Current speed in body heights per second."""
        v = self.velocity_at(self.last_seen, window)
        if v is None:
            return 0.0
        return math.hypot(*v) / max(self.mean_height(), 1.0)

    def position_at(self, t: float) -> tuple[float, float, float] | None:
        """Linear interpolation of (x, y, h) at time ``t`` (no extrapolation)."""
        obs = self.observations
        if not obs or t < obs[0].t or t > obs[-1].t:
            return None
        lo, hi = 0, len(obs) - 1
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if obs[mid].t <= t:
                lo = mid
            else:
                hi = mid
        a, b = obs[lo], obs[hi]
        if b.t == a.t:
            return a.x, a.y, a.h
        r = (t - a.t) / (b.t - a.t)
        r = min(max(r, 0.0), 1.0)
        return a.x + (b.x - a.x) * r, a.y + (b.y - a.y) * r, a.h + (b.h - a.h) * r


class TrackStore:
    """Keeps the movement history of every tracked pedestrian."""

    def __init__(self, stale_after_sec: float = 2.0):
        self.tracks: dict[int, Track] = {}
        self.stale_after_sec = stale_after_sec
        self.now = 0.0

    def update(self, t: float, frame: int, detections: list[tuple[int, tuple, float]],
               points: list[tuple[float, float]] | None = None) -> None:
        """``detections`` = [(track_id, (x1, y1, x2, y2), conf), ...].

        ``points`` optionally gives the foot point of every detection in stabilised
        (camera-motion compensated) coordinates; otherwise the box bottom-centre is used.
        """
        self.now = t
        for i, (tid, (x1, y1, x2, y2), conf) in enumerate(detections):
            track = self.tracks.get(tid)
            if track is None:
                track = self.tracks[tid] = Track(track_id=tid)
            fx, fy = points[i] if points is not None else ((x1 + x2) / 2.0, float(y2))
            track.add(Observation(t=t, frame=frame, x=float(fx), y=float(fy),
                                  h=float(y2 - y1), box=(x1, y1, x2, y2), conf=conf))

    def active(self, min_hits: int = 1, max_age: float | None = None) -> list[Track]:
        max_age = self.stale_after_sec if max_age is None else max_age
        return [tr for tr in self.tracks.values()
                if tr.hits >= min_hits and self.now - tr.last_seen <= max_age]

    def visible(self, min_hits: int = 1) -> list[Track]:
        """Tracks detected in the most recent update."""
        return [tr for tr in self.tracks.values() if tr.hits >= min_hits and tr.last_seen == self.now]

    def prune(self, keep_sec: float) -> None:
        """Trim the raw observation buffers to the most recent ``keep_sec`` seconds."""
        cutoff = self.now - keep_sec
        for tr in self.tracks.values():
            while tr.observations and tr.observations[0].t < cutoff and len(tr.observations) > 2:
                tr.observations.popleft()
