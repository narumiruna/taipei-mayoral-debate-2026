"""Build deployment files from curated inputs with only the Python standard library."""

import json
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory

from .web import render_page

_PUBLIC_FILES = (
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


def _read_object(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ValueError(f"{path.name} must contain valid UTF-8 JSON.") from error
    if not isinstance(value, dict):
        # Treat JSON syntax and schema errors as invalid input values.
        raise ValueError(f"{path.name} must contain a JSON object.")  # noqa: TRY004
    return value


def build_site(data_dir: Path, destination: Path) -> Path:
    """Validate and stage public files, then replace the deployment directory."""
    data_dir = Path(data_dir).resolve()
    destination = Path(destination)
    if destination.is_symlink() or (destination.exists() and not destination.is_dir()):
        raise ValueError("The destination must be a directory, not a symlink or file.")
    output = destination.resolve()
    if data_dir.is_relative_to(output) or output.is_relative_to(data_dir):
        raise ValueError("Input and destination directories must not overlap.")

    for name in _PUBLIC_FILES:
        path = data_dir / name
        if not path.is_file():
            raise FileNotFoundError(f"Required public input is not a file: {path}")
    artifact = _read_object(data_dir / "transcript.json")
    ledger_path = data_dir / "fact-checks.json"
    names = list(_PUBLIC_FILES)
    ledger = None
    if ledger_path.exists() or ledger_path.is_symlink():
        ledger = _read_object(ledger_path)
        names.append(ledger_path.name)
    chapters_path = data_dir / "chapters.json"
    chapters = None
    if chapters_path.exists() or chapters_path.is_symlink():
        chapters = _read_object(chapters_path)

    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=f".{output.name}-", dir=output.parent) as temporary:
        temporary_dir = Path(temporary)
        staging = temporary_dir / "staged"
        staging.mkdir()
        for name in names:
            shutil.copyfile(data_dir / name, staging / name)
        render_page(artifact, staging, fact_checks=ledger, chapters=chapters)

        backup = temporary_dir / "previous"
        had_previous = output.exists()
        if had_previous:
            output.rename(backup)
        try:
            staging.rename(output)
        except BaseException:
            if had_previous:
                backup.rename(output)
            raise

    return destination / "index.html"


if __name__ == "__main__":
    print(build_site(Path("data"), Path("site")))
