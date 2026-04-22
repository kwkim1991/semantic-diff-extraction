# 07. Docs 변경 요약 — vLLM Provider 추가

> 입력: `_workspace/02_architect_decision.md`, `_workspace/03_data_contract.md`, `_workspace/05_backend_changes.md`, `_workspace/06_qa_report.md` (라운드 2 PASS 승인).
> 본 문서는 **wiki-docs** 산출물. 오케스트레이터 최종 병합·CLAUDE.md 변경 이력 갱신 근거.

---

## 수정된 파일 (6개: docs 5 + CLAUDE.md 1)

### 1. `/home/shadeform/workspace/docs/04_api.md`
**변경 섹션**: `POST /api/ai/docdelta` 블록 내부의 "Provider 디스패치" 단락 + "백엔드 env (docdelta 관련)" 표 + 신설 "vllm 실패 매핑 표" + 신설 "외부 계약 무변경 선언" 단락.

**diff 요지**:
- "Provider 디스패치" 단락에 `VllmProvider` 서술 1문장 추가 (3번째 provider, OpenAI-호환 vLLM, 벤더링 `get_diff` 호출).
- env 표에 4행 신규 추가:
  - `VLLM_ENDPOINT` (필수 조건: `LLM_PROVIDER=vllm`; 기본 None → 500)
  - `VLLM_MODEL` (기본 `vllmlora`)
  - `VLLM_API_KEY` (기본 `EMPTY`, OpenAI SDK placeholder)
  - `HF_TOKENIZER` (기본 `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16`)
- `LLM_PROVIDER` 기본값 설명 `"mock" 또는 "finetuned"` → `"mock" / "finetuned" / "vllm" 3값`.
- vllm provider 실패 매핑 표 6행 추가: endpoint 미설정 500, extras 미설치 500 + 설치 안내, APITimeoutError 504 TIMEOUT, APIError/네트워크 502, JSONDecodeError 502, Pydantic 재검증 502.
- "외부 계약 무변경 선언" 단락 추가: doc_id 3단 폴백 + severity="medium" 하드코드는 **provider 내부 구현**이며 `reference/doc_scheme.json` 및 5개 Pydantic 모델은 byte-for-byte 무변경임을 명시.

**앵커**: 파일 내 `### POST /api/ai/docdelta` 헤더 → `> **Provider 디스패치 (2026-04-22)**` 이하 블록.

### 2. `/home/shadeform/workspace/docs/06_tech_stack.md`
**변경 섹션**: "Backend (Phase 2+, Python 스택)" 섹션 아래의 `backend/pyproject.toml` 요약 blockquote + 신설 서브섹션 "train/ ↔ backend/ 관계 (벤더링, 2026-04-22)".

**diff 요지**:
- `backend/pyproject.toml` 요약 blockquote 에 **vllm extra** 문장 추가: `[project.optional-dependencies].vllm = ["openai>=1.0", "transformers>=4.40"]`. 설치 명령 2종(`pip install ".[vllm]"` / `uv sync --extra vllm`) 안내. `openai`/`transformers`/`huggingface-hub` 역할 1줄씩 설명 (OpenAI-호환 엔드포인트 호출 / 토크나이저 로딩 + chat-template / 토크나이저 자산 다운로드).
- `httpx` 는 기존대로 production 의존성(finetuned 용) 유지 명시.
- 신설 서브섹션 "### train/ ↔ backend/ 관계 (벤더링, 2026-04-22)" — 1문단 서술:
  - `train/finetune/{infer_diff,prompt_text}.py` 가 source of truth.
  - `backend/app/services/providers/_vendor/` 로 byte-for-byte 복사 + 8줄 헤더 주석.
  - 벤더링 근거(sys.path 충돌 회피 · 배포 이미지 크기 · 경로 변경 격리).
  - `_vendor/` 언더스코어 prefix = 외부 import 금지 시그널, ruff `extend-exclude` 로 lint 제외.
  - 재벤더링 절차(byte-for-byte 재복사 + 헤더 Copy date 업데이트, 내부 개조 금지).

**앵커**: `## Backend (Phase 2+, Python 스택)` 섹션의 마지막 blockquote 직후.

### 3. `/home/shadeform/workspace/docs/08_tradeoffs.md`
**변경 섹션**: "의사결정 변경 이력" 표 말미.

