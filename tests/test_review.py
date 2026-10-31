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
def speaker_correction(cues):
    return {
        "id": "S001",
        "cue_id": 1,
        "before": cues[0]["speaker"],
        "after": cues[1]["speaker"],
        "reason": "原始說話者分群有誤。",
        "evidence": "回聽 00:00.5–00:02.0，與第二段聲音相符。",
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
    assert review == {**ledger, "speaker_corrections": [], "flags": []}
    assert json.loads(path.read_text(encoding="utf-8")) == ledger


@pytest.mark.parametrize("source_speaker", ["SPEAKER_00", "UNKNOWN"])
@pytest.mark.parametrize("with_text", [False, True])
def test_speaker_correction_replay_preserves_source(
    tmp_path, cues, ledger, correction, speaker_correction, source_speaker, with_text
):
    cues[0]["speaker"] = source_speaker
    if source_speaker == "UNKNOWN":
        cues[0]["label"] = "說話者未確認"
    speaker_correction["before"] = source_speaker
    ledger.update(
        source_sha256=source_fingerprint(cues),
        method="依原始影音校對。",
        speaker_corrections=[speaker_correction],
    )
    if with_text:
        ledger["corrections"] = [correction]
    original = copy.deepcopy(cues)
    original_ledger = copy.deepcopy(ledger)
    path = save_ledger(tmp_path, ledger)

    display, review = apply_review(cues, path)

    expected = [
        {
            **original[0],
            "speaker": original[1]["speaker"],
            "label": original[1]["label"],
            "original_speaker": source_speaker,
            "original_label": original[0]["label"],
            "speaker_correction_id": speaker_correction["id"],
        },
        original[1],
    ]
    if with_text:
        expected[0].update(
            text=correction["after"],
            original_text=correction["before"],
            correction_id=correction["id"],
        )
    assert display == expected
    assert cues == original
    assert all(
        result is not source for result, source in zip(display, cues, strict=True)
    )
    assert review == {**ledger, "flags": []}
    assert review["source_sha256"] == source_fingerprint(original)
    assert review["source_sha256"] != source_fingerprint(display)
    assert apply_review(cues, path) == (display, review)
    with pytest.raises(ValueError, match="source changed"):
        apply_review(display, path)
    assert ledger == original_ledger
    assert json.loads(path.read_text(encoding="utf-8")) == original_ledger


@pytest.mark.parametrize("reverse", [False, True])
def test_speaker_targets_use_original_labels(
    tmp_path, cues, ledger, speaker_correction, reverse
):
    entries = [
        speaker_correction,
        {
            **speaker_correction,
            "id": "S002",
            "cue_id": 2,
            "before": cues[1]["speaker"],
            "after": cues[0]["speaker"],
        },
    ]
    ledger["speaker_corrections"] = entries[::-1] if reverse else entries
    original = copy.deepcopy(cues)

    display, review = apply_review(cues, save_ledger(tmp_path, ledger))

    assert cues == original
    assert [cue["speaker"] for cue in display] == [
        cues[1]["speaker"],
        cues[0]["speaker"],
    ]
    assert [cue["label"] for cue in display] == [cues[1]["label"], cues[0]["label"]]
    assert [cue["original_speaker"] for cue in display] == [
        cue["speaker"] for cue in cues
    ]
    assert [cue["original_label"] for cue in display] == [cue["label"] for cue in cues]
    assert review["speaker_corrections"] == ledger["speaker_corrections"]


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


@pytest.mark.parametrize("invalid", ["speaker", "flag"])
def test_speaker_and_flag_validation_preserves_inputs(
    tmp_path, cues, ledger, correction, speaker_correction, invalid
):
    ledger.update(corrections=[correction], speaker_corrections=[speaker_correction])
    if invalid == "speaker":
        speaker_correction["before"] = "UNKNOWN"
        error = ValueError
        message = "original speaker"
    else:
        ledger["flags"] = [
            {"id": "F001", "cue_id": 1, "reason": "需回聽。", "suggestion": None}
        ]
        error = TypeError
        message = "suggestion"
    original = copy.deepcopy(cues)
    original_ledger = copy.deepcopy(ledger)
    path = save_ledger(tmp_path, ledger)

    with pytest.raises(error, match=message):
        apply_review(cues, path)

    assert cues == original
    assert ledger == original_ledger
    assert json.loads(path.read_text(encoding="utf-8")) == original_ledger


@pytest.mark.parametrize("value", [[], None, "ledger", 7])
def test_ledger_must_be_an_object(tmp_path, cues, value):
    with pytest.raises(TypeError, match="JSON object"):
        apply_review(cues, save_ledger(tmp_path, value))


@pytest.mark.parametrize("field", ["corrections", "speaker_corrections", "flags"])
@pytest.mark.parametrize("value", [None, {}, "entries", False])
def test_entry_collections_must_be_lists(tmp_path, cues, ledger, field, value):
    ledger[field] = value

    with pytest.raises(TypeError, match="must be lists"):
        apply_review(cues, save_ledger(tmp_path, ledger))


@pytest.mark.parametrize("field", ["corrections", "speaker_corrections", "flags"])
@pytest.mark.parametrize("value", [None, [], "entry", 7])
def test_entries_must_be_objects(tmp_path, cues, ledger, field, value):
    ledger[field] = [value]

    with pytest.raises(TypeError, match="JSON object"):
        apply_review(cues, save_ledger(tmp_path, ledger))


@pytest.mark.parametrize("collection", ["corrections", "speaker_corrections"])
@pytest.mark.parametrize("field", ["id", "before", "after", "reason", "evidence"])
@pytest.mark.parametrize("value", [None, "", " \t", 7])
def test_correction_requires_nonempty_strings(
    tmp_path, cues, ledger, correction, speaker_correction, collection, field, value
):
    entry = correction if collection == "corrections" else speaker_correction
    entry[field] = value
    ledger[collection] = [entry]

    with pytest.raises(ValueError, match=field):
        apply_review(cues, save_ledger(tmp_path, ledger))


@pytest.mark.parametrize("collection", ["corrections", "speaker_corrections"])
@pytest.mark.parametrize("field", ["id", "before", "after", "reason", "evidence"])
def test_correction_requires_all_audit_fields(
    tmp_path, cues, ledger, correction, speaker_correction, collection, field
):
    entry = correction if collection == "corrections" else speaker_correction
    entry.pop(field)
    ledger[collection] = [entry]

    with pytest.raises(ValueError, match=field):
        apply_review(cues, save_ledger(tmp_path, ledger))


def test_correction_must_change_text(tmp_path, cues, ledger, correction):
    correction["after"] = correction["before"]
    ledger["corrections"] = [correction]

    with pytest.raises(ValueError, match="must change the text"):
        apply_review(cues, save_ledger(tmp_path, ledger))


@pytest.mark.parametrize("before", ["SPEAKER_01", "UNKNOWN", " SPEAKER_00"])
def test_speaker_correction_requires_exact_source_speaker(
    tmp_path, cues, ledger, speaker_correction, before
):
    ledger["speaker_corrections"] = [{**speaker_correction, "before": before}]

    with pytest.raises(ValueError, match="does not match the original speaker"):
        apply_review(cues, save_ledger(tmp_path, ledger))


@pytest.mark.parametrize(
    "after", ["UNKNOWN", "SPEAKER_99", "speaker_01", "SPEAKER_01 "]
)
def test_speaker_correction_requires_known_non_unknown_target(
    tmp_path, cues, ledger, speaker_correction, after
):
    ledger["speaker_corrections"] = [{**speaker_correction, "after": after}]

    with pytest.raises(ValueError, match="known non-UNKNOWN target speaker"):
        apply_review(cues, save_ledger(tmp_path, ledger))


@pytest.mark.parametrize("speaker", ["SPEAKER_00", "UNKNOWN"])
def test_speaker_correction_must_change_speaker(
    tmp_path, cues, ledger, speaker_correction, speaker
):
    cues[0]["speaker"] = speaker
    ledger.update(
        source_sha256=source_fingerprint(cues),
        speaker_corrections=[
            {**speaker_correction, "before": speaker, "after": speaker}
        ],
    )

    with pytest.raises(ValueError, match="must change the speaker"):
        apply_review(cues, save_ledger(tmp_path, ledger))


@pytest.mark.parametrize("field", ["corrections", "speaker_corrections", "flags"])
@pytest.mark.parametrize("cue_id", [99, "1", True, 1.0, None])
def test_entry_requires_known_integer_cue_id(
    tmp_path, cues, ledger, correction, speaker_correction, field, cue_id
):
    entry = speaker_correction if field == "speaker_corrections" else correction
    ledger[field] = [{**entry, "cue_id": cue_id}]

    with pytest.raises(ValueError, match="Unknown"):
        apply_review(cues, save_ledger(tmp_path, ledger))


@pytest.mark.parametrize("collection", ["corrections", "speaker_corrections"])
@pytest.mark.parametrize("duplicate", ["id", "cue_id"])
def test_duplicate_correction_ids_or_cues_are_rejected(
    tmp_path, cues, ledger, correction, speaker_correction, collection, duplicate
):
    entry = correction if collection == "corrections" else speaker_correction
    source_field = "text" if collection == "corrections" else "speaker"
    second = {
        **entry,
        "id": "SECOND",
        "cue_id": 2,
        "before": cues[1][source_field],
    }
    if collection == "speaker_corrections":
        second["after"] = cues[0]["speaker"]
    second[duplicate] = entry[duplicate]
    ledger[collection] = [entry, second]

    with pytest.raises(ValueError, match="must be unique"):
        apply_review(cues, save_ledger(tmp_path, ledger))


@pytest.mark.parametrize(
    ("first", "second"),
    [
        ("corrections", "speaker_corrections"),
        ("corrections", "flags"),
        ("speaker_corrections", "flags"),
        ("flags", "flags"),
    ],
)
def test_review_entry_ids_are_unique(
    tmp_path, cues, ledger, correction, speaker_correction, first, second
):
    entries = {
        "corrections": correction,
        "speaker_corrections": speaker_correction,
        "flags": {"id": "F001", "cue_id": 1, "reason": "需回聽。"},
    }
    for collection in (first, second):
        ledger.setdefault(collection, []).append(
            {**entries[collection], "id": "DUPLICATE"}
        )

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
    assert review["speaker_corrections"] == []


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
    assert review["speaker_corrections"] == []
    assert len(review["flags"]) == bool(reason_count)
    if reason_count:
        (flag,) = review["flags"]
        assert flag["cue_id"] == 1
        assert len(flag["reason"].splitlines()) == reason_count


@pytest.mark.parametrize("long_alignment", [False, True])
@pytest.mark.parametrize("supplied", [False, True])
def test_resolved_unknown_keeps_alignment_and_supplied_flags(
    tmp_path, cues, ledger, speaker_correction, long_alignment, supplied
):
    cues[0].update(
        speaker="UNKNOWN", label="說話者未確認", end=8 if long_alignment else 2
    )
    ledger.update(
        source_sha256=source_fingerprint(cues),
        speaker_corrections=[{**speaker_correction, "before": "UNKNOWN"}],
    )
    if supplied:
        ledger["flags"] = [
            {
                "id": "F001",
                "cue_id": 1,
                "reason": "說話者時間未與語音重疊，身分未確認。",
                "suggestion": "保留人工待查文字。",
            },
            {"id": "F002", "cue_id": 2, "reason": "另一段仍需確認。"},
        ]
    original = copy.deepcopy(cues)

    display, review = apply_review(cues, save_ledger(tmp_path, ledger))

    assert cues == original
    assert display[0]["speaker"] == cues[1]["speaker"]
    expected = copy.deepcopy(ledger["flags"])
    if long_alignment:
        alignment_flag = {
            "id": "T0001",
            "cue_id": 1,
            "reason": "單字對齊區間異常偏長，可能有時間對齊或漏字問題。",
        }
        if supplied:
            alignment_flag["reason"] += "\n" + expected[0]["reason"]
            alignment_flag["suggestion"] = expected[0]["suggestion"]
            expected[0] = alignment_flag
        else:
            expected = [alignment_flag]
    assert review["flags"] == expected


def test_old_ledger_keeps_unresolved_speaker_and_supplied_flags(
    tmp_path, cues, ledger, correction
):
    cues[0].update(speaker="UNKNOWN", label="說話者未確認")
    ledger.update(
        source_sha256=source_fingerprint(cues),
        corrections=[correction],
        flags=[{"id": "F001", "cue_id": 1, "reason": "人工標記需回聽。"}],
    )

    display, review = apply_review(cues, save_ledger(tmp_path, ledger))

    assert "speaker_corrections" not in ledger
    assert review["speaker_corrections"] == []
    assert display[0] == {
        **cues[0],
        "text": correction["after"],
        "original_text": correction["before"],
        "correction_id": correction["id"],
    }
    assert review["flags"] == [
        {
            "id": "T0001",
            "cue_id": 1,
            "reason": "說話者時間未與語音重疊，身分未確認。\n人工標記需回聽。",
        }
    ]


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
