import copy
import json
import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

from transcripts.fact_checks import validate_fact_checks
from transcripts.web import render_page

DATA = Path(__file__).resolve().parents[1] / "data"
ITEM = ("items", 0)
QUOTE = (*ITEM, "quotes", 0)
SOURCE = (*ITEM, "sources", 0)
REQUIRED_FIELDS = [
    *(
        (key,)
        for key in (
            "version",
            "reviewed_at",
            "scope",
            "method",
            "source_sha256",
            "items",
        )
    ),
    *(
        (*ITEM, key)
        for key in (
            "id",
            "speaker",
            "title",
            "verdict",
            "summary",
            "analysis",
            "limitations",
            "quotes",
            "sources",
        )
    ),
    *((*QUOTE, key) for key in ("cue_id", "text")),
    *(
        (*SOURCE, key)
        for key in ("title", "publisher", "published_at", "url", "evidence")
    ),
]
TEXT_FIELDS = [
    ("scope",),
    ("method",),
    *(
        (*ITEM, key)
        for key in ("id", "speaker", "title", "verdict", "summary", "limitations")
    ),
    (*ITEM, "analysis", 0),
    (*QUOTE, "text"),
    *((*SOURCE, key) for key in ("title", "publisher", "url", "evidence")),
]


@pytest.fixture
def artifact():
    return {
        "metadata": {"duration": 9.0, "model": "local-model", "stage": "diarize"},
        "display_language": "zh-Hant-TW",
        "roles": {
            "SPEAKER_00": {"role": "辯論者1", "name": "王小明", "organization": ""},
            "SPEAKER_01": {"role": "辯論者2", "name": "李小華", "organization": ""},
        },
        "cues": [
            {
                "id": 10,
                "start": 1.0,
                "end": 3.0,
                "speaker": "SPEAKER_00",
                "label": "辯論者1／王小明",
                "text": "第一項主張。",
            },
            {
                "id": 2,
                "start": 4.0,
                "end": 6.0,
                "speaker": "SPEAKER_00",
                "label": "辯論者1／王小明",
                "text": "第二項主張。",
            },
            {
                "id": 30,
                "start": 7.0,
                "end": 9.0,
                "speaker": "SPEAKER_01",
                "label": "辯論者2／李小華",
                "text": "另一位說話者。",
            },
        ],
        "review": {"source_sha256": "a" * 64, "method": "文字校對。"},
    }


@pytest.fixture
def ledger(artifact):
    return {
        "version": 1,
        "reviewed_at": "2026-08-06",
        "scope": "僅查核所列主張。",
        "method": "將引述與公開文件比較。",
        "source_sha256": artifact["review"]["source_sha256"],
        "items": [
            {
                "id": "FC001",
                "speaker": "SPEAKER_00",
                "title": "主張的查核標題。",
                "verdict": "needs-context",
                "summary": "現有資料需要補充背景。",
                "analysis": ["資料的統計範圍不同。", "不可直接比較總數。"],
                "limitations": "僅比較公開資料，未查核所有發言。",
                "quotes": [
                    {"cue_id": cue["id"], "text": cue["text"]}
                    for cue in artifact["cues"][:2]
                ],
                "sources": [
                    {
                        "title": "公開統計資料。",
                        "publisher": "統計機關。",
                        "published_at": "2026-07-30",
                        "url": "https://example.org/report?year=2026&view=all#table",
                        "evidence": "表格顯示兩年度的統計範圍不同。",
                    }
                ],
            }
        ],
    }


def _parent(value, path):
    for key in path[:-1]:
        value = value[key]
    return value


def _context(path):
    return "fact_checks" + "".join(
        f"[{key}]" if isinstance(key, int) else f".{key}" for key in path
    )


def _write_ledger(output, value):
    output.mkdir(parents=True, exist_ok=True)
    path = output / "fact-checks.json"
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return path


def _data_script(html):
    match = re.search(
        r'<script type="application/json" id="debate-data">(.*?)</script>',
        html,
        re.DOTALL,
    )
    assert match is not None
    return match[1]


def _payload(destination):
    return json.loads(_data_script(destination.read_text(encoding="utf-8")))


