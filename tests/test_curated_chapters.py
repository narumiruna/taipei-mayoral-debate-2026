import copy
import json
import math
import re
from itertools import groupby, pairwise
from pathlib import Path

import pytest

from transcripts.chapters import validate_chapters

DATA = Path(__file__).resolve().parents[1] / "data"
SOURCE_SHA256 = "bcc1e56e8d98ed44e2c48d219314380627d9b3e02a76f3f6433645328899aae2"
EXPECTED_TREE = (
    ("introduction", "開場與規則", 1, 34),
    (
        "opening-statements",
        "申論",
        (
            ("shen-opening", "沈伯洋申論", 37, 120),
            ("chiang-opening", "蔣萬安申論", 123, 208),
        ),
    ),
    (
        "cross-examination",
        "交叉詰問",
        (
            (
                "cross-round-1",
                "第一輪",
                (
                    ("cross-round-1-chiang-asks", "蔣問沈答", 220, 281),
                    ("cross-round-1-shen-asks", "沈問蔣答", 284, 346),
                ),
            ),
            (
                "cross-round-2",
                "第二輪",
                (
                    ("cross-round-2-chiang-asks", "蔣問沈答", 349, 411),
                    ("cross-round-2-shen-asks", "沈問蔣答", 415, 478),
                ),
            ),
            (
                "cross-round-3",
                "第三輪",
                (
                    ("cross-round-3-chiang-asks", "蔣問沈答", 484, 544),
                    ("cross-round-3-shen-asks", "沈問蔣答", 547, 610),
                ),
            ),
            (
                "cross-round-4",
                "第四輪",
                (
                    ("cross-round-4-chiang-asks", "蔣問沈答", 613, 675),
                    ("cross-round-4-shen-asks", "沈問蔣答", 678, 738),
                ),
            ),
        ),
    ),
    (
        "media-questions",
        "媒體提問",
        (
            (
                "fan-qiming",
                "樊啟明・TVBS／四年後市民生活",
                (
                    ("fan-question", "記者提問", 747, 764),
                    ("fan-chiang-answer", "蔣萬安回答", 766, 799),
                    ("fan-shen-answer", "沈伯洋回答", 801, 832),
                ),
            ),
            (
                "huang-yanyi",
                "黃燕怡・三立／都更與居住韌性",
                (
                    ("huang-question", "記者提問", 835, 851),
                    ("huang-shen-answer", "沈伯洋回答", 853, 885),
                    ("huang-chiang-answer", "蔣萬安回答", 887, 917),
                ),
            ),
        ),
    ),
    (
        "closing-statements",
        "結論",
        (
            ("chiang-closing", "蔣萬安結論", 924, 990),
            ("shen-closing", "沈伯洋結論", 993, 1066),
        ),
    ),
    ("final-host", "閉幕", 1068, 1082),
)
# Exact source times, not rounded discovery anchors from the plan.
EXPECTED_INTERVALS = (
    (854.632, 1039.612),
    (1050.078, 1531.015),
    (1538.137, 2018.790),
    (2390.712, 2731.962),
    (2740.531, 3086.269),
    (3096.644, 3439.641),
    (3447.712, 3792.127),
    (4135.452, 4476.299),
    (4484.512, 4827.010),
    (4836.298, 5178.810),
    (5185.769, 5529.083),
    (5828.757, 5923.719),
    (5930.041, 6112.422),
    (6116.999, 6295.793),
    (6308.699, 6403.291),
    (6408.667, 6589.775),
    (6594.241, 6772.728),
    (7064.075, 7425.957),
    (7433.333, 7794.477),
    (7963.917, 8026.155),
)


@pytest.fixture
def artifact():
    return json.loads((DATA / "transcript.json").read_text(encoding="utf-8"))


@pytest.fixture
def chapters():
    return json.loads((DATA / "chapters.json").read_text(encoding="utf-8"))


def walk(nodes):
    for node in nodes:
        yield node
        yield from walk(node.get("children", []))


def leaves(nodes):
    return [node for node in walk(nodes) if "children" not in node]


def tree(nodes):
    return tuple(
        (node["id"], node["title"], tree(node["children"]))
        if "children" in node
        else (node["id"], node["title"], node["start_cue_id"], node["end_cue_id"])
        for node in nodes
    )


def test_normalized_chapters_keep_anchors_and_derive_group_ranges(artifact, chapters):
    original_artifact, original_chapters = (
        copy.deepcopy(artifact),
        copy.deepcopy(chapters),
    )

    resolved = validate_chapters(chapters, artifact)

    assert artifact == original_artifact
    assert chapters == original_chapters
    assert set(resolved) == {"source_sha256", "items"}
    assert resolved["source_sha256"] == SOURCE_SHA256
    assert tree(resolved["items"]) == EXPECTED_TREE
    assert tuple(
        (leaf["start"], leaf["end"]) for leaf in leaves(resolved["items"])
    ) == (EXPECTED_INTERVALS)
    cues = {cue["id"]: cue for cue in artifact["cues"]}
    for node in walk(resolved["items"]):
        fields = {"id", "title", "start_cue_id", "end_cue_id", "start", "end"}
        if "children" in node:
            fields.add("children")
            descendants = leaves(node["children"])
            assert node["start_cue_id"] == descendants[0]["start_cue_id"]
            assert node["end_cue_id"] == descendants[-1]["end_cue_id"]
        assert set(node) == fields
        assert node["start"] == cues[node["start_cue_id"]]["start"]
        assert node["end"] == cues[node["end_cue_id"]]["end"]


