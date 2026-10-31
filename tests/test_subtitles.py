import json

import pytest

from transcripts import subtitles


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (0, "00:00:00,000"),
        (1.2344, "00:00:01,234"),
        (1.2346, "00:00:01,235"),
        (59.9996, "00:01:00,000"),
        (3599.9996, "01:00:00,000"),
        (360000, "100:00:00,000"),
    ],
)
def test_timestamp_rounding(seconds, expected):
    assert subtitles.timestamp(seconds) == expected
    assert subtitles.timestamp(seconds, ".") == expected.replace(",", ".")


@pytest.mark.parametrize(
    "seconds", [-1, -0.0001, float("nan"), float("inf"), -float("inf")]
)
def test_timestamp_rejects_invalid_values(seconds):
    with pytest.raises(ValueError, match="finite and non-negative"):
        subtitles.timestamp(seconds)


def aligned_result(words):
    return {
        "metadata": {"duration": 20.0},
        "segments": [{"text": "".join(word["word"] for word in words), "words": words}],
    }


def word(text, start, end, speaker="SPEAKER_00"):
    return {"word": text, "start": start, "end": end, "speaker": speaker}


def test_cues_preserve_unaligned_characters_and_punctuation():
    result = aligned_result(
        [
            {"word": "「"},
            word("你好", 0.1, 0.5),
            {"word": "，"},
            word("世界", 0.5, 0.8),
            {"word": "！」"},
        ]
    )

    cues = subtitles.make_cues(result)

    assert len(cues) == 1
    assert cues[0]["text"] == "「你好，世界！」"
    assert cues[0]["timing"] == "partly_aligned"
    assert (cues[0]["start"], cues[0]["end"]) == (0.1, 0.8)


def test_unaligned_punctuation_after_sentence_end_is_preserved():
    cues = subtitles.make_cues(
        aligned_result(
            [
                word("你好！", 0.1, 0.5),
                {"word": "」"},
            ]
        )
    )

    assert len(cues) == 1
    assert cues[0]["text"] == "你好！」"
    assert cues[0]["timing"] == "partly_aligned"


def test_speaker_change_splits_cues_without_losing_text():
    cues = subtitles.make_cues(
        aligned_result(
            [
                word("第一", 0, 1, "SPEAKER_00"),
                word("第二", 1, 2, "SPEAKER_01"),
                word("第三", 2, 3, "SPEAKER_00"),
            ]
        )
    )

    assert [cue["text"] for cue in cues] == ["第一", "第二", "第三"]
    assert [cue["speaker"] for cue in cues] == [
        "SPEAKER_00",
        "SPEAKER_01",
        "SPEAKER_00",
    ]
    assert [cue["id"] for cue in cues] == [1, 2, 3]


@pytest.mark.parametrize(
    ("words", "expected"),
    [
        ([word("甲", 0, 3), word("乙", 3, 6), word("丙", 6, 6.1)], ["甲乙", "丙"]),
        (
            [word("甲" * 16, 0, 1), word("乙" * 16, 1, 2), word("丙", 2, 3)],
            ["甲" * 16 + "乙" * 16, "丙"],
        ),
        ([word("甲", 0, 1), word("乙", 1.81, 2)], ["甲", "乙"]),
    ],
    ids=["six-second-limit", "32-character-limit", "silence-gap"],
)
def test_cue_grouping_limits(words, expected):
    cues = subtitles.make_cues(aligned_result(words))

    assert [cue["text"] for cue in cues] == expected
    assert all(cue["end"] - cue["start"] <= 6 for cue in cues)
    assert all(len(cue["text"]) <= 32 for cue in cues)


def test_segment_fallback_preserves_and_converts_text(transcript):
    segment = transcript["segments"][0]
    segment.pop("words")
    segment["text"] = "  软件开发，台湾。  "

    (cue,) = subtitles.make_cues(transcript)

    assert cue["text"] == "軟件開發，臺灣。"
    assert cue["timing"] == "segment"
    assert (cue["start"], cue["end"]) == (1.0, 2.0)
    assert segment["text"] == "  软件开发，台湾。  "


