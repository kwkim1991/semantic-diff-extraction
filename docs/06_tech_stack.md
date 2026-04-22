# 06. 기술 스택

각 항목은 **선택 / 대안 / 근거**로 정리. ★ 는 [`frontend/package.json`](../frontend/package.json) 또는 [`backend/pyproject.toml`](../backend/pyproject.toml) 중 **어느 한 쪽이라도 실제 설치된 항목**을 표시 (Phase 2a docdelta PoC 이후부터 backend 의존성도 ★ 범위에 포함; 2026-04-22 Python 전환 이후 backend는 `pyproject.toml` 기준).

## Frontend — Core

| 역할 | 선택 | 대안 | 근거 |
|---|---|---|---|
| Framework | ★ React 19 | Svelte, Solid | 생태계·채용·데모 기반 완성 |
| Build / Dev | ★ Vite 6 | Webpack, Turbopack | HMR·ESM·Tailwind 4 통합 우수 |
| Language | ★ TypeScript 5.8 | — | 타입 안전성은 논쟁 대상 아님 |
| Router | (Phase 2) React Router v6 | TanStack Router, Next.js App Router | 현재는 SPA 단일 뷰, 필요 시 경량 라우터 |

## Frontend — UI / Styling

| 역할 | 선택 | 대안 | 근거 |
|---|---|---|---|
| CSS | ★ Tailwind 4 + `@tailwindcss/vite` | CSS Modules, vanilla-extract | `@theme`·프로즈 플러그인 조합이 마크다운 문서 UI에 최적 |
| Typography | ★ `@tailwindcss/typography` | — | `prose` 클래스로 마크다운 렌더 품질 즉시 확보 |
| Icons | ★ `lucide-react` | Heroicons, Phosphor | 트리셰이킹·디자인 통일성 |
| Animation | ★ `motion` (Framer) | react-spring | 전환·드로어 모션 고품질 |
| Component Lib | (Phase 2) shadcn/ui 일부 차용 | Radix 직접 사용 | 접근성 있는 프리미티브가 필요해질 때 |

## Frontend — Markdown

| 역할 | 선택 | 대안 | 근거 |
|---|---|---|---|
| Renderer | ★ `react-markdown` | `markdown-it`, MDX | React 친화·확장 플러그인 풍부 |
| GFM | ★ `remark-gfm` | — | 표·체크리스트·strikethrough 표준 |
| (Phase 2) 코드 하이라이팅 | `rehype-highlight` 또는 `shiki` | Prism | shiki가 품질 좋으나 번들 크기 고려 |
| (Phase 2) 수식 | `remark-math` + `rehype-katex` | MathJax | KaTeX 번들이 가볍다 |

## Frontend — State / Data

| 역할 | 현재(Phase 1) | Phase 2 | Phase 3 |
|---|---|---|---|
| UI 상태 | ★ `useState` | Zustand | Zustand |
| 영속 상태 | ★ `useLocalStorage` 훅 | + IndexedDB 검토 | TanStack Query로 서버 캐시 |
| 서버 상태 | — | — | **TanStack Query** |

## AI

| 역할 | 선택 | 대안 | 근거 |
|---|---|---|---|
| SDK | ★ `@google/genai` (v1.29) | `openai`, `@anthropic-ai/sdk` | 초기 파트너 선택, 추후 provider-agnostic 레이어 추가 예정 |
| 기본 모델 | (Phase 2) Gemini 2.5 Flash / Pro | GPT-4o mini, Claude Haiku | 스트리밍·비용·한국어 성능 균형 |
| 프롬프트 전략 | 시스템 프롬프트 고정 + prompt caching | — | 에디터 맥락은 동적, 지시문은 정적 |
| 안전장치 | 서버 측 rate limit + 콘텐츠 길이 상한 | — | 남용 방지 |

## Backend (Phase 2+, **Python 스택**)

