# 06. QA 보고서 — vLLM Provider 추가 (3rd provider, 벤더링, asyncio.to_thread)

> 입력: `_workspace/01_request.md`, `02_architect_decision.md`, `03_data_contract.md`, `05_backend_changes.md`.
> 검증 방식: 경계면 교차 비교 + Bash 실행 검증 (backend/.venv).
> QA 는 읽기 전용 — 결함은 보고만 함.

---

## 1. 벤더링 정합성

| 항목 | 결과 | 근거 |
|---|---|---|
| `_vendor/infer_diff.py` 상단 헤더 주석 블록 8줄 존재 | ✓ | 1~8행: `# Vendored from: train/finetune/infer_diff.py` ~ `# Re-vendor when upstream changes: copy file byte-for-byte, update this header.` |
| `_vendor/prompt_text.py` 상단 헤더 주석 블록 8줄 존재 | ✓ | 1~8행 동일 패턴, `Vendored from: train/finetune/prompt_text.py` |
| 헤더 이후 `train/finetune/infer_diff.py` 와 byte-for-byte 동일 | ✓ | `diff train/finetune/infer_diff.py <(tail -n +9 backend/.../_vendor/infer_diff.py)` → 0 라인 차이. line count: 188(원본) + 8(헤더) = 196(벤더) |
| 헤더 이후 `train/finetune/prompt_text.py` 와 byte-for-byte 동일 | ✓ | 동일 diff 0. 67(원본) + 8(헤더) = 75(벤더) |
| `if __name__ == "__main__":` smoke-test 블록 보존 | ✓ | `_vendor/infer_diff.py` line 180 |
| `sys.path.insert(0, _THIS_DIR)` 보존 | ✓ | line 51 |
| `from prompt_text import format_prompt_text` 보존 | ✓ | line 52 |
| `_vendor/__init__.py` 빈 패키지 + docstring | ✓ | 1행: `"""Vendored upstream modules from train/finetune/ — DO NOT EDIT. Re-vendor when upstream changes."""` |

**Section 1: PASS** (8/8).

---

## 2. Provider 계약

| 항목 | 결과 | 근거 |
|---|---|---|
| `VllmProvider.analyze` 시그니처가 `DocdeltaProvider` Protocol (async analyze) 충족 | ✓ | `inspect.iscoroutinefunction(VllmProvider.analyze) == True`, signature `(self, req: DocdeltaRequest) -> DocdeltaResponse` 와 일치 |
| 상단(모듈 레벨) import 에 openai / transformers 없음 | ✓ | `vllm.py` 상단 import: `asyncio`, `json`, `fastapi.HTTPException`, `pydantic.ValidationError`, `...env.env`, `...schemas.docdelta` 뿐. openai/transformers는 함수 본문에서 지연 import (line 127의 `from openai import APIError, APITimeoutError`). |
| `VLLM_ENDPOINT` 미설정 → 500 AI_UPSTREAM | ✓ | 실행 검증: `HTTPException(status=500, detail={'code':'AI_UPSTREAM','message':'VLLM_ENDPOINT is not configured'})` 확인. |
| extras 미설치 환경에서도 `from app.services.providers.vllm import VllmProvider` 성공 | ✓ | 현재 venv 에 openai/transformers **미설치** 상태 확인 (`openai/transformers: NOT INSTALLED`) 에서도 import 에 성공 |

**Section 2: PASS** (4/4).

---

## 3. Dispatcher

| 항목 | 결과 | 근거 |
|---|---|---|
| `docdelta.py` 에 `elif env.LLM_PROVIDER == "vllm": return VllmProvider()` 분기 추가 | ✓ | line 27~28 |
| `MockProvider` / `FinetunedProvider` 파일 byte-for-byte 무변경 | ✓ | `mock.py`(mtime 1776817246) / `finetuned.py`(1776817255) 모두 vLLM 작업 시작 시점(1776830317) 이전 mtime. 내용 검사상 변경 없음. |
| `LLM_PROVIDER=mock` → MockProvider, `finetuned` → FinetunedProvider, `vllm` → VllmProvider, `bogus` → MockProvider fallback | ✓ | 4가지 조합 실행 모두 기대대로 동작 |

