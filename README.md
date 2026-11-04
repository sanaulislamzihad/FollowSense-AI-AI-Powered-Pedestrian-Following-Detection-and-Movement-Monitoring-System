# FollowSense AI

**AI-powered pedestrian following detection, group movement and crowd monitoring.**

FollowSense AI processes recorded video or live CCTV streams (RTSP / HTTP / webcam), detects and tracks
pedestrians, analyses their trajectories and flags situations where one person consistently appears to
follow another. It also detects group walking, measures crowd levels and congestion zones, and presents
everything in a real-time dashboard with review workflow and PDF/CSV reports.

> FollowSense reports *observable movement patterns*. It does not infer intent, does not identify people
> (anonymous track IDs, no face recognition) and every alert should be reviewed by a human operator.

---

## Features

| Module | What it does |
|---|---|
| Pedestrian detection | Pretrained YOLO11 (COCO *person*), optional SAHI-style **tiled** mode for dense crowds |
| Multi-object tracking | ByteTrack or BoT-SORT (ultralytics implementations), configurable occlusion memory |
| Camera motion compensation | Background optical flow + RANSAC similarity → stabilised coordinates, so handheld / PTZ pans don't look like everybody walking together |
| Following detection | Custom trajectory engine: distance, direction, speed, relative position, **time-lagged path retracing**, temporal consistency |
| Relationship classes | Potential following · Same direction · Group walking · No following · Insufficient evidence |
| Group movement | Sustained side-by-side pairs → connected components with stable group IDs, join / leave / split history |
| Crowd management | People-in-view timeline, normal / elevated / critical levels, DBSCAN-style congestion zones, overcrowding & congestion alerts |
| Visualisation | Annotated H.264 video, live MJPEG view, trajectory map, density heatmap, direction rose, speed histogram |
| Alerts & review | WebSocket toasts, event snapshots, confirm / dismiss / notes, jump to the moment in the video |
| Reports | Per-analysis PDF (ReportLab) and CSV export of following / crowd events |

## Architecture

```
 video file / RTSP ──► OpenCV capture ──► resize (≤1280 px) ──► YOLO11 person detection (+ tiles)
                                                                    │
                                    ByteTrack / BoT-SORT  ◄─────────┘
                                            │ track IDs + boxes
              camera motion compensation ◄──┤  (foot points → reference frame)
                                            ▼
                                       TrackStore (trajectory history, kinematics)
                     ┌──────────────────────┼───────────────────────────┐
              FollowingEngine          GroupTracker                CrowdMonitor
          (pairwise, every 0.25 s)   (components of group pairs)  (count, clusters, levels)
                     └──────────┬───────────┴───────────────────────────┘
                                ▼ EngineEvents
     JobManager (thread pool) ──► SQLAlchemy (PostgreSQL / SQLite) ──► FastAPI REST + WebSocket ──► React dashboard
                               └► annotated MP4, snapshots, heatmap, report.pdf
```

```
backend/
  app/core/        detector, tracks, motion, following, groups, crowd, annotate, pipeline
  app/services/    job manager, realtime hub, settings, rendering, reports
  app/api/         REST routers (videos, jobs, events, overview/cameras/settings)
  scripts/         analyze_video.py (CLI)
  tests/           engine, crowd/motion and API tests
frontend/          React 18 + Vite + Tailwind + Chart.js dashboard
Dockerfile, docker-compose.yml
```

## How following is detected

All distances are measured in **body heights** (the average bounding-box height of the two people). This
makes thresholds largely independent of resolution, zoom and camera angle.

Every 0.25 s each pair of nearby tracks is resampled on a common 5 Hz grid over the last
`analysis_window_sec` (default 4 s) and compared:

1. **Distance** — mean separation must be within `follow_min_distance … follow_max_distance` (0.7–6 bh).
2. **Direction similarity** — mean cosine of the velocity vectors (≥ 0.8).
3. **Speed consistency** — slower ÷ faster speed (≥ 0.55).
4. **Relative position** — the follower must be *behind* the leader along the leader's heading
   (inside a ±45° cone) for ≥ 70 % of the window. People mostly *beside* each other are group walking.