@pytest.mark.parametrize(
    ("speaker", "label"),
    [("UNKNOWN", "說話者未確認"), ("SPEAKER_07", "SPEAKER_07（角色未確認）")],
)
def test_unknown_speaker_labels(speaker, label):
    timed_word = word("你好", 0, 1, speaker)
    if speaker == "UNKNOWN":
        timed_word.pop("speaker")

    (cue,) = subtitles.make_cues(aligned_result([timed_word]))

    assert cue["speaker"] == speaker
    assert cue["label"] == label


@pytest.mark.parametrize(
    ("role", "name", "label"),
    [
        ("辯論者1", "沈伯洋", "沈伯洋"),
        ("辯論者2", "蔣萬安", "蔣萬安"),
        ("辯論者1", "", "辯論者1"),
        ("辯論者2", "", "辯論者2"),
        ("主持人1", "TVBS", "主持人1／TVBS"),
        ("提問記者2", "三立", "提問記者2／三立"),
    ],
)
def test_speaker_labels_without_organization(role, name, label):
    roles = {"SPEAKER_00": {"role": role, "name": name}}

    assert subtitles.speaker_label("SPEAKER_00", roles) == label


@pytest.mark.parametrize(
    ("role", "name", "organization", "label"),
    [
        ("主持人1", "黃欣樺", "TVBS", "黃欣樺／TVBS"),
        ("主持人2", "李文儀", "三立", "李文儀／三立"),
        ("提問記者1", "樊啟明", "TVBS", "樊啟明／TVBS"),
        ("提問記者2", "黃燕怡", "三立", "黃燕怡／三立"),
        ("主持人1", "", "TVBS", "主持人1／TVBS"),
    ],
)
def test_speaker_labels_with_organization(role, name, organization, label):
    roles = {"SPEAKER_00": {"role": role, "name": name, "organization": organization}}

    (cue,) = subtitles.make_cues(aligned_result([word("你好", 0, 1)]), roles)

    assert cue["label"] == label


def test_export_formats_and_evidence(tmp_path, transcript, roles):
    output = tmp_path / "exports"

    summary = subtitles.export(transcript, output, roles)

    assert (output / "subtitles.srt").read_text(encoding="utf-8") == (
        "1\n00:00:01,000 --> 00:00:02,000\n【主持人／王小明】這是<測試>&。\n"
    )
    assert (output / "subtitles.vtt").read_text(encoding="utf-8") == (
        "WEBVTT\n\n1\n00:00:01.000 --> 00:00:02.000\n"
        "【主持人／王小明】這是&lt;測試&gt;&amp;。\n"
    )
    markdown = (output / "transcript.md").read_text(encoding="utf-8")
    assert "- Source: `debate.wav`" in markdown
    assert "- Duration: 00:00:04.000" in markdown
    assert "- Processing stage: `diarize`" in markdown
    assert "[00:00:01.000–00:00:02.000] **主持人／王小明** 這是<測試>&。" in markdown
    artifact = json.loads((output / "transcript.json").read_text(encoding="utf-8"))
    assert artifact["metadata"] == {**transcript["metadata"], "source": "debate.wav"}
    assert artifact["display_language"] == "zh-Hant-TW"
    assert artifact["segments"][0]["text"] == "這是<測試>&。"
    assert artifact["segments"][0]["words"][0]["word"] == "這是<測試>&。"
    assert transcript["segments"][0]["text"] == "这是<测试>&。"
    assert transcript["segments"][0]["words"][0]["word"] == "这是<测试>&。"
    assert artifact["speaker_turns"] == transcript["speaker_turns"]
    assert artifact["roles"] == roles
    assert artifact["cues"][0]["text"] == "這是<測試>&。"
    assert artifact["cues"][0]["label"] == "主持人／王小明"
    assert summary == {
        "duration_seconds": 4.0,
        "stage": "diarize",
        "cue_count": 1,
        "first_cue_start": 1.0,
        "last_cue_end": 2.0,
        "speaker_clusters": ["SPEAKER_00"],
        "unassigned_cues": 0,
        "unconfirmed_role_cues": 0,
        "segment_timing_cues": 0,
        "corrected_cues": 0,
        "pending_review_cues": 0,
    }
    assert (
        json.loads((output / "validation.json").read_text(encoding="utf-8")) == summary
    )


