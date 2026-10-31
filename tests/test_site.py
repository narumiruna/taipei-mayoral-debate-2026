import json
import os
import shutil
import subprocess
import sys
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path

import pytest

from transcripts import site

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_FILES = (
    "transcript.json",
    "transcript.md",
    "subtitles.srt",
    "subtitles.vtt",
    "corrections.json",
    "review-needed.json",
    "speaker-roles.json",
    "speaker-review.md",
    "validation.json",
    "verification.json",
)
DOWNLOADS = {
    "transcript.json",
    "transcript.md",
    "subtitles.srt",
    "subtitles.vtt",
    "corrections.json",
}


def _write_json(path, value):
    text = json.dumps(value, ensure_ascii=False, indent=2)
    path.write_bytes(text.replace("\n", "\r\n").encode("utf-8") + b"\r\n")


def _read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _tree(root):
    return {
        path.relative_to(root).as_posix(): path.read_bytes() if path.is_file() else None
        for path in root.rglob("*")
    }


class Page(HTMLParser):
    def __init__(self, path):
        super().__init__()
        self.downloads = []
        self.data = []
        self.in_payload = False
        self.feed(path.read_text(encoding="utf-8"))
        self.close()
        self.payload = json.loads("".join(self.data))

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a" and "download" in attrs:
            self.downloads.append(attrs["href"])
        if tag == "script":
            self.in_payload = attrs.get("id") == "debate-data"

    def handle_endtag(self, tag):
        if tag == "script":
            self.in_payload = False

    def handle_data(self, data):
        if self.in_payload:
            self.data.append(data)


@pytest.fixture
def public_data(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    artifact = {
        "metadata": {"duration": 3.0, "model": "fixture", "stage": "diarize"},
        "display_language": "zh-Hant-TW",
        "roles": {"SPEAKER_00": {"role": "辯論者", "name": "王小明"}},
        "cues": [
            {
                "id": 1,
                "start": 1.0,
                "end": 3.0,
                "speaker": "SPEAKER_00",
                "label": "王小明",
                "text": "這是原話 <文字> & 引述。",
            }
        ],
        "review": {"source_sha256": "a" * 64, "method": "Fixture review."},
    }
    ledger = {
        "version": 1,
        "reviewed_at": "2026-10-31",
        "scope": "Only the listed claim.",
        "method": "Compare the quote with a public source.",
        "source_sha256": "a" * 64,
        "items": [
            {
                "id": "FC001",
                "speaker": "SPEAKER_00",
                "title": "Fixture claim",
                "verdict": "needs-context",
                "summary": "The source supplies context.",
                "analysis": ["The source uses a different scope."],
                "limitations": "Only this claim is checked.",
                "quotes": [{"cue_id": 1, "text": artifact["cues"][0]["text"]}],
                "sources": [
                    {
                        "title": "Fixture report",
                        "publisher": "Fixture publisher",
                        "published_at": "2026-10-30",
                        "url": "https://example.org/report",
                        "evidence": "The report defines its scope.",
                    }
                ],
            }
        ],
    }
    for name in PUBLIC_FILES:
        if name.endswith(".json"):
            _write_json(data / name, {"fixture": name})
        else:
            (data / name).write_bytes(f"Fixture {name}\r\n".encode())
    _write_json(data / "transcript.json", artifact)
    _write_json(data / "fact-checks.json", ledger)
    # Only the two rendered JSON inputs require UTF-8; downloads are opaque bytes.
    (data / "transcript.md").write_bytes(b"# Fixture\r\n\xff\x00\r\n")
    return data


def _old_site(tmp_path):
    destination = tmp_path / "site"
    destination.mkdir()
    (destination / "index.html").write_bytes(b"PREVIOUS HTML\n")
    (destination / "fact-checks.json").write_bytes(b"PREVIOUS LEDGER\n")
    (destination / "archive").mkdir()
    (destination / "archive" / "old.txt").write_bytes(b"PREVIOUS FILE\n")
    return destination


def test_build_stages_explicit_ledger_and_copies_exact_bytes(
    tmp_path, monkeypatch, public_data
):
    destination = tmp_path / "nested" / "site"
    original = _tree(public_data)
    render_page = site.render_page
    calls = []

    def render_staged(artifact, staging, *, fact_checks):
        assert staging.parent.parent == destination.parent
        assert staging != destination
        assert not destination.exists()
        assert _tree(staging) == original
        calls.append((artifact, fact_checks))
        return render_page(artifact, staging, fact_checks=fact_checks)

    monkeypatch.setattr(site, "render_page", render_staged)

    result = site.build_site(public_data, destination)

    assert result == destination / "index.html"
    assert result.is_file()
    assert calls == [
        (
            _read_json(public_data / "transcript.json"),
            _read_json(public_data / "fact-checks.json"),
        )
    ]
    assert {path.name for path in destination.iterdir()} == {
        *PUBLIC_FILES,
        "fact-checks.json",
        "index.html",
    }
    for name, contents in original.items():
        assert (destination / name).read_bytes() == contents
    page = Page(result)
    assert page.payload["cues"] == calls[0][0]["cues"]
    assert page.payload["fact_checks"] == calls[0][1]
    assert set(page.downloads) == DOWNLOADS
    assert len(page.downloads) == len(DOWNLOADS)
    for name in page.downloads:
        assert Path(name).name == name
        assert (result.parent / name).is_file()
    assert _tree(public_data) == original
    assert not (public_data / "index.html").exists()
    assert list(destination.parent.iterdir()) == [destination]


def test_unknown_files_secrets_media_and_directories_are_not_published(
    tmp_path, public_data
):
    for name in (
        "index.html",
        ".env",
        "credentials.json",
        "token.txt",
        "debate.mp4",
        "unknown.json",
        "media/debate.mp4",
        "private/notes.md",
    ):
        path = public_data / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"PRIVATE_SITE_INPUT\n")
    (public_data / "empty-directory").mkdir()
    original = _tree(public_data)
    destination = tmp_path / "site"

    result = site.build_site(public_data, destination)

    assert set(_tree(destination)) == {*PUBLIC_FILES, "fact-checks.json", "index.html"}
    assert b"PRIVATE_SITE_INPUT" not in result.read_bytes()
    assert _tree(public_data) == original