def test_normalized_leaf_intervals_are_half_open_and_leave_breaks_inactive(
    artifact, chapters
):
    resolved_leaves = leaves(validate_chapters(chapters, artifact)["items"])

    def active(time):
        return [
            leaf["id"]
            for leaf in resolved_leaves
            if leaf["start"] <= time < leaf["end"]
        ]

    assert active(0) == []
    for leaf in resolved_leaves:
        assert active(leaf["start"] - 0.001) == []
        assert active(leaf["start"]) == [leaf["id"]]
        assert active(leaf["end"] - 0.001) == [leaf["id"]]
        assert active(leaf["end"]) == []
        assert active(leaf["end"] + 0.001) == []
    for left, right in pairwise(resolved_leaves):
        assert active((left["end"] + right["start"]) / 2) == []


def test_exact_hierarchy_titles_order_and_cue_references(chapters):
    assert tree(chapters["items"]) == EXPECTED_TREE
    assert len(chapters["items"]) == 6
    assert len(leaves(chapters["items"])) == 20
    assert sum("children" in node for node in walk(chapters["items"])) == 10


def test_source_hash_and_metadata_schema(artifact, chapters):
    assert set(chapters) == {"source_sha256", "items"}
    assert chapters["source_sha256"] == artifact["review"]["source_sha256"]
    assert chapters["source_sha256"] == SOURCE_SHA256
    nodes = list(walk(chapters["items"]))
    assert len({node["id"] for node in nodes}) == len(nodes)
    for node in nodes:
        assert re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", node["id"])
        assert isinstance(node["title"], str) and node["title"].strip()
        if "children" in node:
            assert set(node) == {"id", "title", "children"}
            assert node["children"]
        else:
            assert set(node) == {"id", "title", "start_cue_id", "end_cue_id"}
            assert type(node["start_cue_id"]) is int
            assert type(node["end_cue_id"]) is int


def test_exact_intervals_chronology_and_nonoverlap(artifact, chapters):
    cues = {cue["id"]: cue for cue in artifact["cues"]}
    intervals = []
    for leaf in leaves(chapters["items"]):
        first, last = cues[leaf["start_cue_id"]], cues[leaf["end_cue_id"]]
        assert first["id"] <= last["id"]
        assert math.isfinite(first["start"]) and math.isfinite(last["end"])
        assert first["start"] < last["end"]
        intervals.append((first["start"], last["end"]))
    assert tuple(intervals) == EXPECTED_INTERVALS
    assert all(left[1] <= right[0] for left, right in pairwise(intervals))


@pytest.mark.parametrize(
    ("start_id", "end_id", "speaker"),
    [
        (37, 120, "SPEAKER_03"),
        (123, 208, "SPEAKER_04"),
        (747, 764, "SPEAKER_02"),
        (766, 799, "SPEAKER_04"),
        (801, 832, "SPEAKER_03"),
        (835, 851, "SPEAKER_01"),
        (853, 885, "SPEAKER_03"),
        (887, 917, "SPEAKER_04"),
        (924, 990, "SPEAKER_04"),
        (993, 1066, "SPEAKER_03"),
    ],
)
def test_speech_starts_at_first_speaker_cue_and_stops_before_handover(
    artifact, chapters, start_id, end_id, speaker
):
    cues = {cue["id"]: cue for cue in artifact["cues"]}
    assert any(
        (leaf["start_cue_id"], leaf["end_cue_id"]) == (start_id, end_id)
        for leaf in leaves(chapters["items"])
    )
    assert all(
        cues[cue_id]["speaker"] == speaker for cue_id in range(start_id, end_id + 1)
    )
    assert cues[start_id - 1]["speaker"] in {"SPEAKER_00", "SPEAKER_05"}
    assert cues[end_id + 1]["speaker"] in {"SPEAKER_00", "SPEAKER_05"}


@pytest.mark.parametrize("round_index", range(4))
def test_each_cross_direction_keeps_question_answer_followup_and_final_answer(
    artifact, chapters, round_index
):
    rounds = chapters["items"][2]["children"]
    for direction, leaf in enumerate(rounds[round_index]["children"]):
        questioner, answerer, host = (
            ("SPEAKER_04", "SPEAKER_03", "SPEAKER_00")
            if direction == 0
            else ("SPEAKER_03", "SPEAKER_04", "SPEAKER_05")
        )
        selected = [
            cue
            for cue in artifact["cues"]
            if leaf["start_cue_id"] <= cue["id"] <= leaf["end_cue_id"]
        ]
        assert [
            speaker for speaker, _ in groupby(selected, lambda cue: cue["speaker"])
        ] == [
            questioner,
            host,
            answerer,
            host,
            questioner,
            host,
            answerer,
        ]
        assert all(
            "休息" not in cue["text"] and "廣告" not in cue["text"] for cue in selected
        )
        cues = {cue["id"]: cue for cue in artifact["cues"]}
        assert cues[selected[0]["id"] - 1]["speaker"] in {"SPEAKER_00", "SPEAKER_05"}
        assert cues[selected[-1]["id"] + 1]["speaker"] in {"SPEAKER_00", "SPEAKER_05"}


