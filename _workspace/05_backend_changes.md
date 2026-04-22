# 05. Backend 변경 — vLLM Provider 추가

> 입력: `_workspace/01_request.md`, `_workspace/02_architect_decision.md`, `_workspace/03_data_contract.md`.
> 본 문서는 **wiki-backend** 산출물. wiki-qa 회귀 검증 기준.

## 변경 파일 목록 (7개: 신설 4 + 수정 3)

### 신설
1. `/home/shadeform/workspace/backend/app/services/providers/_vendor/__init__.py`
   빈 패키지 + docstring("Vendored upstream modules from train/finetune/ — DO NOT EDIT. Re-vendor when upstream changes.").
2. `/home/shadeform/workspace/backend/app/services/providers/_vendor/prompt_text.py`
   `train/finetune/prompt_text.py` byte-for-byte 복사 + 헤더 주석 블록 6줄 (§3 아키텍트 결정).
3. `/home/shadeform/workspace/backend/app/services/providers/_vendor/infer_diff.py`
   `train/finetune/infer_diff.py` byte-for-byte 복사 + 헤더 주석 블록. 내부 sys.path 해킹(`sys.path.insert(0, _THIS_DIR)` + `from prompt_text import format_prompt_text`) 및 `if __name__ == "__main__":` smoke 테스트 블록 그대로 유지.
4. `/home/shadeform/workspace/backend/app/services/providers/vllm.py`
   `VllmProvider.analyze()`.

### 수정
5. `/home/shadeform/workspace/backend/app/services/docdelta.py`
   dispatcher 에 `elif env.LLM_PROVIDER == "vllm": return VllmProvider()` 분기 추가. mock/finetuned 분기 byte-for-byte 유지. docstring 의 Selection rule 에 vllm 한 줄 추가.
6. `/home/shadeform/workspace/backend/app/env.py`
   - `_PROVIDER_VALUES` 에 `"vllm"` 추가.
   - `_read_provider` Literal 반환 타입을 `Literal["mock", "finetuned", "vllm"]` 로 확장 (cast 포함).
   - `Env` 클래스에 VLLM 관련 4개 필드 추가: `VLLM_ENDPOINT: str | None = None`, `VLLM_MODEL: str = "vllmlora"`, `VLLM_API_KEY: str = "EMPTY"`, `HF_TOKENIZER: str = "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16"`.
   - docstring 의 Secrets 목록에 `VLLM_API_KEY` 추가.
7. `/home/shadeform/workspace/backend/pyproject.toml`
   - `[project.optional-dependencies]` 에 `vllm = ["openai>=1.0", "transformers>=4.40"]` 추가. 기본 `dependencies` 무변경.
   - `[tool.ruff]` 에 `extend-exclude = ["app/services/providers/_vendor"]` 추가 (벤더링 파일 DO-NOT-EDIT 원칙 보호).

### 참고: `.env.example`
`backend/.env.example` 파일이 존재하지 않으므로 F단계 스킵. (미래에 생성 시 VLLM_* 4줄 + `LLM_PROVIDER` 코멘트에 `vllm` 옵션 추가 필요 — wiki-docs 가 담당.)

---

## 핵심 diff 요지

### `backend/app/services/providers/vllm.py` (신설, 약 170 라인)
- `class VllmProvider` 의 `async def analyze(self, req: DocdeltaRequest) -> DocdeltaResponse`.
- 동작 순서 (contract §2~§3 매핑):
  1. `env.VLLM_ENDPOINT` 미설정 → 500 AI_UPSTREAM.
  2. `from ._vendor.infer_diff import get_diff` 지연 import → ImportError 시 500 AI_UPSTREAM (설치 안내 `pip install ".[vllm]"` / `uv sync --extra vllm`).
  3. `flat_known_refs` / `flat_known_texts` 병렬 리스트 생성 (이중 컴프리헨션, 순서 보존).
  4. `req.new_doc == []` 방어적 분기 → 빈 response.
  5. new_doc 원소별로 `await asyncio.to_thread(get_diff, flat_known_texts, nd.context, vllm_endpoint=..., vllm_model=..., vllm_api_key=..., tokenizer_source=...)` N회 호출.
  6. `get_diff` 결과 merge:
     - `new` concat (정렬·중복 제거 금지).
     - `conflict` 변환: `known_text`/`new_text`/`reason` 그대로, `doc_id` 는 `_resolve_doc_id` 3단 폴백 (§3.4), `severity="medium"` 하드코드.
  7. 에러 매핑 (벤더링 `get_diff` try/except, openai 지연 import):
     - `openai.APITimeoutError` → 504 TIMEOUT.
     - `openai.APIError` → 502 AI_UPSTREAM.
     - `json.JSONDecodeError` → 502 AI_UPSTREAM.
     - `ValueError` (endpoint 미지정) → 500 AI_UPSTREAM (step 1에서 선차단됨).
     - 기타 `Exception` → 502 AI_UPSTREAM (message 200자 cap).
     - `HTTPException` pass-through.
  8. 최종 `DocdeltaResponse.model_validate(...)` 재검증 → `ValidationError` 시 502 AI_UPSTREAM.