**Section 3: PASS** (3/3).

---

## 4. Env

| 항목 | 결과 | 근거 |
|---|---|---|
| `_PROVIDER_VALUES == ("mock","finetuned","vllm")` | ✓ | `env.py` line 22 확인 |
| `_read_provider()` 반환 `Literal["mock","finetuned","vllm"]` | ✓ | line 25 signature + line 35 `cast(Literal["mock","finetuned","vllm"], val)` |
| `VLLM_ENDPOINT: str \| None` (기본 None) | ✓ | line 57, 런타임 hint 검증 `str \| None`, 기본값 None |
| `VLLM_MODEL: str = "vllmlora"` | ✓ | line 58, 런타임 `'vllmlora'` |
| `VLLM_API_KEY: str = "EMPTY"` | ✓ | line 59, 런타임 `'EMPTY'` |
| `HF_TOKENIZER: str = "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16"` | ✓ | line 60~62, 런타임 `'nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16'` |

**Section 4: PASS** (6/6).

---

## 5. pyproject

| 항목 | 결과 | 근거 |
|---|---|---|
| `[project.optional-dependencies]` 에 `vllm = ["openai>=1.0", "transformers>=4.40"]` | ✓ | `pyproject.toml` line 25~28 |
| 기본 `dependencies` 무변경 (fastapi, uvicorn[standard], pydantic, python-dotenv, httpx 5개) | ✓ | line 6~12 그대로. `httpx>=0.27` 포함 확인. |
| `[tool.ruff].extend-exclude = ["app/services/providers/_vendor"]` 추가 | ✓ (기대 행동 넘어 추가된 가드) | line 42 |

**Section 5: PASS** (2/2 체크리스트 + 1 보너스 가드).

---

## 6. 불변 규칙 (R1~R4, Document 5필드, reference/doc_scheme.json)

| 항목 | 결과 | 근거 |
|---|---|---|
| `backend/app/schemas/docdelta.py` 변경 없음 | ✓ | mtime 1776806350 (vLLM 작업 전). 5개 모델(DocdeltaDocRef, DocdeltaRequest, DocdeltaConflict, DocdeltaOutput, DocdeltaResponse) 필드·순서·`extra="forbid"` 그대로. |
| `reference/doc_scheme.json` 변경 없음 | ✓ | mtime 1776795056 (가장 오래됨) |
| `frontend/src/types/docdelta.ts` 변경 없음 | ✓ | mtime 1776822205 (vLLM 작업 전) |
| `train/` 변경 없음 | ✓ | `train/finetune/infer_diff.py` mtime 2026-04-22 02:10 (vLLM 작업보다 이른 시각). diff 와 매칭. |
| `backend/app/routers/ai.py` 변경 없음 | ✓ | mtime 1776817270 (vLLM 작업 전). dispatcher 통해 vllm 분기 자동 지원. |

**Section 6: PASS** (5/5).

---

## 7. 매핑 계약 (03_data_contract §2, §3, §4)

| 항목 | 결과 | 근거 |
|---|---|---|
| `flat_known_refs` / `flat_known_texts` 이중 컴프리헨션 존재 | ✓ | `vllm.py` line 92~95: `[ref for group in req.known_docs for ref in group]`, `[r.context for r in flat_known_refs]` — 순서 보존 보장 |
| new_doc 순회하며 `asyncio.to_thread(get_diff, ...)` 호출 | ✓ | line 109~119. `flat_known_texts` 는 루프 밖에서 1회 계산 후 N회 재사용(§2.3 준수) |
| doc_id 3단 폴백 함수 존재 | ✓ | `_resolve_doc_id` (line 44~57). 실행 검증: substring 최초 히트 / 2차 first-ref / 3차 `"unknown"` 모두 기대대로. 빈 known_text 는 1차 스킵 → 2차 first-ref 로 fall-through. |
| `severity="medium"` 상수 하드코드 | ✓ | line 190. 환경변수/파라미터 경로 없음 확인. |
| `source_id` 에코 (`resp.source_id == req.source_id`) | ✓ | line 200 `"source_id": req.source_id` |
| `convert_doc` / `instruction` 은 get_diff 호출에 미포함 | ✓ | 호출 인자: `flat_known_texts`, `nd.context`, vllm_endpoint/model/api_key/tokenizer_source 만 (line 111~119). `req.instruction` / `req.convert_doc` 참조 없음. |

