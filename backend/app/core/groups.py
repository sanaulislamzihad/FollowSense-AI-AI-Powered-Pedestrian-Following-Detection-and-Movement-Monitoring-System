"""Group movement detection: connected components of sustained group-walking pairs."""
from __future__ import annotations

from dataclasses import dataclass, field


def connected_components(edges: list[tuple[int, int]]) -> list[set[int]]:
    parent: dict[int, int] = {}

    def find(x: int) -> int:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b in edges:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb
    comps: dict[int, set[int]] = {}
    for node in parent:
        comps.setdefault(find(node), set()).add(node)
    return list(comps.values())


@dataclass
class Group:
    key: str
    members: set[int]
    start_time: float
    last_time: float
    max_size: int = 0
    all_members: set[int] = field(default_factory=set)
    history: list = field(default_factory=list)  # membership changes: (t, "join"/"leave", id)

    def payload(self) -> dict:
        return {
            "members": sorted(self.members),
            "all_members": sorted(self.all_members),
            "size": len(self.members),
            "max_size": self.max_size,
            "start_time": round(self.start_time, 2),
            "end_time": round(self.last_time, 2),
            "duration": round(self.last_time - self.start_time, 2),
            "history": self.history[-50:],
        }


class GroupTracker:
    """Keeps stable group identities while members join, leave, merge and split."""

    def __init__(self, gap_tolerance: float = 1.5):
        self.gap_tolerance = gap_tolerance
        self.groups: dict[str, Group] = {}
        self._seq = 0

    def update(self, edges: list[tuple[int, int]], t: float):
        from .following import EngineEvent  # local import avoids a cycle

        events = []
        comps = [c for c in connected_components(edges) if len(c) >= 2]
        used: set[str] = set()
        for comp in sorted(comps, key=len, reverse=True):
            best, best_j = None, 0.0
            for key, g in self.groups.items():
                if key in used:
                    continue
                j = len(comp & g.members) / len(comp | g.members)
                if j > best_j:
                    best, best_j = g, j
            if best is not None and best_j >= 0.34:
                used.add(best.key)
                changed = comp != best.members
                for m in comp - best.members:
                    best.history.append((round(t, 2), "join", m))
                for m in best.members - comp:
                    best.history.append((round(t, 2), "leave", m))
                best.members = set(comp)
                best.all_members |= comp
                best.max_size = max(best.max_size, len(comp))
                best.last_time = t
                if changed:
                    events.append(EngineEvent("group", "updated", best.key, best.payload()))
            else:
                self._seq += 1
                g = Group(key=f"G{self._seq}", members=set(comp), start_time=t, last_time=t,
                          max_size=len(comp), all_members=set(comp))
                g.history.append((round(t, 2), "formed", sorted(comp)))
                self.groups[g.key] = g
                used.add(g.key)
                events.append(EngineEvent("group", "opened", g.key, g.payload()))

        for key, g in list(self.groups.items()):
            if key not in used and t - g.last_time > self.gap_tolerance:
                g.history.append((round(t, 2), "separated", sorted(g.members)))
                del self.groups[key]
                events.append(EngineEvent("group", "closed", key, g.payload()))
        return events

    def close_all(self, t: float):
        from .following import EngineEvent

        events = [EngineEvent("group", "closed", k, g.payload()) for k, g in self.groups.items()]
        self.groups.clear()
        return events

    def membership(self) -> dict[int, str]:
        return {m: g.key for g in self.groups.values() for m in g.members}
