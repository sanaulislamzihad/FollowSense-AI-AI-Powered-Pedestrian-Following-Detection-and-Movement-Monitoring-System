"""PDF (ReportLab) and CSV exports."""
from __future__ import annotations

import csv
import io
from datetime import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

from .render import encode_jpeg, heatmap_image, trajectory_image

BRAND = colors.HexColor("#0f766e")
LABELS = {
    "potential_following": "Potential following",
    "same_direction": "Same direction movement",
    "group_walking": "Group walking",
    "no_following": "No following detected",
    "insufficient_evidence": "Insufficient evidence",
}


def fmt_t(sec: float | None) -> str:
    if sec is None:
        return "-"
    m, s = divmod(float(sec), 60)
    return f"{int(m):02d}:{s:04.1f}"


def _table(rows, widths=None, header=True):
    t = Table(rows, colWidths=widths, repeatRows=1 if header else 0)
    style = [
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f1f5f9")]),
    ]
    if header:
        style += [("BACKGROUND", (0, 0), (-1, 0), BRAND), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                  ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold")]
    t.setStyle(TableStyle(style))
    return t


def _img(np_img, max_w=17 * cm, max_h=11 * cm) -> Image:
    h, w = np_img.shape[:2]
    k = min(max_w / w, max_h / h)
    return Image(io.BytesIO(encode_jpeg(np_img, 80)), width=w * k, height=h * k)


def job_pdf(job, following, groups, crowd_events, tracks) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=1.8 * cm, rightMargin=1.8 * cm,
                            topMargin=1.6 * cm, bottomMargin=1.6 * cm,
                            title=f"FollowSense AI report - job {job.id}")
    ss = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=ss["Title"], textColor=BRAND, fontSize=20)
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], textColor=BRAND)
    body = ParagraphStyle("b", parent=ss["BodyText"], fontSize=9.5, leading=13)
    small = ParagraphStyle("s", parent=body, fontSize=8, textColor=colors.HexColor("#475569"))
    story = []

    src = job.video.original_name if job.video else (job.camera.name if job.camera else job.source)
    story += [Paragraph("FollowSense AI - Analysis Report", h1),
              Paragraph(f"Source: <b>{src}</b> &nbsp; | &nbsp; Job #{job.id} &nbsp; | &nbsp; "
                        f"Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}", small), Spacer(1, 10)]

    crowd = job.crowd or {}
    lvl = crowd.get("level_seconds", {})
    summary = [
        ["Metric", "Value", "Metric", "Value"],
        ["Analysed duration", fmt_t(job.duration), "Unique pedestrians (track IDs)", job.total_pedestrians],
        ["Frames processed", job.frames_processed, "Peak people in view", job.peak_count],
        ["Processing speed", f"{job.processing_fps} fps", "Average people in view", job.average_count],
        ["Following events", len(following), "Group events", len(groups)],
        ["Crowd alerts", len(crowd_events), "Time at critical crowd level", f"{lvl.get('critical', 0)} s"],
        ["Camera motion compensated", f"{job.camera_motion} px", "Status", job.status],
    ]
    story += [Paragraph("Summary", h2), _table(summary, [4.2 * cm, 3.6 * cm, 5.4 * cm, 3.2 * cm])]

    rel = job.relationships or {}
    if rel:
        rows = [["Relationship class", "Pedestrian pairs"]] + [[LABELS.get(k, k), v] for k, v in rel.items()]
        story += [Spacer(1, 8), Paragraph("Movement relationship classification", h2), _table(rows, [9 * cm, 4 * cm])]

    story += [Spacer(1, 8), Paragraph("Following events", h2)]
    if following:
        rows = [["#", "Follower", "Leader", "Start", "Duration", "Confidence", "Distance", "Lag", "Status"]]
        for e in following:
            m = e.metrics or {}
            rows.append([e.id, f"ID {e.follower_id}", f"ID {e.leader_id}", fmt_t(e.start_time), f"{e.duration:.1f}s",
                         f"{e.confidence:.0%}", f"{m.get('mean_distance') or 0:.2f} bh",
                         f"{m.get('lag_sec') or 0:.1f}s", e.status])
        story.append(_table(rows))
        story.append(Paragraph("Distance is measured in body heights (bh). Lag = how many seconds later the follower "
                               "passes the leader's positions.", small))
    else:
        story.append(Paragraph("No potential following behaviour was detected.", body))

    if crowd_events:
        story += [Spacer(1, 8), Paragraph("Crowd alerts", h2)]
        rows = [["#", "Type", "Start", "Duration", "Peak", "Status"]]
        rows += [[c.id, c.crowd_type, fmt_t(c.start_time), f"{c.duration:.1f}s", c.peak_count, c.status]
                 for c in crowd_events]
        story.append(_table(rows))

    if groups:
        story += [Spacer(1, 8), Paragraph("Group movement", h2)]
        rows = [["Group", "Members", "Max size", "Start", "Duration"]]
        rows += [[g.group_key, ", ".join(map(str, g.all_members))[:60], g.max_size, fmt_t(g.start_time),
                  f"{g.duration:.1f}s"] for g in groups[:40]]
        story.append(_table(rows))

    story += [PageBreak(), Paragraph("Crowd density heatmap", h2), _img(heatmap_image(job))]
    highlight = {e.leader_id for e in following} | {e.follower_id for e in following}
    story += [Spacer(1, 6), Paragraph("Pedestrian trajectories (following pairs highlighted in red)", h2),
              _img(trajectory_image(job, tracks, highlight))]

    snaps = [e for e in following if e.snapshot_path and Path(e.snapshot_path).exists()][:6]
    if snaps:
        story += [PageBreak(), Paragraph("Event snapshots", h2)]
        for e in snaps:
            story += [Paragraph(f"Event #{e.id}: ID {e.follower_id} following ID {e.leader_id} at "
                                f"{fmt_t(e.start_time)} ({e.confidence:.0%})", body),
                      Image(e.snapshot_path, width=8 * cm, height=8 * cm, kind="proportional"), Spacer(1, 6)]

    story += [Spacer(1, 12), Paragraph(
        "<b>Note:</b> FollowSense AI reports observable movement patterns that resemble following. It does not "
        "determine intent and does not identify individuals (anonymous track IDs, no facial recognition). "
        "Every alert must be reviewed by a human operator before any action is taken.", small)]
    doc.build(story)
    return buf.getvalue()


def following_csv(events) -> str:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["event_id", "job_id", "leader_id", "follower_id", "start_time_s", "end_time_s", "duration_s",
                "confidence", "consistency", "mean_distance_bh", "direction_similarity", "speed_consistency",
                "trajectory_similarity", "behind_ratio", "lag_s", "status", "notes", "created_at"])
    for e in events:
        m = e.metrics or {}
        w.writerow([e.id, e.job_id, e.leader_id, e.follower_id, e.start_time, e.end_time, e.duration,
                    e.confidence, e.consistency, m.get("mean_distance"), m.get("direction_similarity"),
                    m.get("speed_consistency"), m.get("trajectory_similarity"), m.get("behind_ratio"),
                    m.get("lag_sec"), e.status, e.notes, e.created_at.isoformat() if e.created_at else ""])
    return out.getvalue()


def crowd_csv(events) -> str:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["event_id", "job_id", "type", "start_time_s", "end_time_s", "duration_s", "peak_count",
                "peak_time_s", "status"])
    for e in events:
        w.writerow([e.id, e.job_id, e.crowd_type, e.start_time, e.end_time, e.duration, e.peak_count,
                    e.peak_time, e.status])
    return out.getvalue()
