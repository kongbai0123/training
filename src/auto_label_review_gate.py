from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List

from src.project_layout import ProjectLayout


REVIEWED_STATUSES = {"accepted", "rejected", "skipped", "hard_case"}


def build_auto_label_review_gate(project: Dict[str, Any]) -> Dict[str, Any]:
    """Summarize whether auto-label drafts are safe for training.

    Accepted drafts are copied into current LabelMe annotations by the review
    service. Pending drafts should not silently enter or be ignored by a
    training run, so strict mode blocks until every draft has an explicit
    review decision.
    """
    layout = ProjectLayout.from_project(project)
    summaries = list(_iter_job_summaries(layout))

    total = 0
    accepted = 0
    rejected = 0
    skipped = 0
    hard_case = 0
    pending = 0
    jobs_with_pending: List[str] = []

    for summary in summaries:
        job_id = str(summary.get("job_id") or "")
        job_pending = 0
        for item in summary.get("items") or []:
            total += 1
            status = str(item.get("review_status") or "").strip()
            if status == "accepted":
                accepted += 1
            elif status == "rejected":
                rejected += 1
            elif status == "skipped":
                skipped += 1
            elif status == "hard_case":
                hard_case += 1
            elif status not in REVIEWED_STATUSES:
                pending += 1
                job_pending += 1
        if job_pending:
            jobs_with_pending.append(job_id or "(unknown)")

    unsafe_current = _find_unaccepted_auto_label_current_annotations(layout)
    blocked = pending > 0 or bool(unsafe_current)
    warnings = []
    if pending:
        warnings.append(f"{pending} auto-label draft(s) still need review before training.")
    if unsafe_current:
        warnings.append(f"{len(unsafe_current)} current auto-label annotation file(s) are not accepted.")

    return {
        "mode": "strict",
        "blocked": blocked,
        "total_drafts": total,
        "accepted": accepted,
        "rejected": rejected,
        "skipped": skipped,
        "hard_case": hard_case,
        "pending": pending,
        "jobs_with_pending": jobs_with_pending,
        "unsafe_current": unsafe_current,
        "warnings": warnings,
        "message": (
            "Auto-label review gate passed. Accepted drafts can be used for training."
            if not blocked
            else "Auto-label review gate blocked training. Review pending drafts first."
        ),
    }


def auto_label_training_errors(project: Dict[str, Any]) -> List[str]:
    gate = build_auto_label_review_gate(project)
    errors: List[str] = []
    if gate["pending"]:
        jobs = ", ".join(gate["jobs_with_pending"][:4])
        errors.append(
            "Auto-label review gate: "
            f"{gate['pending']} draft(s) are still pending review"
            f"{f' in {jobs}' if jobs else ''}. Accept, reject, skip, or mark them as hard cases before training."
        )
    if gate["unsafe_current"]:
        files = ", ".join(gate["unsafe_current"][:4])
        errors.append(
            "Auto-label review gate: current annotations contain auto-label files that were not accepted: "
            f"{files}. Only accepted drafts may enter training."
        )
    return errors


def _iter_job_summaries(layout: ProjectLayout) -> Iterable[Dict[str, Any]]:
    jobs_root = layout.project_dir / "auto_labeling" / "jobs"
    if not jobs_root.exists():
        return []
    summaries = []
    for summary_path in sorted(jobs_root.glob("*/summary.json")):
        try:
            payload = json.loads(summary_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(payload, dict):
            summaries.append(payload)
    return summaries


def _find_unaccepted_auto_label_current_annotations(layout: ProjectLayout) -> List[str]:
    labelme_dir = layout.resolve_current_labelme_dir().path
    if not labelme_dir.exists():
        return []
    unsafe = []
    for json_path in sorted(labelme_dir.glob("*.json")):
        try:
            payload = json.loads(json_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        flags = payload.get("flags") or {}
        if not flags.get("auto_label"):
            continue
        if flags.get("auto_label_review_status") != "accepted" or flags.get("requires_review") is True:
            unsafe.append(json_path.name)
    return unsafe
