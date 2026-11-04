"""Crowd management: people counting, crowd level, congestion zones, density heatmap."""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components

from ..config import DetectionSettings

LEVELS = ("normal", "elevated", "critical")
CORE_NEIGHBOURS = 3


@dataclass
class Cluster:
    members: list[int]
    bbox: tuple[float, float, float, float]  # frame coordinates
    center: tuple[float, float]

    @property
    def size(self) -> int:
        return len(self.members)


@dataclass
class CrowdStreak:
    kind: str  # overcrowding | congestion
    first_t: float
    last_t: float
    peak: int = 0
    peak_t: float = 0.0
    location: tuple | None = None
    event_key: str | None = None
    samples: list = field(default_factory=list)


def find_clusters(ids, boxes, settings: DetectionSettings) -> list[Cluster]:
    """Group people standing/walking densely together (scale-normalised distances)."""
    n = len(ids)
    if n < settings.congestion_min_people:
        return []
    b = np.asarray(boxes, float)
    feet = np.stack([(b[:, 0] + b[:, 2]) / 2, b[:, 3]], axis=1)
    hs = np.maximum(b[:, 3] - b[:, 1], 1.0)
    d = np.linalg.norm(feet[:, None, :] - feet[None, :, :], axis=2)
    scale = (hs[:, None] + hs[None, :]) / 2
    adj = (d / scale) < settings.congestion_distance
    np.fill_diagonal(adj, False)
    # DBSCAN-style: only people with several close neighbours ("core" points) can link a
    # cluster, so a loose chain of people spread over a plaza is not called congestion.
    core = adj.sum(axis=1) >= CORE_NEIGHBOURS
    core_adj = adj & core[:, None] & core[None, :]
    _, labels = connected_components(csr_matrix(core_adj), directed=False)
    labels = np.where(core, labels, -1)
    for i in np.where(~core)[0]:  # border points join the cluster of a neighbouring core
        nb = np.where(adj[i] & core)[0]
        if len(nb):
            labels[i] = labels[nb[np.argmin(d[i, nb])]]
    out = []
    for lab in np.unique(labels[labels >= 0]):
        idx = np.where(labels == lab)[0]
        if len(idx) < settings.congestion_min_people:
            continue
        x1, y1 = b[idx, 0].min(), b[idx, 1].min()
        x2, y2 = b[idx, 2].max(), b[idx, 3].max()
        out.append(Cluster([int(ids[i]) for i in idx], (float(x1), float(y1), float(x2), float(y2)),
                           (float(feet[idx, 0].mean()), float(feet[idx, 1].mean()))))
    return sorted(out, key=lambda c: c.size, reverse=True)


