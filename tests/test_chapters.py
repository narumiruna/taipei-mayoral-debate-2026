import copy

import pytest

from transcripts.chapters import validate_chapters


@pytest.fixture
def artifact():
    return {
        "metadata": {"duration": 20},
        "review": {"source_sha256": "a" * 64},
        # IDs are deliberately not in numeric order.
        "cues": [
            {"id": 30, "start": 1, "end": 2},
            {"id": 10, "start": 2, "end": 3},
            {"id": 70, "start": 5, "end": 6},
            {"id": 20, "start": 6, "end": 7},
            {"id": 90, "start": 9, "end": 10},
            {"id": 40, "start": 10, "end": 11},
            {"id": 80, "start": 15, "end": 16},
        ],
    }


@pytest.fixture
def chapters():
    return {
        "source_sha256": "a" * 64,
        "items": [
            {
                "id": "phase",
                "title": "Phase",
                "children": [
                    {
                        "id": "opening",
                        "title": "Opening",
                        "start_cue_id": 30,
                        "end_cue_id": 10,
                    },
                    {
                        "id": "round",
                        "title": "Round",
                        "children": [
                            {
                                "id": "question",
                                "title": "Question",
                                "start_cue_id": 70,
                                "end_cue_id": 20,
                            },
                            {
                                "id": "answer",
                                "title": "Answer",
                                "start_cue_id": 90,
                                "end_cue_id": 40,
                            },
                        ],
                    },
                ],
            },
            {
                "id": "closing",
                "title": "Closing",
                "start_cue_id": 80,
                "end_cue_id": 80,
            },
        ],
    }


def _opening(chapters):
    return chapters["items"][0]["children"][0]


def _round(chapters):
    return chapters["items"][0]["children"][1]


def test_resolves_nested_ranges_and_filters_fields_without_mutation(chapters, artifact):
    chapters["private"] = "PRIVATE_ROOT"
    phase = chapters["items"][0]
    phase.update(private="PRIVATE_GROUP", start=-100, end=1000)
    _round(chapters)["private"] = "PRIVATE_NESTED_GROUP"
    _opening(chapters).update(private="PRIVATE_LEAF", start=-100, end=1000)
    original_chapters = copy.deepcopy(chapters)
    original_artifact = copy.deepcopy(artifact)

    result = validate_chapters(chapters, artifact)

    assert result == {
        "source_sha256": "a" * 64,
        "items": [
            {
                "id": "phase",
                "title": "Phase",
                "start_cue_id": 30,
                "end_cue_id": 40,
                "start": 1,
                "end": 11,
                "children": [
                    {
                        "id": "opening",
                        "title": "Opening",
                        "start_cue_id": 30,
                        "end_cue_id": 10,
                        "start": 1,
                        "end": 3,
                    },
                    {
                        "id": "round",
                        "title": "Round",
                        "start_cue_id": 70,
                        "end_cue_id": 40,
                        "start": 5,
                        "end": 11,
                        "children": [
                            {
                                "id": "question",
                                "title": "Question",
                                "start_cue_id": 70,
                                "end_cue_id": 20,
                                "start": 5,
                                "end": 7,
                            },
                            {
                                "id": "answer",
                                "title": "Answer",
                                "start_cue_id": 90,
                                "end_cue_id": 40,
                                "start": 9,
                                "end": 11,
                            },
                        ],
                    },
                ],
            },
            {
                "id": "closing",
                "title": "Closing",
                "start_cue_id": 80,
                "end_cue_id": 80,
                "start": 15,
                "end": 16,
            },
        ],
    }
    assert chapters == original_chapters
    assert artifact == original_artifact
    result["items"][0]["children"][0]["title"] = "Changed"
    assert chapters == original_chapters


def test_allows_adjacent_leaves_and_recording_boundaries(chapters, artifact):
    artifact["cues"][0]["start"] = 0
    artifact["cues"][2]["start"] = 3
    artifact["cues"][4]["start"] = 7
    artifact["cues"][-1]["end"] = 20

    result = validate_chapters(chapters, artifact)

    assert result["items"][0]["start"] == 0
    assert result["items"][-1]["end"] == 20


