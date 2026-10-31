import json

from typer.testing import CliRunner

from transcripts import cli, pipeline, subtitles
from transcripts.review import source_fingerprint
from transcripts.web import render_page


def test_reviewed_exports_use_separate_destination(tmp_path, transcript, roles):
    work = tmp_path / "outputs" / "recording"
    destination = tmp_path / "data"
    destination.mkdir(parents=True)
    checkpoint = work / "work" / "result.json"
    transcript["metadata"]["source_mtime_ns"] = 123
    pipeline.save_json(checkpoint, transcript)
    original_checkpoint = checkpoint.read_bytes()
    pipeline.save_json(destination / "speaker-roles.json", roles)
    cues = subtitles.make_cues(transcript, roles)
    ledger = {
        "source_sha256": source_fingerprint(cues),
        "method": "Test review",
        "corrections": [
            {
                "id": "C001",
                "cue_id": 1,
                "before": cues[0]["text"],
                "after": "這是校對文字。",
                "reason": "Test correction",
                "evidence": "Local test fixture",
            }
        ],
        "flags": [],
    }
    pipeline.save_json(destination / "corrections.json", ledger)
    command = [
        "export",
        "--output-dir",
        str(work),
        "--destination",
        str(destination),
        "--roles",
        str(destination / "speaker-roles.json"),
    ]
    runner = CliRunner()
    for _ in range(2):
        response = runner.invoke(cli.app, command)
        assert response.exit_code == 0, response.output
    artifact = pipeline.load_json(destination / "transcript.json")
    assert artifact["cues"][0]["text"] == "這是校對文字。"
    assert artifact["cues"][0]["original_text"] == cues[0]["text"]
    assert artifact["metadata"]["source"] == "debate.wav"
    assert "source_mtime_ns" not in artifact["metadata"]
    assert "/recordings/" not in json.dumps(artifact)
    assert checkpoint.read_bytes() == original_checkpoint
    assert not (work / "transcript.json").exists()
    assert not (destination / "work").exists()
    for name in ["subtitles.srt", "subtitles.vtt", "transcript.md"]:
        assert "這是校對文字。" in (destination / name).read_text(encoding="utf-8")
    page = (destination / "index.html").read_text(encoding="utf-8")
    assert "../outputs/recording/media/debate.mp4" in page
    assert artifact["segments_text_status"] == "original_asr_before_display_review"


def test_page_encodes_relative_media_paths(tmp_path):
    output = tmp_path / "data"
    media = tmp_path / 'media "clips"'
    page = render_page({"cues": []}, output, media_dir=media).read_text(
        encoding="utf-8"
    )
    assert "../media%20%22clips%22/debate.mp4" in page
    assert "../media%20%22clips%22/poster.jpg" in page
    assert str(tmp_path) not in page


def test_character_conversion_preserves_spoken_terms():
    words = [{"word": "支持候选人，次分区通过预算法。", "start": 0, "end": 3}]
    result = {
        "metadata": {"duration": 3},
        "segments": [{"text": words[0]["word"], "words": words}],
    }
    (cue,) = subtitles.make_cues(result)
    assert cue["text"] == "支持候選人，次分區通過預算法。"
