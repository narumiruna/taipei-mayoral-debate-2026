"""Checkpointed audio decoding, WhisperX alignment, and pyannote diarization."""

import gc
import json
import os
import subprocess
from collections import defaultdict
from contextlib import contextmanager
from importlib.metadata import version
from pathlib import Path
from typing import Any, cast

from loguru import logger

SAMPLE_RATE = 16_000
DIARIZATION_MODEL = "pyannote/speaker-diarization-3.1"


def save_json(path: Path, data: Any) -> None:
    """Replace a checkpoint only after its new contents are complete."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def prepare_run(source: Path, output: Path, model: str, limit: float | None) -> dict:
    stat = source.stat()
    settings = {
        "source": str(source.resolve()),
        "source_size": stat.st_size,
        "source_mtime_ns": stat.st_mtime_ns,
        "model": model,
        "language": "zh",
        "alignment_text": "t2s",
        "sample_rate": SAMPLE_RATE,
        "limit_seconds": limit,
        "diarization_model": DIARIZATION_MODEL,
        "versions": {
            name: version(name)
            for name in ("whisperx", "pyannote.audio", "torch", "torchaudio")
        },
    }
    manifest = output / "work" / "manifest.json"
    if manifest.exists() and load_json(manifest) != settings:
        raise ValueError("Input or settings changed. Use a different --output-dir.")
    save_json(manifest, settings)
    return settings


def decode_audio(source: Path, output: Path, limit: float | None) -> Any:
    """FFmpeg handles Opus pre-skip; timestamps start at decoded sample zero."""
    import imageio_ffmpeg
    import numpy as np
    import soundfile as sf

    waveform = output / "work" / "audio.wav"
    if not waveform.exists():
        temporary = waveform.with_suffix(".tmp.wav")
        command = [
            imageio_ffmpeg.get_ffmpeg_exe(),
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source),
            "-map",
            "0:a:0",
            "-vn",
            "-ac",
            "1",
            "-ar",
            str(SAMPLE_RATE),
            "-c:a",
            "pcm_s16le",
        ]
        if limit is not None:
            command.extend(["-t", str(limit)])
        command.append(str(temporary))
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode:
            temporary.unlink(missing_ok=True)
            raise ValueError(f"Audio decoding failed: {result.stderr.strip()}")
        temporary.replace(waveform)
    audio, rate = sf.read(waveform, dtype="float32")
    if rate != SAMPLE_RATE or audio.ndim != 1 or not audio.size:
        raise ValueError("Expected non-empty mono audio at 16 kHz.")
    return np.ascontiguousarray(audio)


@contextmanager
def checkpoint_types():
    """Allow only the data classes used in the official pyannote checkpoints."""
    import torch
    from omegaconf import DictConfig, ListConfig
    from omegaconf.base import ContainerMetadata, Metadata
    from omegaconf.nodes import AnyNode
    from pyannote.audio.core.model import Introspection
    from pyannote.audio.core.task import Problem, Resolution, Specifications
    from torch.torch_version import TorchVersion

    safe_types: list[Any] = [
        DictConfig,
        ListConfig,
        ContainerMetadata,
        Metadata,
        AnyNode,
        Problem,
        Resolution,
        Specifications,
        TorchVersion,
        Introspection,
        defaultdict,
        Any,
        list,
        dict,
        int,
        float,
        str,
        tuple,
    ]
    with torch.serialization.safe_globals(safe_types):
        yield


def release_gpu() -> None:
    import torch

    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


def transcribe(audio: Any, output: Path, model_name: str, device: str) -> dict:
    checkpoint = output / "work" / "transcribed.json"
    if checkpoint.exists():
        logger.info("Reuse transcription checkpoint")
        return load_json(checkpoint)
    import whisperx

    logger.info("Load WhisperX {} on {}", model_name, device)
    with checkpoint_types():
        model = whisperx.load_model(
            model_name,
            device=device,
            language="zh",
            compute_type="float16" if device == "cuda" else "int8",
        )
    result = model.transcribe(audio, batch_size=16 if device == "cuda" else 4)
    save_json(checkpoint, result)
    del model
    release_gpu()
    logger.info("Transcription saved: {} segments", len(result["segments"]))
    return result


def align(audio: Any, transcript: dict, output: Path, device: str) -> dict:
    checkpoint = output / "work" / "aligned.json"
    if checkpoint.exists():
        logger.info("Reuse alignment checkpoint")
        return load_json(checkpoint)
    import whisperx
    from opencc import OpenCC

    # The default Mandarin aligner has a Simplified Chinese vocabulary. Most
    # Traditional Chinese characters otherwise become wildcard tokens.
    converter = OpenCC("t2s")
    segments = [
        {**segment, "text": converter.convert(segment["text"])}
        for segment in transcript["segments"]
    ]
    logger.info("Align normalized Chinese characters with wav2vec2")
    model, metadata = whisperx.load_align_model(language_code="zh", device=device)
    result = whisperx.align(
        segments,
        model,
        metadata,
        audio,
        device,
        return_char_alignments=False,
    )
    result["language"] = "zh"
    save_json(checkpoint, result)
    del model
    release_gpu()
    logger.info("Alignment saved: {} segments", len(result["segments"]))
    return result


def diarize(audio: Any, transcript: dict, output: Path, device: str) -> dict:
    import pandas as pd
    from huggingface_hub import hf_hub_download
    from huggingface_hub.errors import GatedRepoError
    from whisperx.diarize import DiarizationPipeline, assign_word_speakers

    checkpoint = output / "work" / "diarization.json"
    if checkpoint.exists():
        logger.info("Reuse diarization checkpoint")
        turns = load_json(checkpoint)
        frame = pd.DataFrame(turns, columns=pd.Index(["start", "end", "speaker"]))
    else:
        token = os.environ.get("HF_TOKEN")
        try:
            hf_hub_download(DIARIZATION_MODEL, "config.yaml", token=token)
            hf_hub_download("pyannote/segmentation-3.0", "config.yaml", token=token)
        except GatedRepoError:
            raise ValueError(
                "Hugging Face model access is not approved. Accept the terms at "
                "https://huggingface.co/pyannote/speaker-diarization-3.1 and "
                "https://huggingface.co/pyannote/segmentation-3.0 with the active "
                "Hugging Face account, then rerun. Transcription checkpoints are preserved."
            ) from None
        logger.info("Separate speakers with pyannote.audio; infer speaker count")
        with checkpoint_types():
            model = DiarizationPipeline(
                model_name=DIARIZATION_MODEL,
                use_auth_token=token,
                device=device,
            )
        frame = cast(pd.DataFrame, model(audio))
        turns = frame[["start", "end", "speaker"]].to_dict("records")
        save_json(checkpoint, turns)
        del model
        release_gpu()
    # Do not force labels onto words that do not overlap a detected voice.
    result = dict(
        assign_word_speakers(frame, cast(Any, transcript), fill_nearest=False)
    )
    result["speaker_turns"] = turns
    save_json(output / "work" / "assigned.json", result)
    return result


def run(
    source: Path,
    output: Path,
    model: str = "large-v3",
    device: str = "cuda",
    stop_after: str = "diarize",
    limit: float | None = None,
) -> dict:
    import torch

    if device == "cuda" and not torch.cuda.is_available():
        raise ValueError(
            "CUDA is unavailable. Use --device cpu or install CUDA drivers."
        )
    torch.set_num_threads(8)
    metadata = prepare_run(source, output, model, limit)
    audio = decode_audio(source, output, limit)
    metadata["duration"] = len(audio) / SAMPLE_RATE
    logger.info("Decoded {:.3f} seconds", metadata["duration"])
    result = transcribe(audio, output, model, device)
    result["metadata"] = {**metadata, "stage": "transcribe"}
    save_json(output / "work" / "result.json", result)
    if stop_after != "transcribe":
        result = align(audio, result, output, device)
        result["metadata"] = {**metadata, "stage": "align"}
        save_json(output / "work" / "result.json", result)
    if stop_after == "diarize":
        result = diarize(audio, result, output, device)
        result["metadata"] = {**metadata, "stage": "diarize"}
        save_json(output / "work" / "result.json", result)
    return result