**Section 7: PASS** (6/6).

---

## 8. 에러 매핑 (03_data_contract §4, 6행)

| 사유 | 기대 (status, code) | 실제 구현 | 결과 |
|---|---|---|---|
| `VLLM_ENDPOINT` 미설정 | 500 / AI_UPSTREAM | line 65~72. 실행 검증 OK. | ✓ |
| `openai` / `transformers` 미설치 (설치 안내 포함) | 500 / AI_UPSTREAM | line 77~89 의 try/except ImportError. **그러나** `_vendor/infer_diff.py` 내부가 `from transformers import AutoTokenizer` 을 `_get_tokenizer` 함수 안에서 지연 import 하므로 `from ._vendor.infer_diff import get_diff` 는 extras 없이도 **성공**. 따라서 line 79의 ImportError 분기는 실행 경로상 거의 도달하지 않음. 대신 실제 `get_diff()` 호출 시 ImportError 가 루프 내부 `Exception` 핸들러로 흘러가 502 AI_UPSTREAM + `"No module named 'transformers'"` 로 매핑됨. 실행 검증: `status=502 code=AI_UPSTREAM msg=vLLM upstream error: No module named 'transformers'` | ✗ **결함 #1** |
| `openai.APITimeoutError` | 504 / TIMEOUT | line 132~139 | ✓ (정적) |
| 기타 `openai.APIError` / 네트워크 | 502 / AI_UPSTREAM | line 140~147 (APIError) + line 167~173 (기타 fallback) | ✓ (정적) |
| `json.JSONDecodeError` 파싱 실패 | 502 / AI_UPSTREAM | line 148~155 | ✓ (정적) |
| `DocdeltaResponse` Pydantic 재검증 실패 | 502 / AI_UPSTREAM | line 207~214 | ✓ (정적) |

**Section 8: FAIL** — 결함 #1 (아래).

---

## 9. 실행 검증 (Bash)

| 스크립트 | 결과 | 출력 |
|---|---|---|
| `env.py` import + VLLM_* 기본값 | PASS | `env OK vllmlora nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16 endpoint= None apikey= EMPTY` |
| Dispatcher 3+1 분기 (mock/finetuned/vllm/bogus→mock) | PASS | 각각 `MockProvider`, `FinetunedProvider`, `VllmProvider`, `MockProvider` |
| `VllmProvider` import (extras 미설치) — lazy import | PASS | `lazy import OK`; 확인: `'openai' not in sys.modules and 'transformers' not in sys.modules` |
| `VLLM_ENDPOINT` 미설정 + `LLM_PROVIDER=vllm` 요청 → 500 AI_UPSTREAM | PASS | `endpoint-missing guard OK: 500 {'code': 'AI_UPSTREAM', 'message': 'VLLM_ENDPOINT is not configured'}` |
| `VLLM_ENDPOINT` **설정** + extras 미설치 → 기대: 500 AI_UPSTREAM + 설치 안내 | **FAIL** | 실제: `502 code=AI_UPSTREAM msg=vLLM upstream error: No module named 'transformers'` (설치 안내 문구 부재) |
| `_resolve_doc_id` 3단 폴백 | PASS | substring first-hit, multi-hit → first, no-match → first ref, 빈 refs → `"unknown"`, 빈 known_text → stage 2 |

---

## 10. 종합 불변 규칙 표

