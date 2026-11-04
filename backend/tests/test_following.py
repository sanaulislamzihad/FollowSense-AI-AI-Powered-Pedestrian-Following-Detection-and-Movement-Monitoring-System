"""Synthetic-trajectory tests for the following / group detection engine."""
import math

from app.config import DetectionSettings
from app.core.following import FollowingEngine, Relationship
from app.core.tracks import TrackStore

FPS = 15
H = 100.0  # person height in pixels (1 body height)


def box(x, y, h=H):
    """Foot point (x, y) -> bounding box."""
    return (x - h * 0.2, y - h, x + h * 0.2, y)


def simulate(paths, duration, settings=None):
    """paths: {track_id: f(t) -> (x, y) or None}. Returns (engine, events)."""
    s = settings or DetectionSettings()
    store = TrackStore()
    engine = FollowingEngine(s)
    events = []
    n = int(duration * FPS)
    for f in range(n):
        t = f / FPS
        dets = []
        for tid, fn in paths.items():
            p = fn(t)
            if p is not None:
                dets.append((tid, box(*p), 0.9))
        store.update(t, f, dets)
        if engine.due(t):
            events += engine.step(store, t)
    events += engine.finish(n / FPS)
    return engine, events


def dominant(engine, a, b):
    counts = engine.pair_summary[(min(a, b), max(a, b))]["counts"]
    return max(counts, key=counts.get)


def walk(x0, y0, vx, vy, wobble=0.0, phase=0.0):
    return lambda t: (x0 + vx * t + wobble * math.sin(1.7 * t + phase),
                      y0 + vy * t + wobble * math.cos(1.3 * t + phase))


def test_following_on_curved_path_detected():
    # Leader walks an S-curve; follower walks the same path 2.5 s later.
    def leader(t):
        return 200 + 80 * t, 600 + 150 * math.sin(t / 3)

    def follower(t):
        return leader(t - 2.5) if t >= 2.5 else None

    engine, events = simulate({1: leader, 2: follower}, 20)
    opened = [e for e in events if e.kind == "following" and e.action == "opened"]
    assert len(opened) == 1
    p = opened[0].payload
    assert (p["leader_id"], p["follower_id"]) == (1, 2)
    assert p["confidence"] >= 0.6
    assert p["metrics"]["lag_sec"] > 1.5
    assert dominant(engine, 1, 2) == Relationship.POTENTIAL_FOLLOWING.value


def test_side_by_side_is_group_not_following():
    engine, events = simulate({
        1: walk(200, 500, 80, 10, wobble=3),
        2: walk(200, 590, 80, 10, wobble=3, phase=1.0),
    }, 15)
    assert not [e for e in events if e.kind == "following"]
    groups = [e for e in events if e.kind == "group" and e.action == "opened"]
    assert groups and set(groups[0].payload["members"]) == {1, 2}
    assert dominant(engine, 1, 2) == Relationship.GROUP_WALKING.value


def test_parallel_lanes_are_same_direction():
    engine, events = simulate({
        1: walk(200, 300, 80, 0),
        2: walk(50, 600, 80, 0),  # 3 body heights to the side, slightly behind
    }, 15)
    assert not [e for e in events if e.kind == "following"]
    assert dominant(engine, 1, 2) == Relationship.SAME_DIRECTION.value


def test_opposite_directions_no_following():
    engine, events = simulate({
        1: walk(200, 500, 80, 0),
        2: walk(1400, 560, -80, 0),
    }, 12)
    assert not events
    assert dominant(engine, 1, 2) == Relationship.NO_FOLLOWING.value


def test_short_following_is_not_an_event():
    def leader(t):
        return 200 + 80 * t, 500

    def follower(t):
        return leader(t - 2.0) if 2.0 <= t <= 7.0 else None

    _, events = simulate({1: leader, 2: follower}, 12)
    assert not [e for e in events if e.kind == "following"]


def test_standing_people_insufficient_evidence():
    engine, events = simulate({1: lambda t: (400, 500), 2: lambda t: (600, 500)}, 8)
    assert not events
    assert dominant(engine, 1, 2) == Relationship.INSUFFICIENT.value


def test_crowd_of_people_runs_and_finds_the_follower():
    # 40 random-ish walkers plus one follower pair, checks the engine copes with crowds.
    import random

    rnd = random.Random(7)
    paths = {}
    for i in range(10, 50):
        ang = rnd.uniform(0, 2 * math.pi)
        sp = rnd.uniform(40, 110)
        paths[i] = walk(rnd.uniform(0, 1800), rnd.uniform(0, 1000),
                        sp * math.cos(ang), sp * math.sin(ang), wobble=4, phase=i)
    paths[1] = lambda t: (100 + 90 * t, 300 + 100 * math.sin(t / 2.5))
    paths[2] = lambda t: paths[1](t - 2.2) if t >= 2.2 else None
    _, events = simulate(paths, 18)
    pairs = {(e.payload["leader_id"], e.payload["follower_id"])
             for e in events if e.kind == "following" and e.action == "opened"}
    assert (1, 2) in pairs
