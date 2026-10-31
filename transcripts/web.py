"""Render a debate transcript page with an embedded YouTube player."""

import json
import re
from pathlib import Path

from .fact_checks import validate_fact_checks

_ASSETS = Path(__file__).with_name("assets")


def render_page(
    artifact: dict, output_dir: Path, *, fact_checks: object | None = None
) -> Path:
    """Write inline HTML from an artifact and an explicit optional fact-check ledger."""
    output_dir = Path(output_dir)
    if fact_checks is not None:
        fact_checks = validate_fact_checks(fact_checks, artifact)
    review = artifact.get("review") or {}
    corrections = list(review.get("corrections", []))
    by_id = {cue["id"]: cue for cue in artifact.get("cues", [])}
    for entry in review.get("speaker_corrections", []):
        cue = by_id.get(entry["cue_id"], {})
        corrections.append(
            {
                **entry,
                "before": cue.get("original_label", entry["before"]),
                "after": cue.get("label", entry["after"]),
                "kind": "speaker",
            }
        )
    payload = {
        "metadata": {
            key: artifact.get("metadata", {}).get(key)
            for key in ("duration", "model", "stage")
        },
        "display_language": artifact.get("display_language", "zh-Hant-TW"),
        "roles": {
            speaker: {
                key: role.get(key, "") for key in ("role", "name", "organization")
            }
            for speaker, role in artifact.get("roles", {}).items()
        },
        "cues": [
            {
                key: cue[key]
                for key in (
                    "id",
                    "start",
                    "end",
                    "speaker",
                    "label",
                    "text",
                    "timing",
                    "original_text",
                    "correction_id",
                    "original_speaker",
                    "original_label",
                    "speaker_correction_id",
                )
                if key in cue
            }
            for cue in artifact.get("cues", [])
        ],
        "review": {
            "corrections": [
                {
                    key: item[key]
                    for key in (
                        "id",
                        "cue_id",
                        "before",
                        "after",
                        "reason",
                        "evidence",
                        "kind",
                    )
                    if key in item
                }
                for item in corrections
            ],
            "flags": [
                {
                    key: item[key]
                    for key in (
                        "id",
                        "cue_id",
                        "reason",
                        "suggestion",
                    )
                    if key in item
                }
                for item in review.get("flags", [])
            ],
            "method": review.get("method", ""),
            "source_sha256": review.get("source_sha256", ""),
        },
    }
    if fact_checks is not None:
        payload["fact_checks"] = fact_checks
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    for character, escaped in (
        ("&", "\\u0026"),
        ("<", "\\u003c"),
        (">", "\\u003e"),
        ("\u2028", "\\u2028"),
        ("\u2029", "\\u2029"),
    ):
        data = data.replace(character, escaped)
    replacements = {
        "STYLE": (_ASSETS / "page.css").read_text(encoding="utf-8"),
        "SCRIPT": (_ASSETS / "page.js").read_text(encoding="utf-8"),
        "DATA": data,
    }
    template = (_ASSETS / "page.html").read_text(encoding="utf-8")
    page = re.sub(
        r"\{\{(STYLE|SCRIPT|DATA)\}\}",
        lambda match: replacements[match[1]],
        template,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / "index.html"
    destination.write_text(page, encoding="utf-8")
    return destination
