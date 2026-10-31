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
    original = copy.deepcopy(source_cues)

    replayed, review = apply_review(source_cues, DATA / "corrections.json")

    assert source_cues == original
    assert replayed == artifact["cues"]
    assert review == artifact["review"]
    for source, display in zip(source_cues, replayed, strict=True):
        assert all(
            source[key] == display[key] for key in ("id", "start", "end", "speaker")
        )
    assert "".join(cue["text"] for cue in source_cues[1:3]) == "".join(
        cue["text"] for cue in replayed[1:3]
    ).translate(REMOVE_PUNCTUATION)
    assert not any(flag["cue_id"] == 2 for flag in review["flags"])
    validation = json.loads((DATA / "validation.json").read_text(encoding="utf-8"))
    assert validation["corrected_cues"] == len(review["corrections"])
    assert validation["pending_review_cues"] == len(review["flags"])


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


def test_published_page_cues_match_reviewed_transcript(artifact):
    page = (DATA / "index.html").read_text(encoding="utf-8")
    match = re.search(
        r'<script type="application/json" id="debate-data">(.*?)</script>',
        page,
        re.DOTALL,
    )

    assert match is not None
    assert json.loads(match[1])["cues"] == artifact["cues"]
