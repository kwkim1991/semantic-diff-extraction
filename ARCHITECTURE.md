# Wiki Workspace — Architecture Overview

> 프로젝트 전체를 한 장으로 훑기 위한 단일 진입점. 세부는 [`docs/`](docs/) 9편을 권위 출처로 참조.
> 작성 기준일: 2026-04-22 (Phase 2a 진입 + vLLM provider 추가 반영).

---

## 1. 한 줄 요약

**로컬 우선(local-first) 마크다운 기반 개인/팀 위키 + AI 기반 문서 delta 분석**.
프론트는 localStorage 만으로 완결, 백엔드는 AI(`/api/ai/docdelta`) 프록시 전용.
Phase 0(데모) → 1(위키 완성도) → 2(AI 보조) → 3(클라우드 동기화) → 4(협업) 로 **이전 단계 코드를 버리지 않고** 점진 확장.

## 2. 모노레포 구조

```
wiki-workspace/
├── CLAUDE.md              # 프로젝트 루트 컨텍스트 + 하네스 변경 이력
├── ARCHITECTURE.md        # ← 이 파일 (단일 진입 개요)
├── frontend/              # React 19 + Vite 6 + Tailwind 4 SPA
│   ├── src/
│   │   ├── App.tsx                       # 문서 상태·viewMode (editor|analyze)
│   │   ├── components/
│   │   │   ├── Sidebar.tsx               # 문서 목록·생성·삭제·제목 검색
│   │   │   ├── Editor.tsx                # Edit|Split|Preview 3-모드 (기본 preview)
│   │   │   └── AnalyzePanel.tsx          # txt 업로드 + TF-IDF Top-3 + 결과 렌더
│   │   ├── hooks/useLocalStorage.ts      # 단일 영속 경계
│   │   ├── services/docdelta.ts          # POST /api/ai/docdelta 클라이언트
│   │   ├── types/docdelta.ts             # Pydantic 과 hand-sync 되는 TS 타입
│   │   ├── types.ts                      # Document 5필드 (id/title/content/createdAt/updatedAt)
│   │   ├── utils/loadSeedDocuments.ts    # 첫 실행 seed 10건 (Welcome 대체)
│   │   ├── utils/tfidf.ts                # 순수 JS TF-IDF Top-K
│   │   └── data/1.txt ~ 10.txt           # seed 원문
│   └── vite.config.ts                    # dev proxy `/api` → backend
├── backend/               # FastAPI + Python 3.11 (Phase 2+)
│   ├── pyproject.toml                    # core + [dev] + [gemini] + [vllm] extras
│   └── app/
│       ├── main.py                       # FastAPI 앱 + CORS + 에러 핸들러
│       ├── env.py                        # dotenv + LLM_PROVIDER 디스패치 Literal
│       ├── routers/{ai,health}.py        # /api/ai/docdelta, /api/health
│       ├── schemas/docdelta.py           # reference/doc_scheme.json 과 1:1 Pydantic
│       ├── services/
│       │   ├── docdelta.py               # get_provider() 디스패처
│       │   ├── docdelta_provider.py      # Protocol: async analyze()
│       │   └── providers/
│       │       ├── mock.py               # 결정론적 synthetic 응답
│       │       ├── finetuned.py          # httpx → 임의 외부 HTTP 엔드포인트
│       │       ├── vllm.py               # ← 2026-04-22 추가, OpenAI-호환 vLLM
│       │       └── _vendor/              # train/finetune 에서 벤더링
│       │           ├── infer_diff.py     # byte-for-byte 복사 + 헤더 주석
│       │           └── prompt_text.py    # byte-for-byte 복사 + 헤더 주석
│       └── middleware/{request_id,error_handler}.py
├── docs/                  # 설계·로드맵·트레이드오프 (9편, 1440 라인)
│   ├── 01_overview.md / 02_architecture.md / 03_components.md
│   ├── 04_api.md / 05_data_schema.md / 06_tech_stack.md
│   ├── 07_roadmap.md / 08_tradeoffs.md / README.md
├── reference/             # AI 계약 권위 출처
│   ├── doc_scheme.json                   # DocdeltaRequest/Response 단일 SoT
│   └── train-validation-dataset/*.jsonl  # 학습·검증 데이터
├── train/                 # 학습 코드 (backend 와 독립, 수정 금지)
│   └── finetune/
│       ├── infer_diff.py                 # vLLM 호출 get_diff() 원본
│       └── prompt_text.py                # chat-template 재구성 원본
├── _workspace/            # 현재 하네스 산출물 (감사/후속 작업)
├── _workspace_prev/       # 이전 하네스 산출물 보존
└── .claude/               # 하네스 (agents 6 + skills 7)
```

