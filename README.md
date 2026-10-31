# Debate record

A Traditional Chinese debate transcript with timecoded speaker labels, an
interactive HTML reader, and an auditable text-review ledger. WhisperX handles
transcription and alignment. pyannote.audio separates speakers.

Public site: <https://narumiruna.github.io/taipei-mayoral-debate-2026/>.

## Project layout

| Path | Responsibility |
| --- | --- |
| `transcripts/` | Python package: transcription, alignment, speaker separation, review, subtitles, and export |
| `transcripts/assets/` | Generated JavaScript and copied HTML/CSS used by the Python exporter |
| `web/` | Frontend TypeScript, CSS, and HTML source |
| `data/` | Curated transcripts, subtitles, review records, and fact-check sources |
| `site/` | Generated website and public downloads; ignored deployment output |
| `raw/` | Original media; ignored |
| `outputs/` | Local media derivatives, logs, screenshots, and inference checkpoints; ignored |
| `tests/` | Python regression tests and headless browser checks |

The Python package uses a flat layout without `src/`. Root configuration files
serve this one project. Python imports use `transcripts`; the distribution and
console command remain `2026-debate`.

## Results

Run `bun run build`, then open `site/index.html`.
The page has transcript search, speaker filters, debate chapter navigation,
video seeking, correction comparisons, unresolved review items, sourced fact
checks, and download links.
Reader CSS, JavaScript, and transcript data are inline. Transcript search and
review work offline, including when YouTube is blocked. Video playback uses
[YouTube](https://youtu.be/plpXPrOoV2w) and its iframe API. It requires internet
access and an HTTP(S) preview; YouTube may reject `file://` pages.

| Committable file under `data/` | Contents |
| --- | --- |
| `transcript.md` | Reviewed timecoded transcript |
| `transcript.json` | Reviewed cues, original source segments, roles, and review records |
| `subtitles.srt`, `subtitles.vtt` | Reviewed subtitles |
| `speaker-roles.json` | Speaker mapping and introduction evidence |
| `corrections.json` | Exact before/after text, evidence, source fingerprint, and unresolved flags |
| `review-needed.json` | Unresolved intervals with timestamps |
| `fact-checks.json` | Selected factual claims, exact cue quotes, dated sources, findings, and limits |
| `chapters.json` | Curated debate phases and cue-based navigation boundaries; embedded in HTML only |
| `speaker-review.md` | Role mapping and review limits |
| `validation.json`, `verification.json` | Output checks and counts |

These are text files intended for version control. Published metadata contains
only the source filename, not an absolute local path or source modification time.

Large media, screenshots, logs, and inference checkpoints stay in ignored
`outputs/`. Do not add those files to a commit. The web page plays YouTube video,
not ignored local media. Download links remain local paths relative to
`index.html`, for the transcript, subtitles, and correction ledger.

## Deployment

The GitHub Actions workflow in [`.github/workflows/deploy.yml`](.github/workflows/deploy.yml)
builds and publishes `site/` to GitHub Pages. Changes to website source, curated
data, build configuration, or the workflow trigger a build on pull requests and
pushes to `main`. Only `main` can deploy. To deploy manually, select **Actions →
Deploy webpage → Run workflow** on `main`.

In **Settings → Pages → Build and deployment**, set **Source** to **GitHub Actions**.
The published site is <https://narumiruna.github.io/taipei-mayoral-debate-2026/>.

The workflow installs Bun and uv, then runs `bun run build`. The Python site
builder uses only the standard library through `uv run --no-project python`;
it does not install transcription dependencies or run inference.

The build copies the documented public records from `data/`, validates the
optional fact-check ledger and chapter metadata, and generates one inline HTML
page in `site/`.
It does not change source data. Only `site/` is uploaded. Unknown files, local
credentials, `raw/`, and `outputs/` are not copied. Do not commit `site/` or write
HTML into `data/`.

The public homepage and download URLs do not change: `site/` becomes the
published root, not an extra URL segment. The page plays YouTube video and does
not need local video or poster files. Playback requires access to YouTube;
transcript search, fact checks, review views, and local downloads do not.

### Playback limits

YouTube controls video availability and embedding permissions. IFrame API errors
101 and 150 indicate an embedding restriction. The page then shows a direct
YouTube link. Timestamp clicks update that link to the selected video time.
Transcript search and review remain available.

The automated local check on 2026-10-31 received error 150; live embedded playback
is not verified. A site maintainer must check the published page in a regular
browser with YouTube access before reporting in-page playback as verified.
If the restriction remains, the video owner must allow embedding. The direct
YouTube link remains available when embedded playback is restricted.

Chapter browser tests use a test-only YouTube API stub to check seek requests,
play actions, and current-chapter boundaries. Blocked-network tests also check
text navigation and timestamped external links without YouTube. Neither check
verifies live embedded playback. After chapter changes, a site maintainer must
select representative chapters from all four phases in a browser with YouTube
access and confirm the video and transcript match. This requires the video owner
to permit embedding. Do not report live playback as verified before that check.
The unresolved live-playback check does not prevent local implementation tests
from passing and does not authorize a deployment.

## Preview

From the repository root, build and serve only the deployment output:

```bash
bun run build
uv run --no-project python -m http.server 8765 --bind 127.0.0.1 --directory site
```

Then open <http://127.0.0.1:8765/#fact-checks> for the fact-check tab or
<http://127.0.0.1:8765/> for the transcript. YouTube requires internet access and
may reject `file://` playback. You can open `site/index.html` directly for offline
reading. The server listens only on the local interface and does not serve the
repository. Do not expose it as a public server.

## Chapter navigation

The sidebar's **辯論流程** panel replaces the fixed ten-minute index. It has four
formal phases: **申論**, **交叉詰問**, **媒體提問**, and **結論**. The introduction
and final host segment are separate entries. There are 20 leaf entries in total.
Each of the four cross-examination rounds has two complete question sequences;
a sequence includes the question, answer, follow-up question, and final answer.
Each media question has separate entries for the reporter and both answers.
Media-question titles are summaries, not quotations or official phase names.

Phase groups start expanded. Round and media-question groups start collapsed.
Disclosure controls only expand or collapse; separate buttons navigate to a
group's start or an individual entry. A selection clears all filters, selects
the transcript tab, focuses the target cue, and requests playback. Labels show
the phase or speaker first and the original video time second. The current
chapter follows the selected video time, not page scrolling. Playback updates
do not change disclosure state or keyboard focus. Follow-playback scrolling
remains off by default. Silent opening time, advertisement breaks, and time
after the last segment have no current chapter.

Edit `data/chapters.json`, then run `bun run build`. The file contains
`source_sha256` and ordered `items`. The hash must match
`data/transcript.json`'s `review.source_sha256`. Each item has a unique `id` and a
nonempty `title`. A group has ordered, nonempty `children`. A leaf instead has
`start_cue_id` and `end_cue_id`; both reference existing transcript cues. The
builder derives the half-open interval `[first_cue.start, last_cue.end)` and each
group's bounds from its descendants. Do not duplicate times in chapter metadata
or TypeScript. Keep source cues, subtitle boundaries, and the original video
timeline unchanged, including the silent opening and advertisements.

Chapter ends follow existing cue boundaries, not word-accurate audio cuts.
Some host-transition cues contain a candidate's final syllable. Candidate
entries stop at the last candidate-labeled cue; they do not split or reassign
mixed-speaker cues. The introduction includes the mixed rule/phase transition
cue, and the final host entry includes the unresolved closing-speaker handoff.
These navigation choices do not resolve the transcript's review flags.

The standard-library validator rejects invalid references, source hashes,
non-finite or reversed times, overlapping leaf ranges, and unordered items.
The renderer embeds only validated public fields with the transcript; it does
not fetch chapter data at runtime or publish a separate chapter download.
Existing generic exports without chapter metadata remain valid and show
**尚無章節資料**, with no ten-minute fallback. Invalid metadata stops the build
before it replaces a previous site. To undo chapter implementation changes,
revert only their source paths and run `bun run build`; do not edit generated
HTML or transcript exports by hand. Deployment requires separate authorization.

## Review status

The recording has 1,082 cues and six speaker clusters: two debaters, two hosts,
and two reporters. The user supplied the speaker names. Roles were mapped
from introductions and turn-taking, not from voice characteristics.

The full transcript was reviewed with a second Whisper large-v2 pass. Ten
uncertain passages were also decoded with unbatched large-v3. This is not a
complete manual listening review or a political fact check.

- 227 cues have accepted word or text-boundary corrections with before/after
  records and evidence.
- All 1,082 cues were reviewed for punctuation; 1,056 cues received punctuation
  without word changes. Cue boundaries are not sentence boundaries. The ledger
  stores each changed cue's prior reviewed text in `punctuation_before`.
  There are 1,058 text-corrected cues in total, including punctuation changes.
  Punctuation review does not replace audio verification or clear unresolved flags.
- 46 cues changed when regional phrase substitution was removed. Use `s2tw`
  for Traditional Chinese characters, not `s2twp`, which can change spoken words
  such as `支持`, `分區`, `程序`, and `預算法` into unrelated terms.
- All 18 unassigned-speaker cues were checked against adjacent sentences,
  diarization intervals, and the saved independent ASR. Seventeen short cues
  complete the previous speaker's sentence and have audited speaker corrections.
  Their text and timing are unchanged. This is a contextual review, not a listening
  review. Cue 1076 remains unassigned at the closing-host handoff.
- 86 unique cues remain flagged after temporal and semantic checks are merged.
  These include one unassigned-speaker cue, three long alignments, uncertain
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

## Fact checks

The **事實查核** tab contains a selected-claim review, separate from ASR text
corrections. The 2026-10-31 snapshot covers five claims from each debater and
links to 18 source pages. It is not a complete audit of the debate or either
candidate's past statements. It does not infer intent or estimate a candidate's
overall accuracy.

Each item includes exact transcript quotes, video time, a finding, analysis,
source evidence, and limits. Findings distinguish supported claims, claims that
need context, claims contradicted by evidence, and insufficient evidence.
Unresolved ASR flags remain visible. Missing evidence does not establish that a
claim is false. A source date is the page's marked publication or update date;
undated pages are identified separately from the review date.

Search includes the findings and source text. The speaker and finding filters
can be combined. Reading checks works offline; opening source links and video
requires internet access. The page is a repository research summary, not a
certification from an external fact-checking organization.

Edit `data/fact-checks.json`, then run `bun run build`. The site builder reads
`data/transcript.json` and the optional ledger, then passes both to the renderer.
The renderer never reads input from `site/`. It rejects invalid dates, unsafe
source URLs, mismatched source hashes, changed quotes, and wrong speaker
references before publication. Builds without a ledger remain supported.
The validator checks structure and transcript consistency; it cannot verify
whether a source supports a conclusion.

Commit the source ledger and any frontend changes, not the generated site.
Source pages can change. Review the evidence and update findings rather than
treating validation as renewed source verification.

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
bunx playwright install chromium
bun run test:browser
```

Website builds need Bun, uv, and a Python interpreter, not the transcription
packages. Full Python tests and transcription also require `uv sync --dev`.

`bun run test:browser` builds a fresh site, then blocks external requests while
testing filters, source links, keyboard tabs, transcript navigation, offline
reading, and widths of 1440, 390, and 320 pixels. It also serves the generated
files under the GitHub Pages project path and verifies download bytes.
Fact-check screenshots stay under ignored `outputs/fact-checks/`. Chapter tests
also check native disclosure controls, all navigation targets, current-chapter
boundaries, and API-stub seeking. Expanded and collapsed chapter captures stay
under ignored `outputs/chapters/`; checks include keyboard access in a
1440 × 700 desktop viewport. These captures and tests do not establish live
YouTube playback; see **Playback limits**.

`bun run check` runs Biome and the TypeScript compiler. The build has two stages:

1. `bun run build:assets` checks the frontend, bundles `web/page.ts` into
   `transcripts/assets/page.js`, and copies the HTML and CSS runtime assets.
2. `bun run build:site` uses the curated data and packaged assets to generate
   `site/`. It does not need model checkpoints or third-party Python packages.

`bun run build` runs both stages. Edit frontend source only under `web/`; do not
edit `transcripts/assets/` directly. Keep those generated runtime assets in the
Python package so installed site builders do not require frontend tools.
Generated assets, data exports, and `site/` are not Biome source inputs.

The site builder prepares the full output before replacing a previous site.
Invalid source data leaves the previous output unchanged. Rebuilding removes
stale output files, including a fact-check ledger removed from the inputs.
Reader assets and data stay inline in one HTML file; no frontend server is
required.

### Git hooks

Run `bun install --frozen-lockfile` to install Husky and enable the Git hooks.
The `prepare` script sets `core.hooksPath` to `.husky/_`. The Python checks also
require `uv sync --dev`.

The pre-commit hook calls `bash scripts/pre-commit.sh`. It runs the frontend
checks, Ruff lint and format checks, Python type checks, and Python tests.
A failed check stops the commit. The hook does not format source files or update
`site/`; regression tests build temporary sites for validation.

To run the same checks manually:

```bash
bash scripts/pre-commit.sh
```

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
bun run build
```

Transcript export writes data only; website generation is a separate step.
The exporter automatically reads `corrections.json` from the destination.
Use `--corrections PATH` to import another ledger. Each accepted edit needs a
unique ID, cue ID, exact `before` text, `after` text, reason, and evidence.
Speaker assignments use a separate `speaker_corrections` array with the same
fields; `before` and `after` contain speaker IDs, not transcript text. The target
must be a known speaker in the source cues. IDs must be unique across text
corrections, speaker corrections, and review flags. Each changed cue retains
`original_speaker`, `original_label`, and `speaker_correction_id`. The page shows
these assignments in its correction view. Do not change model checkpoints or
use a nearest-speaker rule to resolve uncertain speech.
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
The website uses the original YouTube video timeline for timestamp seeking.

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
bun run test:browser
```