@pytest.mark.parametrize("with_ledger", [True, False])
def test_repeated_builds_are_byte_identical(tmp_path, public_data, with_ledger):
    if not with_ledger:
        (public_data / "fact-checks.json").unlink()
    original = _tree(public_data)
    destination = tmp_path / "site"
    site.build_site(public_data, destination)
    first = _tree(destination)

    result = site.build_site(public_data, destination)

    assert _tree(destination) == first
    assert ("fact_checks" in Page(result).payload) == with_ledger
    assert _tree(public_data) == original
    assert {path.name for path in tmp_path.iterdir()} == {"data", "site"}


def test_rebuild_removes_stale_files_and_removed_optional_ledger(tmp_path, public_data):
    destination = tmp_path / "site"
    site.build_site(public_data, destination)
    assert "fact_checks" in Page(destination / "index.html").payload
    (destination / "stale.json").write_bytes(b"STALE")
    (destination / ".env").write_bytes(b"SECRET")
    (destination / "media").mkdir()
    (destination / "media" / "debate.mp4").write_bytes(b"MEDIA")
    (public_data / "fact-checks.json").unlink()
    original = _tree(public_data)

    result = site.build_site(public_data, destination)

    assert set(_tree(destination)) == {*PUBLIC_FILES, "index.html"}
    assert "fact_checks" not in Page(result).payload
    assert _tree(public_data) == original
    assert not (public_data / "index.html").exists()
    assert {path.name for path in tmp_path.iterdir()} == {"data", "site"}


@pytest.mark.parametrize("missing", PUBLIC_FILES)
def test_missing_required_input_preserves_previous_output(
    tmp_path, public_data, missing
):
    destination = _old_site(tmp_path)
    (public_data / missing).unlink()
    before = _tree(tmp_path)

    with pytest.raises(FileNotFoundError, match=missing):
        site.build_site(public_data, destination)

    assert _tree(tmp_path) == before