## 3. 런타임 아키텍처 (현재 구동 가능 상태)

```
┌─ Browser ───────────────────────────────────────────────────────┐
│  http://localhost:3000 (or remote 95.133.253.152:3000)          │
│  React 19 SPA — localStorage("wiki-docs")가 단일 영속           │
└────────────────────────────┬────────────────────────────────────┘
                             │ fetch("/api/ai/docdelta", POST)
                             │ (상대경로 → Vite dev proxy 로 흡수)
┌────────────────────────────▼────────────────────────────────────┐
│  Vite dev server :3000                                          │
│  server.proxy: { "/api": env.BACKEND_URL || "localhost:3001" }  │
└────────────────────────────┬────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────┐
│  FastAPI :3001                                                  │
│  • routers/ai.py  → get_provider().analyze(req) (async)         │
│  • get_provider() 는 env.LLM_PROVIDER 로 1개 선택               │
└─────┬─────────────────────┬──────────────────────────┬──────────┘
      │ "mock"              │ "finetuned"              │ "vllm"
      ▼                     ▼                          ▼
  MockProvider        FinetunedProvider           VllmProvider
  (결정론적 synthetic) (httpx → 외부 HTTP)        (asyncio.to_thread)
                                                    │
                                                    │ _vendor/infer_diff.get_diff(...)
                                                    ▼
                                       ┌─ vLLM server :9983/v1 ─┐
                                       │  OpenAI-호환 API       │
                                       │  guided_json DiffOutput│
                                       │  model=vllmlora        │
                                       └────────────────────────┘
```

**기본 모드**는 `mock` — 백엔드만 띄우면 즉시 동작. vLLM 연결은 env 전환 + `[vllm]` extras 설치만으로 가능.

## 4. 핵심 계약 (변경 시 cross-package 영향)

### 4.1 단일 권위 출처
`reference/doc_scheme.json` 이 **Request/Response 구조의 원본**. 프론트 TypeScript와 백엔드 Pydantic은 각각 이를 손수 번역한 복제본이며 wiki-qa가 drift를 교차 검증한다.

```
reference/doc_scheme.json
 ├── frontend/src/types/docdelta.ts   (TypeScript interface)
 └── backend/app/schemas/docdelta.py  (Pydantic v2 BaseModel)
```

### 4.2 `Document` 도메인 타입 (프론트 SoT)
5필드 플랫 구조. 확장 필드는 Phase 별로 추가만, 제거/변경 금지 (R4 불변 규칙).

```ts
interface Document {
  id: string; title: string; content: string;
  createdAt: number; updatedAt: number;
}
```

### 4.3 Docdelta 계약 (Phase 2a)
- `DocdeltaRequest`: `{ source_id, instruction, known_docs: DocRef[][], new_doc: DocRef[], convert_doc: DocRef[] }`
- `DocdeltaResponse`: `{ source_id, output: { new: string[], conflict: Conflict[] } }`
- `Conflict`: `{ doc_id, known_text, new_text, reason, severity: "low"|"medium"|"high" }`
- `source_id`는 요청 → 응답 1:1 에코 (모든 provider 공통).

### 4.4 Provider 매핑 규약 (vllm 전용 서버 내부 변환)
vLLM의 `get_diff` 출력(3필드)을 5필드 `DocdeltaConflict`로 복원:
- `known_docs` flatten → `list[str]`, `new_doc` 원소별로 N회 호출 후 merge.
- `doc_id`: `known_text` substring in 매칭 → 폴백 첫 ref → 폴백 `"unknown"`.
- `severity`: 상수 `"medium"` (자동 분류는 Phase 3+).

## 5. 4대 불변 규칙 (모든 Phase 교차 적용)

| # | 규칙 | 강제 지점 |
|---|---|---|
| R1 | 데이터 이동성 — 언제든 `.md` export 가능 | `Document.content`는 마크다운 원문 문자열 |
| R2 | 로컬 우선 — 네트워크·백엔드 없어도 앱 동작 | 프론트가 localStorage로 완결, `/api/ai/*` 실패는 AnalyzePanel 국지화 |
| R3 | 마크다운 원문 보관 — 서버 어디서도 렌더된 HTML만 저장 금지 | Pydantic `DocRef.context`가 원문, 서버 측 렌더 경로 없음 |
| R4 | 하위 호환 — `Document` 필드 추가만, 제거/변경 금지 | T3 + 05_data_schema.md §3 확장 로드맵 |

## 6. 의사결정 요약 (T1~T12)

상세는 [`docs/08_tradeoffs.md`](docs/08_tradeoffs.md). 여기선 헤드라인만.