def test_absent_ledger_preserves_exact_payload_without_tools(
    tmp_path, monkeypatch, artifact
):
    original = copy.deepcopy(artifact)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PATH", "")

    destination = render_page(artifact, tmp_path / "nested" / "export")

    expected = {
        "metadata": artifact["metadata"],
        "display_language": artifact["display_language"],
        "roles": artifact["roles"],
        "cues": artifact["cues"],
        "review": {
            "corrections": [],
            "flags": [],
            "method": "文字校對。",
            "source_sha256": "a" * 64,
        },
    }
    assert _payload(destination) == expected
    assert _data_script(destination.read_text(encoding="utf-8")) == json.dumps(
        expected, ensure_ascii=False, separators=(",", ":")
    )
    assert artifact == original
    assert list(destination.parent.iterdir()) == [destination]


def test_valid_ledger_embeds_without_mutating_inputs_or_using_tools(
    tmp_path, monkeypatch, artifact, ledger
):
    original_artifact = copy.deepcopy(artifact)
    original_ledger = copy.deepcopy(ledger)
    path = _write_ledger(tmp_path, ledger)
    original_bytes = path.read_bytes()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PATH", "")

    validated = validate_fact_checks(ledger, artifact)
    destination = render_page(artifact, tmp_path, fact_checks=ledger)

    assert validated == ledger
    assert validated is not ledger
    assert _payload(destination)["fact_checks"] == ledger
    assert artifact == original_artifact
    assert ledger == original_ledger
    assert path.read_bytes() == original_bytes
    validated["items"][0]["analysis"].append("Additional analysis.")
    validated["items"][0]["quotes"][0]["text"] = "Changed output."
    validated["items"][0]["sources"][0]["evidence"] = "Changed output."
    assert ledger == original_ledger


def test_only_whitelisted_fields_are_embedded(tmp_path, artifact, ledger):
    expected = copy.deepcopy(ledger)
    private = {"token": "PRIVATE_LEDGER_TOKEN", "path": "/private/research.txt"}
    ledger["private"] = private
    ledger["items"][0]["private"] = private
    for quote in ledger["items"][0]["quotes"]:
        quote["private"] = private
    ledger["items"][0]["sources"][0]["private"] = private
    original = copy.deepcopy(ledger)
    _write_ledger(tmp_path, ledger)

    destination = render_page(artifact, tmp_path, fact_checks=ledger)

    assert _payload(destination)["fact_checks"] == expected
    html = destination.read_text(encoding="utf-8")
    assert "PRIVATE_LEDGER_TOKEN" not in html
    assert "/private/research.txt" not in html
    assert ledger == original


def test_script_text_round_trips_with_existing_renderer_escaping(
    tmp_path, artifact, ledger
):
    malicious = (
        '</script><script>alert("injected")</script>'
        '<img src=x onerror="alert(1)">&\u2028\u2029{{STYLE}}{{SCRIPT}}{{DATA}}'
    )
    for key in ("scope", "method"):
        ledger[key] = malicious
    item = ledger["items"][0]
    for key in ("id", "title", "summary", "limitations"):
        item[key] = malicious
    item["analysis"] = [malicious]
    for quote, cue in zip(item["quotes"], artifact["cues"], strict=False):
        quote["text"] = cue["text"] = malicious
    for key in ("title", "publisher", "evidence"):
        item["sources"][0][key] = malicious
    _write_ledger(tmp_path, ledger)

    html = render_page(artifact, tmp_path, fact_checks=ledger).read_text(
        encoding="utf-8"
    )

    assert json.loads(_data_script(html))["fact_checks"] == ledger
    assert malicious not in html
    tags = []
    parser = HTMLParser()
    parser.handle_starttag = lambda tag, attrs: tags.append((tag, dict(attrs)))
    parser.feed(html)
    parser.close()
    assert sum(tag == "script" for tag, _ in tags) == 2
    assert not any(tag == "img" for tag, _ in tags)
    assert not any(key.startswith("on") for _, attrs in tags for key in attrs)
    raw = _data_script(html)
    for character, escaped in (
        ("<", "\\u003c"),
        (">", "\\u003e"),
        ("&", "\\u0026"),
        ("\u2028", "\\u2028"),
        ("\u2029", "\\u2029"),
    ):
        assert character not in raw
        assert escaped in raw


@pytest.mark.parametrize("value", [None, [], "ledger", 1, True])
def test_root_must_be_an_object(artifact, value):
    with pytest.raises(ValueError, match="fact_checks.*object"):
        validate_fact_checks(value, artifact)


@pytest.mark.parametrize("path", REQUIRED_FIELDS)
def test_all_fields_are_required(artifact, ledger, path):
    del _parent(ledger, path)[path[-1]]

    with pytest.raises(ValueError, match=re.escape(_context(path))):
        validate_fact_checks(ledger, artifact)