@pytest.mark.parametrize("name", ["transcript.md", "fact-checks.json"])
def test_named_input_directory_is_not_copied(tmp_path, public_data, name):
    destination = _old_site(tmp_path)
    path = public_data / name
    path.unlink()
    path.mkdir()
    (path / "secret.txt").write_bytes(b"SECRET")
    before = _tree(tmp_path)

    with pytest.raises(OSError):
        site.build_site(public_data, destination)

    assert _tree(tmp_path) == before


@pytest.mark.parametrize("name", ["transcript.json", "fact-checks.json"])
@pytest.mark.parametrize(
    "contents",
    [b"null", b"[]", b'"text"', b"1", b"true", b"{broken", b'{"text":"\xff"}'],
)
def test_invalid_json_preserves_previous_output(tmp_path, public_data, name, contents):
    destination = _old_site(tmp_path)
    (public_data / name).write_bytes(contents)
    before = _tree(tmp_path)

    with pytest.raises(ValueError, match=name):
        site.build_site(public_data, destination)

    assert _tree(tmp_path) == before


def test_stale_quote_preserves_previous_output_and_source(tmp_path, public_data):
    destination = _old_site(tmp_path)
    ledger = _read_json(public_data / "fact-checks.json")
    ledger["items"][0]["quotes"][0]["text"] = "Stale quote."
    _write_json(public_data / "fact-checks.json", ledger)
    before = _tree(tmp_path)

    with pytest.raises(ValueError, match="exactly match cue"):
        site.build_site(public_data, destination)

    assert _tree(tmp_path) == before


@pytest.mark.parametrize("failure", ["copy", "render"])
def test_staging_failure_preserves_previous_output_and_source(
    tmp_path, monkeypatch, public_data, failure
):
    destination = _old_site(tmp_path)
    before = _tree(tmp_path)
    copyfile = shutil.copyfile

    def fail_copy(source, target):
        if source.name == "subtitles.srt":
            raise OSError("Copy failed.")
        return copyfile(source, target)

    def fail_render(artifact, staging, *, fact_checks):
        (staging / "index.html").write_bytes(b"PARTIAL HTML")
        raise OSError("Render failed.")

    if failure == "copy":
        monkeypatch.setattr(site.shutil, "copyfile", fail_copy)
    else:
        monkeypatch.setattr(site, "render_page", fail_render)

    with pytest.raises(OSError, match="failed"):
        site.build_site(public_data, destination)

    assert _tree(tmp_path) == before


@pytest.mark.parametrize("existing", [True, False])
def test_publication_failure_restores_previous_directory(
    tmp_path, monkeypatch, public_data, existing
):
    destination = _old_site(tmp_path) if existing else tmp_path / "site"
    before = _tree(tmp_path)
    rename = Path.rename
    renames = []
    publication_failed = False

    def fail_publication(source, target):
        nonlocal publication_failed
        target = Path(target)
        renames.append((source, target))
        if target == destination and not publication_failed:
            publication_failed = True
            assert (source / "index.html").is_file()
            assert source.parent.parent == destination.parent
            assert not destination.exists()
            raise OSError("Publication failed.")
        return rename(source, target)

    monkeypatch.setattr(Path, "rename", fail_publication)

    with pytest.raises(OSError, match="Publication failed"):
        site.build_site(public_data, destination)

    assert publication_failed
    assert len(renames) == (3 if existing else 1)
    if existing:
        assert renames[0][0] == destination
        assert renames[0][1] == renames[-1][0]
        assert renames[0][1].parent == renames[1][0].parent
        assert renames[-1][1] == destination
    assert _tree(tmp_path) == before


