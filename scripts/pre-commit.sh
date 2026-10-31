#!/bin/bash
set -euo pipefail

bun run check
uv run ruff check transcripts tests
uv run ruff format --check transcripts tests
uv run ty check transcripts
uv run pytest tests
