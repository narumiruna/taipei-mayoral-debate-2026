import copy
import html
import json
import re
from pathlib import Path

import pytest

from transcripts.review import apply_review
from transcripts.subtitles import timestamp

DATA = Path(__file__).resolve().parents[1] / "data"
PUNCTUATION = frozenset("，。？！；：、（）「」『』—…")
REMOVE_PUNCTUATION = str.maketrans("", "", "".join(PUNCTUATION))


@pytest.fixture
def artifact():
    return json.loads((DATA / "transcript.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    ("speaker", "label"),
    [
        ("SPEAKER_03", "沈伯洋"),
        ("SPEAKER_04", "蔣萬安"),
        ("SPEAKER_05", "黃欣樺／TVBS"),
        ("SPEAKER_00", "李文儀／三立"),
        ("SPEAKER_02", "樊啟明／TVBS"),
        ("SPEAKER_01", "黃燕怡／三立"),
    ],
)
def test_speaker_display_labels(artifact, speaker, label):
    cues = [cue for cue in artifact["cues"] if cue["speaker"] == speaker]

    assert cues
    assert all(cue["label"] == label for cue in cues)


def test_curated_roles_match_role_map(artifact):
    roles = json.loads((DATA / "speaker-roles.json").read_text(encoding="utf-8"))

    assert artifact["roles"] == roles


def test_host_name_stays_with_tvbs_speaker(artifact):
    cues = {cue["id"]: cue for cue in artifact["cues"]}

    assert cues[2]["speaker"] == "SPEAKER_05"
    assert cues[2]["text"].endswith("我是TVBS黃欣樺。")
    assert cues[3]["speaker"] == "SPEAKER_00"
    assert cues[3]["text"].startswith("我是三立電視李文儀")
    assert cues[2]["original_text"].endswith("我是TVBS黃欣")
    assert cues[3]["original_text"].startswith("樺我是三立電視李文儀")


@pytest.mark.parametrize("name", ["subtitles.srt", "subtitles.vtt", "transcript.md"])
def test_text_exports_keep_complete_host_name(name):
    text = (DATA / name).read_text(encoding="utf-8")

    assert "我是TVBS黃欣樺" in text
    assert "樺我是三立電視李文儀" not in text


def test_curated_ledger_replays_without_changing_source_cues(artifact):
    source_cues = copy.deepcopy(artifact["cues"])
    for cue in source_cues:
        cue["text"] = cue.pop("original_text", cue["text"])
        cue.pop("correction_id", None)
        cue["speaker"] = cue.pop("original_speaker", cue["speaker"])
        cue["label"] = cue.pop("original_label", cue["label"])
        cue.pop("speaker_correction_id", None)
    original = copy.deepcopy(source_cues)

    replayed, review = apply_review(source_cues, DATA / "corrections.json")

    assert source_cues == original
    assert replayed == artifact["cues"]
    assert review == artifact["review"]
    speaker_edits = {entry["cue_id"]: entry for entry in review["speaker_corrections"]}
    for source, display in zip(source_cues, replayed, strict=True):
        assert all(source[key] == display[key] for key in ("id", "start", "end"))
        if source["id"] in speaker_edits:
            entry = speaker_edits[source["id"]]
            assert source["speaker"] == display["original_speaker"] == entry["before"]
            assert display["speaker"] == entry["after"]
        else:
            assert source["speaker"] == display["speaker"]
    assert "".join(cue["text"] for cue in source_cues[1:3]) == "".join(
        cue["text"] for cue in replayed[1:3]
    ).translate(REMOVE_PUNCTUATION)
    assert not any(flag["cue_id"] == 2 for flag in review["flags"])
    validation = json.loads((DATA / "validation.json").read_text(encoding="utf-8"))
    assert validation["corrected_cues"] == len(review["corrections"])
    assert validation["speaker_corrected_cues"] == len(review["speaker_corrections"])
    assert validation["pending_review_cues"] == len(review["flags"])


@pytest.mark.parametrize(
    ("cue_id", "speaker"),
    [
        (76, "SPEAKER_03"),
        (153, "SPEAKER_04"),
        (219, "SPEAKER_00"),
        (271, "SPEAKER_03"),
        (362, "SPEAKER_03"),
        (414, "SPEAKER_05"),
        (420, "SPEAKER_03"),
        (569, "SPEAKER_04"),
        (646, "SPEAKER_03"),
        (760, "SPEAKER_02"),
        (934, "SPEAKER_04"),
        (984, "SPEAKER_04"),
        (1017, "SPEAKER_03"),
        (1021, "SPEAKER_03"),
        (1026, "SPEAKER_03"),
        (1042, "SPEAKER_03"),
        (1047, "SPEAKER_03"),
    ],
)
def test_sentence_endings_keep_the_previous_speaker(artifact, cue_id, speaker):
    cues = {cue["id"]: cue for cue in artifact["cues"]}
    cue, previous = cues[cue_id], cues[cue_id - 1]
    edits = {
        entry["cue_id"]: entry for entry in artifact["review"]["speaker_corrections"]
    }

    assert cue["speaker"] == previous["speaker"] == speaker
    assert cue["start"] == previous["end"]
    assert cue["original_speaker"] == "UNKNOWN"
    assert cue["original_label"] == "說話者未確認"
    assert cue["speaker_correction_id"] == edits[cue_id]["id"]
    assert edits[cue_id]["reason"] and edits[cue_id]["evidence"]
    assert cue_id not in {flag["cue_id"] for flag in artifact["review"]["flags"]}


def test_closing_host_boundary_remains_unconfirmed(artifact):
    cues = {cue["id"]: cue for cue in artifact["cues"]}
    unknown = [cue["id"] for cue in artifact["cues"] if cue["speaker"] == "UNKNOWN"]

    assert unknown == [1076]
    assert cues[1076]["text"] == "句"
    assert cues[1075]["speaker"] != cues[1077]["speaker"]
    assert "speaker_correction_id" not in cues[1076]
    (flag,) = [flag for flag in artifact["review"]["flags"] if flag["cue_id"] == 1076]
    assert "交接" in flag["reason"]
    assert "重疊" in flag["reason"]


def test_punctuation_preserves_every_existing_character(artifact):
    ledger = json.loads((DATA / "corrections.json").read_text(encoding="utf-8"))
    reviewed = ledger["punctuation_review"]
    entries = [
        entry for entry in ledger["corrections"] if "punctuation_before" in entry
    ]
    cues = {cue["id"]: cue for cue in artifact["cues"]}

    assert reviewed["reviewed_cues"] == len(cues)
    assert reviewed["changed_cues"] == len(entries) > 0
    for entry in entries:
        before, after = entry["punctuation_before"], entry["after"]
        assert after == cues[entry["cue_id"]]["text"]
        assert before != after
        position = 0
        for character in after:
            if position < len(before) and character == before[position]:
                position += 1
            else:
                assert character in PUNCTUATION, entry["cue_id"]
        assert position == len(before), entry["cue_id"]


@pytest.mark.parametrize(
    ("first", "ending", "second", "beginning"),
    [
        (1, "20", 2, "26"),
        (4, "辯", 5, "論"),
        (9, "候選", 10, "人"),
        (23, "同", 24, "時"),
        (34, "第一階", 35, "段"),
        (37, "朋友", 38, "們"),
    ],
)
def test_punctuation_does_not_split_words(artifact, first, ending, second, beginning):
    cues = {cue["id"]: cue for cue in artifact["cues"]}

    assert cues[first]["text"].endswith(ending)
    assert cues[second]["text"].startswith(beginning)


@pytest.mark.parametrize("name", ["subtitles.srt", "subtitles.vtt", "transcript.md"])
def test_all_text_exports_match_reviewed_cues(artifact, name):
    text = (DATA / name).read_text(encoding="utf-8")
    if name == "transcript.md":
        actual = [line for line in text.splitlines() if line.startswith("[")]
        expected = [
            f"[{timestamp(cue['start'], '.')}–{timestamp(cue['end'], '.')}] "
            f"**{cue['label']}** {cue['text']}"
            for cue in artifact["cues"]
        ]
    else:
        separator = "," if name.endswith("srt") else "."
        blocks = text.strip().split("\n\n")
        if name.endswith("vtt"):
            assert blocks.pop(0) == "WEBVTT"
        actual = [html.unescape(block) for block in blocks]
        expected = [
            f"{cue['id']}\n"
            f"{timestamp(cue['start'], separator)} --> "
            f"{timestamp(cue['end'], separator)}\n"
            f"【{cue['label']}】{cue['text']}"
            for cue in artifact["cues"]
        ]
    assert actual == expected


def test_built_page_cues_match_reviewed_transcript(artifact, curated_site):
    page = curated_site.read_text(encoding="utf-8")
    match = re.search(
        r'<script type="application/json" id="debate-data">(.*?)</script>',
        page,
        re.DOTALL,
    )

    assert match is not None
    assert json.loads(match[1])["cues"] == artifact["cues"]
