"""Pedestrian following detection engine.

For every pair of nearby tracked pedestrians the engine samples both trajectories on a
common time grid and measures:

* distance between the two people (in body heights),
* similarity of walking direction (cosine of velocity vectors),
* speed consistency (ratio of the slower to the faster speed),
* relative position (is one person consistently *behind* the other, along the
  other's heading, rather than beside them?),
* trajectory similarity with time lag (does person B walk through the places
  person A walked through a few seconds earlier?),
* duration and consistency of the relationship over consecutive analysis windows.

The window-level classification is one of :class:`Relationship`. A *following event*
is only raised when the ``potential_following`` classification persists for at least
``min_following_duration_sec`` (with short gaps tolerated). The engine describes
observable movement patterns only; it does not infer intent.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from enum import Enum

import numpy as np

from ..config import DetectionSettings
from .groups import GroupTracker
from .tracks import Track, TrackStore

GRID_DT = 0.2  # seconds between trajectory samples
RETRACE_SIGMA = 0.6  # body heights; tolerance when comparing a follower to a leader's path


class Relationship(str, Enum):
    POTENTIAL_FOLLOWING = "potential_following"
    SAME_DIRECTION = "same_direction"
    GROUP_WALKING = "group_walking"
    NO_FOLLOWING = "no_following"
    INSUFFICIENT = "insufficient_evidence"


# Severity order used when summarising a pair over a whole video.
SEVERITY = {
    Relationship.POTENTIAL_FOLLOWING: 4,
    Relationship.GROUP_WALKING: 3,
    Relationship.SAME_DIRECTION: 2,
    Relationship.NO_FOLLOWING: 1,
    Relationship.INSUFFICIENT: 0,
}


@dataclass
class PairMetrics:
    leader_id: int
    follower_id: int
    coverage: float = 0.0
    moving_ratio: float = 0.0
    mean_distance: float = math.nan
    direction_similarity: float = math.nan
    speed_consistency: float = math.nan
    trajectory_similarity: float = 0.0
    behind_ratio: float = 0.0
    side_ratio: float = 0.0
    lag_sec: float = 0.0
    score: float = 0.0

    def rounded(self) -> dict:
        out = {}
        for k, v in asdict(self).items():
            if isinstance(v, float):
                out[k] = None if math.isnan(v) else round(v, 3)
            else:
                out[k] = v
        return out


@dataclass
class TrackSamples:
    """A track resampled on the shared analysis grid (NaN where unknown)."""

    track_id: int
    pos: np.ndarray  # (G, 2)
    h: np.ndarray  # (G,)
    vel: np.ndarray  # (G, 2) px / s


def sample_track(track: Track, grid: np.ndarray, velocity_steps: int) -> TrackSamples:
    obs = track.observations
    ts = np.fromiter((o.t for o in obs), float, len(obs))
    xs = np.fromiter((o.x for o in obs), float, len(obs))
    ys = np.fromiter((o.y for o in obs), float, len(obs))
    hs = np.fromiter((o.h for o in obs), float, len(obs))
    inside = (grid >= ts[0] - 1e-6) & (grid <= ts[-1] + 1e-6)
    pos = np.full((len(grid), 2), np.nan)
    h = np.full(len(grid), np.nan)
    pos[inside, 0] = np.interp(grid[inside], ts, xs)
    pos[inside, 1] = np.interp(grid[inside], ts, ys)
    h[inside] = np.interp(grid[inside], ts, hs)
    vel = np.full((len(grid), 2), np.nan)
    k = velocity_steps
    if len(grid) > k:
        vel[k:] = (pos[k:] - pos[:-k]) / (k * GRID_DT)
    return TrackSamples(track.track_id, pos, h, vel)


def _nanmean(a: np.ndarray) -> float:
    a = a[~np.isnan(a)]
    return float(a.mean()) if a.size else math.nan


def _orientation_metrics(lead: TrackSamples, foll: TrackSamples, n_win: int,
                         s: DetectionSettings) -> tuple[float, float, float, float]:
    """behind_ratio, side_ratio, trajectory_similarity, lag_sec for ``foll`` behind ``lead``."""
    G = len(lead.h)
    w = slice(G - n_win, G)
    lp, fp = lead.pos[w], foll.pos[w]
    lv = lead.vel[w]
    scale = (lead.h[w] + foll.h[w]) / 2.0
    lspeed = np.linalg.norm(lv, axis=1)
    valid = ~np.isnan(scale) & ~np.isnan(lspeed) & (lspeed / np.maximum(scale, 1) > s.min_moving_speed)
    behind_ratio = side_ratio = 0.0
    if valid.any():
        u = lv[valid] / lspeed[valid, None]
        rel = (fp[valid] - lp[valid]) / scale[valid, None]
        along = (rel * u).sum(axis=1)
        lateral = np.abs(rel[:, 0] * u[:, 1] - rel[:, 1] * u[:, 0])
        behind = (along < -0.3) & (lateral < np.maximum(np.abs(along), 0.6))
        side = (np.abs(along) < 0.6) | (lateral >= np.abs(along))
        behind_ratio = float(behind.mean())
        side_ratio = float(side.mean())

    # Lag search: compare follower(t) with leader(t - lag) for every candidate lag.
    # Vectorised over all lags at once (important in crowded scenes with many pairs).
    best_d, best_lag = math.inf, 0.0
    k_min = max(1, int(round(s.min_lag_sec / GRID_DT)))
    k_max = min(int(round(s.max_lag_sec / GRID_DT)), G - n_win)
    if k_max >= k_min:
        lags = np.arange(k_min, k_max + 1)
        idx = (G - n_win) + np.arange(n_win)[None, :] - lags[:, None]  # (K, n_win)
        d = np.linalg.norm(fp[None, :, :] - lead.pos[idx], axis=2) / scale[None, :]
        ok = ~np.isnan(d)
        counts = ok.sum(axis=1)
        means = np.where(counts > 0, np.where(ok, d, 0).sum(axis=1) / np.maximum(counts, 1), np.inf)
        means[counts < n_win * 0.6] = np.inf
        j = int(np.argmin(means))
        if math.isfinite(means[j]):
            best_d, best_lag = float(means[j]), float(lags[j] * GRID_DT)
    traj_sim = math.exp(-(best_d ** 2) / (2 * RETRACE_SIGMA ** 2)) if math.isfinite(best_d) else 0.0
    return behind_ratio, side_ratio, traj_sim, best_lag


def analyze_pair(a: TrackSamples, b: TrackSamples, n_win: int,
                 s: DetectionSettings) -> tuple[Relationship, PairMetrics]:
    """Classify the movement relationship of two pedestrians over the last ``n_win`` samples."""
    G = len(a.h)
    w = slice(G - n_win, G)
    scale = (a.h[w] + b.h[w]) / 2.0
    both = ~np.isnan(scale)
    coverage = float(both.mean())
    m = PairMetrics(leader_id=a.track_id, follower_id=b.track_id, coverage=coverage)
    if coverage < 0.6:
        return Relationship.INSUFFICIENT, m

    dist = np.linalg.norm(b.pos[w] - a.pos[w], axis=1) / scale
    m.mean_distance = _nanmean(dist)

    va, vb = a.vel[w], b.vel[w]
    sa = np.linalg.norm(va, axis=1) / scale
    sb = np.linalg.norm(vb, axis=1) / scale
    known = ~np.isnan(sa) & ~np.isnan(sb)
    moving = known & (sa > s.min_moving_speed) & (sb > s.min_moving_speed)
    m.moving_ratio = float(moving.sum() / max(known.sum(), 1))
    if known.sum() < n_win * 0.5 or m.moving_ratio < 0.5:
        return Relationship.INSUFFICIENT, m

    cos = (va[moving] * vb[moving]).sum(axis=1) / (
        np.linalg.norm(va[moving], axis=1) * np.linalg.norm(vb[moving], axis=1))
    m.direction_similarity = float(cos.mean())
    m.speed_consistency = float((np.minimum(sa[moving], sb[moving]) /
                                 np.maximum(sa[moving], sb[moving])).mean())

    if m.direction_similarity < s.direction_similarity_threshold:
        return Relationship.NO_FOLLOWING, m
    if m.mean_distance > s.follow_max_distance:
        m.score = 0.0
        return Relationship.SAME_DIRECTION, m

    # Evaluate both orientations and keep the one where somebody is behind the other.
    ab = _orientation_metrics(a, b, n_win, s)  # b follows a
    ba = _orientation_metrics(b, a, n_win, s)  # a follows b
    if (ba[0], ba[2]) > (ab[0], ab[2]):
        m.leader_id, m.follower_id = b.track_id, a.track_id
        chosen = ba
    else:
        chosen = ab
    m.behind_ratio, m.side_ratio, m.trajectory_similarity, m.lag_sec = chosen

    dir_score = max(0.0, (m.direction_similarity - 0.5) / 0.5)
    m.score = float(np.clip(0.25 * dir_score + 0.2 * m.speed_consistency +
                            0.3 * m.trajectory_similarity + 0.25 * m.behind_ratio, 0, 1))

    if (m.mean_distance <= s.group_max_distance and m.side_ratio >= 0.5
            and m.speed_consistency >= s.speed_consistency_threshold):
        return Relationship.GROUP_WALKING, m

    if (s.follow_min_distance <= m.mean_distance <= s.follow_max_distance
            and m.behind_ratio >= s.behind_ratio_threshold
            and m.trajectory_similarity >= s.trajectory_similarity_threshold
            and m.speed_consistency >= s.speed_consistency_threshold
            and m.lag_sec >= s.min_lag_sec):
        return Relationship.POTENTIAL_FOLLOWING, m

    return Relationship.SAME_DIRECTION, m


# ---------------------------------------------------------------------------
# Temporal consistency
# ---------------------------------------------------------------------------
@dataclass
class FollowStreak:
    leader_id: int
    follower_id: int
    first_t: float
    last_t: float
    scores: list = field(default_factory=list)
    metrics: list = field(default_factory=list)
    positives: int = 0
    ticks: int = 0
    event_key: str | None = None  # set once the event was raised

    def duration(self) -> float:
        return self.last_t - self.first_t


@dataclass
class EngineEvent:
    """Emitted by the engine; consumed by the pipeline (DB, websocket, snapshots)."""

    kind: str  # following | group
    action: str  # opened | updated | closed
    key: str
    payload: dict


class FollowingEngine:
    """Stateful engine: run :meth:`step` periodically with the current track store."""

    def __init__(self, settings: DetectionSettings):
        self.s = settings
        self.n_win = max(5, int(round(settings.analysis_window_sec / GRID_DT)))
        self.n_lag = int(round(settings.max_lag_sec / GRID_DT))
        self.velocity_steps = max(1, int(round(settings.velocity_window_sec / GRID_DT)))
        self.streaks: dict[tuple[int, int], FollowStreak] = {}
        self.group_streaks: dict[tuple[int, int], list[float]] = {}  # pair -> [first_t, last_t]
        self.groups = GroupTracker(gap_tolerance=settings.gap_tolerance_sec)
        self.current: dict[tuple[int, int], tuple[Relationship, PairMetrics]] = {}
        self.pair_summary: dict[tuple[int, int], dict] = {}
        self.label_counts: dict[str, int] = {r.value: 0 for r in Relationship}
        self._event_seq = 0
        self.last_t = -math.inf

    # -- public API -------------------------------------------------------
    def due(self, t: float) -> bool:
        return t - self.last_t >= self.s.analysis_interval_sec - 1e-9

    def step(self, store: TrackStore, t: float) -> list[EngineEvent]:
        self.last_t = t
        events: list[EngineEvent] = []
        G = self.n_win + self.n_lag
        grid = t - GRID_DT * np.arange(G - 1, -1, -1)
        tracks = [tr for tr in store.active(min_hits=self.s.min_track_hits, max_age=0.6)
                  if len(tr.observations) >= 2]
        samples = {tr.track_id: sample_track(tr, grid, self.velocity_steps) for tr in tracks}
        self.current = {}
        ids = sorted(samples)
        for i, ia in enumerate(ids):
            ta = store.tracks[ia]
            for ib in ids[i + 1:]:
                tb = store.tracks[ib]
                scale = (ta.last.h + tb.last.h) / 2.0
                gap = math.hypot(ta.last.x - tb.last.x, ta.last.y - tb.last.y) / max(scale, 1)
                if gap > self.s.follow_max_distance * 1.5:
                    continue
                rel, metrics = analyze_pair(samples[ia], samples[ib], self.n_win, self.s)
                key = (ia, ib)
                self.current[key] = (rel, metrics)
                self._summarise(key, rel, metrics)
                if rel == Relationship.POTENTIAL_FOLLOWING:
                    events += self._on_following(key, metrics, t)
                elif rel == Relationship.GROUP_WALKING:
                    gs = self.group_streaks.get(key)
                    if gs is None or t - gs[1] > self.s.gap_tolerance_sec:
                        self.group_streaks[key] = [t, t]
                    else:
                        gs[1] = t
                if key in self.streaks:
                    self.streaks[key].ticks += 1

        events += self._close_stale_streaks(t)
        events += self._update_groups(t)
        return events

    def finish(self, t: float) -> list[EngineEvent]:
        """Close every open event (end of video / stream stopped)."""
        events = self._close_stale_streaks(t, force=True)
        events += self.groups.close_all(t)
        return events

    def active_following(self) -> list[FollowStreak]:
        return [st for st in self.streaks.values() if st.event_key]

    # -- internals --------------------------------------------------------
    def _summarise(self, key, rel: Relationship, metrics: PairMetrics) -> None:
        self.label_counts[rel.value] += 1
        summ = self.pair_summary.setdefault(key, {"counts": {}, "max_score": 0.0})
        summ["counts"][rel.value] = summ["counts"].get(rel.value, 0) + 1
        summ["max_score"] = max(summ["max_score"], metrics.score)

    def _confidence(self, st: FollowStreak) -> float:
        recent = st.scores[-40:]
        base = float(np.mean(recent)) if recent else 0.0
        consistency = st.positives / max(st.ticks, 1)
        dur = min(1.0, st.duration() / (2 * self.s.min_following_duration_sec))
        return round(float(np.clip(base * (0.55 + 0.25 * dur + 0.2 * consistency), 0, 1)), 3)

    def _streak_payload(self, st: FollowStreak) -> dict:
        ms = st.metrics[-40:]
        agg = {}
        for name in ("mean_distance", "direction_similarity", "speed_consistency",
                     "trajectory_similarity", "behind_ratio", "lag_sec"):
            vals = [m[name] for m in ms if m.get(name) is not None]
            agg[name] = round(float(np.mean(vals)), 3) if vals else None
        return {
            "leader_id": st.leader_id,
            "follower_id": st.follower_id,
            # evidence for the first positive window started one window earlier
            "start_time": round(max(0.0, st.first_t - self.s.analysis_window_sec), 2),
            "end_time": round(st.last_t, 2),
            "duration": round(st.duration() + self.s.analysis_window_sec, 2),
            "confidence": self._confidence(st),
            "consistency": round(st.positives / max(st.ticks, 1), 3),
            "metrics": agg,
        }

    def _on_following(self, key, m: PairMetrics, t: float) -> list[EngineEvent]:
        st = self.streaks.get(key)
        if st is not None and (st.leader_id != m.leader_id or t - st.last_t > self.s.gap_tolerance_sec):
            # Roles swapped or the relationship was interrupted: close and restart.
            closed = self._close(key, st, st.last_t)
            st = None
        else:
            closed = []
        if st is None:
            st = self.streaks[key] = FollowStreak(m.leader_id, m.follower_id, t, t)
        st.last_t = t
        st.positives += 1
        st.scores.append(m.score)
        st.metrics.append(m.rounded())
        events = closed
        if (st.event_key is None and st.duration() >= self.s.min_following_duration_sec
                and self._confidence(st) >= self.s.min_alert_confidence):
            self._event_seq += 1
            st.event_key = f"F{self._event_seq}"
            events.append(EngineEvent("following", "opened", st.event_key, self._streak_payload(st)))
        elif st.event_key and st.positives % 8 == 0:
            events.append(EngineEvent("following", "updated", st.event_key, self._streak_payload(st)))
        return events

    def _close(self, key, st: FollowStreak, t: float) -> list[EngineEvent]:
        self.streaks.pop(key, None)
        if st.event_key:
            return [EngineEvent("following", "closed", st.event_key, self._streak_payload(st))]
        return []

    def _close_stale_streaks(self, t: float, force: bool = False) -> list[EngineEvent]:
        events = []
        for key, st in list(self.streaks.items()):
            if force or t - st.last_t > self.s.gap_tolerance_sec:
                events += self._close(key, st, t)
        return events

    def _update_groups(self, t: float) -> list[EngineEvent]:
        edges = []
        for key, (first_t, last_t) in list(self.group_streaks.items()):
            if t - last_t > self.s.gap_tolerance_sec:
                del self.group_streaks[key]
            elif last_t - first_t >= self.s.min_group_duration_sec:
                edges.append(key)
        return self.groups.update(edges, t)
