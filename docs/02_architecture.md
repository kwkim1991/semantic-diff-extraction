# 02. 시스템 아키텍처

## 전체 구성도

Phase 1(현재 데모)은 **프론트엔드 단독 · localStorage 저장**. Phase 2a 진입의 **docdelta PoC(2026-04-22 재구성)** 로 `backend/`에 **Python 3.11 + FastAPI + Uvicorn** 뼈대와 `POST /api/ai/docdelta` mock 엔드포인트가 생겼다 — 실 LLM(Gemini) 호출·SSE·rate limit은 여전히 미구현. 초기 Express/tsx 스택은 LLM·학습 데이터 생태계와의 궁합을 이유로 Python으로 전환(T9, 2026-04-22). 아래는 Phase 2~4에서 추가될 컴포넌트까지 포함한 목표 아키텍처.

```
┌────────────────────────────────────────────────────────────────────┐
│                    Frontend (React 19 + Vite SPA)                   │
│                                                                     │
│  ┌──────────┐   ┌──────────────────────────────┐   ┌────────────┐  │
│  │ Sidebar  │   │         Editor               │   │ AI Panel   │  │
│  │          │   │  ┌─────────┐  ┌───────────┐  │   │ (Phase 2)  │  │
│  │ 문서목록 │   │  │ Edit    │  │ Preview   │  │   │            │  │
│  │ 생성/삭제│   │  │textarea │  │ markdown  │  │   │ 요약/제안  │  │
│  └────┬─────┘   │  └────┬────┘  └─────┬─────┘  │   └─────┬──────┘  │
│       │         │       │  Split mode       │           │          │
│       │         └───────┼───────────────────┘           │          │
│       │                 │                                │          │
│       ▼                 ▼                                ▼          │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │              State Layer (React state + Hooks)                │  │
│  │  documents: Document[]   activeDocumentId: string | null      │  │
│  └────────────────────────┬─────────────────────────────────────┘  │
│                           │                                         │
│                           ▼                                         │
│              ┌────────────────────────┐                             │
│              │  useLocalStorage       │  Phase 1: 단독 persistence  │
│              │  (key: "wiki-docs")    │                             │
│              └────────┬───────────────┘                             │
└───────────────────────┼─────────────────────────────────────────────┘
                        │
           Phase 2~3에서 추가 ──────────────┐
                        │                  │
                        ▼                  ▼
            ┌───────────────────┐   ┌────────────────────────┐
            │  Sync API         │   │  AI Service            │
            │  (FastAPI/Python) │   │  Gemini proxy          │
            │  REST + WS        │   │  (google-generativeai) │
            └─────────┬─────────┘   └────────────────────────┘
                      │
              ┌───────▼────────┐
              │  Postgres      │  문서/버전/공유 권한
              │  + Object Store│  첨부파일(선택)
              └────────────────┘
```

## 레이어 구분

### 1. Presentation Layer — React 컴포넌트
- **역할**: 사용자 입력 수집, 마크다운 렌더, 편집 모드 제어.
- **주요 컴포넌트**:
  - [`Sidebar`](../frontend/src/components/Sidebar.tsx): 문서 목록 · 생성 · 삭제 · 활성 선택 · 제목 검색 필터(PoC)
  - [`Editor`](../frontend/src/components/Editor.tsx): 제목/본문 입력, `edit | split | preview` 3-모드
  - (Phase 2+) `AIPanel`, `CommandPalette`, `ShareDialog`, `SearchBar`

### 2. State Layer — React state + Custom hooks
- **역할**: 문서 컬렉션과 활성 문서 ID 보관, 뷰와 저장소 사이의 경계.
- 현재는 [`App.tsx`](../frontend/src/App.tsx)에서 `useState` + `useLocalStorage`로 직접 관리.
- 규모가 커지면 **TanStack Query + Zustand** 도입(서버 상태 ↔ UI 상태 분리).

### 3. Persistence Layer
| 계층 | 현재 (Phase 1) | 목표 (Phase 3+) |
|---|---|---|
| 로컬 | `localStorage` (key: `wiki-docs`) | IndexedDB로 승격 (대용량·바이너리) |
| 원격 | — | Postgres + Object Storage |
| 동기화 | — | Optimistic update + 서버 권위, CRDT는 Phase 4에서 평가 |

### 4. (Phase 2+) Application Layer — FastAPI (Python) API
- `GET /documents`, `PUT /documents/:id`, `POST /documents`, `DELETE /documents/:id`
- `POST /ai/summarize`, `POST /ai/suggest-title` — Gemini 프록시(키는 서버 보관)
- 상세 계약은 [04_api.md](04_api.md).

