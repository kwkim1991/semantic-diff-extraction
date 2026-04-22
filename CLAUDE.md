# Wiki Workspace

마크다운 기반 개인/팀 위키 + (Phase 2+) AI 기반 문서 delta 분석(new/conflict 추출). 설계는 [`docs/`](docs/README.md), AI 계약 권위 출처는 [`reference/doc_scheme.json`](reference/doc_scheme.json).

## 모노레포 구조

| 경로 | 역할 |
|---|---|
| `frontend/` | React 19 + Vite + Tailwind 4 SPA. `src/`, `package.json`, `index.html`, `vite.config.ts` 등 프론트 자산 포함. |
| `backend/` | (Phase 2+) **FastAPI(Python 3.11+) + AI 프록시** — 2026-04-22 Python 재구성(T9 번복) 이후 docdelta mock 엔드포인트 탑재. Phase 3에서 SQLAlchemy 2.0 + Alembic 추가 예정. |
| `docs/` | 설계·로드맵·트레이드오프 문서 9개. |
| `reference/` | AI 엔드포인트 계약의 **권위 출처**: `doc_scheme.json`(input/output 구조) + `train-validation-dataset/*.jsonl`(학습/검증 데이터). |
| `_workspace/` | 하네스 중간 산출물(감사/후속 작업용). |
| `.claude/` | 하네스 (에이전트 정의 6개 + 스킬 7개). |

## 하네스: Wiki Workspace

**목표:** 위키 제품을 Phase 0(데모)부터 Phase 4(협업)까지 확장하면서 아키텍처·구현·계약·문서 동기화를 전문가 팀으로 조율한다.

**트리거:** Wiki Workspace(`frontend/`, `backend/`, `docs/`, `reference/`)의 기능 구현·확장·수정·설계 검토·회귀 검증 요청 시 `wiki-workspace-orchestrator` 스킬을 사용하라. 단순 질문이나 코드 설명은 직접 응답 가능.