- 상단 import 전략 (extra 미설치 환경에서 부팅 차단 금지):
  ```python
  from __future__ import annotations
  import asyncio, json
  from fastapi import HTTPException
  from pydantic import ValidationError
  from ...env import env
  from ...schemas.docdelta import DocdeltaConflict, DocdeltaDocRef, DocdeltaOutput, DocdeltaRequest, DocdeltaResponse
  ```
  - `openai` / `transformers` / 벤더링 `get_diff` 는 함수 본문에서만 지연 import.

### `backend/app/services/docdelta.py`
```diff
 Selection rule:
 * `LLM_PROVIDER == "finetuned"` -> `FinetunedProvider`
+* `LLM_PROVIDER == "vllm"`      -> `VllmProvider`
 * anything else (including default "mock")  -> `MockProvider`
 ...
 from .providers.finetuned import FinetunedProvider
 from .providers.mock import MockProvider
+from .providers.vllm import VllmProvider

 def get_provider() -> DocdeltaProvider:
     if env.LLM_PROVIDER == "finetuned":
         return FinetunedProvider()
+    elif env.LLM_PROVIDER == "vllm":
+        return VllmProvider()
     return MockProvider()
```

### `backend/app/env.py`
```diff
-Secrets (`GEMINI_API_KEY`, `FINETUNED_API_KEY`) are never logged ...
+Secrets (`GEMINI_API_KEY`, `FINETUNED_API_KEY`, `VLLM_API_KEY`) are never ...

-_PROVIDER_VALUES: tuple[str, ...] = ("mock", "finetuned")
+_PROVIDER_VALUES: tuple[str, ...] = ("mock", "finetuned", "vllm")

-def _read_provider() -> Literal["mock", "finetuned"]:
+def _read_provider() -> Literal["mock", "finetuned", "vllm"]:
     ...
-    return cast(Literal["mock", "finetuned"], val)
+    return cast(Literal["mock", "finetuned", "vllm"], val)

-    LLM_PROVIDER: Literal["mock", "finetuned"] = _read_provider()
+    LLM_PROVIDER: Literal["mock", "finetuned", "vllm"] = _read_provider()
     FINETUNED_API_URL: Optional[str] = os.environ.get("FINETUNED_API_URL") or None
     FINETUNED_API_KEY: Optional[str] = os.environ.get("FINETUNED_API_KEY") or None
     FINETUNED_TIMEOUT_SEC: int = int(os.environ.get("FINETUNED_TIMEOUT_SEC", "30"))
+
+    # vLLM provider (2026-04-22). See _workspace/02_architect_decision.md §9.
+    VLLM_ENDPOINT: str | None = os.environ.get("VLLM_ENDPOINT") or None
+    VLLM_MODEL: str = os.environ.get("VLLM_MODEL", "vllmlora")
+    VLLM_API_KEY: str = os.environ.get("VLLM_API_KEY", "EMPTY")
+    HF_TOKENIZER: str = os.environ.get(
+        "HF_TOKENIZER", "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16"
+    )
```
- 기존 3개 `Optional[str]` 필드는 **pre-existing 상태 유지** (ruff UP045 기존 위반은 건드리지 않음). 새 `VLLM_ENDPOINT` 만 modern `str | None` 문법으로 두어 **새 lint 위반 0건**.

### `backend/pyproject.toml`
```diff
 gemini = [
     "google-generativeai>=0.7",
 ]
+vllm = [
+    "openai>=1.0",
+    "transformers>=4.40",
+]
 ...
 [tool.ruff]
 line-length = 100
 target-version = "py311"
+# Vendored upstream modules are DO-NOT-EDIT (see
+# app/services/providers/_vendor/__init__.py). Skip lint on them.
+extend-exclude = ["app/services/providers/_vendor"]
```
- 기본 `dependencies` 무변경. `httpx`/`fastapi`/`pydantic`/`python-dotenv`/`uvicorn` 그대로.

---

## 불변성 체크 (03_data_contract §6 기준)