```
R1 데이터 이동성 (Document JSON 왕복)  : ✓  — Document 5필드·localStorage 모두 무변경 (프론트 손대지 않음)
R2 로컬 우선 (서버 없이 프론트 동작)    : ✓  — 본 작업은 백엔드 전용. 프론트는 기존 /api/ai/docdelta 호출 동선 유지
R3 마크다운 원문 보관                   : ✓  — context 문자열 원문 그대로 get_diff 에 넘김. 서버측 HTML 변환·저장 없음
R4 하위 호환 (기존 API/필드/동작 유지)  : ✓  — DocdeltaRequest/Response/Conflict/Output/DocRef 5모델 byte-for-byte 유지. mock/finetuned 분기·에러 매핑 그대로. reference/doc_scheme.json 0-byte diff.
```

**모두 ✓ (4/4).**

---

## 발견된 결함

### #1 [심각도: 중] extras 미설치 케이스에서 에러 매핑이 500 AI_UPSTREAM + 설치 안내가 아니라 502 AI_UPSTREAM + 원시 ImportError 메시지로 매핑됨
- **위치**: `backend/app/services/providers/vllm.py` 의 line 77~89 (try/except ImportError) vs line 120~173 (루프 내부 except).
- **입력**: `LLM_PROVIDER=vllm`, `VLLM_ENDPOINT=http://...`, extras (`openai`/`transformers`) 미설치 상태에서 `/api/ai/docdelta` 호출.
- **기대** (03_data_contract §4 2행, 05_backend_changes §3.16, 01_request §에러 매핑 2행): HTTP 500, code=AI_UPSTREAM, message 에 `pip install ".[vllm]"` 또는 `uv sync --extra vllm` 설치 안내 포함.
- **실제** (실행 검증):
  - status 502 (설계상 500 이어야 함)
  - detail = `{'code': 'AI_UPSTREAM', 'message': 'vLLM upstream error: No module named \'transformers\''}`
  - 설치 안내 문구(`pip install`, `[vllm]`, `uv sync --extra vllm` 어느 것도) 포함되지 않음.
- **원인**: `_vendor/infer_diff.py` 가 `transformers` 와 `openai` 를 **함수 본문**(`_get_tokenizer`, `_get_client`) 에서 지연 import 한다. 따라서 vllm.py line 78 의 `from ._vendor.infer_diff import get_diff` 는 extras 가 없어도 **성공**한다. ImportError 는 실제 `get_diff()` 실행 시(즉 `await asyncio.to_thread(get_diff, ...)` 내부)에서야 발생하며, 이 시점엔 line 78~89 의 ImportError 핸들러가 아니라 line 122 의 `except Exception` 경로를 타고 최종 line 167~173 의 generic 502 AI_UPSTREAM 으로 귀결된다.
- **해결 주체**: **wiki-backend**
- **해결 방향 제안 (QA 권고, 구현은 wiki-backend 재량)**:
  - (a) vllm.py 의 `except Exception as e` 블록에서 `isinstance(e, ImportError)` 또는 `isinstance(e, ModuleNotFoundError)` 분기를 추가해 500 AI_UPSTREAM + 설치 안내로 매핑, 또는
  - (b) vllm.py 상단 혹은 `analyze()` 진입 직후 (endpoint 체크 다음) 에서 `import openai` / `import transformers` 를 **probe** 하여 extras 부재를 즉시 감지하고 500 AI_UPSTREAM + 설치 안내로 raise. (heavy import 는 아니고 metadata 만 확인하고 싶다면 `importlib.util.find_spec("openai")` / `find_spec("transformers")` 사용.)
  - 둘 중 어느 경로든 `_vendor/infer_diff.py` 원본은 **개조 금지** (아키텍트 §3 원칙 유지).
- **재현 명령**:
  ```bash
  cd /home/shadeform/workspace/backend
  LLM_PROVIDER=vllm VLLM_ENDPOINT=http://localhost:9983/v1 .venv/bin/python -c "
  import asyncio, fastapi
  from app.services.providers.vllm import VllmProvider
  from app.schemas.docdelta import DocdeltaRequest, DocdeltaDocRef
  req = DocdeltaRequest(source_id='T', instruction='x',
      known_docs=[[DocdeltaDocRef(doc_id='k1', context='c1')]],
      new_doc=[DocdeltaDocRef(doc_id='n1', context='c2')])
  try: asyncio.run(VllmProvider().analyze(req))
  except fastapi.HTTPException as e: print(e.status_code, e.detail)
  "
  # 실제: 502 {'code': 'AI_UPSTREAM', 'message': "vLLM upstream error: No module named 'transformers'"}
  # 기대: 500 {'code': 'AI_UPSTREAM', 'message': "... pip install \".[vllm]\" ... uv sync --extra vllm ..."}
  ```

