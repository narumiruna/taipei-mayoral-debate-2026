"""Validate cue-based chapter metadata and resolve public navigation intervals."""

import math
import re


def _object(value: object, field: str) -> dict:
    if not isinstance(value, dict):
        # JSON schema errors use ValueError, including invalid field types.
        raise ValueError(f"{field} must be an object.")  # noqa: TRY004
    return value


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a nonempty string.")
    return value


def _list(value: object, field: str, *, nonempty: bool = False) -> list:
    if not isinstance(value, list) or (nonempty and not value):
        requirement = "a nonempty list" if nonempty else "a list"
        raise ValueError(f"{field} must be {requirement}.")
    return value


def _hash(value: object, field: str) -> str:
    text = _text(value, field)
    if not re.fullmatch(r"[0-9a-f]{64}", text):
        raise ValueError(f"{field} must be a lowercase 64-character SHA-256 hash.")
    return text


def _time(value: object, field: str) -> int | float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            if math.isfinite(value) and value >= 0:
                return value
        except OverflowError:
            pass
    raise ValueError(f"{field} must be a finite nonnegative number.")


def validate_chapters(chapters: object, artifact: dict) -> dict:
    """Return public fields and derived times without changing either input."""
    root = _object(chapters, "chapters")
    source_hash = _hash(root.get("source_sha256"), "chapters.source_sha256")
    review = _object(artifact.get("review"), "artifact.review")
    artifact_hash = _hash(review.get("source_sha256"), "artifact.review.source_sha256")
    if source_hash != artifact_hash:
        raise ValueError(
            "chapters.source_sha256 must match artifact.review.source_sha256."
        )
    metadata_value = artifact.get("metadata")
    metadata = _object(
        {} if metadata_value is None else metadata_value, "artifact.metadata"
    )
    duration_value = metadata.get("duration")
    cues = {}
    for position, value in enumerate(_list(artifact.get("cues"), "artifact.cues")):
        field = f"artifact.cues[{position}]"
        cue = _object(value, field)
        cue_id = cue.get("id")
        if type(cue_id) is not int or cue_id in cues:
            raise ValueError(f"{field}.id must be a unique integer.")
        start = _time(cue.get("start"), f"{field}.start")
        end = _time(cue.get("end"), f"{field}.end")
        if start >= end:
            raise ValueError(f"{field} must have start < end within the recording.")
        cues[cue_id] = (position, start, end)
    duration = (
        max((end for _, _, end in cues.values()), default=0)
        if duration_value is None
        else _time(duration_value, "artifact.metadata.duration")
    )
    if any(end > duration for _, _, end in cues.values()):
        raise ValueError("artifact.cues must have start < end within the recording.")

    identities = set()
    leaves = []

    def nodes(values: object, field: str, *, nonempty: bool = False) -> list:
        result = []
        previous_position = -1
        for index, value in enumerate(_list(values, field, nonempty=nonempty)):
            node_field = f"{field}[{index}]"
            node = _object(value, node_field)
            public: dict = {
                key: _text(node.get(key), f"{node_field}.{key}")
                for key in ("id", "title")
            }
            if public["id"] in identities:
                raise ValueError(f"{node_field}.id must be unique: {public['id']!r}.")
            identities.add(public["id"])
            if "children" in node:
                if "start_cue_id" in node or "end_cue_id" in node:
                    raise ValueError(
                        f"{node_field} must not combine children and leaf cue references."
                    )
                children = nodes(
                    node["children"], f"{node_field}.children", nonempty=True
                )
                public.update(
                    start_cue_id=children[0]["start_cue_id"],
                    end_cue_id=children[-1]["end_cue_id"],
                    start=children[0]["start"],
                    end=children[-1]["end"],
                    children=children,
                )
            else:
                for key in ("start_cue_id", "end_cue_id"):
                    cue_id = node.get(key)
                    if type(cue_id) is not int or cue_id not in cues:
                        raise ValueError(
                            f"{node_field}.{key} must reference an existing integer cue ID."
                        )
                    public[key] = cue_id
                first_position, start, first_end = cues[public["start_cue_id"]]
                last_position, last_start, end = cues[public["end_cue_id"]]
                if (
                    first_position > last_position
                    or start > last_start
                    or first_end > end
                ):
                    raise ValueError(
                        f"{node_field} must have a chronological cue range."
                    )
                public.update(start=start, end=end)
                leaves.append(public)
            first_position = cues[public["start_cue_id"]][0]
            last_position = cues[public["end_cue_id"]][0]
            if first_position <= previous_position:
                raise ValueError(
                    f"{node_field} must be in chronological sibling order."
                )
            previous_position = last_position
            result.append(public)
        return result

    items = nodes(root.get("items"), "chapters.items")
    previous_end = 0
    for leaf in leaves:
        if leaf["start"] < previous_end:
            raise ValueError(
                "Chapter leaf intervals must be ordered and must not overlap."
            )
        previous_end = leaf["end"]
    return {"source_sha256": source_hash, "items": items}
