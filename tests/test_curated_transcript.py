import copy
import json
import re
from pathlib import Path

import pytest

from transcripts.review import apply_review

DATA = Path(__file__).resolve().parents[1] / "data"


@pytest.fixture
def artifact():
    return json.loads((DATA / "transcript.json").read_text(encoding="utf-8"))


def test_host_name_stays_with_tvbs_speaker(artifact):
    cues = {cue["id"]: cue for cue in artifact["cues"]}

    assert cues[2]["speaker"] == "SPEAKER_05"
    assert cues[2]["text"].endswith("我是TVBS黃欣樺")
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
    )
    assert not any(flag["cue_id"] == 2 for flag in review["flags"])
    validation = json.loads((DATA / "validation.json").read_text(encoding="utf-8"))
    assert validation["corrected_cues"] == len(review["corrections"])
    assert validation["pending_review_cues"] == len(review["flags"])


def test_published_page_cues_match_reviewed_transcript(artifact):
    page = (DATA / "index.html").read_text(encoding="utf-8")
    match = re.search(
        r'<script type="application/json" id="debate-data">(.*?)</script>',
        page,
        re.DOTALL,
    )

    assert match is not None
    assert json.loads(match[1])["cues"] == artifact["cues"]
