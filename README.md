# Debate record

A Traditional Chinese debate transcript with timecoded speaker labels, an
interactive HTML reader, and an auditable text-review ledger. WhisperX handles
transcription and alignment. pyannote.audio separates speakers.

## Project layout

| Path | Responsibility |
| --- | --- |
| `transcripts/` | Python package: transcription, alignment, speaker separation, review, subtitles, and export |
| `transcripts/assets/` | Generated JavaScript and copied HTML/CSS used by the Python exporter |
| `web/` | Frontend TypeScript, CSS, and HTML source |
| `data/` | Curated transcripts, subtitles, review records, and the single-file web page |
| `raw/` | Original media; ignored |
| `outputs/` | Local media derivatives, logs, screenshots, and inference checkpoints; ignored |
| `tests/` | Python regression tests |

The Python package uses a flat layout without `src/`. Root configuration files
serve this one project. Python imports use `transcripts`; the distribution and
console command remain `2026-debate`.

## Results

Open [`data/index.html`](data/index.html).
The page has transcript search, speaker filters, video seeking, correction
comparisons, unresolved review items, and download links. CSS, JavaScript, and
transcript data are embedded. No CDN or external service is required.

| Committable file under `data/` | Contents |
| --- | --- |
| `index.html` | Responsive transcript and review page |
| `transcript.md` | Reviewed timecoded transcript |
| `transcript.json` | Reviewed cues, original source segments, roles, and review records |
| `subtitles.srt`, `subtitles.vtt` | Reviewed subtitles |
| `speaker-roles.json` | Speaker mapping and introduction evidence |
| `corrections.json` | Exact before/after text, evidence, source fingerprint, and unresolved flags |
| `review-needed.json` | Unresolved intervals with timestamps |
| `speaker-review.md` | Role mapping and review limits |
| `validation.json`, `verification.json` | Output checks and counts |

These are text files intended for version control. Published metadata contains
only the source filename, not an absolute local path or source modification time.

Large media, screenshots, logs, and inference checkpoints stay in ignored
`outputs/`. Do not add those files to a commit. The web page uses relative links
to `outputs/plpXPrOoV2w/media/debate.mp4` and `media/poster.jpg`.
Without local media, transcript search and review remain available.

## Deployment

The GitHub Actions workflow in [`.github/workflows/deploy.yml`](.github/workflows/deploy.yml)
publishes `data/` to GitHub Pages. It runs when a push to `main` changes `data/`
or the workflow file. To deploy manually, select **Actions → Deploy webpage →
Run workflow** on `main`.

In **Settings → Pages → Build and deployment**, set **Source** to **GitHub Actions**.
The published site is <https://narumiruna.github.io/taipei-mayoral-debate-2026/>.

The workflow publishes the committed HTML, transcripts, subtitles, and review
records without installing Python or running model inference. Rebuild and
re-export the page before pushing frontend changes. Only `data/` is uploaded;
`raw/`, `outputs/`, and local credentials are excluded. Video and poster files
are not hosted, so video playback is unavailable on the published page.
Transcript search, review views, and downloads remain available.

## Preview

Open the HTML file directly, or run this command from the repository root:

```bash
uv run --with rangehttpserver python -m RangeHTTPServer 8765 --bind 127.0.0.1
```

Then open <http://127.0.0.1:8765/data/>. HTTP preview supports byte-range
requests for the large video and avoids local-file caption restrictions. The
server listens only on the local interface. Do not expose it as a public server.

## Review status

The recording has 1,082 cues and six speaker clusters: two debaters, two hosts,
and two reporters. The user supplied the debater name labels. Roles were mapped
from introductions and turn-taking, not from voice characteristics.

The full transcript was reviewed with a second Whisper large-v2 pass. Ten
uncertain passages were also decoded with unbatched large-v3. This is not a
complete manual listening review or a political fact check.

- 225 cues have accepted text corrections with before/after records and evidence.
- 46 cues changed when regional phrase substitution was removed. Use `s2tw`
  for Traditional Chinese characters, not `s2twp`, which can change spoken words
  such as `支持`, `分區`, `程序`, and `預算法` into unrelated terms.
- 104 unique cues remain flagged after temporal and semantic checks are merged.
  These include 18 unassigned-speaker cues, three long alignments, uncertain
  names, possible omissions, and disputed ASR alternatives.
- Preserve numbers, political statements, and possible spoken mistakes. For
  example, `三規一章` is retained because the other debater explicitly refers
  to that wording. Do not replace it with the standard policy name.