def test_reporter_names_organizations_and_neutral_question_summaries(
    artifact, chapters
):
    fan, huang = chapters["items"][3]["children"]
    roles = artifact["roles"]
    assert (roles["SPEAKER_02"]["name"], roles["SPEAKER_02"]["organization"]) == (
        "樊啟明",
        "TVBS",
    )
    assert (roles["SPEAKER_01"]["name"], roles["SPEAKER_01"]["organization"]) == (
        "黃燕怡",
        "三立",
    )
    assert fan["title"] == "樊啟明・TVBS／四年後市民生活"
    assert huang["title"] == "黃燕怡・三立／都更與居住韌性"
    cues = {cue["id"]: cue for cue in artifact["cues"]}
    assert "TVBS新聞部副理樊啟明" in cues[747]["text"]
    assert "三立新聞網資深總監黃燕怡" in cues[833]["text"]
    assert "四年之後" in cues[754]["text"]
    assert "首都居住韌性的願景" in cues[851]["text"]


@pytest.mark.parametrize(
    ("before_id", "after_id"),
    [(211, 212), (480, 481), (740, 741), (919, 920), (1067, 1068)],
)
def test_advertisement_gaps_have_no_leaf(artifact, chapters, before_id, after_id):
    cues = {cue["id"]: cue for cue in artifact["cues"]}
    gap_start, gap_end = cues[before_id]["end"], cues[after_id]["start"]
    assert gap_end - gap_start > 160
    for leaf in leaves(chapters["items"]):
        start, end = (
            cues[leaf["start_cue_id"]]["start"],
            cues[leaf["end_cue_id"]]["end"],
        )
        assert end <= gap_start or start >= gap_end


def test_only_internal_host_prompts_and_introduction_or_closure_are_selected(
    artifact, chapters
):
    selected = {
        cue_id
        for leaf in leaves(chapters["items"])
        for cue_id in range(leaf["start_cue_id"], leaf["end_cue_id"] + 1)
    }
    excluded_ranges = (
        (35, 36),
        (121, 122),
        (209, 219),
        (282, 283),
        (347, 348),
        (412, 414),
        (479, 483),
        (545, 546),
        (611, 612),
        (676, 677),
        (739, 746),
        (765, 765),
        (800, 800),
        (833, 834),
        (852, 852),
        (886, 886),
        (918, 923),
        (991, 992),
        (1067, 1067),
    )
    excluded = {
        cue_id for first, last in excluded_ranges for cue_id in range(first, last + 1)
    }
    assert {cue["id"] for cue in artifact["cues"]} - selected == excluded
    assert all(
        cue["speaker"] in {"SPEAKER_00", "SPEAKER_05"}
        for cue in artifact["cues"]
        if cue["id"] in excluded
    )


def test_mixed_boundary_cues_are_not_split_or_extended_through_handovers(
    artifact, chapters
):
    cues = {cue["id"]: cue for cue in artifact["cues"]}
    # These host cues contain a trailing word from the previous candidate.
    # Keep cue boundaries: do not include the host handover or alter the cue.
    for last_id, ending, host_id, host_prefix in (
        (411, "楚。謝", 412, "謝。接下來"),
        (478, "最嚴格把", 479, "關。謝謝"),
        (544, "精神的目", 545, "的。現在"),
        (675, "事情。謝", 676, "謝。接下來"),
        (799, "我們已經出", 800, "發。同樣"),
        (1066, "續", 1067, "做。謝謝"),
    ):
        assert cues[last_id]["text"].endswith(ending)
        assert cues[host_id]["text"].startswith(host_prefix)
        assert any(leaf["end_cue_id"] == last_id for leaf in leaves(chapters["items"]))
    # Cue 34 completes the rules and starts a formal-phase introduction.
    # Cues 35–36 contain only the first candidate's handover and stay outside.
    assert "提醒兩位要格外注意" in cues[34]["text"]
    assert "我們要請沈伯洋先生" in cues[35]["text"]
    assert chapters["items"][0]["end_cue_id"] == 34
    assert chapters["items"][-1]["start_cue_id"] == 1068
    assert chapters["items"][-1]["end_cue_id"] == artifact["cues"][-1]["id"] == 1082
    assert cues[1082]["text"] == "感謝您的收看，我們再會。"
    # The unresolved, overlapping host handover remains inside one final leaf.
    assert cues[1076]["speaker"] == "UNKNOWN"
    assert cues[1077]["start"] == cues[1078]["start"]
