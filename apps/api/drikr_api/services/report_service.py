"""CSV and PDF report generation from persisted records."""

from __future__ import annotations

import csv
import io
from datetime import datetime
from importlib import resources
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from drikr_api.models import InstructorReview, ScoreResult, TrainingSession

DIMENSION_KEYS = ("recognition", "timing", "consistency", "uncertainty", "objectives", "procedure")
FOREST = colors.HexColor("#1F4D3A")
RULE = colors.HexColor("#D9D6CE")
MUTED = colors.HexColor("#5E625F")


def _safe_cell(value: Any) -> Any:
    """Neutralise spreadsheet formula injection (OWASP CSV injection guidance)."""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


def sessions_csv(rows: list[tuple[TrainingSession, ScoreResult | None, InstructorReview | None]]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    header = [
        "session_id",
        "trainee_username",
        "trainee_name",
        "scenario_key",
        "scenario_version",
        "mode",
        "attempt",
        "difficulty_level",
        "status",
        "completion_reason",
        "created_at",
        "completed_at",
        "overall",
        "passed",
        "rubric_key",
        "rubric_version",
        *[f"{d}_score" for d in DIMENSION_KEYS],
        "review_status",
    ]
    w.writerow(header)
    for s, r, rv in rows:
        dims = r.result.get("dimensions", {}) if r else {}
        w.writerow(
            [
                _safe_cell(v)
                for v in [
                    str(s.id),
                    s.trainee.username,
                    s.trainee.display_name,
                    s.scenario.key,
                    s.scenario.version,
                    s.mode.value,
                    s.attempt_number,
                    s.difficulty_level,
                    s.status.value,
                    s.completion_reason or "",
                    s.created_at.isoformat(),
                    s.completed_at.isoformat() if s.completed_at else "",
                    "" if not r or r.overall is None else r.overall,
                    "" if not r or r.passed is None else ("yes" if r.passed else "no"),
                    s.rubric.key,
                    s.rubric.version,
                    *["" if dims.get(d, {}).get("score") is None else dims[d]["score"] for d in DIMENSION_KEYS],
                    rv.status.value if rv else "",
                ]
            ]
        )
    return buf.getvalue()


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    body = ParagraphStyle(
        "body", parent=base["BodyText"], fontName="Helvetica", fontSize=9, leading=12, alignment=TA_LEFT
    )
    return {
        "title": ParagraphStyle(
            "title", parent=body, fontName="Helvetica-Bold", fontSize=16, leading=20, textColor=FOREST
        ),
        "h2": ParagraphStyle(
            "h2",
            parent=body,
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=14,
            spaceBefore=10,
            spaceAfter=4,
            textColor=FOREST,
        ),
        "body": body,
        "muted": ParagraphStyle("muted", parent=body, textColor=MUTED, fontSize=8, leading=10),
        "cell": ParagraphStyle("cell", parent=body, fontSize=8, leading=10),
    }


def _table(data: list[list[Any]], widths: list[float], st: dict[str, ParagraphStyle]) -> Table:
    rows = [[Paragraph(str(c), st["cell"]) if not isinstance(c, Paragraph) else c for c in row] for row in data]
    t = Table(rows, colWidths=widths, repeatRows=1)
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EEF2EF")),
                ("LINEBELOW", (0, 0), (-1, -1), 0.4, RULE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return t


def _iso(v: datetime | None) -> str:
    return v.isoformat() if v else "-"


def _esc(v: Any) -> str:
    return str(v).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def session_pdf(
    s: TrainingSession,
    r: ScoreResult | None,
    rv: InstructorReview | None,
    generated_by: str,
    *,
    include_notes: bool = True,
) -> bytes:
    st = _styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=f"After-action review {s.id}",
        author="Drikr Systems training simulator",
    )
    W = doc.width
    # Official Drikr Systems logo (1236 x 222 px source), drawn 50 mm wide.
    logo = (resources.files("drikr_api") / "assets" / "drikr-logo.png").read_bytes()
    header = Image(io.BytesIO(logo), width=50 * mm, height=50 * mm * 222 / 1236)
    header.hAlign = "LEFT"
    story: list[Any] = [
        header,
        Spacer(1, 4),
        Paragraph("After-Action Review", st["title"]),
        Paragraph(
            "Training record generated from a simulated exercise. "
            "All tracks, sensor readings and events are synthetic. "
            "This document is not an operational report.",
            st["muted"],
        ),
        Spacer(1, 6),
        Paragraph("Session overview", st["h2"]),
    ]
    overview = [
        ["Field", "Value"],
        ["Scenario", f"{_esc(s.scenario.name)} ({_esc(s.scenario.key)} v{s.scenario.version})"],
        ["Trainee", f"{_esc(s.trainee.display_name)} ({_esc(s.trainee.username)})"],
        ["Mode / attempt", f"{s.mode.value} / attempt {s.attempt_number}"],
        ["Status", f"{s.status.value} ({s.completion_reason or 'n/a'})"],
        ["Duration", f"{s.sim_elapsed_ms / 1000:.1f} s of {s.duration_ms / 1000:.0f} s simulated"],
        ["Difficulty level", str(s.difficulty_level)],
        ["Seed", str(s.seed)],
        [
            "Started / completed",
            f"{_iso(s.started_at)} / {_iso(s.completed_at)}",
        ],
        ["Engine", f"{s.engine_version}; timeline digest {s.timeline_digest[:16]}..."],
    ]
    if r is not None:
        overview += [
            ["Scoring", f"{r.scoring_engine_version}; rubric {_esc(s.rubric.key)} v{r.rubric_version}"],
            [
                "Overall",
                "insufficient data"
                if r.overall is None
                else f"{r.overall:.1f}% ({'pass' if r.passed else 'not passed'}; "
                f"pass mark {r.result.get('pass_mark')}%)",
            ],
            ["Input digest", r.input_digest],
        ]
    story.append(_table(overview, [W * 0.28, W * 0.72], st))

    if r is not None and r.status == "scored":
        res = r.result
        story.append(Paragraph("Performance breakdown", st["h2"]))
        dims = [["Dimension", "Score", "Weight", "Effective weight", "Explanation"]]
        for k in DIMENSION_KEYS:
            d = res["dimensions"][k]
            dims.append(
                [
                    d["label"],
                    "n/a" if d["score"] is None else f"{d['score']:.1f}%",
                    f"{d['weight']:.2f}",
                    f"{d['effective_weight']:.3f}",
                    _esc(d["summary"]),
                ]
            )
        story.append(_table(dims, [W * 0.2, W * 0.1, W * 0.1, W * 0.13, W * 0.47], st))
        story.append(Paragraph(_esc(res["explanation"]), st["muted"]))

        story.append(Paragraph("Learning objectives", st["h2"]))
        obj = [["Objective", "Status", "Detail"]] + [
            [_esc(o["description"]), o["status"].replace("_", " "), _esc(o["detail"])] for o in res["objectives"]
        ]
        story.append(_table(obj, [W * 0.4, W * 0.14, W * 0.46], st))

        story.append(Paragraph("Track decisions", st["h2"]))
        items = [["Track", "Ground truth", "Classification", "First decision", "Response", "Expected"]]
        for it in res["items"]:
            items.append(
                [
                    it["track_id"],
                    _esc(it["true_class"]) + (" (cooperative)" if it["cooperative"] else ""),
                    f"{it['final_classification'] or 'not classified'} ({it['final_confidence'] or '-'})",
                    "-"
                    if it["first_classification_s"] is None
                    else f"{it['first_classification_s'] - it['first_available_s']:.1f} s after first seen",
                    it["final_response"] or "none",
                    ", ".join(it["expected_responses"]),
                ]
            )
        story.append(_table(items, [W * 0.1, W * 0.2, W * 0.2, W * 0.17, W * 0.16, W * 0.17], st))

        errs = res["errors"]
        story.append(Paragraph("Error analysis", st["h2"]))
        err_rows = [["Category", "Count", "Tracks"]]
        for k, label in (
            ("incorrect_classifications", "Incorrect classifications"),
            ("missed_tracks", "Missed (never classified)"),
            ("inconsistent_decisions", "Inconsistent decisions"),
            ("overconfident", "Overconfident on weak evidence"),
            ("procedure_violations", "Procedural violations"),
        ):
            err_rows.append(
                [label, str(len(errs[k])), ", ".join(sorted({e.get("track_id") or "" for e in errs[k]}))[:200] or "-"]
            )
        story.append(_table(err_rows, [W * 0.35, W * 0.1, W * 0.55], st))

        story.append(Paragraph("Feedback", st["h2"]))
        for line in res["feedback"]["strengths"]:
            story.append(Paragraph("Strength: " + _esc(line), st["body"]))
        for line in res["feedback"]["improvements"]:
            story.append(Paragraph("Improve: " + _esc(line), st["body"]))
    elif r is not None:
        story.append(Paragraph("Performance", st["h2"]))
        story.append(Paragraph(_esc(r.result.get("explanation", "")), st["body"]))
    else:
        story.append(Paragraph("No score result is available for this session.", st["body"]))

    if rv is not None:
        story.append(Paragraph("Instructor review", st["h2"]))
        rev = [
            ["Field", "Value"],
            ["Reviewer", _esc(rv.reviewer.display_name)],
            ["Status", rv.status.value.replace("_", " ")],
            ["Strengths", _esc(rv.strengths) or "-"],
            ["Areas to improve", _esc(rv.improvements) or "-"],
            ["Focus objectives", ", ".join(rv.focus_objectives) or "-"],
        ]
        if include_notes:
            rev.append(["Instructor notes", _esc(rv.notes) or "-"])
        story.append(_table(rev, [W * 0.28, W * 0.72], st))

    story.append(Spacer(1, 10))
    story.append(
        Paragraph(
            f"Generated {datetime.now().astimezone().isoformat(timespec='seconds')} by {_esc(generated_by)}.",
            st["muted"],
        )
    )
    doc.build(story)
    return buf.getvalue()
