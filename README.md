# Wiki Workspace

> **한국어 버전:** [README.ko.md](README.ko.md)

Local-first markdown wiki with AI-powered document delta analysis.

- **Zero-setup** — first launch seeds 10 sample documents, everything persists to `localStorage`. No login, no server required to start.
- **Edit / Split / Preview** 3-mode markdown editor (CommonMark + GFM), 300 ms debounced autosave.
- **AI docdelta** — upload a new `.txt`, the app picks the top-3 most similar workspace docs via pure-JS TF-IDF, and a model extracts `new` facts and `conflict` pairs against what you already know.
- Three interchangeable AI backends: `mock` (deterministic synthetic), `finetuned` (your HTTP endpoint), **`vllm`** (OpenAI-compatible vLLM server with `guided_json`).

## Quickstart

### Prerequisites
- Node 20+ (v12 cannot run Vite 6 — use `nvm install 24`).
- Python 3.11+ with [uv](https://github.com/astral-sh/uv) (or plain `pip`).

### Run (mock mode — default, no LLM needed)

```bash
# 1) Backend (FastAPI on :3001)
cd backend
uv sync
uv run uvicorn app.main:app --port 3001

# 2) Frontend (Vite on :3000, proxies /api → :3001)
cd ../frontend
npm ci
npm run dev
```

Open http://localhost:3000 — the first run seeds 10 sample documents, switches the editor to **Preview** by default, and the AnalyzePanel is ready to accept uploads.

### Run with a real vLLM model

```bash
# Install heavy extras once
cd backend && uv sync --extra vllm

# Start backend with vLLM enabled (assumes vLLM is already serving on :9983)
LLM_PROVIDER=vllm VLLM_ENDPOINT=http://localhost:9983/v1 \
  uv run uvicorn app.main:app --port 3001
```

See [ARCHITECTURE.md §8.2](ARCHITECTURE.md#82-env-매트릭스) for the full env matrix (finetuned provider, tokenizer override, timeouts).

## Repository layout

```
frontend/    React 19 + Vite 6 + Tailwind 4 SPA
backend/     FastAPI + Pydantic v2 (Phase 2+)
docs/        Design docs (9 files, authoritative)
reference/   doc_scheme.json (single source of truth for AI contract)
train/       Fine-tuning code (vendored into backend/_vendor/, do NOT edit)
.claude/     Agent harness (6 agents + 7 skills)
```

## Documentation

| Entry point | Purpose |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | 5-minute whole-project overview |
| [docs/01_overview.md](docs/01_overview.md) | Product vision, user scenarios |
| [docs/02_architecture.md](docs/02_architecture.md) | Layer design, data flows |
| [docs/04_api.md](docs/04_api.md) | API contract and error envelope |
| [docs/05_data_schema.md](docs/05_data_schema.md) | `Document` type, storage schemas |
| [docs/07_roadmap.md](docs/07_roadmap.md) | Phase 0→4 roadmap |
| [docs/08_tradeoffs.md](docs/08_tradeoffs.md) | T1–T12 decisions and reversals |

## Invariants (never break)

- **R1 Data portability** — always exportable to plain `.md`.
- **R2 Local-first** — the app works without network or backend.
- **R3 Raw markdown** — the server never stores HTML-rendered content.
- **R4 Backward-compatible `Document`** — fields can only be added.

See [`ARCHITECTURE.md §5`](ARCHITECTURE.md#5-4대-불변-규칙-모든-phase-교차-적용).

## Status

Phase 2a (AI server proxy with 3 providers) is live. Phase 2b client-side flow (upload + TF-IDF Top-3 + AnalyzePanel) works end-to-end. Phase 3 (cloud sync) and Phase 4 (collaboration) are not started.

## License

Not yet declared.