- [x] Pydantic 5개 모델 (`DocdeltaDocRef`/`DocdeltaRequest`/`DocdeltaConflict`/`DocdeltaOutput`/`DocdeltaResponse`) 필드·타입·순서·`extra="forbid"` 무변경 (`backend/app/schemas/docdelta.py` 전혀 건드리지 않음).
- [x] `DocdeltaConflict` 5필드 선언 순서 유지: `doc_id, known_text, new_text, reason, severity`.
- [x] `source_id` 1:1 에코 (VllmProvider 의 `model_validate` 호출에서 `req.source_id` 그대로 사용).
- [x] 프론트 타입 무변경 (프론트 디렉토리 손대지 않음).
- [x] `reference/doc_scheme.json` 무변경.
- [x] `mock` / `finetuned` provider 동작·에러 매핑·import 경로 byte-for-byte 유지. dispatcher 의 기존 2개 분기 라인 수정 없음.
- [x] env 기본값 §5.2 표와 정확히 일치 (`vllmlora`, `EMPTY`, `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16`, `VLLM_ENDPOINT` 기본 None).
- [x] `doc_id` 3단 폴백 구현 = §3.4 (substring `in`, 최초 히트, `"unknown"` 리터럴).
- [x] `severity="medium"` 상수 하드코드.
- [x] `asyncio.to_thread(get_diff, ...)` 로 sync 호출 위임 (벤더링 파일 내부 개조 금지).
- [x] 에러 매핑 = §4 표 (6행 status·code 쌍).
- [x] `routers/ai.py` 수정 0 (dispatcher 의존으로 자동 지원).
- [x] train/ 디렉토리 수정 0.

---

## 실행 검증 결과

### 1) env import
```
$ cd backend && .venv/bin/python -c "from app.env import env; print(env.LLM_PROVIDER, env.VLLM_MODEL, env.VLLM_API_KEY, env.HF_TOKENIZER, env.VLLM_ENDPOINT)"
mock vllmlora EMPTY nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16 None
```
→ 기본 분기 `mock`, VLLM_* 4개 기본값 계약 표와 완전 일치, VLLM_ENDPOINT 미설정 시 None.

### 2) Dispatcher 분기
```
$ LLM_PROVIDER=mock      ... → MockProvider       # 기본 분기 보존
$ LLM_PROVIDER=finetuned ... → FinetunedProvider  # 기존 분기 보존
$ LLM_PROVIDER=vllm      ... → VllmProvider       # 새 분기 동작
$ LLM_PROVIDER=bogus     ... → MockProvider       # invalid fallback 보존
```

### 3) VllmProvider import (extra 미설치 환경)
```
$ .venv/bin/python -c "from app.services.providers.vllm import VllmProvider; print('OK')"
OK
$ # 확인: import 시점에 openai/transformers 가 sys.modules 에 들어가지 않음
confirmed: openai/transformers not eagerly imported on VllmProvider module load
```

### 4) `VLLM_ENDPOINT` 미설정 가드
```
$ .venv/bin/python -c "... VllmProvider().analyze(req) ..."
status=500 detail={'code': 'AI_UPSTREAM', 'message': 'VLLM_ENDPOINT is not configured'}
```
→ §4 표 1행 일치. 벤더링 import 보다 먼저 차단 확인.

### 5) `_resolve_doc_id` 3단 폴백 (§3.4)
```
$ .venv/bin/python -c "... assert _resolve_doc_id('world', refs) == 'd1' ..."
_resolve_doc_id 3-stage fallback: all assertions passed
```
- 1차 substring `in` 매칭 (첫 히트) OK.
- 2차 first-ref 폴백 OK.
- 3차 `"unknown"` 리터럴 폴백 OK.
- 빈 known_text 는 1차 건너뛰고 2차 first-ref 폴백 OK.

### 6) 빈 `new_doc` 방어 브랜치
```
$ .venv/bin/python -c "... empty new_doc ..."
empty new_doc branch OK: {'source_id': 'test-empty', 'output': {'new': [], 'conflict': []}}
```
→ §2.5 방어적 안전장치 동작. 라우터 422 가 선차단하지만 provider 레벨에서도 안전.

### 7) Ruff lint
```
$ cd backend && uv tool run --from 'ruff>=0.4' ruff check app
Found 3 errors.  (모두 pre-existing: env.py 의 GEMINI_API_KEY / FINETUNED_API_URL / FINETUNED_API_KEY Optional[str])
```
- **새 lint 위반 0건**. 이번 작업으로 추가된 `VLLM_ENDPOINT` 는 `str | None` 문법 사용.
- 벤더링 디렉토리는 `extend-exclude` 로 제외 → `_vendor/infer_diff.py` 의 I001 (import 블록 미정렬, 이는 upstream sys.path 해킹 때문) 이 lint 목록에서 빠짐.

