"""Build readable subtitle cues without merging different speaker clusters."""

import html
import math
from pathlib import Path

from opencc import OpenCC

from .pipeline import load_json, save_json
from .review import apply_review

UNKNOWN = "UNKNOWN"


def timestamp(seconds: float, separator: str = ",") -> str:
    if not math.isfinite(seconds) or seconds < 0:
        raise ValueError("A timestamp must be finite and non-negative.")
    milliseconds = round(seconds * 1000)
    hours, milliseconds = divmod(milliseconds, 3_600_000)
    minutes, milliseconds = divmod(milliseconds, 60_000)
    whole_seconds, milliseconds = divmod(milliseconds, 1000)
    return f"{hours:02}:{minutes:02}:{whole_seconds:02}{separator}{milliseconds:03}"


def validate_roles(roles: dict, speakers: set[str]) -> None:
    if not isinstance(roles, dict):
        raise TypeError("Roles must be a JSON object keyed by speaker cluster.")
    for speaker, entry in roles.items():
        if speaker not in speakers:
            raise ValueError(f"Unknown speaker in role map: {speaker}")
        if (
            not isinstance(entry, dict)
            or not entry.get("role")
            or not entry.get("evidence")
        ):
            raise ValueError(f"Role {speaker} requires role and evidence fields.")
        if any(
            not isinstance(entry.get(field, ""), str)
            for field in ("role", "name", "organization")
        ):
            raise TypeError(
                f"Role {speaker} requires string role, name, and organization fields."
            )
        if not isinstance(entry["evidence"], list):
            raise TypeError(f"Role {speaker} evidence must be a list.")
        for evidence in entry["evidence"]:
            if (
                not isinstance(evidence, dict)
                or not isinstance(evidence.get("start"), (float, int))
                or not math.isfinite(evidence["start"])
                or evidence["start"] < 0
                or not isinstance(evidence.get("text"), str)
                or not evidence["text"].strip()
            ):
                raise ValueError(f"Role {speaker} evidence requires start and text.")


def speaker_label(speaker: str, roles: dict) -> str:
    entry = roles.get(speaker)
    if not entry:
        return "說話者未確認" if speaker == UNKNOWN else f"{speaker}（角色未確認）"
    if entry.get("organization"):
        return "／".join((entry.get("name") or entry["role"], entry["organization"]))
    if entry["role"].startswith("辯論者") and entry.get("name"):
        return entry["name"]
    return "／".join(part for part in (entry["role"], entry.get("name", "")) if part)


def make_cues(result: dict, roles: dict | None = None) -> list[dict]:
    roles = roles or {}
    converter = OpenCC("s2tw")
    duration = result["metadata"]["duration"]
    cues: list[dict] = []
    current: dict | None = None

    def flush() -> None:
        nonlocal current
        if current:
            current["text"] = converter.convert(current["text"].strip())
            current["label"] = speaker_label(current["speaker"], roles)
            if current["text"]:
                cues.append(current)
        current = None

    for segment in result["segments"]:
        words = segment.get("words", [])
        timed = [word for word in words if "start" in word and "end" in word]
        if not timed:
            flush()
            text = segment["text"].strip()
            start, end = float(segment["start"]), float(segment["end"])
            if text:
                if not 0 <= start < end <= duration + 0.05:
                    raise ValueError(f"Invalid segment time: {start} to {end}")
                current = {
                    "start": start,
                    "end": min(end, duration),
                    "text": text,
                    "speaker": segment.get("speaker", UNKNOWN),
                    "timing": "segment",
                }
                flush()
            continue
        # Keep untimed punctuation and characters. Their time is only estimated.
        pending = ""
        for word in words:
            text = word["word"]
            if "start" not in word or "end" not in word:
                if current:
                    current["text"] += text
                    current["timing"] = "partly_aligned"
                else:
                    pending += text
                continue
            start, end = float(word["start"]), float(word["end"])
            if not (
                math.isfinite(start)
                and math.isfinite(end)
                and 0 <= start <= end <= duration + 0.05
            ):
                raise ValueError(f"Invalid aligned word time: {start} to {end}")
            # A zero-length aligned character needs a visible cue, not a zero-length cue.
            end = min(duration, max(end, start + 0.001))
            if end <= start:
                raise ValueError("Aligned word starts at or after the audio end.")
            speaker = word.get("speaker", UNKNOWN)
            had_pending = bool(pending)
            text = pending + text
            pending = ""
            if current and (
                speaker != current["speaker"]
                or start - current["end"] > 0.8
                or end - current["start"] > 6
                or len(current["text"] + text) > 32
            ):
                flush()
            if current is None:
                current = {
                    "start": start,
                    "end": end,
                    "text": text,
                    "speaker": speaker,
                    "timing": "partly_aligned" if had_pending else "aligned",
                }
            else:
                current["text"] += text
                current["end"] = max(current["end"], end)
                if had_pending:
                    current["timing"] = "partly_aligned"
            if text.endswith(tuple("。！？!?；;")):
                flush()
        if pending:
            if cues and current is None:
                cues[-1]["text"] += converter.convert(pending)
                cues[-1]["timing"] = "partly_aligned"
            elif current:
                current["text"] += pending
                current["timing"] = "partly_aligned"
    flush()
    # Alignment may assign the same interval to adjacent characters. Preserve the
    # times in JSON, but put cues in chronological order for subtitle readers.
    cues.sort(key=lambda cue: cue["start"])
    for index, cue in enumerate(cues, 1):
        cue["id"] = index
    return cues