---

## 경계면 교차 비교 결과 요약

| 경계면 | 결과 | 비고 |
|---|---|---|
| `schemas/docdelta.py` ↔ `reference/doc_scheme.json` | ✓ | 둘 다 변경 없음 |
| `services/providers/vllm.py` ↔ `03_data_contract §2~§3` | ✓ | 매핑 규칙 7항목 모두 일치 |
| `services/providers/vllm.py` ↔ `03_data_contract §4` 에러 매핑 | ✗ | 결함 #1 (extras-missing 행이 500+안내가 아니라 502+원시 메시지) |
| `services/docdelta.py` ↔ `env.py` LLM_PROVIDER literal | ✓ | `"mock"/"finetuned"/"vllm"` 3값 완전 대응 |
| `_vendor/*.py` ↔ `train/finetune/*.py` | ✓ | 헤더 8줄 외 byte-for-byte 동일 (diff 0) |
| `pyproject.toml [optional-dependencies].vllm` ↔ `02_architect §6` | ✓ | `openai>=1.0`, `transformers>=4.40` |
| `env.py` VLLM_* 4 필드 ↔ `03_data_contract §5.2` 기본값 표 | ✓ | 4개 필드 기본값 모두 일치 |
| `routers/ai.py` ↔ `03_data_contract §1.1` 라우터 무변경 | ✓ | 변경 없음 |
| `mock.py`/`finetuned.py` ↔ `03_data_contract §1.3` 무변경 | ✓ | mtime 및 내용 확인 |

---

## 승인 여부

