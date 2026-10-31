import copy
import json

import pytest

from transcripts.review import apply_review, source_fingerprint


@pytest.fixture
def cues():
    return [
        {
            "id": 1,
            "start": 0.5,
            "end": 2.0,
            "speaker": "SPEAKER_00",
            "label": "主持人／王小明",
            "text": "辨識原文。",
            "timing": "aligned",
        },
        {
            "id": 2,
            "start": 2.0,
            "end": 3.0,
            "speaker": "SPEAKER_01",
            "label": "候選人",
            "text": "第二段原文。",
            "timing": "segment",
        },
    ]


@pytest.fixture
def correction(cues):
    return {
        "id": "C001",
        "cue_id": 1,
        "before": cues[0]["text"],
        "after": "修訂文字。",
        "reason": "辨識同音字有誤。",
        "evidence": "回聽 00:00.5–00:02.0。",
    }


@pytest.fixture
def ledger(cues):
    return {"source_sha256": source_fingerprint(cues), "corrections": [], "flags": []}


def save_ledger(tmp_path, ledger):
    path = tmp_path / "corrections.json"
    path.write_text(json.dumps(ledger, ensure_ascii=False), encoding="utf-8")
    return path


@pytest.mark.parametrize(
    ("field", "value"),
    [("id", 9), ("start", 0.6), ("end", 2.1), ("speaker", "UNKNOWN"), ("text", "別字")],
)
def test_fingerprint_binds_source_fields(cues, field, value):
    changed = copy.deepcopy(cues)
    changed[0][field] = value

    assert source_fingerprint(changed) != source_fingerprint(cues)


def test_fingerprint_ignores_display_labels(cues):
    fingerprint = source_fingerprint(cues)
    cues[0]["label"] = "另一個顯示名稱"
    cues[1].pop("label")

    assert source_fingerprint(cues) == fingerprint
    assert len(fingerprint) == 64
    int(fingerprint, 16)


def test_correction_preserves_input_and_timing(tmp_path, cues, ledger, correction):
    original = copy.deepcopy(cues)
    ledger.update(method="依原始影音校對。", corrections=[correction])
    path = save_ledger(tmp_path, ledger)

    display, review = apply_review(cues, path)

    assert cues == original
    assert all(
        result is not source for result, source in zip(display, cues, strict=True)
    )
    assert display == [
        {
            **original[0],
            "text": correction["after"],
            "original_text": correction["before"],
            "correction_id": correction["id"],
        },
        original[1],
    ]
    assert review == {**ledger, "flags": []}
    assert json.loads(path.read_text(encoding="utf-8")) == ledger


@pytest.mark.parametrize("fingerprint", [None, "0" * 64])
def test_missing_or_stale_source_is_rejected(tmp_path, cues, ledger, fingerprint):
    ledger.pop("source_sha256")
    if fingerprint is not None:
        ledger["source_sha256"] = fingerprint

    with pytest.raises(ValueError, match="source changed"):
        apply_review(cues, save_ledger(tmp_path, ledger))


def test_all_corrections_are_validated_before_application(
    tmp_path, cues, ledger, correction
):
    original = copy.deepcopy(cues)
    ledger["corrections"] = [
        correction,
        {**correction, "id": "C002", "cue_id": 2, "before": "不是原文"},
    ]

    with pytest.raises(ValueError, match="does not match the original text"):
        apply_review(cues, save_ledger(tmp_path, ledger))

    assert cues == original


@pytest.mark.parametrize("value", [[], None, "ledger", 7])
def test_ledger_must_be_an_object(tmp_path, cues, value):
    with pytest.raises(TypeError, match="JSON object"):
        apply_review(cues, save_ledger(tmp_path, value))


@pytest.mark.parametrize("field", ["corrections", "flags"])
@pytest.mark.parametrize("value", [None, {}, "entries", False])
def test_entry_collections_must_be_lists(tmp_path, cues, ledger, field, value):
    ledger[field] = value

    with pytest.raises(TypeError, match="must be lists"):
        apply_review(cues, save_ledger(tmp_path, ledger))


@pytest.mark.parametrize("field", ["corrections", "flags"])
@pytest.mark.parametrize("value", [None, [], "entry", 7])
def test_entries_must_be_objects(tmp_path, cues, ledger, field, value):
    ledger[field] = [value]

    with pytest.raises(TypeError, match="JSON object"):
        apply_review(cues, save_ledger(tmp_path, ledger))


@pytest.mark.parametrize("field", ["id", "before", "after", "reason", "evidence"])
@pytest.mark.parametrize("value", [None, "", " \t", 7])
def test_correction_requires_nonempty_strings(
    tmp_path, cues, ledger, correction, field, value
):
    correction[field] = value
    ledger["corrections"] = [correction]

    with pytest.raises(ValueError, match=field):
        apply_review(cues, save_ledger(tmp_path, ledger))


