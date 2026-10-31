import json

import pytest
from typer.testing import CliRunner

from transcripts import cli, pipeline

runner = CliRunner()


@pytest.fixture
def no_inference(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("This command must not run audio decoding or model inference.")

    for name in ("run", "decode_audio", "transcribe", "align", "diarize"):
        monkeypatch.setattr(pipeline, name, forbidden)


@pytest.mark.parametrize(
    "arguments",
    [
        ["missing.wav", "--output-dir", "output"],
        ["directory", "--output-dir", "output"],
        ["audio.wav"],
        ["audio.wav", "--output-dir", "existing-file"],
        ["audio.wav", "--output-dir", "output", "--device", "gpu"],
        ["audio.wav", "--output-dir", "output", "--stop-after", "unknown"],
        ["audio.wav", "--output-dir", "output", "--limit-seconds", "0"],
        ["audio.wav", "--output-dir", "output", "--limit-seconds", "-1"],
        ["audio.wav", "--output-dir", "output", "--limit-seconds", "0.09"],
        ["audio.wav", "--output-dir", "output", "--roles", "missing.json"],
        ["audio.wav", "--output-dir", "output", "--roles", "directory"],
    ],
)
def test_transcribe_rejects_invalid_arguments(
    tmp_path, monkeypatch, no_inference, arguments
):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "audio.wav").write_bytes(b"not decoded")
    (tmp_path / "existing-file").write_text("not a directory", encoding="utf-8")
    (tmp_path / "directory").mkdir()

    result = runner.invoke(cli.app, ["transcribe", *arguments])

    assert result.exit_code == 2, result.output
    assert "Error" in result.output


@pytest.mark.parametrize("output_kind", ["missing", "file"])
def test_export_rejects_invalid_output_directory(tmp_path, no_inference, output_kind):
    output = tmp_path / "output"
    if output_kind == "file":
        output.write_text("not a directory", encoding="utf-8")

    result = runner.invoke(cli.app, ["export", "--output-dir", str(output)])

    assert result.exit_code == 2, result.output


def test_export_reports_missing_checkpoint(tmp_path, no_inference):
    result = runner.invoke(cli.app, ["export", "--output-dir", str(tmp_path)])

    assert result.exit_code == 1
    assert not (tmp_path / "transcript.json").exists()


@pytest.mark.parametrize("with_roles", [False, True])
def test_export_uses_checkpoint_without_inference(
    tmp_path, no_inference, transcript, roles, with_roles
):
    checkpoint = tmp_path / "work" / "result.json"
    pipeline.save_json(checkpoint, transcript)
    original = checkpoint.read_bytes()
    arguments = ["export", "--output-dir", str(tmp_path)]
    if with_roles:
        role_file = tmp_path / "roles.json"
        pipeline.save_json(role_file, roles)
        arguments.extend(["--roles", str(role_file)])

    result = runner.invoke(cli.app, arguments)

    assert result.exit_code == 0, result.output
    assert checkpoint.read_bytes() == original
    for name in ("subtitles.srt", "subtitles.vtt", "transcript.md", "validation.json"):
        assert (tmp_path / name).is_file()
    artifact = json.loads((tmp_path / "transcript.json").read_text(encoding="utf-8"))
    assert artifact["segments"][0]["text"] == "這是<測試>&。"
    assert artifact["segments"][0]["words"][0]["word"] == "這是<測試>&。"
    assert artifact["cues"][0]["text"] == "這是<測試>&。"
    assert artifact["cues"][0]["label"] == (
        "主持人／王小明" if with_roles else "SPEAKER_00（角色未確認）"
    )
    assert artifact["roles"] == (roles if with_roles else {})


@pytest.mark.parametrize(
    "role_map",
    [
        {"SPEAKER_00": {"role": "主持人"}},
        {"SPEAKER_00": {"role": 1, "evidence": [{"start": 1, "text": "claim"}]}},
        {"SPEAKER_99": {"role": "主持人", "evidence": [{"start": 1, "text": "claim"}]}},
        ["not a role object"],
    ],
)
def test_export_rejects_invalid_roles(tmp_path, no_inference, transcript, role_map):
    pipeline.save_json(tmp_path / "work" / "result.json", transcript)
    role_file = tmp_path / "roles.json"
    pipeline.save_json(role_file, role_map)

    result = runner.invoke(
        cli.app,
        ["export", "--output-dir", str(tmp_path), "--roles", str(role_file)],
    )

    assert result.exit_code == 1
    assert not (tmp_path / "transcript.json").exists()