| 역할 | 선택 | 대안 | 근거 |
|---|---|---|---|
| 언어 | ★ **Python 3.11+** | Node.js/Express, Go | LLM/데이터 파이프라인 생태계(LangChain, 벡터 DB 클라이언트 등)와의 궁합, 연구 코드 공유 용이. T9 2026-04-22 결정. |
| Framework | ★ **FastAPI** | Flask, Django-REST, Starlette 단독 | Pydantic 통합, OpenAPI 자동, async 네이티브. 학습/추론 API 흔히 쓰는 조합. |
| ASGI 서버 | ★ **Uvicorn** (`uvicorn[standard]`) | Hypercorn, Daphne | FastAPI 표준 런너, `--reload` dev 편의 |
| 스키마/검증 | ★ **Pydantic v2** | marshmallow, dataclasses+custom | reference/doc_scheme.json과 1:1 매핑 용이, FastAPI 기본 |
| Env 로드 | ★ **python-dotenv** | pydantic-settings, dynaconf | 단일 프로세스·단일 파일로 충분 |
| LLM SDK | **google-generativeai** (Phase 2 실 연동 시) | openai, anthropic | T8 — Gemini 우선, 2번째 공급자 이전엔 추상화 연기. docdelta PoC는 mock-first로 미설치. |
| HTTP 클라이언트 | ★ **httpx** (>=0.27, async) | requests, aiohttp | 2026-04-22 production 의존성 승격 (기존엔 `dev` extras 에 testclient 용으로만). `FinetunedProvider` 가 외부 finetuned docdelta 엔드포인트 호출에 사용. |
| 의존성 관리 | ★ **pyproject.toml** (PEP 621) + `uv`(권장) 또는 `pip` | poetry, hatch | 표준 포맷, `uv`는 속도, `pip install -e .` 로도 동작 |
| Lint/Format | **ruff** | black + flake8 + isort | 한 툴로 셋 다 대체, 속도 |
| 타입 체크 | **pyright** (또는 mypy) | — | FastAPI/Pydantic과 궁합 |
| 테스트 | **pytest** + **pytest-asyncio** + `fastapi.testclient.TestClient` | unittest | 사실상 표준 |
| ORM (Phase 3) | **SQLAlchemy 2.0** (async) | SQLModel, Tortoise | 성숙도·쿼리 표현력 |
| Migration (Phase 3) | **Alembic** | atlas | SQLAlchemy 표준 짝 |
| Auth (Phase 3) | **Authlib** + 세션 쿠키, 또는 FastAPI Users | Clerk, Auth0 | OSS 유지, 데이터 경계 자율 |
| Queue (Phase 3+) | **Celery(Redis broker)** 또는 **RQ** | graphile-worker | Python 생태계 표준, 재시도·스케줄 |
| Rate limit | **slowapi** | 수제 미들웨어 | FastAPI 호환, 분·시간 제한 데코레이터 |

> `backend/pyproject.toml` (2026-04-22 신설, 같은 날 보강) — core deps: `fastapi`, `uvicorn[standard]`, `pydantic`, `python-dotenv`, **`httpx>=0.27`**(provider 추상화 도입으로 production 승격, `FinetunedProvider` upstream 호출에 사용). dev extras: `pytest`, `pytest-asyncio`, `pyright`, `ruff` (httpx 는 이제 core 이므로 dev 에서 빠짐). gemini extra(선택): `google-generativeai`. **vllm extra(선택, 2026-04-22 추가)**: `openai>=1.0`, `transformers>=4.40`. 설치: `pip install ".[vllm]"` 또는 `uv sync --extra vllm`. 역할별 근거 — `openai`: vLLM 의 OpenAI-호환 `/v1/completions` 엔드포인트를 동일 SDK로 호출 (벤더링된 `train/finetune/infer_diff.py::get_diff` 내부 의존). `transformers`: `AutoTokenizer.from_pretrained(HF_TOKENIZER)` 로 모델 토크나이저 로딩 후 chat-template 적용 (사전 토큰화된 프롬프트를 vLLM `prompt` 파라미터로 전달). `huggingface-hub`: `transformers` 의 전이 의존성으로 토크나이저 자산 다운로드(HF 모델 ID 로 주어지는 경우) 처리. extras 미설치 + `LLM_PROVIDER=vllm` 조합은 첫 `get_diff()` 호출 시 `500 AI_UPSTREAM` + 설치 안내 문구로 귀결 (docs/04 참조). **실 Gemini 연동은 미진행** — docdelta 는 `LLM_PROVIDER=mock`(synthetic), `finetuned`(외부 엔드포인트 프록시), 또는 `vllm`(OpenAI-호환 vLLM 서빙 + 벤더링 `get_diff`) 3종 디스패치.

### train/ ↔ backend/ 관계 (벤더링, 2026-04-22)