---

## wiki-qa 검증 집중 포인트

1. **벤더링 헤더 주석** — `_vendor/prompt_text.py` 와 `_vendor/infer_diff.py` 의 파일 최상단에 6줄 헤더 블록(`# Vendored from: ...` ~ `# Re-vendor when upstream changes...`)이 존재하고 원본 docstring 보다 **앞**에 위치하는지.
2. **벤더링 byte-for-byte 검증** — 헤더 이후의 라인이 `train/finetune/{파일명}` 과 byte-for-byte 동일한지 (`diff -u train/finetune/infer_diff.py <(tail -n +9 backend/.../_vendor/infer_diff.py)` 등).
3. **Dispatcher 분기 수** — `backend/app/services/docdelta.py` 의 `get_provider` 가 3개 분기 (mock/finetuned/vllm) 만 가지는지, `LLM_PROVIDER="mock"` / `LLM_PROVIDER="bogus"` 양쪽이 `MockProvider` 로 귀결되는지.
4. **Env 기본값 정확성** — `VLLM_MODEL="vllmlora"`, `VLLM_API_KEY="EMPTY"`, `HF_TOKENIZER="nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16"`. 오타 / 대소문자 불일치 없음. `VLLM_ENDPOINT` 미설정 시 None (빈 문자열 아님).
5. **Extra 미설치 환경 부팅** — `uv sync` (vllm extra 없이) 후 `uvicorn app.main:app` 이 **에러 없이** 기동하는지. `LLM_PROVIDER=mock` / `finetuned` 는 vllm.py 모듈이 import 되더라도 openai/transformers 를 pull 하지 않아야 함.
6. **LLM_PROVIDER=vllm + extra 미설치** → 첫 request 에서 500 AI_UPSTREAM + 설치 안내 메시지 포함 (메시지에 `pip install ".[vllm]"` 또는 `uv sync --extra vllm` 문자열).
7. **LLM_PROVIDER=vllm + VLLM_ENDPOINT 미설정** → 500 AI_UPSTREAM, message `"VLLM_ENDPOINT is not configured"`.
8. **`doc_id` 3단 폴백** — substring `in` 매칭, 최초 히트 인덱스, 첫 flat-known DocRef 폴백, `"unknown"` 리터럴.
9. **`severity="medium"` 하드코드** — 환경변수/파라미터로 override 되지 않음.
10. **`source_id` 에코** — 응답 `resp.source_id == req.source_id`.
11. **`reference/doc_scheme.json` diff 0 bytes** — 외부 계약 무변경 확인.
12. **`mock` / `finetuned` / `schemas/docdelta.py` / `routers/ai.py` / `train/` 디렉토리** — 수정 diff 0.
13. **Pyproject** — `[project].dependencies` 무변경 (5개), `[project.optional-dependencies].vllm` 신규 2개, `[tool.ruff].extend-exclude` 신규 1개.

---

## 재작업: QA 결함 #1 수정 (extras 미설치 에러 매핑 — 2026-04-22)

### 배경
QA §8 / §9 (`_workspace/06_qa_report.md`) 에서 결함 1건 보고:
- `LLM_PROVIDER=vllm` + `VLLM_ENDPOINT` 설정 + `[vllm]` extras (`openai`/`transformers`) **미설치** 상태에서 `/api/ai/docdelta` 호출 시
- **기대**: 500 AI_UPSTREAM + `pip install ".[vllm]"` / `uv sync --extra vllm` 설치 안내
- **실제 (수정 전)**: 502 AI_UPSTREAM + 원시 `"No module named 'transformers'"` 메시지
- **원인**: `_vendor/infer_diff.py` 가 `transformers` / `openai` 를 `_get_tokenizer` / `_get_client` **함수 본문**에서 지연 import. 따라서 vllm.py 상단 `from ._vendor.infer_diff import get_diff` 자체는 extras 없이도 성공하고, ImportError 는 `get_diff()` 첫 호출 시점에 발생해 기존 코드의 `except Exception` (502 fallback) 으로 빠졌음.

### 수정 범위 (최소 개입)
- **단일 파일**: `backend/app/services/providers/vllm.py` 만 수정.
- `_vendor/infer_diff.py`, `_vendor/prompt_text.py`: **byte-for-byte 무변경** (아키텍트 §3 벤더링 개조 금지 원칙).
- `docdelta.py`, `env.py`, `pyproject.toml`, `mock.py`, `finetuned.py`, `schemas/`, `routers/`, `reference/`, `train/`: 모두 무변경.