def test_export_without_roles_keeps_speaker_unconfirmed(tmp_path, transcript):
    summary = subtitles.export(transcript, tmp_path)
    artifact = json.loads((tmp_path / "transcript.json").read_text(encoding="utf-8"))

    assert artifact["roles"] == {}
    assert artifact["cues"][0]["label"] == "SPEAKER_00（角色未確認）"
    assert summary["unconfirmed_role_cues"] == 1


def test_roles_accept_organization(roles):
    roles["SPEAKER_00"]["organization"] = "TVBS"

    subtitles.validate_roles(roles, {"SPEAKER_00"})

    assert subtitles.speaker_label("SPEAKER_00", roles) == "王小明／TVBS"


def test_roles_accept_evidence_and_optional_name(roles):
    subtitles.validate_roles(roles, {"SPEAKER_00"})
    roles["SPEAKER_00"].pop("name")
    subtitles.validate_roles(roles, {"SPEAKER_00"})
    assert subtitles.speaker_label("SPEAKER_00", roles) == "主持人"


@pytest.mark.parametrize("role_map", [[], "主持人", None, {"SPEAKER_99": {}}])
def test_roles_reject_non_objects_and_unknown_speakers(role_map):
    with pytest.raises((TypeError, ValueError)):
        subtitles.validate_roles(role_map, {"SPEAKER_00"})


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("role", None),
        ("role", ""),
        ("role", 1),
        ("name", 1),
        ("organization", 1),
        ("organization", None),
        ("evidence", None),
        ("evidence", []),
        ("evidence", "an unsupported claim"),
        ("evidence", [{}]),
        ("evidence", ["claim"]),
        ("evidence", [{"start": -1, "text": "claim"}]),
        ("evidence", [{"start": float("nan"), "text": "claim"}]),
        ("evidence", [{"start": float("inf"), "text": "claim"}]),
        ("evidence", [{"start": "1", "text": "claim"}]),
        ("evidence", [{"start": 1, "text": "  "}]),
        ("evidence", [{"start": 1, "text": 123}]),
    ],
)
def test_roles_reject_invalid_fields_and_evidence(roles, field, value):
    roles["SPEAKER_00"][field] = value

    with pytest.raises((TypeError, ValueError)):
        subtitles.validate_roles(roles, {"SPEAKER_00"})


@pytest.mark.parametrize("role_map", [[], "", False, 0])
def test_export_rejects_empty_non_object_roles(tmp_path, transcript, role_map):
    with pytest.raises(TypeError, match="JSON object"):
        subtitles.export(transcript, tmp_path, role_map)


def test_untimed_prefix_is_marked_as_estimated():
    (cue,) = subtitles.make_cues(
        aligned_result(
            [
                {"word": "「"},
                word("你好", 0.1, 0.5),
            ]
        )
    )
    assert cue["text"] == "「你好"
    assert cue["timing"] == "partly_aligned"


def test_equal_start_times_keep_source_order():
    cues = subtitles.make_cues(
        aligned_result(
            [
                word("先", 0, 2, "SPEAKER_00"),
                word("後", 0, 1, "SPEAKER_01"),
            ]
        )
    )
    assert [cue["text"] for cue in cues] == ["先", "後"]


@pytest.mark.parametrize("start,end", [(-1, 1), (2, 1), (0, float("nan")), (0, 30)])
def test_segment_fallback_rejects_invalid_times(transcript, start, end):
    segment = transcript["segments"][0]
    segment.pop("words")
    segment.update(start=start, end=end)
    with pytest.raises(ValueError, match="Invalid segment time"):
        subtitles.make_cues(transcript)


def test_export_rejects_unsupported_role_before_writing(tmp_path, transcript):
    output = tmp_path / "exports"
    with pytest.raises(ValueError, match="Unknown speaker"):
        subtitles.export(transcript, output, {"SPEAKER_99": {}})
    assert not output.exists()
