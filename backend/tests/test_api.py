"""End-to-end API test: upload a small synthetic video and walk through every endpoint."""
import time

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def video_file(tmp_path_factory):
    path = tmp_path_factory.mktemp("vid") / "synthetic.mp4"
    w = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 10, (320, 240))
    rng = np.random.default_rng(0)
    bg = cv2.GaussianBlur((rng.random((240, 320, 3)) * 255).astype(np.uint8), (5, 5), 1)
    for _ in range(30):
        w.write(bg)
    w.release()
    return path


def wait_job(client, job_id, timeout=180):
    end = time.time() + timeout
    while time.time() < end:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in ("completed", "failed", "stopped"):
            return job
        time.sleep(0.5)
    raise AssertionError("job did not finish")


def test_health_and_settings(client):
    assert client.get("/api/health").json()["status"] == "ok"
    s = client.get("/api/settings").json()
    assert "min_following_duration_sec" in s["values"]
    upd = client.put("/api/settings", json={"min_following_duration_sec": 7, "bogus": 1}).json()
    assert upd["values"]["min_following_duration_sec"] == 7.0
    assert "bogus" not in upd["values"]
    assert client.post("/api/settings/reset").json()["values"]["min_following_duration_sec"] == 5.0


def test_upload_analyse_and_report(client, video_file):
    with video_file.open("rb") as fh:
        r = client.post("/api/videos", files={"file": ("synthetic.mp4", fh, "video/mp4")})
    assert r.status_code == 200, r.text
    video = r.json()
    assert video["frame_count"] == 30
    job = wait_job(client, video["latest_job"]["id"])
    assert job["status"] == "completed", job.get("error")
    assert job["frames_processed"] > 0

    jid = job["id"]
    assert client.get(f"/api/jobs/{jid}/video").headers["content-type"] == "video/mp4"
    assert client.get(f"/api/jobs/{jid}/heatmap.png").status_code == 200
    assert client.get(f"/api/jobs/{jid}/trajectories.png").status_code == 200
    an = client.get(f"/api/jobs/{jid}/analytics").json()
    assert an["heatmap"]["cols"] == 64 and len(an["directions"]) == 8
    pdf = client.get(f"/api/jobs/{jid}/report.pdf")
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
    csv = client.get(f"/api/events/following/export.csv?job_id={jid}")
    assert csv.text.startswith("event_id")
    ov = client.get("/api/overview").json()
    assert ov["videos"] >= 1 and ov["jobs_completed"] >= 1
    assert any(v["id"] == video["id"] for v in client.get("/api/videos").json())


def test_review_following_event(client):
    from app.database import SessionLocal
    from app.models import AnalysisJob, FollowingEvent

    with SessionLocal() as db:
        job = db.query(AnalysisJob).first()
        ev = FollowingEvent(job_id=job.id, event_key="F99", leader_id=1, follower_id=2, start_time=1,
                            end_time=9, duration=8, confidence=0.8, metrics={"lag_sec": 2})
        db.add(ev)
        db.commit()
        eid = ev.id
    r = client.patch(f"/api/events/following/{eid}", json={"status": "dismissed", "notes": "same queue"})
    assert r.json()["status"] == "dismissed" and r.json()["notes"] == "same queue"
    assert client.patch(f"/api/events/following/{eid}", json={"status": "weird"}).status_code == 422
    listed = client.get("/api/events/following?status=dismissed").json()
    assert any(e["id"] == eid for e in listed)


def test_cameras_crud(client):
    cam = client.post("/api/cameras", json={"name": "Gate", "source_url": "rtsp://127.0.0.1:1/none"}).json()
    assert client.get("/api/cameras").json()[0]["name"] == "Gate"
    assert client.delete(f"/api/cameras/{cam['id']}").json()["ok"]