### 변경 요지 (diff)
per-`new_doc` try 블록의 `except` 순서를 구조화하여 `except ImportError` 전용 분기 추가:

```python
# (루프 진입 직전) openai 예외 타입 지연 import — 없으면 빈 튜플 sentinel 로 폴백
try:
    from openai import APIError, APITimeoutError
except ImportError:
    APIError = ()           # type: ignore[assignment,misc]
    APITimeoutError = ()    # type: ignore[assignment,misc]

try:
    result = await asyncio.to_thread(get_diff, ...)
except HTTPException:
    raise
except APITimeoutError as e:        # openai 있음 → 504 TIMEOUT
    raise HTTPException(504, {"code":"TIMEOUT", ...}) from e
except ImportError as e:            # NEW — [vllm] extras 미설치 500 + 설치 안내
    raise HTTPException(500, {"code":"AI_UPSTREAM",
        "message": f'vllm extras not installed ({e}). '
                   'Install with `pip install ".[vllm]"` or `uv sync --extra vllm`.'
    }) from e
except ValueError as e:             # 500 AI_UPSTREAM (infer_diff endpoint guard 보험)
    raise HTTPException(500, ...) from e
except json.JSONDecodeError as e:   # 502 AI_UPSTREAM
    raise HTTPException(502, ...) from e
except APIError as e:               # 502 AI_UPSTREAM
    raise HTTPException(502, ...) from e
except Exception as e:              # 502 AI_UPSTREAM (fallback, 200자 cap)
    raise HTTPException(502, ...) from e
```

포인트:
1. `except ImportError` 가 전용 분기로 분리 → `ModuleNotFoundError` 는 하위 클래스이므로 자동 포함.
2. `APITimeoutError` / `APIError` 참조는 **try 블록 외부**에서 지연 import → openai 미설치 환경에서도 `NameError` 없이 except 절이 문법적으로 유효. 빈 튜플 sentinel 은 `except ()` 가 아무것도 catch 하지 않는 Python 표준 동작을 활용 (확인 완료).
3. `from e` 체인 유지 → 원 스택 트레이스는 로그 차원에서 보존되되 응답 메시지는 200자 cap + 설치 안내.
4. 기존 `VLLM_ENDPOINT` 미설정 가드(step 1)·`from ._vendor.infer_diff import get_diff` 상단 ImportError 가드(step 2, `analyze()` 진입 직후 — 이 경로는 실행상 거의 도달하지 않지만 방어적으로 유지)·`DocdeltaResponse` 재검증(step 7) 모두 **무변경**.

### 검증 결과
```bash
$ cd /home/shadeform/workspace/backend

# 1) Lazy import 유지
$ .venv/bin/python -c "from app.services.providers.vllm import VllmProvider; import sys; \
    assert 'openai' not in sys.modules and 'transformers' not in sys.modules; print('lazy OK')"
lazy OK

# 2) extras 미설치 + VLLM_ENDPOINT 설정 → 500 AI_UPSTREAM + 설치 안내 (핵심 수정 검증)
$ LLM_PROVIDER=vllm VLLM_ENDPOINT=http://localhost:9999/v1 .venv/bin/python -c "..."
status= 500 code= AI_UPSTREAM msg= vllm extras not installed (No module named 'transformers'). \
  Install with `pip install ".[vllm]"` or `uv sync --extra vllm`.
extras-missing guard OK

# 3) VLLM_ENDPOINT 미설정 가드 (기존 동작 보존)
$ LLM_PROVIDER=vllm .venv/bin/python -c "..."
endpoint-missing guard OK

# 4) Dispatcher 3분기 보존
mock -> MockProvider
finetuned -> FinetunedProvider
vllm -> VllmProvider

# 5) Ruff (vllm.py 단독)
$ uv tool run --from 'ruff>=0.4' ruff check app/services/providers/vllm.py
All checks passed!

# 6) Ruff (app 전체) — pre-existing 3건만 남고 신규 0건 (§7 보고서의 기존 3건과 동일: env.py Optional[str] UP045)
Found 3 errors.
```

### 불변 보장
- `reference/doc_scheme.json` / `schemas/docdelta.py` / `frontend/src/types/docdelta.ts` / `train/finetune/*` / `_vendor/*` : 무변경.
- mock / finetuned provider 동작 : 무변경 (dispatcher 검증 통과).
- 응답 상태코드 테이블 (§4) : 이번 수정으로 결함 #1 행만 "502 → 500 + 설치 안내" 로 정합. 나머지 5행 매핑 무변경.
