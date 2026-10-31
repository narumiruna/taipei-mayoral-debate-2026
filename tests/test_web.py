import copy
import json
import re
from html import unescape
from html.parser import HTMLParser
from importlib.resources import files
from pathlib import Path

import pytest

from transcripts.web import render_page


class PageParser(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.elements = []
        self.scripts = []
        self.in_script = False
        self.feed(html)
        self.close()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.elements.append((tag, attrs))
        if tag == "script":
            self.scripts.append({"attrs": attrs, "text": ""})
            self.in_script = True

    def handle_endtag(self, tag):
        if tag == "script":
            self.in_script = False

    def handle_data(self, data):
        if self.in_script:
            self.scripts[-1]["text"] += data

    def payload(self):
        (script,) = [
            script
            for script in self.scripts
            if script["attrs"].get("id") == "debate-data"
        ]
        assert script["attrs"]["type"] == "application/json"
        return json.loads(script["text"])


@pytest.fixture
def artifact():
    return {
        "metadata": {
            "duration": 3.5,
            "model": "local-model",
            "stage": "diarize",
            "source": "/private/source.wav",
            "token": "PRIVATE_METADATA",
        },
        "display_language": "zh-Hant-TW",
        "roles": {
            "SPEAKER_00": {
                "role": "主持人",
                "name": "王小明",
                "evidence": "PRIVATE_ROLE_EVIDENCE",
            }
        },
        "cues": [
            {
                "id": 1,
                "start": 0.5,
                "end": 3.5,
                "speaker": "SPEAKER_00",
                "label": "主持人／王小明",
                "text": "修訂文字。",
                "timing": "aligned",
                "original_text": "辨識原文。",
                "correction_id": "C001",
                "words": "PRIVATE_CUE_WORDS",
            }
        ],
        "review": {
            "source_sha256": "a" * 64,
            "method": "回聽影音。",
            "corrections": [
                {
                    "id": "C001",
                    "cue_id": 1,
                    "before": "辨識原文。",
                    "after": "修訂文字。",
                    "reason": "同音字有誤。",
                    "evidence": "00:00.5–00:03.5 的影音。",
                    "private": "PRIVATE_CORRECTION",
                }
            ],
            "flags": [
                {
                    "id": "F001",
                    "cue_id": 1,
                    "reason": "尚待確認。",
                    "suggestion": "可能文字。",
                    "private": "PRIVATE_FLAG",
                }
            ],
            "private": "PRIVATE_REVIEW",
        },
        "segments": "PRIVATE_SEGMENTS",
        "speaker_turns": "PRIVATE_SPEAKER_TURNS",
        "private": "PRIVATE_ARTIFACT",
    }


def test_nested_output_embeds_only_whitelisted_data(tmp_path, artifact):
    original = copy.deepcopy(artifact)
    output = tmp_path / "nested" / "export"

    destination = render_page(artifact, output)

    assert destination == output / "index.html"
    assert destination.is_file()
    assert list(output.iterdir()) == [destination]
    assert artifact == original
    html = destination.read_text(encoding="utf-8")
    payload = PageParser(html).payload()
    assert set(payload) == {"metadata", "display_language", "roles", "cues", "review"}
    assert payload["metadata"] == {
        "duration": 3.5,
        "model": "local-model",
        "stage": "diarize",
    }
    assert payload["display_language"] == "zh-Hant-TW"
    assert payload["roles"] == {
        "SPEAKER_00": {"role": "主持人", "name": "王小明", "organization": ""}
    }
    assert payload["cues"] == [
        {key: value for key, value in artifact["cues"][0].items() if key != "words"}
    ]
    assert payload["review"] == {
        "source_sha256": "a" * 64,
        "method": "回聽影音。",
        "corrections": [
            {
                key: value
                for key, value in artifact["review"]["corrections"][0].items()
                if key != "private"
            }
        ],
        "flags": [
            {
                key: value
                for key, value in artifact["review"]["flags"][0].items()
                if key != "private"
            }
        ],
    }
    assert "PRIVATE_" not in html
    assert "/private/source.wav" not in html


def test_page_preserves_speaker_organization(tmp_path, artifact):
    artifact["roles"]["SPEAKER_00"]["organization"] = "TVBS"
    artifact["cues"][0]["label"] = "王小明／TVBS"

    page = PageParser(render_page(artifact, tmp_path).read_text(encoding="utf-8"))

    assert page.payload()["roles"]["SPEAKER_00"]["organization"] == "TVBS"
    assert page.payload()["cues"][0]["label"] == "王小明／TVBS"


def test_page_includes_speaker_corrections_in_review_cards(tmp_path, artifact):
    cue = artifact["cues"][0]
    cue.update(
        original_speaker="UNKNOWN",
        original_label="說話者未確認",
        speaker_correction_id="S001",
    )
    artifact["review"]["speaker_corrections"] = [
        {
            "id": "S001",
            "cue_id": 1,
            "before": "UNKNOWN",
            "after": "SPEAKER_00",
            "reason": "延續前一句。",
            "evidence": "前後文與時間資料。",
            "private": "PRIVATE_SPEAKER_EVIDENCE",
        }
    ]
    original = copy.deepcopy(artifact)

    html = render_page(artifact, tmp_path).read_text(encoding="utf-8")
    payload = PageParser(html).payload()

    assert artifact == original
    assert payload["cues"][0]["original_speaker"] == "UNKNOWN"
    assert payload["cues"][0]["original_label"] == "說話者未確認"
    assert payload["cues"][0]["speaker_correction_id"] == "S001"
    assert payload["review"]["corrections"][-1] == {
        "id": "S001",
        "cue_id": 1,
        "before": "說話者未確認",
        "after": cue["label"],
        "reason": "延續前一句。",
        "evidence": "前後文與時間資料。",
        "kind": "speaker",
    }
    assert "PRIVATE_" not in html


def test_malicious_text_round_trips_without_executable_markup(tmp_path, artifact):
    malicious = (
        '</script><script>alert("injected")</script>'
        '<img src=x onerror="alert(1)">&\u2028\u2029{{STYLE}}{{SCRIPT}}{{DATA}}'
    )
    artifact["cues"][0]["text"] = malicious
    artifact["roles"]["SPEAKER_00"]["name"] = malicious
    artifact["review"]["method"] = malicious
    artifact["review"]["corrections"][0]["evidence"] = malicious
    artifact["review"]["flags"][0]["suggestion"] = malicious

    html = render_page(artifact, tmp_path).read_text(encoding="utf-8")

    page = PageParser(html)
    payload = page.payload()
    assert payload["cues"][0]["text"] == malicious
    assert payload["roles"]["SPEAKER_00"]["name"] == malicious
    assert payload["review"]["method"] == malicious
    assert payload["review"]["corrections"][0]["evidence"] == malicious
    assert payload["review"]["flags"][0]["suggestion"] == malicious
    assert len(page.scripts) == 2
    raw_data = page.scripts[0]["text"]
    for character, escaped in [
        ("<", "\\u003c"),
        (">", "\\u003e"),
        ("&", "\\u0026"),
        ("\u2028", "\\u2028"),
        ("\u2029", "\\u2029"),
    ]:
        assert character not in raw_data
        assert escaped in raw_data
    for marker in ("{{STYLE}}", "{{SCRIPT}}", "{{DATA}}"):
        assert marker in raw_data
        assert marker not in page.scripts[1]["text"]
    assert not any(tag == "img" for tag, _ in page.elements)
    assert not any(key.startswith("on") for _, attrs in page.elements for key in attrs)
    assert "injected" not in page.scripts[1]["text"]
    assert malicious not in html


def test_page_embeds_reader_with_youtube_and_relative_downloads(tmp_path, artifact):
    html = render_page(artifact, tmp_path).read_text(encoding="utf-8")
    page = PageParser(html)

    assert len(page.scripts) == 2
    assert all("src" not in script["attrs"] for script in page.scripts)
    assert page.scripts[1]["text"].strip()
    assert any(tag == "style" for tag, _ in page.elements)
    assert all(
        attrs.get("href", "").startswith("data:")
        for tag, attrs in page.elements
        if tag == "link"
    )
    assert not re.search(r"\bfetch\s*\(|@import\b", html)
    assert set(re.findall(r"https?://[^\s\"'<>`]+", unescape(html))) == {
        "https://www.youtube.com/embed/plpXPrOoV2w?enablejsapi=1&playsinline=1",
        "https://youtu.be/plpXPrOoV2w",
        "https://www.youtube.com/iframe_api",
    }
    assert "https://www.youtube.com/iframe_api" in page.scripts[1]["text"]
    assert all(marker not in html for marker in ("{{STYLE}}", "{{SCRIPT}}", "{{DATA}}"))
    assert "{{MEDIA_" not in html
    assert not any(tag in {"video", "source", "track"} for tag, _ in page.elements)
    assert not any("poster" in attrs for _, attrs in page.elements)
    assert not re.search(r"(?:media/|outputs/|raw/|\.mp4\b|poster\.jpg)", html)
    assert str(tmp_path) not in html
    (iframe,) = [attrs for tag, attrs in page.elements if tag == "iframe"]
    assert iframe["id"] == "debate-video"
    assert iframe["src"] == (
        "https://www.youtube.com/embed/plpXPrOoV2w?enablejsapi=1&playsinline=1"
    )
    assert iframe["title"] == "辯論完整影音"
    assert {value.strip() for value in iframe["allow"].split(";")} == {
        "autoplay",
        "encrypted-media",
        "picture-in-picture",
        "web-share",
    }
    assert iframe["referrerpolicy"] == "strict-origin-when-cross-origin"
    assert "allowfullscreen" in iframe
    (fallback,) = [
        attrs
        for tag, attrs in page.elements
        if tag == "a" and attrs.get("id") == "video-link"
    ]
    assert fallback["href"] == "https://youtu.be/plpXPrOoV2w"
    assert fallback["target"] == "_blank"
    assert "noopener" in fallback.get("rel", "").split()
    resources = {
        (tag, key, value)
        for tag, attrs in page.elements
        for key, value in attrs.items()
        if key in {"src", "poster"}
        or (key == "href" and not value.startswith(("#", "data:")))
    }
    assert resources == {
        (
            "iframe",
            "src",
            "https://www.youtube.com/embed/plpXPrOoV2w?enablejsapi=1&playsinline=1",
        ),
        ("a", "href", "https://youtu.be/plpXPrOoV2w"),
        ("a", "href", "transcript.md"),
        ("a", "href", "transcript.json"),
        ("a", "href", "subtitles.srt"),
        ("a", "href", "subtitles.vtt"),
        ("a", "href", "corrections.json"),
    }
    assert {
        attrs["href"]
        for tag, attrs in page.elements
        if tag == "a" and "download" in attrs
    } == {
        "transcript.md",
        "transcript.json",
        "subtitles.srt",
        "subtitles.vtt",
        "corrections.json",
    }


@pytest.mark.parametrize("review", ["missing", {}, None])
def test_missing_or_empty_review_renders(tmp_path, artifact, review):
    if review == "missing":
        artifact.pop("review")
    else:
        artifact["review"] = review

    page = PageParser(render_page(artifact, tmp_path).read_text(encoding="utf-8"))

    assert page.payload()["review"] == {
        "corrections": [],
        "flags": [],
        "method": "",
        "source_sha256": "",
    }
    assert page.payload()["cues"][0]["text"] == "修訂文字。"


def test_empty_artifact_renders(tmp_path):
    page = PageParser(render_page({}, tmp_path).read_text(encoding="utf-8"))

    assert page.payload() == {
        "metadata": {"duration": None, "model": None, "stage": None},
        "display_language": "zh-Hant-TW",
        "roles": {},
        "cues": [],
        "review": {"corrections": [], "flags": [], "method": "", "source_sha256": ""},
    }


def test_runtime_assets_contain_only_built_files():
    assets = files("transcripts").joinpath("assets")

    assert {path.name for path in assets.iterdir()} == {
        "page.js",
        "page.css",
        "page.html",
    }
    assert all(path.is_file() for path in assets.iterdir())


@pytest.mark.parametrize("name", ["page.css", "page.html"])
def test_runtime_assets_match_canonical_source(name):
    runtime = files("transcripts").joinpath("assets", name)
    source = Path(__file__).resolve().parents[1] / "web" / name

    assert runtime.read_bytes() == source.read_bytes()


def test_renderer_embeds_generated_typescript_bundle(tmp_path, artifact):
    bundle = (
        files("transcripts").joinpath("assets", "page.js").read_text(encoding="utf-8")
    )
    assert bundle.startswith("/* Generated from web/page.ts.")
    page = PageParser(render_page(artifact, tmp_path).read_text(encoding="utf-8"))
    assert page.scripts[1]["text"].strip() == bundle.strip()


def test_renderer_needs_no_typescript_source_or_frontend_tools(
    tmp_path, monkeypatch, artifact
):
    assets = files("transcripts").joinpath("assets")
    runtime_assets = tmp_path / "runtime-assets"
    runtime_assets.mkdir()
    for name in ("page.html", "page.css", "page.js"):
        (runtime_assets / name).write_text(
            assets.joinpath(name).read_text(encoding="utf-8"),
            encoding="utf-8",
        )
    monkeypatch.setattr("transcripts.web._ASSETS", runtime_assets)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PATH", "")
    destination = render_page(artifact, tmp_path / "output")
    assert not (runtime_assets / "page.ts").exists()
    assert (
        PageParser(destination.read_text(encoding="utf-8")).payload()["cues"][0]["id"]
        == 1
    )