@pytest.mark.parametrize("value", [None, True, 1, [], {}, "", " \t\n"])
@pytest.mark.parametrize("path", TEXT_FIELDS)
def test_displayed_strings_must_be_nonempty(artifact, ledger, path, value):
    _parent(ledger, path)[path[-1]] = value

    with pytest.raises(ValueError, match=re.escape(_context(path))):
        validate_fact_checks(ledger, artifact)


@pytest.mark.parametrize("version", [None, True, False, "1", 1.0, 0, 2, [], {}])
def test_version_requires_integer_one(artifact, ledger, version):
    ledger["version"] = version

    with pytest.raises(ValueError, match="fact_checks.version"):
        validate_fact_checks(ledger, artifact)


@pytest.mark.parametrize("value", [None, {}, "list", 1, True])
@pytest.mark.parametrize(
    "path", [("items",), (*ITEM, "analysis"), (*ITEM, "quotes"), (*ITEM, "sources")]
)
def test_collections_must_be_lists(artifact, ledger, path, value):
    _parent(ledger, path)[path[-1]] = value

    with pytest.raises(ValueError, match=re.escape(_context(path))):
        validate_fact_checks(ledger, artifact)


@pytest.mark.parametrize("key", ["analysis", "quotes", "sources"])
def test_item_collections_must_not_be_empty(artifact, ledger, key):
    ledger["items"][0][key] = []

    with pytest.raises(ValueError, match=rf"items\[0\].{key}.*nonempty"):
        validate_fact_checks(ledger, artifact)


def test_empty_items_are_allowed(artifact, ledger):
    ledger["items"] = []

    assert validate_fact_checks(ledger, artifact) == ledger


@pytest.mark.parametrize("value", [None, [], "entry", 1, True])
@pytest.mark.parametrize("path", [ITEM, QUOTE, SOURCE])
def test_entries_must_be_objects(artifact, ledger, path, value):
    _parent(ledger, path)[path[-1]] = value

    with pytest.raises(ValueError, match=re.escape(_context(path))):
        validate_fact_checks(ledger, artifact)


@pytest.mark.parametrize(
    "value",
    [None, True, 1, "", "a" * 63, "a" * 65, "A" * 64, "g" * 64, "a" * 63 + "\n"],
)
@pytest.mark.parametrize("target", ["ledger", "artifact"])
def test_source_hash_must_be_lowercase_sha256(artifact, ledger, target, value):
    if target == "ledger":
        ledger["source_sha256"] = value
    else:
        artifact["review"]["source_sha256"] = value

    with pytest.raises(ValueError, match="source_sha256"):
        validate_fact_checks(ledger, artifact)


def test_missing_artifact_hash_fails(artifact, ledger):
    artifact["review"].pop("source_sha256")

    with pytest.raises(ValueError, match="artifact.review.source_sha256"):
        validate_fact_checks(ledger, artifact)


@pytest.mark.parametrize("review", [None, [], "review", True])
def test_invalid_artifact_review_fails(artifact, ledger, review):
    artifact["review"] = review

    with pytest.raises(ValueError, match="artifact.review"):
        validate_fact_checks(ledger, artifact)


def test_missing_artifact_review_fails(artifact, ledger):
    artifact.pop("review")

    with pytest.raises(ValueError, match="artifact.review"):
        validate_fact_checks(ledger, artifact)


def test_source_hash_must_match_artifact(artifact, ledger):
    ledger["source_sha256"] = "b" * 64

    with pytest.raises(ValueError, match="source_sha256.*match"):
        validate_fact_checks(ledger, artifact)


@pytest.mark.parametrize("cue_id", [None, True, False, "10", 10.0, 999, [], {}])
def test_quotes_require_existing_integer_cue_ids(artifact, ledger, cue_id):
    if isinstance(cue_id, bool):
        artifact["cues"][0]["id"] = int(cue_id)
    ledger["items"][0]["quotes"][0]["cue_id"] = cue_id

    with pytest.raises(ValueError, match=r"quotes\[0\].cue_id"):
        validate_fact_checks(ledger, artifact)


@pytest.mark.parametrize("index", [0, 1])
def test_every_quote_must_exactly_match_display_text(artifact, ledger, index):
    ledger["items"][0]["quotes"][index]["text"] += " "

    with pytest.raises(ValueError, match=rf"quotes\[{index}\].text.*exactly match"):
        validate_fact_checks(ledger, artifact)


def test_quote_cannot_use_original_text(artifact, ledger):
    artifact["cues"][0]["original_text"] = "未校對原文。"
    ledger["items"][0]["quotes"][0]["text"] = artifact["cues"][0]["original_text"]

    with pytest.raises(ValueError, match=r"quotes\[0\].text.*exactly match"):
        validate_fact_checks(ledger, artifact)