def export(
    result: dict,
    output: Path,
    roles: dict | None = None,
    corrections: Path | None = None,
) -> dict:
    roles = {} if roles is None else roles
    speakers = {turn["speaker"] for turn in result.get("speaker_turns", [])}
    validate_roles(roles, speakers)
    cues = make_cues(result, roles)
    if not cues:
        raise ValueError("No speech cues were produced.")
    if corrections is None and (output / "corrections.json").is_file():
        corrections = output / "corrections.json"
    cues, review = apply_review(cues, corrections)
    output.mkdir(parents=True, exist_ok=True)
    if corrections:
        if corrections.resolve() != (output / "corrections.json").resolve():
            save_json(output / "corrections.json", load_json(corrections))
    else:
        save_json(
            output / "corrections.json",
            {
                "source_sha256": review["source_sha256"],
                "method": review["method"],
                "corrections": [],
                "flags": [],
            },
        )
    srt, vtt = [], ["WEBVTT\n"]
    markdown = [
        "# Debate transcript\n",
        f"- Source: `{Path(result['metadata']['source']).name}`",
        f"- Duration: {timestamp(result['metadata']['duration'], '.')}",
        f"- Processing stage: `{result['metadata']['stage']}`",
        "- Text: automatic transcription, converted to Traditional Chinese.",
        "- Speaker clusters are not verified identities. Unmapped roles remain unconfirmed.",
        "- Overlap, names, and low-confidence speech require review.",
        (
            f"- Text review: {len(review['corrections'])} corrected cues; "
            f"{len(review['flags'])} cues require review. See `corrections.json`."
        ),
        "- Source segments and character times are unchanged; reviewed cue text may differ.\n",
    ]
    for cue in cues:
        text = f"【{cue['label']}】{cue['text']}"
        srt.append(
            f"{cue['id']}\n{timestamp(cue['start'])} --> {timestamp(cue['end'])}\n{text}\n"
        )
        vtt.append(
            f"{cue['id']}\n{timestamp(cue['start'], '.')} --> {timestamp(cue['end'], '.')}\n"
            f"{html.escape(text)}\n"
        )
        markdown.append(
            f"[{timestamp(cue['start'], '.')}–{timestamp(cue['end'], '.')}] "
            f"**{cue['label']}** {cue['text']}\n"
        )
    (output / "subtitles.srt").write_text("\n".join(srt), encoding="utf-8")
    (output / "subtitles.vtt").write_text("\n".join(vtt), encoding="utf-8")
    (output / "transcript.md").write_text("\n".join(markdown), encoding="utf-8")
    # Keep model input text in work/ only. All text fields in the public
    # transcript use Traditional Chinese, including the aligned character list.
    converter = OpenCC("s2tw")
    display_segments = []
    for segment in result["segments"]:
        display = {**segment, "text": converter.convert(segment["text"])}
        if "words" in segment:
            display["words"] = [
                {**word, "word": converter.convert(word["word"])}
                for word in segment["words"]
            ]
        display_segments.append(display)
    metadata = {
        key: value
        for key, value in result["metadata"].items()
        if key != "source_mtime_ns"
    }
    metadata["source"] = Path(metadata["source"]).name
    artifact = {
        "metadata": metadata,
        "display_language": "zh-Hant-TW",
        "roles": roles,
        "segments": display_segments,
        "speaker_turns": result.get("speaker_turns", []),
        "cues": cues,
        "segments_text_status": "original_asr_before_display_review",
        "review": review,
    }
    save_json(output / "transcript.json", artifact)
    by_id = {cue["id"]: cue for cue in cues}
    save_json(
        output / "review-needed.json",
        [
            {
                **by_id[flag["cue_id"]],
                "review_id": flag["id"],
                "reasons": flag["reason"].splitlines(),
                "suggestion": flag.get("suggestion", ""),
            }
            for flag in review["flags"]
        ],
    )
    summary = {
        "duration_seconds": result["metadata"]["duration"],
        "stage": result["metadata"]["stage"],
        "cue_count": len(cues),
        "first_cue_start": cues[0]["start"],
        "last_cue_end": max(cue["end"] for cue in cues),
        "speaker_clusters": sorted(speakers),
        "unassigned_cues": sum(cue["speaker"] == UNKNOWN for cue in cues),
        "unconfirmed_role_cues": sum(cue["speaker"] not in roles for cue in cues),
        "segment_timing_cues": sum(cue["timing"] != "aligned" for cue in cues),
        "corrected_cues": len(review["corrections"]),
        "pending_review_cues": len(review["flags"]),
    }
    save_json(output / "validation.json", summary)
    return summary
