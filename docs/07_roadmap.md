# 07. 로드맵

데모(Phase 0) → 완성형 위키 → AI → 동기화 → 협업. 각 Phase는 이전 Phase의 **출력**을 입력으로 삼고, 이전 Phase의 코드를 **버리지 않는다**.

---

## Phase 0 — 프론트엔드 데모 (완료, 현재 레포 상태)

**목표**: 마크다운 에디터 + 사이드바 + localStorage 로 단독 동작하는 MVP.

### 현재 구현된 것
- [x] React 19 + Vite 6 + TypeScript + Tailwind 4 빌드 파이프라인
- [x] `App` · `Sidebar` · `Editor` · `useLocalStorage` ([03_components.md](03_components.md))
- [x] Edit / Split / Preview 3-모드 에디터
- [x] CommonMark + GFM 렌더 (`react-markdown` + `remark-gfm`)
- [x] 300ms debounce 저장
- [x] ~~첫 실행 시 "Welcome" 문서 시드~~ (2026-04-22 대체 — 아래 seed 10건 로더로 교체)
- [x] 첫 실행 시 초기 seed 10건 로더 (`frontend/src/data/1.txt ~ 10.txt` → `seed-doc-{1..10}` Document, Welcome 자동 생성 대체, 2026-04-22 `frontend/src/utils/loadSeedDocuments.ts`)

---

## Phase 1 — 위키 완성도 (목표 2주)

**목표**: 데모를 "매일 쓸 수 있는 도구"로 끌어올린다. **백엔드 없이**.

### 작업
- [~] 사이드바 검색바 (제목 필터 PoC 완료 / 본문 검색·200ms debounce 미구현)
- [ ] `⌘K` 커맨드 팔레트 (문서 이동 / 생성 / 삭제)
- [ ] 폴더 트리 (`parentId` 도입, 드래그앤드롭은 Phase 2에서)
- [ ] 태그 필드 + 태그별 필터
- [ ] 아이콘(이모지) 지정
- [ ] Export / Import (JSON 및 `.md` zip)
- [ ] 다크 모드 토글 (`prefers-color-scheme` + 수동 토글)
- [ ] 접근성 보강 (포커스 링 · `aria-label` · 키보드 네비게이션)
- [ ] ESLint + Prettier + Vitest 도입, CI 구성

### 완료 기준 (DoD)
- 새 사용자가 매뉴얼 없이 30분 안에 "매일 쓰는 개인 위키"로 전환할 수 있음.
- Lighthouse: Performance ≥ 95, Accessibility ≥ 90.
- 핵심 흐름(생성/편집/삭제/검색)에 Vitest 단위 테스트 커버리지 존재.

---

## Phase 2 — AI 보조 (목표 2주)

**목표**: 편집 중 맥락에 맞는 AI 액션을 1급 시민으로 노출.

### 2a. 서버 프록시 (3~4일, **Python/FastAPI 스택**)
- [~] **FastAPI + Uvicorn** 서버 뼈대 (`backend/` 디렉토리, Python 3.11+, PoC 재구성 2026-04-22 — 초기 Express/tsx 구현을 Python으로 전환)
- [ ] `GEMINI_API_KEY` 주입 (PoC mock-first — 실 LLM 연동 미진행; `backend/.env.example`에 placeholder만)
- [ ] `/api/ai/summarize`, `/api/ai/suggest-title`, `/api/ai/rewrite` 구현 (mock, `google-generativeai` 실 연동은 후속)
- [~] `/api/ai/docdelta` 구현 (mock, 2026-04-22 — `reference/doc_scheme.json` 준수, Pydantic v2 스키마)
- [~] ~~`/api/ai/docdelta` fixture 분기 — curated 3종(DEMO-scenario_{1,2,3})의 ground-truth 응답 매핑 (2026-04-22, `backend/app/services/docdelta_fixtures.py`)~~ **(2026-04-22 철회)** — provider 추상화로 교체. `docdelta_fixtures.py` 파일 삭제, `routers/ai.py` 의 `DEMO-*` 분기 제거.
- [x] `/api/ai/docdelta` provider 추상화 — `services/docdelta_provider.py`(Protocol) + `services/docdelta.py`(디스패처) + `services/providers/{mock.py,finetuned.py}`, `LLM_PROVIDER` env 로 mock/finetuned 디스패치 (2026-04-22)
- [x] `/api/ai/docdelta` **vLLM provider 추가** — `services/providers/vllm.py` 신설(3번째 provider, 공존) + `services/providers/_vendor/{infer_diff,prompt_text}.py` 신설(`train/finetune/*.py` byte-for-byte 벤더링 + 헤더 주석) + dispatcher `"vllm"` 분기 + `VLLM_ENDPOINT`/`VLLM_MODEL`/`VLLM_API_KEY`/`HF_TOKENIZER` 4개 env + `[project.optional-dependencies].vllm = ["openai>=1.0", "transformers>=4.40"]` (2026-04-22). `asyncio.to_thread` 로 sync `get_diff` Protocol 호환, `doc_id` 3단 폴백 복원 + `severity="medium"` 상수, extras 미설치 시 500 AI_UPSTREAM + 설치 안내. `mock`/`finetuned`/`Document`/`reference/doc_scheme.json`/프론트 전부 무변경.
- [ ] SSE 스트리밍 지원 (FastAPI `StreamingResponse`)
- [ ] 간단한 in-memory rate limit (또는 `slowapi`)

