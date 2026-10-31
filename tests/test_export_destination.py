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
    assert (
        "https://www.youtube.com/embed/plpXPrOoV2w?enablejsapi=1&amp;playsinline=1"
        in page
    )
    assert 'href="https://youtu.be/plpXPrOoV2w"' in page
    assert "../outputs/" not in page
    assert "media/debate.mp4" not in page
    assert artifact["segments_text_status"] == "original_asr_before_display_review"


def test_speaker_review_replays_without_changing_checkpoint(
    tmp_path, transcript, roles
):
    work, destination = tmp_path / "work", tmp_path / "data"
    segment = transcript["segments"][0]
    segment["text"] = "謝謝。"
    segment["words"] = [
        {"word": "謝", "start": 1.0, "end": 1.9, "speaker": "SPEAKER_00"},
        {"word": "謝。", "start": 1.9, "end": 2.0},
    ]
    checkpoint = work / "work" / "result.json"
    pipeline.save_json(checkpoint, transcript)
    original = checkpoint.read_bytes()
    cues = subtitles.make_cues(transcript, roles)
    pipeline.save_json(destination / "speaker-roles.json", roles)
    pipeline.save_json(
        destination / "corrections.json",
        {
            "source_sha256": source_fingerprint(cues),
            "corrections": [],
            "speaker_corrections": [
                {
                    "id": "S002",
                    "cue_id": 2,
                    "before": "UNKNOWN",
                    "after": "SPEAKER_00",
                    "reason": "延續前一句的謝謝。",
                    "evidence": "前後文與既有時間資料。",
                }
            ],
            "flags": [],
        },
    )
    runner = CliRunner()
    for _ in range(2):
        response = runner.invoke(
            cli.app,
            [
                "export",
                "--output-dir",
                str(work),
                "--destination",
                str(destination),
                "--roles",
                str(destination / "speaker-roles.json"),
            ],
        )
        assert response.exit_code == 0, response.output
    artifact = pipeline.load_json(destination / "transcript.json")
    reviewed = artifact["cues"][1]
    assert reviewed["speaker"] == "SPEAKER_00"
    assert reviewed["original_speaker"] == "UNKNOWN"
    assert reviewed["original_label"] == "說話者未確認"
    assert reviewed["speaker_correction_id"] == "S002"
    assert all(reviewed[key] == cues[1][key] for key in ("id", "start", "end", "text"))
    assert checkpoint.read_bytes() == original
    assert artifact["review"]["flags"] == []
    summary = pipeline.load_json(destination / "validation.json")
    assert summary["unassigned_cues"] == 0
    assert summary["speaker_corrected_cues"] == 1
    for name in ["subtitles.srt", "subtitles.vtt", "transcript.md"]:
        text = (destination / name).read_text(encoding="utf-8")
        assert "主持人／王小明" in text
        assert "說話者未確認" not in text


def test_youtube_page_is_independent_of_export_directory(tmp_path):
    outputs = [tmp_path / "data", tmp_path / 'nested "exports"' / "site"]
    pages = [
        render_page({"cues": []}, output).read_text(encoding="utf-8")
        for output in outputs
    ]
    assert pages[0] == pages[1]
    for page in pages:
        assert (
            "https://www.youtube.com/embed/plpXPrOoV2w?enablejsapi=1&amp;playsinline=1"
            in page
        )
        assert 'href="https://youtu.be/plpXPrOoV2w"' in page
        assert "media/debate.mp4" not in page
        assert "media/poster.jpg" not in page
        assert str(tmp_path) not in page
        for name in (
            "transcript.md",
            "transcript.json",
            "subtitles.srt",
            "subtitles.vtt",
            "corrections.json",
        ):
            assert f'href="{name}"' in page


def test_character_conversion_preserves_spoken_terms():
    words = [{"word": "支持候选人，次分区通过预算法。", "start": 0, "end": 3}]
    result = {
        "metadata": {"duration": 3},
        "segments": [{"text": words[0]["word"], "words": words}],
    }
    (cue,) = subtitles.make_cues(result)
    assert cue["text"] == "支持候選人，次分區通過預算法。"