**diff 요지**:
- 기존 T1~T12 항목 및 기존 변경 이력 행(9행) **전부 무변경**.
- 표 말미에 **신규 행 1개 추가** — 날짜 `2026-04-22`, 제목 `vLLM provider 추가 + train/finetune 코드 벤더링`. 내용:
  - 변경 범위: 백엔드 파일 목록 (vllm.py / _vendor/*.py / docdelta.py dispatcher / env.py 4필드 / pyproject.toml extra + ruff exclude).
  - 매핑 규칙 요약: known_docs flatten + new_doc N회 호출 + merge, doc_id 3단 폴백, severity="medium" 상수, source_id 에코.
  - 에러 매핑 6행 요약.
  - 영향 범위: `Document` 5필드 · `reference/doc_scheme.json` · `mock`/`finetuned` provider 계약 · 프론트 전부 무변경.
  - 사유: (1) train/ 수정 금지 하에 `get_diff()` 재사용 필요 → 벤더링, (2) mock/finetuned 와 공존(교체 X), (3) 의존성 optional extra 격리, (4) sync → async 경계는 `asyncio.to_thread`, (5) doc_id/severity 는 provider 내부 복원 (외부 계약 무영향), (6) 아키텍트 §2 승인 — T8 과 상충하지 않아 **신규 T 번호 신설 없음**.
  - 상세 근거 참조: `_workspace/02_architect_decision.md`, `_workspace/03_data_contract.md`, `_workspace/05_backend_changes.md`.

**앵커**: `## 의사결정 변경 이력` 표 마지막 행 (10번째 데이터 행).

### 4. `/home/shadeform/workspace/docs/02_architecture.md`
**변경 섹션**: `#### Phase 2a 현재 상태 (2026-04-22, provider 추상화 적용)` 블록.

**diff 요지**:
- 헤더 제목에 "+ vLLM provider 추가" 꼬리 추가.
- `pyproject.toml` 불릿에 `[project.optional-dependencies].vllm` + ruff extend-exclude 가드 추가.
- `app/env.py` 불릿에 VLLM_* 4개 env 신규 필드 + `LLM_PROVIDER` Literal 3값 확장 명시.
- `app/routers/ai.py` 불릿에 "vllm 분기는 dispatcher 레벨에서 자동 지원, 라우터 변경 없음" 명시.
- `app/schemas/docdelta.py` 불릿에 "vLLM provider 추가에도 byte-for-byte 무변경" 명시.
- `app/services/docdelta.py` dispatcher 불릿에 `"vllm" → VllmProvider()` 분기 추가 서술.
- 신설 불릿 3개:
  - `app/services/providers/vllm.py` (VllmProvider, asyncio.to_thread + doc_id 3단 폴백 + severity 하드코드 + 지연 import).
  - `app/services/providers/_vendor/__init__.py`.
  - `app/services/providers/_vendor/infer_diff.py` (byte-for-byte + 8줄 헤더).
  - `app/services/providers/_vendor/prompt_text.py` (동일 패턴).
- 신설 불릿 "_vendor/ 디렉토리 메모" — 외부 import 금지 시그널 · source of truth · 재벤더링 절차.
- 실행 안내 마지막 줄에 "vllm 전환은 추가로 `pip install ".[vllm]"` 또는 `uv sync --extra vllm`" 명시.
- 상세 근거 참조에 "2026-04-22 vLLM 추가분" 언급 추가.

**참고**: 상단 ASCII 다이어그램은 provider 분기를 표현하지 않아 수정하지 않음(2개 provider 시점에도 표현 없었음, 불필요한 drift 방지).

**앵커**: `### 4. (Phase 2+) Application Layer — FastAPI (Python) API` 하위의 `#### Phase 2a 현재 상태` 블록.

### 5. `/home/shadeform/workspace/docs/07_roadmap.md`
**변경 섹션**: Phase 2 → 2a. 서버 프록시 불릿 목록.

**diff 요지**:
- 기존 "provider 추상화 (2026-04-22)" 완료 불릿 **그대로 유지**.
- 바로 아래 **신규 완료 불릿 1개 추가** (`[x]` 체크): "`/api/ai/docdelta` **vLLM provider 추가**" — vllm.py + _vendor/* + dispatcher 분기 + env 4개 + optional extra 요약. QA 라운드 2 PASS 근거로 체크됨.

**앵커**: `### 2a. 서버 프록시` 불릿 중 "provider 추상화" 아래.

### 6. `/home/shadeform/workspace/CLAUDE.md`
**변경 섹션**: "변경 이력" 표 말미.

**diff 요지**:
- 기존 6행 **전부 무변경**.
- 표 말미에 **신규 행 1개 추가**:
  - 날짜: 2026-04-22.
  - 변경 내용: "vLLM provider 추가 (3rd provider, 공존) + train/finetune/{infer_diff, prompt_text}.py 를 backend/app/services/providers/_vendor/ 로 벤더링".
  - 대상: backend 7개 파일(vllm.py + _vendor/*.py 3개 + docdelta.py + env.py + pyproject.toml) + docs 3개(04, 06, 08) + 선택 2개(02, 07).
  - 사유: 본문에 train/ 수정 금지 · 벤더링 전략 · optional extra 격리 · asyncio.to_thread · doc_id 3단 폴백 + severity 상수 · 에러 매핑 6행 · 외부 계약 무변경 · T 번호 신설 안함의 근거(아키텍트 §2 승인) 요약.

**앵커**: `**변경 이력:**` 표의 마지막 데이터 행 (7번째).

---

## 신규 파일 / 삭제 파일
- 신규: 없음 (docs 파일은 모두 기존 파일 수정).
- 삭제: 없음.

---

## 링크 · 참조 무결성 점검

| 점검 항목 | 결과 | 비고 |
|---|---|---|
| docs 간 상호 참조 (T1~T12) | OK | T 번호 신설 없음 → 모든 "T7 참조", "T8 해설" 등 인용이 그대로 유효. |
| `reference/doc_scheme.json` 링크 | OK | 04_api.md 본문 링크 (`../reference/doc_scheme.json`) 무변경. |
| `frontend/*.tsx` 경로 참조 | OK | 02·03 에서 참조하는 프론트 파일 경로 무변경(프론트 수정 0). |
| `backend/app/...` 경로 참조 | OK | 02 의 Phase 2a 블록에 vllm.py / _vendor/* 경로 추가는 신규 언급으로 기존 참조 깨뜨리지 않음. |
| `_workspace/*.md` 교차 참조 | OK | 02 · 08 에서 `_workspace/02_architect_decision.md`, `_workspace/03_data_contract.md`, `_workspace/05_backend_changes.md` 참조. 전부 실재 파일. |
| 의사결정 변경 이력 표 구조 | OK | 기존 9행 보존 + 10행 추가. 표 헤더(`날짜/항목/변경/이유`) 유지. |
| CLAUDE.md 변경 이력 표 구조 | OK | 기존 6행 보존 + 7행 추가. 표 헤더(`날짜/변경 내용/대상/사유`) 유지. |
| 로드맵 체크박스 체계 | OK | `[x]` / `[~]` / `[ ]` 기존 사용 패턴 따라 vllm 항목을 `[x]` 로 추가 (QA 라운드 2 PASS 근거). |

---

## 불변성 재확인 (QA 라운드 2 PASS 기준, 문서 차원)

| 항목 | 결과 |
|---|---|
| `docs/` 에서 기존 T1~T12 항목 **한 글자도 수정 안 함** | OK |
| 기존 의사결정 변경 이력 9행 **한 글자도 수정 안 함** | OK |
| 기존 CLAUDE.md 변경 이력 6행 **한 글자도 수정 안 함** | OK |
| `reference/doc_scheme.json` 언급이 문서에서 여전히 "권위 출처"로 표기 | OK (04_api.md 105행) |
| 프론트 관련 변경 서술 전무 | OK (변경 없음을 명시) |
| mock / finetuned provider 계약 "byte-for-byte 무변경" 명시 | OK (02, 04, 08) |

---

## 이전 산출물과의 중복 회피
- `_workspace/07_docs_changes.md` 이전 버전 파일은 존재하지 않음(Read 결과). 따라서 중복 반영 위험 없음.
- 이번 라운드 수정은 **vLLM provider 추가** 단 하나의 주제에 한정 — 이전 라운드(데모 흐름 재설계)의 문서 변경은 이미 반영되어 있으며 본 작업에서 재수정하지 않음.

---

## T 번호 신설 여부
**신설 안 함.** 근거: `_workspace/02_architect_decision.md §2` 에서 본 결정이 T8 ("2번째 공급자" 원칙) 과 상충하지 않는다고 명시적으로 승인됨 — Protocol(`DocdeltaProvider`) 은 이미 `FinetunedProvider` 도입 시 정당화된 추상이고, `VllmProvider` 는 그 재사용(3번째 구현)일 뿐. 의사결정 변경 이력 테이블에만 행 추가로 기록.

**다음에 T 번호 신설이 필요한 조건 (참고)**:
- vLLM 서버가 multi-tenant 환경으로 확장되어 **프로비저닝 전략**이 독립된 트레이드오프로 부상할 때.
- `transformers`/`openai` 가 기본 production 의존성으로 승격되어 extras 격리가 깨질 때.
- 벤더링 drift 가 빈번해져 train/ 을 파이썬 패키지로 승격하는 결정이 내려질 때.
- 이상 조건 발생 시 `T13` 혹은 그 시점 최대 번호 + 1 로 신규 항목 신설.

---

## QA 재검증 체크포인트 (이 산출물로 최종 판단)

| 체크포인트 | 결과 | 근거 |
|---|---|---|
| docs/04 `LLM_PROVIDER` 값 목록에 `vllm` 포함 | OK | 04_api.md 의 env 표 `LLM_PROVIDER` 행. |
| docs/04 VLLM_* 4개 env 기본값이 03_data_contract §5.2 표와 일치 | OK | `None` / `vllmlora` / `EMPTY` / `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16` 정확히 일치. |
| docs/04 에러 매핑 6행이 03_data_contract §4 표와 일치 | OK | 사유/HTTP/code 3열 모두 일치 (500 AI_UPSTREAM × 2, 504 TIMEOUT × 1, 502 AI_UPSTREAM × 3). |
| docs/04 doc_id 3단 폴백 + severity 가 **provider 내부 동작**이며 `reference/doc_scheme.json` 무변경임을 명시 | OK | "외부 계약 무변경 선언" 단락. |
| docs/06 `[vllm]` extras 설치 안내 포함 | OK | `pip install ".[vllm]"` / `uv sync --extra vllm` 둘 다 명기. |
| docs/06 `openai` / `transformers` / `huggingface-hub` 역할 1줄씩 | OK | 요약 blockquote 안에 3개 역할 서술. |
| docs/06 httpx 는 production 의존성(finetuned 용) 유지 명시 | OK | 기존 서술 유지 + "vllm 추가에도 불변"으로 맥락 유지. |
| docs/06 train/ ↔ backend/ 벤더링 관계 서술 1문단 | OK | 신설 서브섹션. |
| docs/08 의사결정 변경 이력에 **신규 행 1개** (기존 행 전부 보존) | OK | 10행째 추가, 9행까진 무변경. |
| docs/08 에서 기존 T1~T12 항목 전부 무변경 | OK | T 번호 신설 없음, 본문 어느 T 항목도 수정하지 않음. |
| docs/02 벤더링 `_vendor/` 의도(외부 import 금지, train/ SoT) 1~2줄 메모 | OK | `_vendor/ 디렉토리 메모` 불릿. |
| docs/07 Phase 2a 로드맵에 vllm 항목 (`[x]` 체크) 추가 | OK | 기존 provider 추상화 완료 항목 아래 1행. |
| CLAUDE.md 변경 이력 표에 **신규 행 1개** (기존 6행 보존) | OK | 7행째 추가. |

---

**한 줄 요약:** vLLM provider 추가(3rd provider, 벤더링)를 `docs/04·06·08 + 02·07 + CLAUDE.md` 6개 파일에 반영 완료 — 기존 T1~T12 항목 및 의사결정 변경 이력 9행·CLAUDE.md 변경 이력 6행은 **한 글자도 수정 없이** 보존, 신규 T 번호 신설 없이 이력 1행 + 관련 섹션만 추가. 외부 계약(`reference/doc_scheme.json`, 5개 Pydantic 모델) 무변경 · mock/finetuned 계약 무변경 · 프론트 무변경 문서 차원에서 명시.