### 2b. 클라이언트 통합
- [ ] `AIPanel` 컴포넌트 (우측 드로어)
- [~] `AnalyzePanel` 컴포넌트 (Editor 카드 내 인라인 — docdelta PoC, 2026-04-22) — `AIPanel` 도입 시 탭으로 흡수 후보
- [~] ~~Sidebar "데모 시나리오 불러오기" 로더 — curated 3종을 localStorage에 append-only 적재 (2026-04-22, `frontend/src/fixtures/demoScenarios.ts` + `frontend/src/utils/loadDemoScenarios.ts`)~~ **(2026-04-22 철회)** — 파일·버튼·prop 전부 삭제. 아래 업로드 흐름으로 대체.
- [x] txt 업로드 기반 Analyze 흐름 — AnalyzePanel 업로드 버튼 + drag-drop zone (100KB 상한, UTF-8 강제), 프론트 TF-IDF Top-3 유사도 선정, `known_docs` 단일 그룹 요청, 결과 렌더 + "워크스페이스에 저장" 승격 버튼 (2026-04-22, `frontend/src/utils/tfidf.ts` + `components/AnalyzePanel.tsx` 전면 재작성)
- [ ] 에디터 툴바에 AI 액션 버튼
- [ ] 선택 영역 재작성 → 블록 대체
- [ ] 스트리밍 응답 실시간 렌더

### 완료 기준
- 사용자가 문서 편집 중 3-클릭 이내로 요약/제목/재작성 실행.
- 키 노출 없음 (브라우저 DevTools/네트워크 탭으로 확인).
- AI 미응답 시 그레이스풀 degradation (에러 UI, 재시도 버튼).

---

## Phase 3 — 클라우드 동기화 (목표 3주)

**목표**: 여러 기기에서 동일한 문서 집합. 로컬 우선, 서버는 정본.

### 3a. 인증 + 저장소 (1.5주, **Python 스택**)
- [ ] **Authlib** (또는 FastAPI Users) 기반 Google OAuth 로그인 — 세션 쿠키 (T9 스택)
- [ ] Postgres + **SQLAlchemy 2.0(async) + Alembic** 연동 (T9 스택; 이전 Drizzle 결정은 Python 전환으로 교체)
- [ ] `/api/documents` CRUD 5종 구현 ([04_api.md](04_api.md))
- [ ] 로컬 → 서버 최초 업로드 마법사

### 3b. 동기화 레이어 (1.5주)
- [ ] TanStack Query 도입 (낙관적 업데이트 · 무효화)
- [ ] 오프라인 큐 + 재연결 시 재시도
- [ ] `base_version` 기반 낙관적 동시성 제어
- [ ] 충돌 시 diff 기반 머지 UI

### 완료 기준
- 기기 A에서 편집 → 3초 내 기기 B 반영 (온라인 상황).
- 오프라인 편집 → 재연결 시 자동 병합, 충돌만 사용자에게 노출.
- 인증된 사용자의 데이터는 격리 (테스트로 확인).

---

## Phase 4 — 협업 (목표 3주)

**목표**: 문서 공유 · 실시간 동시 편집 · 히스토리.

### 작업
- [ ] `ShareDialog` — 이메일 초대, 링크 공유, role 선택
- [ ] 권한 체크 미들웨어 (viewer/commenter/editor)
- [ ] WebSocket 채널 (`/api/documents/:id/ws`)
- [ ] Presence: 현재 보고 있는 사용자 아바타 표시
- [ ] 실시간 커서 · 선택 영역 동기화
- [ ] Y.js 도입 결정 (T7 참조) — 도입 시 프로토콜 교체
- [ ] 버전 히스토리 (타임라인 + restore)
- [ ] 댓글 스레드 (블록 앵커링)

### 완료 기준
- 두 사용자가 동시 편집 시 문자 유실 0.
- 권한 시나리오(viewer는 편집 불가 등) E2E 테스트 통과.
- 90일 이내 히스토리 복원 가능.

---

## Phase 5+ (선택)

- **모바일**: PWA → React Native 앱 랩핑
- **확장**: 슬래시 커맨드 기반 블록 시스템 (Notion 유사)
- **템플릿**: 회의록/주간보고 템플릿 갤러리
- **임베드**: 유튜브·코드스니펫·칸반 블록
- **공개 퍼블리시**: 문서를 공개 링크로 발행 (정적 생성)
- **AI 검색**: 문서 전체 코퍼스를 임베딩해 자연어 질의

---

## 전체 일정 (목표 베이스라인)

| Phase | 기간 | 누적 |
|---|---|---|
| 0 (완료) | — | — |
| 1 | 2주 | 2주 |
| 2 | 2주 | 4주 |
| 3 | 3주 | 7주 |
| 4 | 3주 | 10주 |

총 **약 10주(2.5개월)** 로 개인용 → 팀 협업까지 완성.
인력 여유가 있으면 Phase 2와 Phase 3의 서버 작업을 병렬화 가능.

---

## Phase 간 불변 규칙

1. **데이터 이동성 유지**: 언제든 Export 한 번으로 표준 `.md` 로 빠져나갈 수 있어야 한다.
2. **로컬 우선 유지**: Phase 3 이후에도 인터넷 없이 앱이 동작해야 한다.
3. **마크다운 원문 보관**: 서버 어디서도 렌더된 HTML만 보관하지 않는다.
4. **하위 호환 깨지 않기**: `Document` 타입에 필드를 **추가**만 한다(필수 필드 변경 금지, 제거 금지).