#### Phase 2a 현재 상태 (2026-04-22, provider 추상화 적용 + vLLM provider 추가)
- `backend/` 레이아웃 (Python 패키지):
  - `pyproject.toml` (PEP 621: fastapi, uvicorn, pydantic, python-dotenv, **httpx**(2026-04-22 production 승격). `[project.optional-dependencies].vllm = ["openai>=1.0", "transformers>=4.40"]` 추가(2026-04-22). `[tool.ruff].extend-exclude = ["app/services/providers/_vendor"]` 가드.)
  - `app/main.py` (FastAPI 앱 · CORS · `X-Request-ID` 미들웨어 · 통일 에러 핸들러)
  - `app/env.py` (python-dotenv 로드 + 필수 변수 검증; 2026-04-22 이후 `LLM_PROVIDER`/`FINETUNED_API_URL`/`FINETUNED_API_KEY`/`FINETUNED_TIMEOUT_SEC` 4개 + **2026-04-22 추가로 `VLLM_ENDPOINT`/`VLLM_MODEL`/`VLLM_API_KEY`/`HF_TOKENIZER` 4개 신규 필드. `LLM_PROVIDER` Literal 은 `"mock" | "finetuned" | "vllm"` 3값으로 확장**)
  - `app/routers/ai.py` (`/api/ai/docdelta` 라우트, Pydantic req/res 검증 + `get_provider().analyze(req)` 위임 — `DEMO-*` 분기는 2026-04-22 철회·삭제됨. **vllm 분기는 dispatcher 레벨에서 자동 지원되며 라우터 변경 없음.**)
  - `app/routers/health.py` (`/api/health`)
  - `app/schemas/docdelta.py` (reference/doc_scheme.json과 1:1 Pydantic 모델 — vLLM provider 추가에도 **byte-for-byte 무변경**)
  - `app/services/docdelta_provider.py` (2026-04-22 신규 — PEP 544 `Protocol`: `async def analyze(req) -> DocdeltaResponse`)
  - `app/services/docdelta.py` (2026-04-22 신규 — `get_provider()` 디스패처. `env.LLM_PROVIDER == "finetuned"` → `FinetunedProvider()`, `"vllm"` → `VllmProvider()` (2026-04-22 추가), 그 외 → `MockProvider()`)
  - `app/services/providers/__init__.py` (2026-04-22 신규 — 빈 패키지 파일)
  - `app/services/providers/mock.py` (2026-04-22 신규 — 이전 `services/docdelta_mock.py` 본문을 **무변경 복사** 이사 + `MockProvider` 클래스 래퍼. 결정론적 synthetic 응답. vLLM 추가로 인한 변경 없음.)
  - `app/services/providers/finetuned.py` (2026-04-22 신규 — `httpx.AsyncClient` 기반 스텁. `FINETUNED_API_URL` POST, 응답 `DocdeltaResponse.model_validate_json` 재검증. 미설정/Timeout/HTTPError/upstream 4xx 5xx/shape 위반 각각 500/504/502/502/500 매핑. vLLM 추가로 인한 변경 없음.)
  - `app/services/providers/vllm.py` (2026-04-22 신규 — `VllmProvider.analyze()`. 벤더링 `get_diff` 를 `asyncio.to_thread` 로 감싸 `req.new_doc` 원소별 N회 호출 후 merge. `conflict[].doc_id` 는 known_text substring 3단 폴백으로 복원, `severity="medium"` 하드코드. `openai`/`transformers` 는 함수 본문에서 지연 import — extras 미설치 시에도 모듈 import 자체는 성공하며, 첫 `get_diff()` 호출 시점에서 `ImportError` 를 500 AI_UPSTREAM + 설치 안내로 매핑.)
  - `app/services/providers/_vendor/__init__.py` (2026-04-22 신규 — 빈 패키지 + docstring `"""Vendored upstream modules from train/finetune/ — DO NOT EDIT."""`)
  - `app/services/providers/_vendor/infer_diff.py` (2026-04-22 신규 — `train/finetune/infer_diff.py` **byte-for-byte 복사** + 상단 8줄 헤더 주석(`Vendored from: ...`, `Copy date: 2026-04-22`, `DO NOT EDIT HERE`, 재벤더링 절차)). 내부 sys.path 해킹 및 smoke-test 블록 원본 그대로 유지.
  - `app/services/providers/_vendor/prompt_text.py` (2026-04-22 신규 — `train/finetune/prompt_text.py` byte-for-byte 복사 + 동일 헤더)
  - (삭제됨, 2026-04-22) `app/services/docdelta_mock.py` → `services/providers/mock.py` 로 이사
  - (삭제됨, 2026-04-22) `app/services/docdelta_fixtures.py` → B+C 철회로 완전 삭제
