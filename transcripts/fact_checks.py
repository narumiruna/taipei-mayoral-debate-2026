"""Validate curated fact checks against the reviewed transcript without fetching sources."""

import ipaddress
import re
import unicodedata
from datetime import date
from urllib.parse import urlsplit

_VERDICTS = {"supported", "needs-context", "contradicted", "insufficient-evidence"}


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


def _date(value: object, field: str) -> date:
    text = _text(value, field)
    if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", text):
        try:
            return date.fromisoformat(text)
        except ValueError:
            pass
    raise ValueError(f"{field} must be a valid YYYY-MM-DD date.")


def _hash(value: object, field: str) -> str:
    text = _text(value, field)
    if not re.fullmatch(r"[0-9a-f]{64}", text):
        raise ValueError(f"{field} must be a lowercase 64-character SHA-256 hash.")
    return text


def _valid_hostname(hostname: str) -> bool:
    if "%" in hostname:
        return False
    try:
        ipaddress.ip_address(hostname)
        return True
    except ValueError:
        pass
    if all(character in "0123456789." for character in hostname):
        return False
    try:
        hostname = hostname.encode("idna").decode("ascii").removesuffix(".")
    except UnicodeError:
        return False
    return len(hostname) <= 253 and all(
        re.fullmatch(r"[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?", label)
        for label in hostname.split(".")
    )


def _url(value: object, field: str) -> str:
    text = _text(value, field)
    error = f"{field} must be an HTTPS URL with a valid hostname and no credentials."
    if "\\" in text or any(
        character.isspace() or unicodedata.category(character) in {"Cc", "Cf", "Cs"}
        for character in text
    ):
        raise ValueError(
            f"{field} must not contain backslashes, whitespace, or control characters."
        )
    try:
        parsed = urlsplit(text)
        hostname = parsed.hostname
        # Accessing port also rejects nonnumeric and out-of-range ports.
        _ = parsed.port
    except ValueError as cause:
        raise ValueError(error) from cause
    if (
        parsed.scheme != "https"
        or parsed.username is not None
        or parsed.password is not None
        or not hostname
        or not _valid_hostname(hostname)
        or parsed.netloc.endswith(":")
        or (
            parsed.netloc.startswith("[")
            and not re.fullmatch(r"\[[^\]]+\](?::[0-9]+)?", parsed.netloc)
        )
    ):
        raise ValueError(error)
    return text


def _source(value: object, field: str, reviewed_at: date) -> dict:
    source = _object(value, field)
    if "published_at" not in source:
        raise ValueError(f"{field}.published_at is required (YYYY-MM-DD or null).")
    published_at = source["published_at"]
    if published_at is not None:
        published = _date(published_at, f"{field}.published_at")
        if published > reviewed_at:
            raise ValueError(f"{field}.published_at must not be after reviewed_at.")
    return {
        "title": _text(source.get("title"), f"{field}.title"),
        "publisher": _text(source.get("publisher"), f"{field}.publisher"),
        "published_at": published_at,
        "url": _url(source.get("url"), f"{field}.url"),
        "evidence": _text(source.get("evidence"), f"{field}.evidence"),
    }


def validate_fact_checks(ledger: object, artifact: dict) -> dict:
    """Return public fields only; require exact quotes in transcript cue order."""
    root = _object(ledger, "fact_checks")
    if type(root.get("version")) is not int or root["version"] != 1:
        raise ValueError("fact_checks.version must be the integer 1.")
    reviewed_at = _date(root.get("reviewed_at"), "fact_checks.reviewed_at")
    source_hash = _hash(root.get("source_sha256"), "fact_checks.source_sha256")
    review = _object(artifact.get("review"), "artifact.review")
    artifact_hash = _hash(review.get("source_sha256"), "artifact.review.source_sha256")
    if source_hash != artifact_hash:
        raise ValueError(
            "fact_checks.source_sha256 must match artifact.review.source_sha256."
        )
    result = {
        "version": 1,
        "reviewed_at": reviewed_at.isoformat(),
        "scope": _text(root.get("scope"), "fact_checks.scope"),
        "method": _text(root.get("method"), "fact_checks.method"),
        "source_sha256": source_hash,
        "items": [],
    }
    roles = _object(artifact.get("roles", {}), "artifact.roles")
    cues = {}
    for position, value in enumerate(_list(artifact.get("cues", []), "artifact.cues")):
        cue = _object(value, f"artifact.cues[{position}]")
        cue_id = cue.get("id")
        if type(cue_id) is not int or cue_id in cues:
            raise ValueError(f"artifact.cues[{position}].id must be a unique integer.")
        cues[cue_id] = (position, cue)
    identities = set()
    for index, value in enumerate(_list(root.get("items"), "fact_checks.items")):
        field = f"fact_checks.items[{index}]"
        item = _object(value, field)
        public: dict = {
            key: _text(item.get(key), f"{field}.{key}")
            for key in ("id", "speaker", "title", "verdict", "summary", "limitations")
        }
        identity = public["id"]
        if identity in identities:
            raise ValueError(f"{field}.id must be unique: {identity!r}.")
        identities.add(identity)
        if public["verdict"] not in _VERDICTS:
            raise ValueError(f"{field}.verdict is not a supported verdict.")
        speaker = public["speaker"]
        role = _object(roles.get(speaker), f"{field}.speaker role in artifact.roles")
        _text(role.get("name"), f"artifact.roles[{speaker!r}].name")
        public["analysis"] = [
            _text(entry, f"{field}.analysis[{entry_index}]")
            for entry_index, entry in enumerate(
                _list(item.get("analysis"), f"{field}.analysis", nonempty=True)
            )
        ]
        public["quotes"] = []
        quoted_ids = set()
        previous_position = -1
        for quote_index, value in enumerate(
            _list(item.get("quotes"), f"{field}.quotes", nonempty=True)
        ):
            quote_field = f"{field}.quotes[{quote_index}]"
            quote = _object(value, quote_field)
            cue_id = quote.get("cue_id")
            if type(cue_id) is not int or cue_id not in cues:
                raise ValueError(
                    f"{quote_field}.cue_id must reference an existing cue."
                )
            if cue_id in quoted_ids:
                raise ValueError(
                    f"{quote_field}.cue_id must be unique within the item."
                )
            quoted_ids.add(cue_id)
            position, cue = cues[cue_id]
            if position <= previous_position:
                raise ValueError(
                    f"{quote_field}.cue_id must be in chronological cue order."
                )
            previous_position = position
            text = _text(quote.get("text"), f"{quote_field}.text")
            if text != cue.get("text"):
                raise ValueError(
                    f"{quote_field}.text must exactly match cue {cue_id}.text."
                )
            if speaker != cue.get("speaker"):
                raise ValueError(f"{field}.speaker must match cue {cue_id}.speaker.")
            public["quotes"].append({"cue_id": cue_id, "text": text})
        public["sources"] = [
            _source(entry, f"{field}.sources[{entry_index}]", reviewed_at)
            for entry_index, entry in enumerate(
                _list(item.get("sources"), f"{field}.sources", nonempty=True)
            )
        ]
        result["items"].append(public)
    return result