- **전체: 재작업 필요** (결함 #1 해결 후 재검증).
- 결함 #1 은 사용자 경험 상 중요도 "중" (HTTP status 가 500→502 로 뒤바뀌고 설치 안내가 사라짐). 외부 계약(`reference/doc_scheme.json`, Document 5필드) 과 기존 mock/finetuned 동작은 무변경이므로 **외부 블로커는 아님**. 다만 01_request + 02_architect + 03_data_contract + 05_backend_changes 네 문서가 모두 "500 + 설치 안내" 를 기재하고 있어 스펙 대 구현 간 차이가 명시적. 스펙을 구현에 맞출지(문서 수정) / 구현을 스펙에 맞출지(코드 수정) 는 오케스트레이터·사용자 판단.
- 다른 15개 체크리스트 항목(§1~§7, §9~§10)은 모두 PASS.

---

**한 줄 요약:** 벤더링·dispatcher·env·매핑·source_id 에코·severity 하드코드·lazy import·VLLM_ENDPOINT guard·Document/reference/doc_scheme/train/frontend 무변경 모두 통과; 단 1건 — extras 미설치 시 500 AI_UPSTREAM + 설치 안내가 나와야 할 자리에 502 AI_UPSTREAM + 원시 ImportError 메시지가 나가는 에러-매핑 gap 이 있어 wiki-backend 재작업 필요.

---

### 재검증 결과 (라운드 2)

**결과: PASS (승인).** 결함 #1 이 해결되었고, 이전 라운드의 15 PASS 모두 회귀 없음.

#### 1. 결함 #1 회귀 검증

| 항목 | 결과 | 근거 |
|---|---|---|
| `vllm.py` 의 per-call try/except 블록에 `except ImportError as e` 전용 arm 추가 | PASS | line 146~161 신설. 분기: 500 AI_UPSTREAM + message 에 `.[vllm]` / `--extra vllm` 설치 안내 포함. `from e` chain 유지. |
| 실행 검증 (`VLLM_ENDPOINT=http://localhost:9999/v1`, extras 미설치) | PASS | 실제 출력: `500 vllm extras not installed (No module named 'transformers'). Install with \`pip install ".[vllm]"\` or \`uv sync --extra vllm\`.` — status·code·설치 안내 3항목 모두 기대 일치. |
| 설치 안내 토큰 검사 (`'.[vllm]' in msg or '--extra vllm' in msg`) | PASS | 둘 다 포함 (이중 안내). |

#### 2. 회귀 방지 (이전 15 PASS 유지)

| 항목 | 결과 | 근거 |
|---|---|---|
| Lazy import: `from app.services.providers.vllm import VllmProvider` 후 `'openai' not in sys.modules and 'transformers' not in sys.modules` | PASS | `LAZY-IMPORT OK: openai/transformers not in sys.modules` |
| Dispatcher 4분기 (`mock`/`finetuned`/`vllm`/`bogus`) | PASS | `mock→MockProvider`, `finetuned→FinetunedProvider`, `vllm→VllmProvider`, `bogus→MockProvider` (fallback) 전부 기대 일치 |
| `VLLM_ENDPOINT` 미설정 → 500 AI_UPSTREAM + `VLLM_ENDPOINT` 토큰 | PASS | `500 VLLM_ENDPOINT is not configured` |
| 벤더링 byte-for-byte 동일 (`train/finetune/*.py` vs `_vendor/*.py` 헤더 제외) | PASS | `diff train/finetune/infer_diff.py <(tail -n +9 _vendor/infer_diff.py)` exit 0; `prompt_text.py` 도 exit 0 |
| 이번 라운드에서 `vllm.py` **외** 수정 없음 | PASS | mtime 비교 (기준: 이번 라운드 vllm.py 수정 시각 1776831126): `mock.py`=1776817246, `finetuned.py`=1776817255, `docdelta.py`=1776830401, `docdelta_provider.py`=1776817234, `env.py`=1776830527, `schemas/docdelta.py`=1776806350, `routers/ai.py`=1776817270, `pyproject.toml`=1776830509, `_vendor/infer_diff.py`=1776830356, `_vendor/prompt_text.py`=1776830317, `_vendor/__init__.py`=1776830296, `providers/__init__.py`=1776817227, `reference/doc_scheme.json`=1776795056, `frontend/src/types/docdelta.ts`=1776822205 — **모두 vllm.py 수정 시각 이전** |
| `train/` 변경 없음 | PASS | `find train/ -newer docdelta.py` → 출력 없음 |
| `frontend/` 소스 변경 없음 | PASS | `frontend/src/types/docdelta.ts` mtime 1776822205 (이번 라운드 시작 전) |

#### 3. 종합 불변 규칙 재선언

```
R1 데이터 이동성  : PASS — Document 5필드·localStorage 무변경
R2 로컬 우선      : PASS — 이번 수정은 백엔드 에러 매핑 한정, 프론트·오프라인 동작 무영향
R3 마크다운 원문  : PASS — context 그대로 전달, HTML 변환 없음
R4 하위 호환      : PASS — DocdeltaRequest/Response/Conflict/Output/DocRef 5모델·mock/finetuned·reference/doc_scheme.json 모두 byte-for-byte 유지
```

#### 4. 새로 발견된 결함

없음.

#### 5. 체크리스트 최종

§1 벤더링 정합성 PASS / §2 Provider 계약 PASS / §3 Dispatcher PASS / §4 Env PASS / §5 pyproject PASS / §6 불변 규칙 PASS / §7 매핑 계약 PASS / §8 에러 매핑 **PASS (이전 FAIL → 해결)** / §9 실행 검증 **PASS (extras-missing 행 재검증 통과)** / §10 종합 불변 규칙 PASS.

**승인 여부: 전체 PASS — 라운드 2 종결. 오케스트레이터 병합 진행 가능.**

**한 줄 요약:** 결함 #1 (extras 미설치 시 502 → 500 + 설치 안내) 해결 확인 및 이전 15 PASS 회귀 없음 — 라운드 2 최종 PASS.