def test_empty_root_list_is_valid(chapters, artifact):
    chapters["items"] = []
    assert validate_chapters(chapters, artifact) == {
        "source_sha256": "a" * 64,
        "items": [],
    }


@pytest.mark.parametrize("value", [None, [], "chapters", 1, True])
def test_rejects_non_object_root(value, artifact):
    with pytest.raises(ValueError, match="chapters must be an object"):
        validate_chapters(value, artifact)


@pytest.mark.parametrize("value", [None, "", "a" * 63, "A" * 64, 1, "b" * 64])
def test_rejects_invalid_or_wrong_source(chapters, artifact, value):
    chapters["source_sha256"] = value
    with pytest.raises(ValueError, match="source_sha256"):
        validate_chapters(chapters, artifact)


@pytest.mark.parametrize("value", [None, {}, {"source_sha256": "b" * 64}])
def test_rejects_missing_or_wrong_artifact_review(chapters, artifact, value):
    artifact["review"] = value
    with pytest.raises(ValueError, match="artifact.review"):
        validate_chapters(chapters, artifact)


@pytest.mark.parametrize("value", [None, {}, "items", (), True])
def test_rejects_invalid_items(chapters, artifact, value):
    chapters["items"] = value
    with pytest.raises(ValueError, match="chapters.items must be a list"):
        validate_chapters(chapters, artifact)


@pytest.mark.parametrize("value", [None, [], "node", 1])
def test_rejects_non_object_node(chapters, artifact, value):
    chapters["items"][0] = value
    with pytest.raises(ValueError, match=r"items\[0\] must be an object"):
        validate_chapters(chapters, artifact)


@pytest.mark.parametrize("field", ["id", "title"])
@pytest.mark.parametrize("value", [None, "", " \t\n", 1, [], True])
@pytest.mark.parametrize("group", [True, False])
def test_rejects_invalid_node_text(chapters, artifact, field, value, group):
    node = chapters["items"][0] if group else _opening(chapters)
    node[field] = value
    with pytest.raises(ValueError, match=rf"\.{field} must be a nonempty string"):
        validate_chapters(chapters, artifact)


@pytest.mark.parametrize("identity", ["phase", "round", "opening"])
def test_rejects_duplicate_ids_across_hierarchy(chapters, artifact, identity):
    chapters["items"][-1]["id"] = identity
    with pytest.raises(ValueError, match="id must be unique"):
        validate_chapters(chapters, artifact)


@pytest.mark.parametrize("value", [[], None, {}, "children", True])
def test_rejects_empty_or_invalid_group(chapters, artifact, value):
    _round(chapters)["children"] = value
    with pytest.raises(ValueError, match="children must be a nonempty list"):
        validate_chapters(chapters, artifact)


@pytest.mark.parametrize("field", ["start_cue_id", "end_cue_id"])
def test_rejects_ambiguous_group_even_with_null_reference(chapters, artifact, field):
    _round(chapters)[field] = None
    with pytest.raises(ValueError, match="combine children and leaf cue references"):
        validate_chapters(chapters, artifact)


@pytest.mark.parametrize("field", ["start_cue_id", "end_cue_id"])
@pytest.mark.parametrize("value", [None, 999, True, 30.0, "30", [], {}])
def test_rejects_invalid_leaf_reference(chapters, artifact, field, value):
    _opening(chapters)[field] = value
    with pytest.raises(ValueError, match=rf"\.{field} must reference"):
        validate_chapters(chapters, artifact)


@pytest.mark.parametrize("field", ["start_cue_id", "end_cue_id"])
def test_rejects_missing_leaf_reference(chapters, artifact, field):
    del _opening(chapters)[field]
    with pytest.raises(ValueError, match=rf"\.{field} must reference"):
        validate_chapters(chapters, artifact)


@pytest.mark.parametrize("field", ["start", "end"])
@pytest.mark.parametrize(
    "value", [-1, None, True, "1", float("nan"), float("inf"), float("-inf")]
)
def test_rejects_invalid_cue_times(chapters, artifact, field, value):
    artifact["cues"][0][field] = value
    with pytest.raises(
        ValueError, match=rf"\.{field} must be a finite nonnegative number"
    ):
        validate_chapters(chapters, artifact)