| # | 제목 | 현 선택 | 버린 것 |
|---|---|---|---|
| T1 | Local-first | localStorage 단독 (Phase 1) | 처음부터 Firebase/Supabase |
| T2 | 마크다운 원문 저장 | `Document.content`는 문자열 | Notion식 블록 그래프 |
| T3 | Document 플랫 5필드 | YAGNI, 필요 시점에만 추가 | 예상 필드 선제 투입 |
| T4 | React 19 + Vite SPA | HMR + 마크다운 UI 속도 우위 | Next.js/Remix SSR |
| T5 | Tailwind 4 + Typography | `prose`로 품질 80% 확보 | MUI/Chakra 풀 키트 |
| T6 | 300ms debounce 저장 | 타이핑 체감 무지연 | 매-키 저장 or 수동 Ctrl+S |
| T7 | 서버 권위 동기화 (Phase 3) | base_version 낙관적 잠금 | 처음부터 CRDT(Y.js) |
| T8 | AI provider 추상화 연기 | 2번째 공급자 도입 시 |  초기 universal router |
| T9 | **Node/Express → Python/FastAPI 번복** (2026-04-22) | LLM 생태계 궁합 | Express + `packages/shared` TS 공유 |
| T10 | CommonMark + GFM 전용 | 표준 준수 = 이동성 | 커스텀 단축 문법 |
| T11 | Zustand는 Phase 2부터 | 현재 규모엔 과잉 | Redux Toolkit 선제 |
| T12 | 모노레포 (frontend + backend) | reference scheme 단일 SoT | 프론트/백 분리 레포 |

**최근 변경 이력** (2026-04-22, 의사결정 변경 이력 마지막 3행):
1. 데모 시나리오 로더 도입 → 2. 즉시 철회 (txt 업로드·TF-IDF·provider 추상화로 재설계) → 3. **vLLM provider 추가 + train/finetune 벤더링**.

## 7. Phase 로드맵 (현재 위치 ★)

| Phase | 목표 | 기간 | 상태 |
|---|---|---|---|
| 0 | 프론트엔드 데모 (seed 10건 + 3-모드 에디터) | — | **완료** |
| 1 | 위키 완성도 (검색·커맨드팔레트·태그·Export) | 2주 | 일부 진행 |
| **2a** | **AI 서버 프록시 (FastAPI + provider 3종)** | 3~4일 | **★ 현재 (mock/finetuned/vllm 완료, Gemini/SSE 미진행)** |
| 2b | AI 클라이언트 통합 (AnalyzePanel + 업로드) | — | **완료 (txt 업로드·TF-IDF Top-3)** |
| 3 | 클라우드 동기화 (Authlib·Postgres·SQLAlchemy) | 3주 | 미진입 |
| 4 | 협업 (WebSocket·presence·Y.js 결정) | 3주 | 미진입 |

## 8. Provider 시스템 세부

### 8.1 디스패치 룰
```python
# backend/app/services/docdelta.py
def get_provider() -> DocdeltaProvider:
    if env.LLM_PROVIDER == "finetuned": return FinetunedProvider()
    if env.LLM_PROVIDER == "vllm":      return VllmProvider()
    return MockProvider()   # "mock" 및 불량 값 fallback
```

### 8.2 Env 매트릭스

| Env | mock | finetuned | vllm |
|---|---|---|---|
| `LLM_PROVIDER` | `mock` | `finetuned` | `vllm` |
| `FINETUNED_API_URL` | — | 필수 | — |
| `FINETUNED_API_KEY` | — | 선택 | — |
| `FINETUNED_TIMEOUT_SEC` | — | 기본 30 | — |
| `VLLM_ENDPOINT` | — | — | 필수 (예: `http://localhost:9983/v1`) |
| `VLLM_MODEL` | — | — | 기본 `vllmlora` |
| `VLLM_API_KEY` | — | — | 기본 `EMPTY` |
| `HF_TOKENIZER` | — | — | 기본 Nemotron-3-Nano |
| `[vllm]` extras 설치 | 불필요 | 불필요 | **필수** |

### 8.3 에러 매핑 (3종 공통 envelope: `{error: {code, message}}`)

| 사유 | status | code |
|---|---|---|
| Validation (Pydantic / empty new_doc) | 422 | VALIDATION |
| Provider 미설정 / vllm extras 미설치 | 500 | AI_UPSTREAM |
| Upstream timeout (httpx / OpenAI SDK) | 504 | TIMEOUT |
| Upstream 4xx/5xx · 네트워크 · 파싱 실패 | 502 | AI_UPSTREAM |

