"""Apply auditable display-text corrections without changing source timings."""

import hashlib
import json
from pathlib import Path

from .pipeline import load_json


def source_fingerprint(cues: list[dict]) -> str:
    """Bind a correction ledger to the exact source cues, not display labels."""
    source = [
        {key: cue[key] for key in ("id", "start", "end", "speaker", "text")}
        for cue in cues
    ]
    encoded = json.dumps(
        source,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _text(entry: dict, key: str) -> str:
    value = entry.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Review entry requires a non-empty {key} string.")
    return value


def apply_review(cues: list[dict], path: Path | None = None) -> tuple[list[dict], dict]:
    """Validate every edit before applying any edit. Keep uncertain text intact."""
    fingerprint = source_fingerprint(cues)
    ledger = load_json(path) if path else {}
    if not isinstance(ledger, dict):
        raise TypeError("The correction ledger must be a JSON object.")
    if path and ledger.get("source_sha256") != fingerprint:
        raise ValueError(
            "Correction source changed. Review the new cues before exporting."
        )
    corrections = ledger.get("corrections", [])
    supplied_flags = ledger.get("flags", [])
    if not isinstance(corrections, list) or not isinstance(supplied_flags, list):
        raise TypeError("Review corrections and flags must be lists.")
    by_id = {cue["id"]: cue for cue in cues}
    edits = {}
    entry_ids = set()
    for entry in corrections:
        if not isinstance(entry, dict):
            raise TypeError("Each correction must be a JSON object.")
        identity = _text(entry, "id")
        cue_id = entry.get("cue_id")
        if type(cue_id) is not int or cue_id not in by_id:
            raise ValueError(f"Unknown correction cue: {cue_id}")
        if identity in entry_ids or cue_id in edits:
            raise ValueError("Correction IDs and corrected cue IDs must be unique.")
        entry_ids.add(identity)
        if _text(entry, "before") != by_id[cue_id]["text"]:
            raise ValueError(f"Correction {identity} does not match the original text.")
        after = _text(entry, "after")
        if after == entry["before"]:
            raise ValueError(f"Correction {identity} must change the text.")
        _text(entry, "reason")
        _text(entry, "evidence")
        edits[cue_id] = entry

    flags: dict[int, dict] = {}
    for cue in cues:
        reasons = []
        if cue["speaker"] == "UNKNOWN":
            reasons.append("說話者時間未與語音重疊，身分未確認。")
        if cue["end"] - cue["start"] > 6.01:
            reasons.append("單字對齊區間異常偏長，可能有時間對齊或漏字問題。")
        if reasons:
            flags[cue["id"]] = {
                "id": f"T{cue['id']:04d}",
                "cue_id": cue["id"],
                "reason": "\n".join(reasons),
            }
    for entry in supplied_flags:
        if not isinstance(entry, dict):
            raise TypeError("Each review flag must be a JSON object.")
        identity = _text(entry, "id")
        cue_id = entry.get("cue_id")
        if type(cue_id) is not int or cue_id not in by_id:
            raise ValueError(f"Unknown review flag cue: {cue_id}")
        if identity in entry_ids:
            raise ValueError("Correction and review flag IDs must be unique.")
        entry_ids.add(identity)
        reason = _text(entry, "reason")
        suggestion = entry.get("suggestion", "")
        if not isinstance(suggestion, str):
            raise TypeError("A review suggestion must be a string.")
        if cue_id in flags:
            flags[cue_id]["reason"] += "\n" + reason
            if suggestion:
                flags[cue_id]["suggestion"] = suggestion
        else:
            flags[cue_id] = dict(entry)

    result = []
    for cue in cues:
        display = dict(cue)
        if cue["id"] in edits:
            entry = edits[cue["id"]]
            display.update(
                text=entry["after"],
                original_text=cue["text"],
                correction_id=entry["id"],
            )
        result.append(display)
    review = {
        "source_sha256": fingerprint,
        "method": ledger.get("method", "尚未進行文字校對；時間與身分標記由程式檢查。"),
        "corrections": corrections,
        "flags": sorted(flags.values(), key=lambda flag: flag["cue_id"]),
    }
    return result, review