`train/finetune/infer_diff.py` 와 `train/finetune/prompt_text.py` 는 **backend 의 source of truth** 이며, 수정 금지 제약하에 `backend/app/services/providers/_vendor/{infer_diff.py, prompt_text.py}` 로 **byte-for-byte 복사**(상단 8줄 헤더 주석만 추가)되어 backend 프로세스에서 직접 import 된다. 이 벤더링 전략은 아키텍트 결정 `_workspace/02_architect_decision.md §3` 에 근거하며, (a) `train/` 이 자체 sys.path 해킹을 포함해 backend 런타임 import 순서와 충돌할 수 있고, (b) 배포 이미지에서 `train/` 전체 트리(학습 데이터셋 포함)를 끌어올 필요가 없으며, (c) `train/` 의 경로·파일명 변경이 backend 런타임을 깨지 않도록 격리하기 위함이다. `_vendor/` 디렉토리의 언더스코어 prefix 는 외부 import 금지 의도 시그널이며 `backend/pyproject.toml [tool.ruff].extend-exclude` 로 lint 제외도 명시되어 있다. `train/` 업스트림 변경 감지 시 재벤더링 절차: byte-for-byte 재복사 + 헤더 주석의 "Copy date" 업데이트 (벤더링 파일 내부 개조 금지 원칙 유지).

> **왜 Python으로 전환했나**: Phase 2의 주력 기능인 `/api/ai/docdelta`는 **문서 그룹 간 의미 비교**이며, 후속으로 벡터 검색·파인튜닝·학습 데이터 스키마(`reference/train-validation-dataset/`)를 다룬다. Python 생태계(LangChain, 벡터 DB 클라이언트, LLM 학습 스크립트)와의 결합이 Node.js 대비 결정적 이득. Express/tsx 스택에서 FastAPI로 전환하면서 프론트(Node)·백(Python) 이종 런타임이 됐지만, 모노레포 내 API 계약(OpenAPI + reference scheme)만 정확하면 경계는 깨끗하다.

## Storage (Phase 3+)

| 역할 | 선택 | 대안 | 근거 |
|---|---|---|---|
| RDB | Postgres 16 | MySQL | jsonb·array·GIN 인덱스 |
| 캐시 | Redis | Memcached | 세션·rate limit·queue 공용 |
| Object Storage | S3 호환 (MinIO 로컬 / S3 프로덕션) | 로컬 FS | 첨부 파일 |
| 검색 (Phase 3 후반) | Postgres Full-Text → Meilisearch | Elasticsearch | 규모 작을 때는 PG로 충분 |

## Infra / Ops (Phase 3+)

| 역할 | 선택 | 대안 | 근거 |
|---|---|---|---|
| 컨테이너 | Docker + docker-compose(로컬) / Fly·Render·Railway(프로덕션) | k8s | 팀·규모 대비 과하지 않게 |
| CI/CD | GitHub Actions | GitLab CI | 레포 위치 |
| 모니터링 | Sentry(에러) + Plausible(제품 분석) | Datadog | OSS·가벼움 |
| 로깅 | **structlog** (또는 `loguru`) JSON → Loki (프로덕션) | stdlib `logging`, `pino`(Node) | Python 전환(T9) 반영. structlog은 구조화 로깅 표준, FastAPI/Uvicorn과 어댑터 연결 용이 |
| Secrets | `.env`(로컬) → 플랫폼 secret store | Vault | 간결 |

## 개발 도구

| 역할 | 선택 |
|---|---|
| 패키지 관리 | ★ npm (로컬 `package-lock.json`) |
| 타입 체크 | ★ `tsc --noEmit` (`npm run lint`) |
| 린트 | ESLint + `@typescript-eslint` (Phase 2 진입 시 추가) |
| 포맷 | Prettier (Phase 2 진입 시 추가) |
| 테스트 | Vitest + React Testing Library (Phase 2) + Playwright (Phase 3) |
| Pre-commit | `lint-staged` + Husky (Phase 2) |

## 선택 이유 요약

1. **데모 스택을 그대로 존중**: 현재 `package.json`에 든 것을 버리지 않고 위에 얹는 방식.
2. **프레임워크 대신 라이브러리 조합**: Next.js/Remix를 피한 이유는 Phase 1이 명백한 SPA이기 때문. Phase 3에서 SSR이 필요해지면 그때 재검토.
3. **Tailwind 4 + Typography**: 마크다운 문서 전용 앱에서 거의 무적의 조합. 커스텀 CSS 최소화.
4. **점진적 도입**: ESLint/테스트/Zustand 모두 "필요해지는 Phase"에 들어온다. Phase 1에는 의도적으로 없다.
5. **AI는 서버 프록시로**: 브라우저에 Gemini 키가 나가지 않도록 Phase 2에 Python(FastAPI)을 1차 도입. 초기 계획은 Express였으나 LLM/학습 데이터 생태계 궁합 때문에 Python으로 전환(T9 2026-04-22).