def test_deleted_cue_is_rejected(artifact, ledger):
    artifact["cues"].pop(1)

    with pytest.raises(ValueError, match=r"quotes\[1\].cue_id"):
        validate_fact_checks(ledger, artifact)


@pytest.mark.parametrize("speaker", ["SPEAKER_01", "MISSING_SPEAKER"])
def test_wrong_or_unknown_speaker_is_rejected(artifact, ledger, speaker):
    ledger["items"][0]["speaker"] = speaker

    with pytest.raises(ValueError, match=r"items\[0\].speaker"):
        validate_fact_checks(ledger, artifact)


def test_every_quote_must_match_item_speaker(artifact, ledger):
    cue = artifact["cues"][2]
    ledger["items"][0]["quotes"].append({"cue_id": cue["id"], "text": cue["text"]})

    with pytest.raises(ValueError, match=r"speaker.*cue 30.speaker"):
        validate_fact_checks(ledger, artifact)


@pytest.mark.parametrize("name", [None, "", " \t", 1, True])
def test_speaker_role_requires_nonempty_name(artifact, ledger, name):
    artifact["roles"]["SPEAKER_00"]["name"] = name

    with pytest.raises(ValueError, match=r"artifact.roles.*name"):
        validate_fact_checks(ledger, artifact)


def test_speaker_role_requires_name_field(artifact, ledger):
    artifact["roles"]["SPEAKER_00"].pop("name")

    with pytest.raises(ValueError, match=r"artifact.roles.*name"):
        validate_fact_checks(ledger, artifact)


def test_item_ids_must_be_unique(artifact, ledger):
    ledger["items"].append(copy.deepcopy(ledger["items"][0]))

    with pytest.raises(ValueError, match=r"items\[1\].id.*unique"):
        validate_fact_checks(ledger, artifact)


def test_quote_ids_must_be_unique_within_item(artifact, ledger):
    quotes = ledger["items"][0]["quotes"]
    quotes.append(copy.deepcopy(quotes[0]))

    with pytest.raises(ValueError, match=r"quotes\[2\].cue_id.*unique"):
        validate_fact_checks(ledger, artifact)


def test_quotes_can_be_shared_by_distinct_items(artifact, ledger):
    second = copy.deepcopy(ledger["items"][0])
    second["id"] = "FC002"
    ledger["items"].append(second)

    assert validate_fact_checks(ledger, artifact) == ledger


def test_reversed_quotes_are_rejected(artifact, ledger):
    ledger["items"][0]["quotes"].reverse()

    with pytest.raises(ValueError, match="chronological cue order"):
        validate_fact_checks(ledger, artifact)


@pytest.mark.parametrize(
    "verdict", ["supported", "needs-context", "contradicted", "insufficient-evidence"]
)
def test_all_supported_verdicts_are_accepted(artifact, ledger, verdict):
    ledger["items"][0]["verdict"] = verdict

    assert validate_fact_checks(ledger, artifact) == ledger


@pytest.mark.parametrize(
    "verdict", ["true", "false", "unknown", "Supported", "supported "]
)
def test_unknown_verdicts_are_rejected(artifact, ledger, verdict):
    ledger["items"][0]["verdict"] = verdict

    with pytest.raises(ValueError, match=r"items\[0\].verdict"):
        validate_fact_checks(ledger, artifact)


@pytest.mark.parametrize(
    "value",
    [
        True,
        20260806,
        "",
        "20260806",
        "2026-W32-4",
        "2026-8-06",
        "2026-08-6",
        "2026-08-06T00:00:00",
        "2026-08-06 ",
        "2026-02-29",
        "2026-02-30",
        "2026-00-01",
        "2026-13-01",
        "0000-01-01",
    ],
)
@pytest.mark.parametrize("path", [("reviewed_at",), (*SOURCE, "published_at")])
def test_dates_require_valid_iso_calendar_dates(artifact, ledger, path, value):
    _parent(ledger, path)[path[-1]] = value

    with pytest.raises(ValueError, match=re.escape(_context(path))):
        validate_fact_checks(ledger, artifact)


def test_review_date_cannot_be_null(artifact, ledger):
    ledger["reviewed_at"] = None

    with pytest.raises(ValueError, match="fact_checks.reviewed_at"):
        validate_fact_checks(ledger, artifact)


