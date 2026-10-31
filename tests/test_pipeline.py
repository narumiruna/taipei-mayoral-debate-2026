import os
import sys
from types import SimpleNamespace

import pytest

from debate import pipeline


@pytest.fixture
def run_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "version", lambda name: "test-version")
    source = tmp_path / "debate.wav"
    source.write_bytes(b"local audio fixture")
    return source, tmp_path / "output"


def test_manifest_reuses_identical_source_and_settings(run_paths):
    source, output = run_paths

    first = pipeline.prepare_run(source, output, "large-v3", 60.0)
    second = pipeline.prepare_run(source, output, "large-v3", 60.0)

    assert first == second
    assert pipeline.load_json(output / "work" / "manifest.json") == first
    assert first["source"] == str(source.resolve())
    assert first["source_size"] == source.stat().st_size
    assert first["source_mtime_ns"] == source.stat().st_mtime_ns
    assert first["model"] == "large-v3"
    assert first["limit_seconds"] == 60.0


def test_alignment_normalizes_traditional_text_and_reuses_checkpoint(
    tmp_path, monkeypatch
):
    observed = []

    def fake_align(segments, *args, **kwargs):
        observed.extend(segments)
        return {"segments": segments, "word_segments": []}

    monkeypatch.setitem(
        sys.modules,
        "whisperx",
        SimpleNamespace(
            load_align_model=lambda **kwargs: (object(), {}),
            align=fake_align,
        ),
    )
    monkeypatch.setattr(pipeline, "release_gpu", lambda: None)
    original = {"segments": [{"start": 0, "end": 1, "text": "歡迎臺北候選人"}]}

    first = pipeline.align(None, original, tmp_path, "cpu")
    second = pipeline.align(None, original, tmp_path, "cpu")

    assert observed == [{"start": 0, "end": 1, "text": "欢迎台北候选人"}]
    assert original["segments"][0]["text"] == "歡迎臺北候選人"
    assert first == second
    assert first["language"] == "zh"


@pytest.mark.parametrize(
    "change", ["source-path", "source-size", "source-mtime", "model", "limit"]
)
def test_manifest_rejects_changed_inputs_without_replacing_checkpoint(
    run_paths, change
):
    source, output = run_paths
    original = pipeline.prepare_run(source, output, "large-v3", None)
    checkpoint = output / "work" / "result.json"
    pipeline.save_json(checkpoint, {"segments": ["existing transcription"]})
    model, limit = "large-v3", None

    if change == "source-path":
        replacement = source.with_name("different.wav")
        replacement.write_bytes(source.read_bytes())
        stat = source.stat()
        os.utime(replacement, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        source = replacement
    elif change == "source-size":
        source.write_bytes(b"changed audio with a different size")
    elif change == "source-mtime":
        stat = source.stat()
        os.utime(source, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
    elif change == "model":
        model = "small"
    else:
        limit = 60.0

    with pytest.raises(ValueError, match="Input or settings changed"):
        pipeline.prepare_run(source, output, model, limit)

    assert pipeline.load_json(output / "work" / "manifest.json") == original
    assert pipeline.load_json(checkpoint) == {"segments": ["existing transcription"]}