class CrowdMonitor:
    def __init__(self, settings: DetectionSettings):
        self.s = settings
        self.timeline: list[dict] = []  # sampled every 0.5 s
        self.level = "normal"
        self.count = 0
        self.clusters: list[Cluster] = []
        self.peak_count = 0
        self.peak_time = 0.0
        self._count_sum = 0
        self._frames = 0
        self._last_sample = -math.inf
        self.streaks: dict[str, CrowdStreak] = {}
        self._seq = 0
        self.level_seconds = {lvl: 0.0 for lvl in LEVELS}
        self._last_t: float | None = None

    def classify(self, count: int) -> str:
        if count >= self.s.crowd_critical_count:
            return "critical"
        if count >= self.s.crowd_warning_count:
            return "elevated"
        return "normal"

    def update(self, t: float, ids: list[int], boxes: list[tuple]) -> list:
        from .following import EngineEvent

        self.count = len(ids)
        self.level = self.classify(self.count)
        if self._last_t is not None:
            self.level_seconds[self.level] += max(0.0, t - self._last_t)
        self._last_t = t
        self._count_sum += self.count
        self._frames += 1
        if self.count > self.peak_count:
            self.peak_count, self.peak_time = self.count, t
        self.clusters = find_clusters(ids, boxes, self.s)
        if t - self._last_sample >= 0.5:
            self._last_sample = t
            self.timeline.append({
                "t": round(t, 2), "count": self.count, "level": self.level,
                "clusters": len(self.clusters),
                "max_cluster": self.clusters[0].size if self.clusters else 0,
            })

        events = []
        active = {}
        if self.level == "critical":
            active["overcrowding"] = (self.count, None)
        if self.clusters:
            c = self.clusters[0]
            active["congestion"] = (c.size, c.bbox)
        for kind, (value, loc) in active.items():
            st = self.streaks.get(kind)
            if st is None or t - st.last_t > self.s.gap_tolerance_sec:
                if st is not None:
                    events += self._close(kind, st)
                st = self.streaks[kind] = CrowdStreak(kind, t, t)
            st.last_t = t
            if value >= st.peak:
                st.peak, st.peak_t, st.location = value, t, loc
            if st.event_key is None and st.last_t - st.first_t >= self.s.crowd_alert_min_duration_sec:
                self._seq += 1
                st.event_key = f"C{self._seq}"
                events.append(EngineEvent("crowd", "opened", st.event_key, self._payload(st)))
        for kind, st in list(self.streaks.items()):
            if kind not in active and t - st.last_t > self.s.gap_tolerance_sec:
                events += self._close(kind, st)
        return events

    def finish(self) -> list:
        events = []
        for kind, st in list(self.streaks.items()):
            events += self._close(kind, st)
        return events

    def _close(self, kind: str, st: CrowdStreak) -> list:
        from .following import EngineEvent

        self.streaks.pop(kind, None)
        if st.event_key:
            return [EngineEvent("crowd", "closed", st.event_key, self._payload(st))]
        return []

    def _payload(self, st: CrowdStreak) -> dict:
        return {
            "crowd_type": st.kind,
            "start_time": round(st.first_t, 2),
            "end_time": round(st.last_t, 2),
            "duration": round(st.last_t - st.first_t, 2),
            "peak_count": st.peak,
            "peak_time": round(st.peak_t, 2),
            "location": [round(v, 1) for v in st.location] if st.location else None,
        }

    def summary(self) -> dict:
        return {
            "peak_count": self.peak_count,
            "peak_time": round(self.peak_time, 2),
            "average_count": round(self._count_sum / max(self._frames, 1), 2),
            "level_seconds": {k: round(v, 1) for k, v in self.level_seconds.items()},
            "timeline": self.timeline,
        }


class MovementAccumulator:
    """Density heatmap (reference coordinates) and walking-direction histogram."""

    def __init__(self, width: int, height: int, cols: int = 64):
        self.width, self.height = width, height
        self.cols = cols
        self.rows = max(1, int(round(cols * height / max(width, 1))))
        self.grid = np.zeros((self.rows, self.cols), np.float64)
        self.direction_bins = np.zeros(8, np.int64)  # 0 = right, counter-clockwise (image up)
        self.speed_samples: list[float] = []

    def add_points(self, pts: np.ndarray) -> None:
        if len(pts) == 0:
            return
        cx = (pts[:, 0] / self.width * self.cols).astype(int)
        cy = (pts[:, 1] / self.height * self.rows).astype(int)
        ok = (cx >= 0) & (cx < self.cols) & (cy >= 0) & (cy < self.rows)
        np.add.at(self.grid, (cy[ok], cx[ok]), 1)

    def add_velocity(self, vx: float, vy: float, speed_bh: float) -> None:
        ang = math.degrees(math.atan2(-vy, vx)) % 360
        self.direction_bins[int(((ang + 22.5) % 360) // 45)] += 1
        self.speed_samples.append(round(speed_bh, 3))

    def congestion_zones(self, top: int = 5) -> list[dict]:
        if self.grid.max() <= 0:
            return []
        g = self.grid / self.grid.max()
        flat = np.argsort(g.ravel())[::-1][:top]
        return [{"row": int(i // self.cols), "col": int(i % self.cols), "intensity": round(float(g.ravel()[i]), 3)}
                for i in flat if g.ravel()[i] > 0.3]

    def heatmap(self) -> dict:
        mx = float(self.grid.max()) or 1.0
        return {"rows": self.rows, "cols": self.cols, "width": self.width, "height": self.height,
                "values": np.round(self.grid / mx, 3).tolist()}