@pytest.mark.parametrize("published_at", [None, "2024-02-29", "2026-08-06"])
def test_undated_and_not_future_sources_are_accepted(artifact, ledger, published_at):
    ledger["items"][0]["sources"][0]["published_at"] = published_at

    assert validate_fact_checks(ledger, artifact) == ledger


def test_source_cannot_be_published_after_review(artifact, ledger):
    ledger["items"][0]["sources"][0]["published_at"] = "2026-08-07"

    with pytest.raises(ValueError, match="published_at.*after reviewed_at"):
        validate_fact_checks(ledger, artifact)


@pytest.mark.parametrize(
    "url",
    [
        "http://example.org/report",
        "ftp://example.org/report",
        "javascript:alert(1)",
        "data:text/html,example",
        "//example.org/report",
        "https:///report",
        "https://",
        "https://user@example.org/report",
        "https://user:password@example.org/report",
        "https://@example.org/report",
        "https://:password@example.org/report",
        " https://example.org/report",
        "https://example.org/report ",
        "https://example.org/a b",
        "https://example.org/a\tb",
        "https://example.org/a\nb",
        "https://example.org/a\rb",
        "https://example.org/a\x00b",
        "https://example.org/a\x1fb",
        "https://example.org/a\x7fb",
        "https://example.org/a\x85b",
        "https://example.org/a\u200bb",
        "https://example.org/a\u2028b",
        "https://example.org/a\\b",
        "https://bad_host.example/report",
        "https://-bad.example/report",
        "https://bad-.example/report",
        "https://example..org/report",
        "https://.example.org/report",
        "https://exa%6dple.org/report",
        f"https://{'a' * 64}.org/report",
        "https://" + ".".join(["a" * 63] * 4) + "/report",
        "https://999.1.2.3/report",
        "https://[not-an-ip]/report",
        "https://[::1/report",
        "https://[::1]suffix/report",
        "https://example.org:abc/report",
        "https://example.org:65536/report",
        "https://example.org:/report",
    ],
)
def test_unsafe_or_invalid_source_urls_are_rejected(artifact, ledger, url):
    ledger["items"][0]["sources"][0]["url"] = url

    with pytest.raises(ValueError, match=r"sources\[0\].url"):
        validate_fact_checks(ledger, artifact)


@pytest.mark.parametrize(
    "url",
    [
        "https://example.org",
        "HTTPS://EXAMPLE.ORG/report",
        "https://sub.example.org:443/report?q=a%20b#table",
        "https://example.org./report",
        "https://127.0.0.1/report",
        "https://[2001:db8::1]:443/report",
        "https://例子.台灣/report",
    ],
)
def test_valid_https_source_urls_are_preserved(artifact, ledger, url):
    ledger["items"][0]["sources"][0]["url"] = url

    assert validate_fact_checks(ledger, artifact) == ledger


@pytest.mark.parametrize("failure", ["quote", "hash", "root", "version"])
def test_invalid_ledger_does_not_overwrite_existing_page(
    tmp_path, artifact, ledger, failure
):
    if failure == "quote":
        ledger["items"][0]["quotes"][0]["text"] = "Stale quotation."
    elif failure == "hash":
        ledger["source_sha256"] = "b" * 64
    elif failure == "root":
        ledger = []
    else:
        ledger["version"] = True
    _write_ledger(tmp_path, ledger)
    destination = tmp_path / "index.html"
    destination.write_bytes(b"EXISTING PAGE\n")

    with pytest.raises(ValueError):
        render_page(artifact, tmp_path, fact_checks=ledger)

    assert destination.read_bytes() == b"EXISTING PAGE\n"


@pytest.mark.parametrize("contents", [b"{invalid JSON", b"\xff"])
def test_renderer_does_not_read_a_ledger_from_output(tmp_path, artifact, contents):
    ledger_path = tmp_path / "fact-checks.json"
    ledger_path.write_bytes(contents)

    page = render_page(artifact, tmp_path)

    assert "fact_checks" not in _payload(page)
    assert ledger_path.read_bytes() == contents


def test_committed_curated_ledger_matches_transcript(tmp_path, curated_site):
    artifact = json.loads((DATA / "transcript.json").read_text(encoding="utf-8"))
    ledger = json.loads((DATA / "fact-checks.json").read_text(encoding="utf-8"))
    validated = validate_fact_checks(ledger, artifact)
    assert validated["source_sha256"] == artifact["review"]["source_sha256"]
    page = render_page(artifact, tmp_path, fact_checks=ledger)
    assert _payload(page)["fact_checks"] == validated
    assert _payload(curated_site)["fact_checks"] == validated