@pytest.mark.parametrize("start,end", [(2, 2), (3, 2), (19, 21)])
def test_rejects_invalid_cue_intervals(chapters, artifact, start, end):
    artifact["cues"][0].update(start=start, end=end)
    with pytest.raises(ValueError, match="start < end within the recording"):
        validate_chapters(chapters, artifact)


@pytest.mark.parametrize("value", [-1, True, "20", float("nan"), float("inf")])
def test_rejects_invalid_duration(chapters, artifact, value):
    artifact["metadata"]["duration"] = value
    with pytest.raises(ValueError, match="metadata.duration"):
        validate_chapters(chapters, artifact)


@pytest.mark.parametrize("value", [[], "metadata"])
def test_rejects_invalid_metadata(chapters, artifact, value):
    artifact["metadata"] = value
    with pytest.raises(ValueError, match="artifact.metadata"):
        validate_chapters(chapters, artifact)


@pytest.mark.parametrize("metadata", ["missing", None, {}, {"duration": None}])
def test_derives_duration_from_cues_when_metadata_duration_is_absent(
    chapters, artifact, metadata
):
    if metadata == "missing":
        artifact.pop("metadata")
    else:
        artifact["metadata"] = metadata
    original = copy.deepcopy(artifact)

    result = validate_chapters(chapters, artifact)

    assert result["items"][-1]["end"] == 16
    assert artifact == original


def test_empty_chapters_and_cues_need_no_metadata(chapters):
    chapters["items"] = []
    assert validate_chapters(
        chapters, {"cues": [], "review": {"source_sha256": "a" * 64}}
    ) == {"source_sha256": "a" * 64, "items": []}


@pytest.mark.parametrize("value", [None, {}, "cues"])
def test_rejects_invalid_artifact_cues(chapters, artifact, value):
    artifact["cues"] = value
    with pytest.raises(ValueError, match="artifact.cues"):
        validate_chapters(chapters, artifact)


@pytest.mark.parametrize("value", [None, True, "30", 30.0, 10])
def test_rejects_wrong_type_or_duplicate_artifact_cue_id(chapters, artifact, value):
    artifact["cues"][0]["id"] = value
    with pytest.raises(ValueError, match="id must be a unique integer"):
        validate_chapters(chapters, artifact)


def test_rejects_reversed_cue_order_even_with_valid_combined_time_range(
    chapters, artifact
):
    _opening(chapters).update(start_cue_id=10, end_cue_id=30)
    artifact["cues"][0]["end"] = 4
    with pytest.raises(ValueError, match="chronological cue range"):
        validate_chapters(chapters, artifact)


@pytest.mark.parametrize("field,value", [("start", 0.5), ("end", 1.5)])
def test_rejects_reversed_boundary_times(chapters, artifact, field, value):
    artifact["cues"][1][field] = value
    if field == "end":
        artifact["cues"][1]["start"] = 1
    with pytest.raises(ValueError, match="chronological cue range"):
        validate_chapters(chapters, artifact)


@pytest.mark.parametrize("level", ["root", "phase", "round"])
def test_rejects_reversed_siblings_at_each_level(chapters, artifact, level):
    siblings = {
        "root": chapters["items"],
        "phase": chapters["items"][0]["children"],
        "round": _round(chapters)["children"],
    }[level]
    siblings.reverse()
    with pytest.raises(ValueError, match="chronological sibling order"):
        validate_chapters(chapters, artifact)


@pytest.mark.parametrize("across_groups", [True, False])
def test_rejects_overlapping_leaves_with_distinct_cues(
    chapters, artifact, across_groups
):
    cue_index = 6 if across_groups else 4
    artifact["cues"][cue_index]["start"] = 10 if across_groups else 6.5
    with pytest.raises(ValueError, match="leaf intervals.*must not overlap"):
        validate_chapters(chapters, artifact)


def test_rejects_reused_cue_between_leaves(chapters, artifact):
    _round(chapters)["children"][1]["start_cue_id"] = 20
    with pytest.raises(ValueError, match="chronological sibling order"):
        validate_chapters(chapters, artifact)
