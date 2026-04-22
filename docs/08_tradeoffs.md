# 08. 주요 트레이드오프 & 의사결정

설계 과정에서 의식적으로 **선택한 것**과 **버린 것**. 나중에 되돌아볼 때 맥락을 잃지 않기 위함.

---

## T1. Local-first (localStorage) ↔ 서버 우선

**선택**: Phase 1은 **localStorage 단독**. 서버는 Phase 3부터 추가.

**이유**:
- 로그인·네트워크 없이 즉시 동작하는 제품 경험은 Notion/Confluence 대비 **결정적 차별점**.
- 초기 사용자 확보 전에 서버 운영비와 인증 복잡도를 떠안을 이유가 없다.
- Phase 3에서 서버가 들어와도 localStorage는 **로컬 캐시**로 계속 살아남는다 — 버리는 코드가 아님.

**버린 것**: "처음부터 Firebase/Supabase 로 백엔드부터 잡고 간다" 방식. 반복 속도를 잃는다.

**의사결정 트리거**: 동일 사용자의 2기기 사용 요구가 높아질 때 Phase 3 승격.

---

## T2. 마크다운 원문 저장 ↔ 블록/AST 기반 저장 (Notion 모델)

**선택**: **마크다운 문자열 원문**을 `Document.content` 로 보관.

**이유**:
- **이동성**: 언제든 `.md` 로 빠져나갈 수 있음 → 벤더 락인 없음.
- **렌더러 교체 자유**: `react-markdown` 을 다른 렌더러로 교체해도 데이터는 그대로.
- **AI 입력으로 자연**: 요약/재작성 프롬프트에 원문을 그대로 넣을 수 있음.

**버린 것**: Notion식 블록 그래프(각 블록이 id를 가지고 중첩). 구조화된 데이터가 필요한 기능(블록 단위 댓글·권한·실시간 커서 앵커링)은 **구현이 더 복잡**해진다.

**의사결정 보류 요소**: Phase 4에서 블록 앵커 댓글·슬래시 커맨드가 주력 기능이 되면, 원문은 유지하되 **파생 AST 인덱스**를 별도 가지는 하이브리드로 전환 검토.

---

## T3. 단일 `Document` 플랫 타입 ↔ 풍부한 메타 구조

**선택**: 현재 5개 필드(`id/title/content/createdAt/updatedAt`). 확장 필드는 **필요할 때만** 추가.

**이유**: [05_data_schema.md §3](05_data_schema.md) 참조. YAGNI — 폴더/태그/아이콘은 Phase 1에서만 정당화됨. Phase 0 데모에는 없어도 동작함.

**버린 것**: "미래에 필요할 것" 을 예상해서 `tags`, `parentId`, `pinned` 를 선제적으로 넣는 것. 늘리는 건 쉽고, 잘못된 필드를 빼는 건 어렵다.

---

## T4. React + Vite ↔ Next.js/Remix (SSR 프레임워크)

**선택**: **React 19 + Vite** SPA.

**이유**:
- Phase 1의 제품은 로그인 없는 단일 페이지 — SSR 이득 없음.
- Vite HMR + Tailwind 4 통합이 극도로 빠름.
- 서버 렌더가 필요해지는 시점(공개 퍼블리시 페이지 등)은 Phase 5+.

**버린 것**: Next.js App Router의 레이아웃/라우팅/서버 컴포넌트 편의. 라우팅 수요가 늘면 React Router v6로 보강, 서버 컴포넌트는 도입하지 않는다.

**의사결정 트리거**: SEO가 필요한 공개 페이지가 제품의 중요한 축이 되면 Next.js 하위 앱으로 분리 배포 검토.

---

## T5. Tailwind 4 + Typography ↔ 컴포넌트 라이브러리 정답 채택

**선택**: **Tailwind 4 + `@tailwindcss/typography`** 조합. 컴포넌트 라이브러리는 필요할 때 Radix/shadcn을 부분 도입.