5. **Trajectory similarity with lag** — for lags 0.4–6 s the follower's path is compared with the
   leader's path *lag seconds earlier*; the best lag gives a similarity `exp(-d²/2σ²)`. A follower walks
   through the places the leader just walked through, which parallel walkers do not.
6. **Temporal consistency** — a following *event* is raised only when the window-level classification
   stays "potential following" for `min_following_duration_sec` (default 5 s), tolerating short gaps
   (`gap_tolerance_sec`). Leader/follower roles are decided per window from the behind-ratio.

Confidence = weighted window score (direction, speed, trajectory similarity, behind ratio) scaled by
event duration and the share of positive windows. All thresholds are editable in **Settings**.

## Running locally

Requirements: Python 3.10+ (tested on 3.13), Node 18+.

```bash
# backend
cd backend
pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

# frontend (dev server with proxy to :8000)
cd frontend
npm install
npm run dev            # http://localhost:5173
```

On Windows `start.bat` opens both. The YOLO weights (`yolo11n.pt`) download automatically on first use.
Without `FS_DATABASE_URL` a SQLite file is created in `backend/data/`; for PostgreSQL copy
`backend/.env.example` to `backend/.env` and set the URL. API docs: <http://localhost:8000/docs>.

If `frontend/dist` exists (after `npm run build`) the backend also serves the dashboard on port 8000.

### Command-line analysis

```bash
cd backend
python scripts/analyze_video.py ../video.mp4 --out annotated.mp4 --snapshots snaps/
python scripts/analyze_video.py rtsp://user:pass@cam/stream --settings '{"tracker":"botsort"}'
```

### Docker (PostgreSQL + app)

```bash
docker compose up --build      # http://localhost:8000
```

For a GPU host build with `--build-arg TORCH_INDEX=https://download.pytorch.org/whl/cu121`, run with
the NVIDIA runtime and set `FS_DEVICE=0`.

### Tests

```bash
cd backend
python -m pytest -q
```

Engine tests use synthetic trajectories (curved-path following, side-by-side groups, parallel lanes,
opposite directions, short following, standing people, a 40-person crowd); crowd/motion tests cover
congestion clustering, overcrowding alerts and camera-pan compensation; the API test uploads a video and
exercises every endpoint including the PDF report.

## Configuration notes for real cameras

- **Crowd levels** (`crowd_warning_count`, `crowd_critical_count`) depend on how much of the scene a
  camera sees — set them per site.
- **CPU vs GPU** — on a laptop CPU, YOLO11n at 1280 px runs ≈ 2–3 analysed frames/s. Recorded video is
  sampled at `target_fps` (default 15), so analysis is slower than real time on CPU; a GPU gives real-time
  processing for live streams. Live streams always analyse the newest frame and drop stale ones.
- **Dense crowds** — enable `detection_mode = tiled` (and ideally a GPU) for small, distant people.
- **Fixed CCTV** — camera motion compensation automatically stays at identity when the camera is static.

## Limitations

- Following detection measures movement similarity, not intent; people in a queue or walking the same
  corridor single-file can be flagged and must be reviewed.
- Heavy occlusion and ID switches in crowds can break or merge trajectories.
- Very dense, distant crowds (people ≈ 10 px tall) are beyond a person detector; a density-estimation
  model would be needed for exact counts there.
- Pixel-space analysis (no ground-plane calibration): strong perspective makes distances approximate.
- Camera motion compensation assumes a mostly planar/distant background; long handheld recordings
  accumulate small drift.

## Privacy

Anonymous numeric track IDs only, no facial recognition or identity matching. Uploaded videos,
annotated outputs and snapshots are stored under `FS_DATA_DIR` and can be deleted from the dashboard
(Video Management → delete removes the video, analyses, events and files).