### 8.4 vLLM 전용 파이프라인
```
DocdeltaRequest
  ↓ (flatten known_docs + iterate new_doc)
for nd in req.new_doc:
    await asyncio.to_thread(
        _vendor.infer_diff.get_diff,
        flat_known_texts, nd.context,
        vllm_endpoint=..., vllm_model=..., tokenizer_source=...,
    )
    # 내부: transformers chat-template → OpenAI SDK /v1/completions
    #       with extra_body={"guided_json": DiffOutput.model_json_schema()}
  ↓ (3필드 conflict → 5필드 DocdeltaConflict 복원)
DocdeltaResponse
```

## 9. 하네스 (`.claude/`)

프로젝트 작업을 수행하는 전문가 에이전트 팀. **Wiki Workspace 관련 구현·확장·수정·설계 검토·회귀 검증은 `wiki-workspace-orchestrator` 스킬을 통해 조율**되며, 단순 질문·코드 설명은 직접 응답 가능.

| 에이전트 | 책임 |
|---|---|
| `wiki-architect` | 설계 결정·불변 규칙 검토·트레이드오프 분석 |
| `wiki-data` | Document/API/DB 스키마 계약·하위 호환 보증 |
| `wiki-frontend` | React + Vite + Tailwind 구현 |
| `wiki-backend` | FastAPI·Pydantic·(Phase 3) SQLAlchemy 구현 |
| `wiki-qa` | 통합 정합성·불변 규칙·경계면 교차 검증 |
| `wiki-docs` | docs/ 동기화·의사결정 이력 기록 |

## 10. 개발 환경 / 실행

### 10.1 Node (프론트)
```bash
# nvm 로 Node 20+ 활성 (v12 로는 Vite 6 기동 불가)
. ~/.nvm/nvm.sh && nvm use 24
cd frontend
npm ci                   # 최초 1회 (native binding 재설치 필요)
npm run dev              # http://localhost:3000, Vite proxy /api → :3001
```

### 10.2 Python (백엔드)
```bash
cd backend
uv sync                               # core 의존성
uv sync --extra vllm                  # vLLM 호출이 필요하면 추가
# mock 모드 (기본)
uv run uvicorn app.main:app --port 3001
# vllm 모드
LLM_PROVIDER=vllm VLLM_ENDPOINT=http://localhost:9983/v1 \
  uv run uvicorn app.main:app --port 3001
```

### 10.3 Smoke test
```bash
curl -sS -X POST http://localhost:3001/api/ai/docdelta \
  -H "Content-Type: application/json" \
  -d '{"source_id":"T","instruction":"t",
       "known_docs":[[{"doc_id":"k1","context":"sample"}]],
       "new_doc":[{"doc_id":"n1","context":"new"}]}'
```

## 11. 관련 문서 링크

| 문서 | 다룸 |
|---|---|
| [docs/01_overview.md](docs/01_overview.md) | 제품 문제 정의·핵심 가치·사용 시나리오 |
| [docs/02_architecture.md](docs/02_architecture.md) | 레이어 구조·데이터 흐름 6개 Flow (A~F) |
| [docs/03_components.md](docs/03_components.md) | 컴포넌트별 상세 설계·훅 분해 |
| [docs/04_api.md](docs/04_api.md) | API 계약 (동기화·AI 프록시 · 에러 envelope) |
| [docs/05_data_schema.md](docs/05_data_schema.md) | Document 타입·localStorage·Postgres 스키마 |
| [docs/06_tech_stack.md](docs/06_tech_stack.md) | 기술 선택 근거·의존성 매트릭스 |
| [docs/07_roadmap.md](docs/07_roadmap.md) | Phase 0~4 작업·완료 기준·일정 |
| [docs/08_tradeoffs.md](docs/08_tradeoffs.md) | T1~T12 트레이드오프 + 의사결정 변경 이력 |
| [reference/doc_scheme.json](reference/doc_scheme.json) | AI 계약 권위 출처 (JSON) |
| [CLAUDE.md](CLAUDE.md) | 루트 컨텍스트 + 하네스 변경 이력 |
| [frontend/CLAUDE.md](frontend/CLAUDE.md) | 프론트 서브패키지 게이트 |

---

**이 문서의 역할**: `docs/` 9편을 대체하지 않는다. 처음 합류한 사람이 5분 안에 전체 지형을 파악하는 용도. 세부 의사결정·계약·구현 가이드는 각 문서의 권위 출처를 따라간다. 불변 규칙(R1~R4) · T1~T12 · Phase 경계는 여기서 요약만 하고, 상충 시 `docs/08_tradeoffs.md` 본문이 이긴다.