- Corrected cue text retains the original cue time range. Source segments and
  character times remain the original ASR data, not newly aligned corrected text.
  `segments_text_status` identifies that distinction in JSON.
- `work/original-export/` retains the earlier display exports locally. Raw model
  checkpoints are unchanged. The correction ledger also records normalization
  changes, so the earlier wording can be compared without committing work files.

Use the page's correction and pending-review views before quoting uncertain
speech. A second ASR result is evidence, not proof of exact speech.

## Setup

```bash
uv sync --dev
```

The project uses Python 3.12, WhisperX 3.7.2, pyannote.audio 3.4.0, and matching
PyTorch/TorchAudio 2.8.0 CUDA 12.8 packages. Python 3.14 and TorchAudio 2.9 or later
are not compatible with this pyannote version. `imageio-ffmpeg` supplies FFmpeg.
The tested GPU is an RTX 4090. Use `--device cpu` if CUDA is unavailable.

### Frontend development

The browser source is `web/page.ts`. It uses strict TypeScript
with typed transcript data and checked DOM access. Biome formats and checks the
TypeScript source, CSS, and frontend configuration. The stylesheet uses separate
component sections; its CSS-only `noDescendingSpecificity` rule is disabled
because it compares selectors from unrelated components. Other recommended
checks and the explicit `noExplicitAny` rule remain enabled.

```bash
bun install --frozen-lockfile
bun run format
bun run check
bun run build
```

`bun run check` runs Biome and the TypeScript compiler. `bun run build` checks the
source, bundles `web/page.ts` as a browser IIFE in `transcripts/assets/page.js`,
and copies `web/page.html` and `web/page.css` into `transcripts/assets/`.

Edit frontend source only under `web/`. Do not edit `transcripts/assets/` directly;
regenerate its three runtime files with `bun run build`. Keep those files in the
Python package so exports and installed wheels do not require `web/`, Bun,
Node.js, or TypeScript at runtime. Generated assets and data exports are not
Biome source inputs.

After changing the frontend, rebuild it and run the export command below to
update `data/index.html`. The page remains a self-contained HTML file that works
without a frontend development server.

### Model access

Use the saved Hugging Face login or set `HF_TOKEN`. The same account must accept
both model agreements:

1. <https://huggingface.co/pyannote/speaker-diarization-3.1>
2. <https://huggingface.co/pyannote/segmentation-3.0>

A valid login does not grant gated-model access by itself. `HF_TOKEN` overrides
the saved login. Prefix a command with `env -u HF_TOKEN` to use the saved login
without changing the current shell. Never put tokens in source, HTML, logs, or
committed files.

## Regenerate results

The expensive inference files remain under `outputs/plpXPrOoV2w/work/`.
Regenerate the committable results without model inference:

```bash
uv run 2026-debate export \
  --output-dir outputs/plpXPrOoV2w \
  --destination data \
  --roles data/speaker-roles.json
```

The exporter automatically reads `corrections.json` from the destination.
Use `--corrections PATH` to import another ledger. Each accepted edit needs a
unique ID, cue ID, exact `before` text, `after` text, reason, and evidence.
Uncertain alternatives belong in `flags`, not accepted corrections.
A source fingerprint rejects stale edits if the underlying cues change.

For inference from the original audio:

```bash
env -u HF_TOKEN uv run 2026-debate transcribe raw/plpXPrOoV2w.webm \
  --output-dir outputs/plpXPrOoV2w --destination data \
  --roles data/speaker-roles.json
```

This recording's MP4 contains video only; the WebM contains matching Opus audio.
Decode from sample zero. Do not remove the silent opening or advertisement breaks.
The first speech starts at `00:14:14.632` on the original video timeline.
The local web video combines both streams without trimming the timeline.

Checkpoints use atomic JSON replacement. A rerun reuses complete stages. If the
input, model, package versions, or clip length changes, use a new work directory.
For a new diarization run, inspect speaker IDs before reusing a saved role map.
Do not force the speaker count to four.

`--stop-after transcribe` omits character alignment; `--stop-after align` omits
speaker separation. Use a separate directory with `--limit-seconds` for a short
run. The first 90 seconds of this recording are silent.

## Checks

```bash
uv run pytest tests
uv run ruff check transcripts tests
uv run ruff format --check transcripts tests
uv run ty check transcripts
bun run check
bun run build
node --check transcripts/assets/page.js
```