**변경 이력:**
| 날짜 | 변경 내용 | 대상 | 사유 |
|------|----------|------|------|
| 2026-04-22 | 초기 구성 (agents 6개, skills 7개) | 전체 | docs 기반 하네스 신규 구축 |
| 2026-04-22 | reference/doc_scheme.json을 AI 엔드포인트 계약 권위 출처로 등록 | docs/04_api.md, wiki-backend-implement, wiki-data-contract | 사용자 제공 학습 데이터·input/output 구조를 endpoint 설계에 반영 |
| 2026-04-22 | 프로젝트를 모노레포 구조로 재편 (`frontend/`, `backend/` 분리) | 모든 에이전트/스킬의 경로 참조 | 사용자가 디렉토리 구조 변경 |
| 2026-04-22 | **백엔드 스택 Node/Express → Python/FastAPI 전환** | `wiki-backend.md` 에이전트 정의, `wiki-backend-implement/SKILL.md`, docs/02·04·06·07·08, `backend/` 파일 트리 | LLM·학습 데이터 생태계 궁합, T9 번복 결정 반영 |
| 2026-04-22 | 데모 시나리오 로더 도입 (Phase 2 PoC 시연 보강) | 프론트 `fixtures/demoScenarios.ts` + `utils/loadDemoScenarios.ts` + Sidebar 버튼, 백엔드 `services/docdelta_fixtures.py` + `routers/ai.py` 디스패처. docs/04·07·08 동기화. | reference 데이터셋 기반 curated 3종으로 AnalyzePanel UI 세 상태(new+conflict / new-only / empty) 시연 가능. `source_id="DEMO-"+key` deterministic dispatch. Document 타입·reference/doc_scheme.json 무변경. |
| 2026-04-22 | **데모 흐름 재설계: B+C 철회 + txt 업로드 + TF-IDF + provider 추상화로 교체** | 프론트: `fixtures/demoScenarios.ts`·`utils/loadDemoScenarios.ts`·Sidebar `onLoadDemoScenarios` prop 삭제 + `utils/loadSeedDocuments.ts`(seed 10건, Welcome 대체)·`utils/tfidf.ts`(순수 JS Top-3)·`components/AnalyzePanel.tsx` 전면 재작성. 백엔드: `services/docdelta_fixtures.py`·`services/docdelta_mock.py` 삭제, `services/docdelta_provider.py`(Protocol)+`services/docdelta.py`(디스패처)+`services/providers/{__init__,mock,finetuned}.py` 신설, `LLM_PROVIDER`/`FINETUNED_API_URL`/`FINETUNED_API_KEY`/`FINETUNED_TIMEOUT_SEC` env 4개 추가, `httpx>=0.27` production 의존성 승격. docs/02·03·04·06·07·08 동기화 (08 의사결정 변경 이력에 "철회" + "재설계" 2행 추가, 기존 "도입" 행 보존). | curated 3종 하드코드 시연이 "실제 사용 동선"과 괴리 → 사용자 요구에 따라 동적 업로드·자동 유사문서 선정·모델 분석·선택적 승격 흐름으로 교체. 실 finetuned API 붙일 수 있게 env 기반 provider 디스패처 사전 준비. seed 10건이 Welcome 자동 생성 대체. DynamoDB 제안은 명시적 거절(T1 local-first + Phase 3 Postgres 결정 유지). `Document` 5필드·`reference/doc_scheme.json` 여전히 무변경. 신규 T 항목 신설 없이 `docs/08_tradeoffs.md` 의사결정 변경 이력에만 기록(mock/real 디스패치는 T8 의 "2번째 공급자" 기준과 다른 축). |
| 2026-04-22 | vLLM provider 추가 (3rd provider, 공존) + train/finetune/{infer_diff, prompt_text}.py 를 backend/app/services/providers/_vendor/ 로 벤더링 | `backend/app/services/providers/{vllm.py, _vendor/__init__.py, _vendor/infer_diff.py, _vendor/prompt_text.py}`, `backend/app/services/docdelta.py`, `backend/app/env.py`, `backend/pyproject.toml`, `docs/04_api.md`, `docs/06_tech_stack.md`, `docs/08_tradeoffs.md` (선택 반영: `docs/02_architecture.md`, `docs/07_roadmap.md`) | train/ 의 `get_diff()` (OpenAI-호환 vLLM + `guided_json` 강제 `DiffOutput` 스키마) 를 backend 에서 직접 호출하기 위해. train/ 수정 금지 제약으로 벤더링 방식 선택(헤더 8줄 주석으로 원본·재벤더링 절차 명시, 내부 개조 금지). 의존성은 optional extra `[vllm] = ["openai>=1.0", "transformers>=4.40"]` 로 격리(기본 `pip install .` 사용자 부담 0). `env.LLM_PROVIDER` Literal 을 `"mock"|"finetuned"|"vllm"` 3값으로 확장 + `VLLM_ENDPOINT`/`VLLM_MODEL`/`VLLM_API_KEY`/`HF_TOKENIZER` 4개 env 추가. sync `get_diff` 는 `asyncio.to_thread` 로 감싸 Protocol(`async def analyze`) 호환 유지. `conflict[].doc_id` 는 known_text substring `in` 매칭 3단 폴백으로 복원(1차 최초 히트 → 2차 첫 flat-known DocRef → 3차 `"unknown"`), `severity="medium"` 상수 하드코드. 에러 매핑 6행: endpoint 미설정/extras 미설치 → 500 AI_UPSTREAM(설치 안내 포함), `APITimeoutError` → 504 TIMEOUT, `APIError`/네트워크/`JSONDecodeError`/Pydantic 재검증 → 502 AI_UPSTREAM. `mock`·`finetuned` provider 계약·`Document` 5필드·`reference/doc_scheme.json`·프론트 전부 무변경. 아키텍트 승인: 본 결정은 T8("2번째 공급자" 원칙)과 상충하지 않으므로(Protocol 은 finetuned 도입으로 이미 정당화) 신규 T 번호 신설 없이 `docs/08_tradeoffs.md` 의사결정 변경 이력에만 이력 1행 추가. |
