from pathlib import Path

import pytest

from transcripts.site import build_site


@pytest.fixture(scope="session")
def curated_site(tmp_path_factory):
    data = Path(__file__).resolve().parents[1] / "data"
    return build_site(data, tmp_path_factory.mktemp("curated") / "site")


@pytest.fixture
def transcript():
    return {
        "metadata": {
            "source": "/recordings/debate.wav",
            "duration": 4.0,
            "stage": "diarize",
        },
        "segments": [
            {
                "start": 1.0,
                "end": 2.0,
                "text": "这是<测试>&。",
                "speaker": "SPEAKER_00",
                "words": [
                    {
                        "word": "这是<测试>&。",
                        "start": 1.0,
                        "end": 2.0,
                        "speaker": "SPEAKER_00",
                    },
                ],
            },
        ],
        "speaker_turns": [{"start": 0.0, "end": 4.0, "speaker": "SPEAKER_00"}],
    }


@pytest.fixture
def roles():
    return {
        "SPEAKER_00": {
            "role": "主持人",
            "name": "王小明",
            "evidence": [{"start": 1.0, "text": "我是主持人王小明。"}],
        },
    }