@pytest.mark.parametrize(
    "relationship",
    ["same", "child", "parent", "normalized", "destination-alias", "input-alias"],
)
def test_overlapping_resolved_directories_are_rejected(
    tmp_path, public_data, relationship
):
    source = public_data
    if relationship == "same":
        destination = source
    elif relationship == "child":
        destination = source / "site"
    elif relationship == "parent":
        destination = tmp_path
    elif relationship == "normalized":
        destination = source / "missing" / ".."
    else:
        alias = tmp_path / "data-alias"
        alias.symlink_to(source, target_is_directory=True)
        if relationship == "destination-alias":
            destination = alias / "site"
        else:
            source = alias
            destination = tmp_path
    before = _tree(tmp_path)

    with pytest.raises(ValueError, match="overlap"):
        site.build_site(source, destination)

    assert _tree(tmp_path) == before


@pytest.mark.parametrize("target_kind", ["directory", "file", "missing"])
def test_symlink_destination_is_rejected_without_changing_target(
    tmp_path, public_data, target_kind
):
    target = tmp_path / "unrelated"
    if target_kind == "directory":
        target.mkdir()
        (target / "keep.txt").write_bytes(b"KEEP")
    elif target_kind == "file":
        target.write_bytes(b"KEEP")
    destination = tmp_path / "site"
    destination.symlink_to(target, target_is_directory=target_kind == "directory")
    before = _tree(tmp_path)

    with pytest.raises(ValueError, match="destination.*symlink"):
        site.build_site(public_data, destination)

    assert destination.is_symlink()
    assert destination.readlink() == target
    assert _tree(tmp_path) == before
    if target_kind == "missing":
        assert not target.exists()


def test_file_destination_is_rejected(tmp_path, public_data):
    destination = tmp_path / "site"
    destination.write_bytes(b"UNRELATED FILE")
    before = _tree(tmp_path)

    with pytest.raises(ValueError, match="destination.*directory"):
        site.build_site(public_data, destination)

    assert _tree(tmp_path) == before


def test_module_command_uses_only_stdlib_in_copied_runtime(tmp_path, public_data):
    runtime = tmp_path / "runtime"
    package = runtime / "transcripts"
    package.mkdir(parents=True)
    for name in ("__init__.py", "site.py", "web.py", "fact_checks.py"):
        shutil.copyfile(ROOT / "transcripts" / name, package / name)
    shutil.copytree(ROOT / "transcripts" / "assets", package / "assets")
    data = runtime / "data"
    shutil.copytree(public_data, data)
    original = _tree(data)
    environment = {
        key: value
        for key, value in os.environ.items()
        if key not in {"PYTHONPATH", "PYTHONHOME"}
    }
    environment["PATH"] = ""

    response = subprocess.run(
        [sys.executable, "-S", "-m", "transcripts.site"],
        cwd=runtime,
        env=environment,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )

    assert response.returncode == 0, response.stderr
    assert response.stdout == "site/index.html\n"
    assert response.stderr == ""
    destination = runtime / "site"
    assert set(_tree(destination)) == {*PUBLIC_FILES, "fact-checks.json", "index.html"}
    page = Page(destination / "index.html")
    assert page.payload["fact_checks"] == _read_json(data / "fact-checks.json")
    assert set(page.downloads) == DOWNLOADS
    for name, contents in original.items():
        assert (destination / name).read_bytes() == contents
    assert _tree(data) == original
    assert _tree(public_data) == original
    assert not (data / "index.html").exists()


def test_committed_inputs_build_all_ten_curated_fact_checks(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    for name in (*PUBLIC_FILES, "fact-checks.json"):
        shutil.copyfile(ROOT / "data" / name, data / name)
    original = _tree(data)
    ledger = _read_json(data / "fact-checks.json")

    result = site.build_site(data, tmp_path / "site")

    embedded = Page(result).payload["fact_checks"]
    assert embedded == ledger
    assert [item["id"] for item in embedded["items"]] == [
        f"FC{number:03d}" for number in range(1, 11)
    ]
    assert Counter(item["speaker"] for item in embedded["items"]) == {
        "SPEAKER_03": 5,
        "SPEAKER_04": 5,
    }
    assert _tree(data) == original
    assert not (data / "index.html").exists()
