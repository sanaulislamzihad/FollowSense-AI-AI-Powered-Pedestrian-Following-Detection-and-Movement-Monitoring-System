"""Run the FollowSense pipeline on a video from the command line.

    python scripts/analyze_video.py path/to/video.mp4 --out annotated.mp4 [--seconds 15]
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import DetectionSettings, app_config  # noqa: E402
from app.core.pipeline import Callbacks, VideoAnalyzer  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("source")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--seconds", type=float, default=0, help="stop after N seconds of video")
    ap.add_argument("--settings", type=str, default="{}", help="JSON overrides")
    ap.add_argument("--model", default=app_config.yolo_model)
    ap.add_argument("--snapshots", type=Path, default=None)
    args = ap.parse_args()

    settings = DetectionSettings.from_dict(json.loads(args.settings))
    stop = threading.Event()
    if args.snapshots:
        args.snapshots.mkdir(parents=True, exist_ok=True)

    def on_event(ev, frame, t):
        p = ev.payload
        if ev.kind == "following":
            print(f"[{t:6.1f}s] FOLLOWING {ev.action:7s} {ev.key}: {p['follower_id']} -> {p['leader_id']} "
                  f"conf={p['confidence']} dur={p['duration']} metrics={p['metrics']}")
        elif ev.kind == "group":
            print(f"[{t:6.1f}s] GROUP     {ev.action:7s} {ev.key}: members={p['members']}")
        else:
            print(f"[{t:6.1f}s] CROWD     {ev.action:7s} {ev.key}: {p['crowd_type']} peak={p['peak_count']}")
        if args.snapshots and frame is not None and ev.action == "opened":
            import cv2
            cv2.imwrite(str(args.snapshots / f"{ev.key}.jpg"), frame)

    def on_progress(st):
        print(f"  t={st['t']:6.1f}s people={st['count']:3d} level={st['level']:8s} "
              f"tracks={st['tracks_total']:4d} follow={st['following_active']} groups={st['groups_active']} "
              f"fps={st['processing_fps']}", flush=True)
        if args.seconds and st["t"] >= args.seconds:
            stop.set()

    start = time.time()
    res = VideoAnalyzer(args.source, settings, model_path=args.model, device=app_config.device,
                        output_path=args.out, callbacks=Callbacks(on_event=on_event, on_progress=on_progress),
                        stop_event=stop).run()
    print("\n=== summary ===")
    print(f"duration={res.duration}s frames={res.frames_processed} fps={res.processing_fps} "
          f"wall={time.time() - start:.1f}s camera_motion={res.camera_motion}px")
    print(f"pedestrians={len(res.tracks)} crowd peak={res.crowd['peak_count']} avg={res.crowd['average_count']}")
    print(f"relationships={res.relationships}")
    print(f"directions={res.directions}")


if __name__ == "__main__":
    main()