@pytest.mark.parametrize("field", ["id", "before", "after", "reason", "evidence"])
def test_correction_requires_all_audit_fields(
    tmp_path, cues, ledger, correction, field
):
    correction.pop(field)
    ledger["corrections"] = [correction]

    with pytest.raises(ValueError, match=field):
        apply_review(cues, save_ledger(tmp_path, ledger))


def test_correction_must_change_text(tmp_path, cues, ledger, correction):
    correction["after"] = correction["before"]
    ledger["corrections"] = [correction]

    with pytest.raises(ValueError, match="must change the text"):
        apply_review(cues, save_ledger(tmp_path, ledger))


@pytest.mark.parametrize("field", ["corrections", "flags"])
@pytest.mark.parametrize("cue_id", [99, "1", True, 1.0, None])
def test_entry_requires_known_integer_cue_id(
    tmp_path, cues, ledger, correction, field, cue_id
):
    ledger[field] = [{**correction, "cue_id": cue_id}]

    with pytest.raises(ValueError, match="Unknown"):
        apply_review(cues, save_ledger(tmp_path, ledger))


@pytest.mark.parametrize("duplicate", ["id", "cue_id"])
def test_duplicate_correction_ids_or_cues_are_rejected(
    tmp_path, cues, ledger, correction, duplicate
):
    second = {
        **correction,
        "id": "C002",
        "cue_id": 2,
        "before": cues[1]["text"],
    }
    second[duplicate] = correction[duplicate]
    ledger["corrections"] = [correction, second]

    with pytest.raises(ValueError, match="must be unique"):
        apply_review(cues, save_ledger(tmp_path, ledger))


@pytest.mark.parametrize("collision", ["flag", "correction"])
def test_review_entry_ids_are_unique(tmp_path, cues, ledger, correction, collision):
    flag = {"id": "F001", "cue_id": 1, "reason": "需回聽。"}
    ledger["flags"] = [flag]
    if collision == "flag":
        ledger["flags"].append({**flag, "cue_id": 2})
    else:
        ledger["corrections"] = [{**correction, "id": flag["id"]}]

    with pytest.raises(ValueError, match="must be unique"):
        apply_review(cues, save_ledger(tmp_path, ledger))


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("id", None, ValueError),
        ("reason", " ", ValueError),
        ("suggestion", 7, TypeError),
    ],
)
def test_invalid_flag_fields_are_rejected(tmp_path, cues, ledger, field, value, error):
    ledger["flags"] = [{"id": "F001", "cue_id": 1, "reason": "需回聽。", field: value}]

    with pytest.raises(error, match=field):
        apply_review(cues, save_ledger(tmp_path, ledger))


def test_uncertain_suggestion_does_not_change_text(tmp_path, cues, ledger):
    original = copy.deepcopy(cues)
    ledger["flags"] = [
        {
            "id": "F001",
            "cue_id": 1,
            "reason": "尚未確認。",
            "suggestion": "可能的文字。",
        }
    ]

    display, review = apply_review(cues, save_ledger(tmp_path, ledger))

    assert display == cues == original
    assert review["flags"] == ledger["flags"]
    assert review["corrections"] == []


@pytest.mark.parametrize(
    ("speaker", "end", "reason_count"),
    [
        ("SPEAKER_00", 6.01, 0),
        ("SPEAKER_00", 6.02, 1),
        ("UNKNOWN", 2, 1),
        ("UNKNOWN", 7, 2),
    ],
)
def test_automatic_unknown_and_long_timing_flags(cues, speaker, end, reason_count):
    cues[0].update(start=0, end=end, speaker=speaker)
    original = copy.deepcopy(cues)

    display, review = apply_review(cues)

    assert display == cues == original
    assert review["source_sha256"] == source_fingerprint(cues)
    assert review["corrections"] == []
    assert len(review["flags"]) == bool(reason_count)
    if reason_count:
        (flag,) = review["flags"]
        assert flag["cue_id"] == 1
        assert len(flag["reason"].splitlines()) == reason_count


@pytest.mark.parametrize("automatic", [False, True])
def test_flags_for_same_cue_merge(tmp_path, cues, ledger, automatic):
    if automatic:
        cues[0].update(speaker="UNKNOWN", end=8)
        ledger["source_sha256"] = source_fingerprint(cues)
    ledger["flags"] = [
        {"id": "F002", "cue_id": 2, "reason": "第二段需確認。"},
        {"id": "F001", "cue_id": 1, "reason": "第一個原因。"},
        {
            "id": "F003",
            "cue_id": 1,
            "reason": "第二個原因。",
            "suggestion": "待查文字。",
        },
    ]

    display, review = apply_review(cues, save_ledger(tmp_path, ledger))

    assert display == cues
    first, second = review["flags"]
    assert [first["cue_id"], second["cue_id"]] == [1, 2]
    assert first["reason"].endswith("第一個原因。\n第二個原因。")
    assert len(first["reason"].splitlines()) == (4 if automatic else 2)
    assert first["suggestion"] == "待查文字。"
    assert second == ledger["flags"][0]