- **`_vendor/` 디렉토리 메모**: 언더스코어 prefix 는 외부 import 금지 시그널. `train/finetune/*.py` 가 source of truth 이며, backend 는 수정 금지 원칙하에 byte-for-byte 복사본만 유지한다. upstream 변경 감지 시 재벤더링 절차(헤더 주석의 Copy date 업데이트 + 파일 재복사)는 wiki-qa 가 교차 검증.
- 실행: `cd backend && uv run uvicorn app.main:app --reload --port 3001` (또는 `pip install -e . && python -m uvicorn ...`). CORS 화이트리스트 단일 origin `http://localhost:3000`. `GEMINI_API_KEY`는 env placeholder만, 호출 코드 없음. `LLM_PROVIDER=mock` 이 기본이고, finetuned / vllm 전환은 관련 env 설정 후 재기동만 하면 됨 (vllm 은 추가로 `pip install ".[vllm]"` 또는 `uv sync --extra vllm` 으로 optional extras 설치 필요).
- 프론트와의 타입 공유: Pydantic 모델(Py)과 `frontend/src/types/docdelta.ts`(TS)는 **수동 동기화**. 계약 drift는 wiki-qa가 reference/doc_scheme.json 기준으로 교차 검증.
- 상세 근거: `_workspace/02_architect_decision.md` §6 (provider 추상화), `_workspace/05_backend_changes.md`, 그리고 2026-04-22 vLLM 추가분은 동일 경로의 후속 라운드 산출물 및 `docs/08_tradeoffs.md` 의사결정 변경 이력 참조.

### 5. (Phase 4) Collaboration Layer
- WebSocket 기반 실시간 편집 (선택: Y.js CRDT).
- Presence(보고 있는 사용자 표시), comment thread, version history.

## 데이터 흐름 (현재 Phase 1 기준)

### Flow A — 앱 초기화
```
App 마운트
  → useLocalStorage("wiki-docs") 가 기존 문서 로드
  → documents.length === 0 이면 "Welcome" 문서 시드
  → activeDocumentId = documents[0].id
  → Sidebar 렌더, Editor 활성 문서 표시
```

### Flow B — 문서 생성
```
User: "+ New Document" 클릭
  → handleCreateDocument(): 빈 Document를 맨 앞에 prepend
  → activeDocumentId = newDoc.id
  → Editor가 빈 제목/본문으로 교체됨
  → useLocalStorage 가 자동 persist
```

### Flow C — 편집 (debounce 저장)
```
User: textarea 타이핑
  → localTitle / localContent state 즉시 업데이트(입력 반응성)
  → 300ms debounce 후 onChange 호출
  → App.handleUpdateDocument: documents 배열에서 해당 id를 교체(updatedAt 갱신)
  → useLocalStorage 가 동기 persist
```

### Flow D — 모드 전환
```
User: Edit / Split / Preview 토글 클릭
  → Editor 내부 state `mode` 변경
  → split 모드에서는 좌우 패널 동시 렌더
  → preview 는 react-markdown + remark-gfm 으로 렌더
```

## Phase 2~4에서 추가되는 흐름

### Flow E — 클라우드 동기화 (Phase 3)
```
편집 발생 → 로컬 저장 즉시 반영(optimistic)
          → 백그라운드 큐에 적재
          → PUT /documents/:id (exponential backoff)
          → 실패 시 "offline" 배지, 재연결 시 재시도
```

### Flow F — AI 보조 (Phase 2)
```
User: AI 패널에서 "요약" 클릭
  → POST /ai/summarize { content }
  → 서버: Gemini 호출 (키 서버 보관)
  → 스트리밍 응답을 에디터 사이드 패널에 표시
  → 사용자가 "삽입" 선택 시 본문에 머지
```

## 왜 이 구조인가

- **로컬 우선(local-first)**: 로그인·네트워크 없이도 완결된 사용 경험. 서버는 "옵션"이지 전제가 아니다.
- **경계를 얇게**: Phase 1은 컴포넌트 3개 + 훅 1개로 충분하도록 단순화 — 과잉 추상화를 의도적으로 피한다.
- **표준 우위**: 마크다운 + GFM이라는 **열려 있는 포맷**을 선택함으로써 데이터 이동성 보장 (import/export가 자명).
- **점진 확장 가능**: 각 Phase가 이전 Phase의 코드를 **버리지 않고** 위에 얹는 형태. Phase 1 `useLocalStorage`는 Phase 3에서도 로컬 캐시로 계속 쓰인다.
