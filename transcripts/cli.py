"""Command-line entry point for debate transcription and role-aware exports."""

from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer
from loguru import logger

from . import pipeline, subtitles

app = typer.Typer(no_args_is_help=True, pretty_exceptions_enable=False)


class Stage(StrEnum):
    transcribe = "transcribe"
    align = "align"
    diarize = "diarize"


class Device(StrEnum):
    cuda = "cuda"
    cpu = "cpu"


@app.command()
def transcribe(
    audio: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
    output_dir: Annotated[Path, typer.Option(file_okay=False)],
    model: str = "large-v3",
    device: Device = Device.cuda,
    stop_after: Stage = Stage.diarize,
    limit_seconds: Annotated[float | None, typer.Option(min=0.1)] = None,
    roles: Annotated[Path | None, typer.Option(exists=True, dir_okay=False)] = None,
    corrections: Annotated[
        Path | None, typer.Option(exists=True, dir_okay=False)
    ] = None,
    destination: Annotated[Path | None, typer.Option(file_okay=False)] = None,
) -> None:
    """Transcribe mono/stereo media; resume unchanged checkpoints on rerun."""
    try:
        result = pipeline.run(
            audio,
            output_dir,
            model,
            device.value,
            stop_after.value,
            limit_seconds,
        )
        role_map = pipeline.load_json(roles) if roles else {}
        target = destination or output_dir
        summary = subtitles.export(
            result,
            target,
            role_map,
            corrections,
            media_dir=output_dir / "media",
        )
        logger.info("Exports saved in {}: {}", target, summary)
    except (TypeError, ValueError) as error:
        logger.error("{}", error)
        raise typer.Exit(1) from None


@app.command("export")
def export_transcript(
    output_dir: Annotated[Path, typer.Option(exists=True, file_okay=False)],
    roles: Annotated[Path | None, typer.Option(exists=True, dir_okay=False)] = None,
    corrections: Annotated[
        Path | None, typer.Option(exists=True, dir_okay=False)
    ] = None,
    destination: Annotated[Path | None, typer.Option(file_okay=False)] = None,
) -> None:
    """Regenerate reviewed text and HTML exports without model inference."""
    checkpoint = output_dir / "work" / "result.json"
    if not checkpoint.exists():
        logger.error("No result checkpoint: {}", checkpoint)
        raise typer.Exit(1)
    try:
        result = pipeline.load_json(checkpoint)
        role_map = pipeline.load_json(roles) if roles else {}
        target = destination or output_dir
        summary = subtitles.export(
            result,
            target,
            role_map,
            corrections,
            media_dir=output_dir / "media",
        )
        logger.info("Exports saved in {}: {}", target, summary)
    except (TypeError, ValueError) as error:
        logger.error("{}", error)
        raise typer.Exit(1) from None


def main() -> None:
    app()