**이유**:
- 이 제품은 **본질이 마크다운 문서 UI** — `prose` 클래스만으로 렌더 품질 80%를 확보.
- MUI/Chakra 같은 풀 컴포넌트 키트는 디자인 톤을 강제하고 번들이 크다.
- shadcn의 copy-paste 모델이 우리 요구와 일치 (Phase 2에서 Dialog/Dropdown이 필요해지면 그때 차용).

**버린 것**: 디자인 일관성을 라이브러리에 위임하는 편리함. 대신 우리가 얇은 디자인 시스템을 Phase 2에 정의해야 한다.

---

## T6. Debounce 300ms ↔ 즉시 저장 / 수동 저장

**선택**: 타이핑 후 **300ms debounce** 로 localStorage persist ([`Editor.tsx:27-32`](../frontend/src/components/Editor.tsx#L27-L32)).

**이유**:
- 매 키 입력마다 JSON 직렬화 + localStorage write 는 낭비이자 큰 문서에서 지연 유발.
- Ctrl+S 같은 수동 저장은 2020년대 UX에 맞지 않음.
- 300ms 는 "타이핑 멈춘 직후" 로 체감되어 데이터 유실 체감이 0에 가깝다.

**리스크**: 탭 급종료 시 최근 300ms 분량 유실 가능. Phase 3에서는 `visibilitychange` 이벤트에 즉시 flush.

---

## T7. CRDT(Y.js) ↔ 서버 권위 동기화 (OT / last-write-wins)

**선택**: **Phase 3은 낙관적 동시성 제어(base_version)**. Phase 4에서 실시간 동시 편집 요구가 실측될 때 **Y.js 도입 여부 결정**.

**이유**:
- CRDT는 편집 품질 최상이지만 **복잡도·번들 크기·학습곡선**이 크다.
- 대부분의 개인/소규모 팀 사용 패턴은 비동시 편집에 가까움 — 낙관적 잠금으로 충분.
- 도입하더라도 마크다운 원문 보관은 유지(Y.Text 위에 mirror).

**버린 것**: 처음부터 완벽한 협업 에디터. 대신 Phase 1~3의 개발 속도를 지킨다.

**의사결정 트리거**: 동일 문서에 대한 동시 편집 세션 중 충돌 UI 노출률이 월간 활성 문서의 3% 이상일 때.

---

## T8. AI 공급자: Gemini 우선, provider-agnostic 레이어 연기

**선택**: Phase 2는 **Gemini 전용**(`@google/genai`). 추상화 레이어는 공급자 2개째 도입 시점에 만든다.

**이유**:
- 추상화는 2개 이상의 구현을 만들어본 뒤에 하는 것이 옳다 — 1개만으로 만든 추상은 반드시 틀린다.
- Gemini 2.5 Flash 는 비용·한국어·스트리밍 균형이 현 시점(2026-04) 우위.

**버린 것**: 처음부터 OpenAI·Anthropic·Google을 모두 감싸는 Router. Phase 2의 속도를 잃는다.

---

## T9. 서버 스택: **Python + FastAPI** (이전 Express 결정 번복, 2026-04-22)

**현 선택**: **Python 3.11+ + FastAPI + Uvicorn + Pydantic v2**. AI 프록시(docdelta 포함)와 Phase 3 CRUD·Phase 4 WebSocket 모두 이 스택으로 진행.

**이전 선택과 번복 사유**:
- 초기 결정은 Node.js + Express였다 (이유: `package.json`에 이미 포함, 유지보수 비용 최소화). Phase 2a PoC(2026-04-22 오전)도 Express/tsx로 1차 구현됨.
- 같은 날 오후 Python 전환 — 이유:
  - Phase 2의 주력 기능 `/api/ai/docdelta`는 **문서 그룹 의미 비교**로, 후속 개발이 벡터 검색·파인튜닝·학습 데이터셋(`reference/train-validation-dataset/`) 등 **Python이 1급 시민인 영역**으로 확장된다.
  - LangChain·llama-index·vLLM·datasets·pandas 같은 Python 생태계 컴포넌트를 Node.js로 우회 호출하는 비용이 장기적으로 더 크다고 판단.
  - FastAPI + Pydantic 조합이 `reference/doc_scheme.json`과 1:1 매핑되며 OpenAPI 자동 생성이 계약 일관성 유지에 기여.
- 비용: 프론트(Node 18+)와 백(Python 3.11+) **이종 런타임**. 단, 모노레포 내 API 계약(OpenAPI + reference scheme)만 정확히 유지하면 경계는 깨끗.

**버린 것**:
- Express의 단일 런타임 이점. tsx + TypeScript 공유 타입(`packages/shared`).
- Fastify/Hono 계열(Node 진영 성능 우위). 이번 결정에서는 Node 자체를 떠남.

**의사결정 트리거 (이 선택을 뒤집을 조건)**:
- WebSocket 동시 접속 수천 이상 + Python GIL/ASGI 성능 병목이 실측될 때 → 고부하 경로만 Go/Rust 사이드카로 분리.
- 팀 주력 언어가 Python에서 벗어나면 재검토.
- Phase 2 끝나기 전에 다시 Node로 번복될 경우 T8 원칙(구현 1개 전 추상 금지) 재조정 필요 — 그래서 번복 비용이 상당함을 인지.

---

## T10. 동기/원격 Markdown 호환성

**선택**: **CommonMark + GFM** 을 유일한 표준으로. 확장은 remark/rehype 플러그인으로만 추가.

**이유**: 이동성([05_data_schema.md §6](05_data_schema.md))의 근간. 커스텀 문법은 다른 도구와의 호환을 깨뜨린다.

**버린 것**: 직접 정의한 단축 문법이나 Notion식 `/` 명령이 **저장 포맷**에 섞이는 것. `/` 커맨드는 **UX 헬퍼일 뿐**, 결과물은 순수 마크다운이어야 한다.

---

## T11. 상태 라이브러리: 현재 없음 → 필요할 때 Zustand

**선택**: Phase 1은 `useState` 만. Phase 2 진입 시 Zustand 도입.

**이유**:
- 컴포넌트 3개 · 상태 2개 규모에 전역 스토어는 **과잉 추상화**.
- Redux Toolkit은 이 규모에선 말 그대로 무거움.
- Zustand는 러닝커브 얕고, TanStack Query와 함께 써도 충돌 없음.

---

## T12. 모노레포 ↔ 프론트/백 분리 레포

**선택**: **모노레포**(현재 디렉토리 확장). 프론트/백 서브디렉토리 분리 — 2026-04 기준 `frontend/`(구현) + `backend/`(Phase 2a docdelta PoC로 2026-04-22 초기화 후 Python 재구성, mock 엔드포인트 1개만 탑재).

**이유**:
- `Document` 계약이 프론트/백 공유 — 모노레포 안에서 reference/doc_scheme.json이라는 "언어 중립 단일 출처"를 두고 양쪽이 각자 모델로 번역.
- 배포는 분리 가능(Vercel/Netlify + Fly/Render/Railway Python).

**현재 구조 (Phase 1 + Phase 2a PoC, Python 재구성)**:
```
wiki-workspace/
  frontend/                (React 19 + Vite + Tailwind — 구현 완료)
    src/
  backend/                 (FastAPI + Python 3.11, docdelta mock — 2026-04-22 Python 재구성)
    pyproject.toml
    app/
      main.py              (FastAPI 앱)
      env.py               (python-dotenv)
      routers/ai.py        (/api/ai/docdelta)
      routers/health.py
      schemas/docdelta.py  (Pydantic 모델)
      services/docdelta_mock.py
      middleware/request_id.py
      middleware/error_handler.py
  docs/                    (설계 문서)
  reference/               (계약 scheme·데이터셋)
```

**확장 구조 예시 (Phase 3 도달 시)**:
```
wiki-workspace/
  frontend/                (프론트)
  backend/                 (FastAPI + SQLAlchemy + Alembic)
    app/
      db/                  (SQLAlchemy models, session)
      alembic/             (마이그레이션)
      routers/documents.py (Phase 3 CRUD)
  infra/
    docker/
  docs/
```

**타입 공유 전략**: `packages/shared`(TS) 방식은 **포기** — 프론트(TS)와 백(Python)이 이종 런타임이므로 공유 코드베이스 불가. 대신 `reference/doc_scheme.json`이 **계약 원본**이고, 양쪽이 각자:
- frontend: `frontend/src/types/docdelta.ts` (TypeScript interface)
- backend: `backend/app/schemas/docdelta.py` (Pydantic BaseModel)

둘의 drift는 wiki-qa가 reference scheme과 매번 교차 검증. Phase 3 진입 시 코드 생성기(`datamodel-code-generator` 등)로 Pydantic/TS 자동 생성 검토.

---

## 의사결정 변경 이력

| 날짜 | 항목 | 변경 | 이유 |
|---|---|---|---|
| 2026-04-22 | 프로젝트 방향 전환 | DocDelta(문서 비교 시스템) → Wiki Workspace (개인/팀 마크다운 위키) | 데모 프론트엔드를 기준으로 재정렬. 기존 설계의 비교·검색·벡터 인덱싱은 범위 밖으로 이동. |
| 2026-04-22 | 전체 아키텍처 재작성 | FastAPI/vLLM/ChromaDB 스택 제거 · React/Vite/Tailwind/Gemini 스택으로 교체 | 실제 레포 자산(`frontend/src/`) 반영 |
| 2026-04-22 | 사이드바 제목 검색 PoC | useState 내부 상태 + Array.filter, 라이브러리 미도입 | T3·T11 준수, 하네스 E2E 검증 목적 |
| 2026-04-22 | docdelta 엔드포인트 PoC (Phase 2a 부분 진입) | Express+mock 서비스로 E2E 동작 흐름 확보, 실 Gemini/SSE/rate limit 연기 | T1(local-first 보장 — 백엔드 미기동 시 앱 나머지 정상), T8(구현 1개 전 추상 금지 — Gemini 호출 코드 미포함), T9(Express 유지, 당일 오후 번복), T11(Zustand 미도입, `AnalyzePanel`은 useState만) 준수. 하네스 개발 PoC |
| 2026-04-22 | **T9 번복: 백엔드 스택 Node/Express → Python/FastAPI** | Phase 2a PoC 코드 전부 재구성, `backend/` 파일 트리 교체(`pyproject.toml` + `app/` Python 패키지) | LLM·학습 데이터·벡터 검색 생태계(Python 1급)와의 궁합 우선. `reference/train-validation-dataset/` 활용 예정. 프론트(Node)·백(Python) 이종 런타임 비용은 reference/doc_scheme.json 단일 출처로 흡수. 하네스 `wiki-backend` 에이전트·스킬 동반 업데이트. |
| 2026-04-22 | **Phase 2 PoC 데모 시나리오 로더 도입** | 프론트 `frontend/src/fixtures/demoScenarios.ts` + `frontend/src/utils/loadDemoScenarios.ts` + Sidebar "데모 시나리오 불러오기" 버튼 신설. 백엔드 `backend/app/services/docdelta_fixtures.py` 신설 + `routers/ai.py` 디스패처 3줄 추가. `Document` 타입·`reference/doc_scheme.json` 무변경. | reference 데이터셋(validation jsonl) 기반 curated 3종(`new+conflict` / `new-only` / `empty`)으로 `AnalyzePanel`의 UI 세 상태를 재현 가능 상태로 시연. `source_id = "DEMO-" + demoScenarioKey` 기반 deterministic dispatch — 프론트 로더 전용 교차 타입으로 메타를 심어 T3(단일 Document 플랫 타입) 유지. 기존 synthetic mock은 non-DEMO source_id에 대해 그대로 폴백(T8 "구현 1개 전 추상 금지" + R4 하위 호환 준수). |
| 2026-04-22 | **Phase 2 PoC 데모 시나리오 로더 철회** (위 행의 즉시 번복) | 프론트 `fixtures/demoScenarios.ts` + `utils/loadDemoScenarios.ts` + Sidebar "데모 시나리오 불러오기" 버튼·`onLoadDemoScenarios` prop·`demoScenarioKey` 교차 타입·`resolveSourceId` 삭제. 백엔드 `services/docdelta_fixtures.py` 삭제 + `routers/ai.py` 의 `source_id.startswith("DEMO-")` 분기 제거. `Document` 5필드·`reference/doc_scheme.json` 여전히 무변경. 기록은 이 이력 테이블·로드맵의 취소선으로 보존. | curated 3종 하드코드 시연은 "사전에 결과를 알고 있는 연출"로 실제 제품 사용 동선(사용자 업로드 → 시스템 유사 문서 자동 선정 → 모델 분석)과 괴리. 사용자가 "실제 흐름에 가까운 데모" 재설계를 요구 — 동적 업로드 경로로 교체. T8 원칙 자체는 유지되며 아래 provider 추상화 행이 별도 정당화됨. architect decision `_workspace/02_architect_decision.md §0.2 / §6 / §11` 참조. |
| 2026-04-22 | **txt 업로드 기반 동적 Analyze 흐름 + Docdelta Provider 추상화 도입** | 프론트: 초기 seed 10건 로더(`utils/loadSeedDocuments.ts`, Welcome 자동 생성 대체) + AnalyzePanel 업로드 버튼/drag-drop zone(100KB·UTF-8) + 순수 JS TF-IDF(`utils/tfidf.ts`) Top-3 유사도 + "워크스페이스에 저장" 승격 버튼. 백엔드: `services/docdelta_provider.py`(Protocol) + `services/docdelta.py`(디스패처) + `services/providers/{mock.py,finetuned.py}`, `LLM_PROVIDER` / `FINETUNED_API_URL` / `FINETUNED_API_KEY` / `FINETUNED_TIMEOUT_SEC` 4개 env 추가, `httpx>=0.27` production 의존성 승격. `Document` 5필드·`reference/doc_scheme.json` 무변경. | (1) 사용자가 직접 업로드한 요약 txt 에 대해 workspace 내 유사 문서를 자동 선정·비교하는 "실제 제품 동선" 재현 = Phase 2 본격 진입. (2) 실 finetuned API 연동을 env 전환만으로 가능하게 사전 준비 — mock ↔ finetuned 디스패처는 "같은 공급자 내부 mock/real" 차이에 가까워 T8("2번째 공급자" 기준)와는 배치되지 않음(주: T8 해설에 mock/real 분리와 provider-agnostic 추상화는 별개 축). (3) DynamoDB 제안은 명시적 거절 — T1(local-first) + Phase 3 Postgres(T9) 결정을 **번복하지 않음**. 재진입 조건은 `_workspace/02_architect_decision.md §11.3` 에 명시(멀티 테넌트/글로벌 분산/쓰기 헤비 워크로드 실증 시 별도 T 항목 신설). 현 시점에서는 코드·문서 어디에도 DynamoDB 관련 언급 추가하지 않음. |
| 2026-04-22 | **vLLM provider 추가 + train/finetune 코드 벤더링** | 백엔드: `services/providers/vllm.py` 신설(3번째 provider, `mock`/`finetuned` 와 공존, byte-for-byte 무변경), `services/providers/_vendor/{__init__.py, infer_diff.py, prompt_text.py}` 신설(`train/finetune/{infer_diff,prompt_text}.py` 를 byte-for-byte 복사 + 상단 8줄 헤더 주석 `Vendored from: ... / DO NOT EDIT HERE`), `services/docdelta.py` dispatcher 에 `"vllm"` 분기 1줄 추가, `env.py` 에 `_PROVIDER_VALUES=("mock","finetuned","vllm")` 확장 + `VLLM_ENDPOINT: str \| None = None` / `VLLM_MODEL: str = "vllmlora"` / `VLLM_API_KEY: str = "EMPTY"` / `HF_TOKENIZER: str = "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16"` 4개 env 추가, `pyproject.toml` `[project.optional-dependencies].vllm = ["openai>=1.0", "transformers>=4.40"]` 추가 + `[tool.ruff].extend-exclude = ["app/services/providers/_vendor"]` 가드. 매핑 규칙: `known_docs` flatten → `list[str]`, `new_doc` 원소별로 `asyncio.to_thread(get_diff, flat_known, item.context)` N회 호출 후 merge, `conflict[].doc_id` 는 known_text substring `in` 매칭 3단 폴백(1차 최초 히트 → 2차 첫 flat-known DocRef → 3차 리터럴 `"unknown"`), `conflict[].severity` 상수 `"medium"` 하드코드, `source_id` 1:1 에코. 에러 매핑 6행: `VLLM_ENDPOINT` 미설정 → 500 AI_UPSTREAM, `[vllm]` extras 미설치 → 500 AI_UPSTREAM + 설치 안내, `APITimeoutError` → 504 TIMEOUT, `APIError`/네트워크 → 502 AI_UPSTREAM, `JSONDecodeError` → 502 AI_UPSTREAM, Pydantic 재검증 실패 → 502 AI_UPSTREAM. `Document` 5필드 · `reference/doc_scheme.json` · `mock`/`finetuned` provider 계약 · 프론트 전부 무변경. | (1) 사용자가 학습한 vLLM(OpenAI-호환 서빙) 모델을 backend 에서 직접 호출해야 하는데, 로직은 이미 `train/finetune/infer_diff.py::get_diff()` 에 존재하고 `train/` 은 수정 금지. 따라서 `_vendor/` 디렉토리로 byte-for-byte 복사(+ 헤더 주석으로 재벤더링 절차 명시)하여 backend 에서 import. (2) mock/finetuned 와 공존(교체 X) — finetuned 는 임의 HTTP 엔드포인트를 소유한 사용자의 탈출구이고, vllm 은 OpenAI-호환 서빙 특화이므로 둘 다 필요. (3) `transformers`/`openai` 는 100MB+ 전이 의존성을 끌어오므로 `[project.optional-dependencies].vllm` extra 로 격리 — 기본 `pip install .` 사용자에게 설치 부담 제로. (4) `get_diff()` 는 sync + heavy(tokenizer 로딩) 이므로 `asyncio.to_thread` 로 감싸서 Protocol(`async def analyze`) 호환 유지, 벤더링 파일 내부는 개조하지 않음. (5) `doc_id` 복원은 벤더링 `get_diff` 출력이 `known_text`/`new_text`/`reason` 3필드만 주므로 substring 매칭으로 복원(3단 폴백), `severity` 는 PoC 단계 `"medium"` 고정(자동 분류는 Phase 3+). (6) 아키텍트 §2 는 본 결정이 T8("2번째 공급자" 원칙)을 위반하지 않는다고 승인 — Protocol 추상은 이미 finetuned 도입 시 정당화되었고 vllm 은 그 재사용 — 따라서 **신규 T 항목 신설 없이** 이력만 추가. 상세 근거: `_workspace/02_architect_decision.md`, `_workspace/03_data_contract.md`, `_workspace/05_backend_changes.md`. |
