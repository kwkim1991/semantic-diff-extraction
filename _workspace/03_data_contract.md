# 03. 데이터 계약 — vLLM Provider 추가 (벤더링 `get_diff` 매핑)

> 입력: `_workspace/01_request.md`, `_workspace/02_architect_decision.md` §7.
> 본 문서는 **wiki-data** 산출물. wiki-backend 구현·wiki-qa 검증의 계약 기준.
> 범위: `POST /api/ai/docdelta` 에 `LLM_PROVIDER=vllm` 분기가 추가되는 경우의
> 요청→호출→응답 매핑 규칙 + env 계약 + 에러 매핑 + 불변성 선언.

---

## 1. 불변성 선언 (Byte-for-byte 유지)

본 변경(vLLM provider 추가)은 **외부 계약과 기존 provider 동작을 일체 건드리지 않는다.**
아래 항목은 wiki-backend 구현 시 **변경 금지**이며, wiki-qa는 회귀를 검증한다.

### 1.1 외부 계약 (프론트·AI 스킴)
- `Document` 5필드 무변경: `title`, `content`, `tags`, `updatedAt`, `type`.
- `reference/doc_scheme.json` **바이트 단위 무변경** (input/output 구조 동일).
- 프론트 타입 `frontend/src/types/docdelta.ts` (및 연관 타입) **무변경**.
- `/api/ai/docdelta` HTTP 메서드·경로·상태 코드 매핑·에러 바디 형태 **무변경**.

### 1.2 Pydantic 스키마 (`backend/app/schemas/docdelta.py`)
다음 5개 모델의 **필드명·타입·순서·`extra="forbid"` 설정·`default_factory`** 전부 무변경:

| 모델 | 필드 (선언 순서 고정) |
|---|---|
| `DocdeltaDocRef` | `doc_id: str`, `context: str` |
| `DocdeltaRequest` | `source_id: str`, `instruction: str`, `known_docs: list[list[DocdeltaDocRef]]`, `new_doc: list[DocdeltaDocRef]`, `convert_doc: list[DocdeltaDocRef] = Field(default_factory=list)` |
| `DocdeltaConflict` | `doc_id: str`, `known_text: str`, `new_text: str`, `reason: str`, `severity: Literal["low","medium","high"]` |
| `DocdeltaOutput` | `new: list[str]`, `conflict: list[DocdeltaConflict]` |
| `DocdeltaResponse` | `source_id: str`, `output: DocdeltaOutput` |

### 1.3 기존 provider 동작
- `backend/app/services/providers/mock.py` 와 `backend/app/services/providers/finetuned.py` 의 입출력·에러 매핑·fixture 분기는 **byte-for-byte 동일**.
- `backend/app/services/docdelta.py` dispatcher 는 `"vllm"` 분기만 **추가**, 기존 `"mock"`/`"finetuned"` 분기 **무변경**.

---

## 2. 요청 → 벤더링 `get_diff` 입력 매핑

### 2.1 대상 함수 시그니처 (벤더링 원본 그대로 사용)
```python
# backend/app/services/providers/_vendor/infer_diff.py
def get_diff(known_docs: list[str], new_doc: str) -> dict:
    """반환 예:
    {
      "new": ["...", "..."],
      "conflict": [{"known_text": "...", "new_text": "...", "reason": "..."}]
    }
    """
```
- 본 함수는 **sync**. `VllmProvider.analyze` 는 `asyncio.to_thread(get_diff, flat_known, item.context)` 로 호출한다 (02 §5).

### 2.2 `flat_known` 계산식
```python
flat_known: list[str] = [ref.context for group in req.known_docs for ref in group]
```
- **순서 보존 규칙**: `req.known_docs` 의 outer list 순서를 먼저 소진하고, 각 group 의 inner list 순서 그대로 이어붙인다 (Python 이중 컴프리헨션 기본 의미).
- doc_id 복원 시 동일 순서의 **병렬 리스트** `flat_known_refs: list[DocdeltaDocRef]` 도 함께 유지한다:
  ```python
  flat_known_refs: list[DocdeltaDocRef] = [ref for group in req.known_docs for ref in group]
  # assert len(flat_known) == len(flat_known_refs)
  # assert all(flat_known[i] == flat_known_refs[i].context for i in range(len(flat_known)))
  ```
- 빈 group 은 그대로 흘려보낸다 (empty list 의 이중 컴프리헨션은 빈 결과). `req.known_docs == []` 도 허용되며 `flat_known == []` 이 된다.

### 2.3 `new_doc` N회 호출 규칙
`req.new_doc: list[DocdeltaDocRef]` 길이 N ≥ 1. (N==0 은 라우터에서 이미 **422** 로 차단되므로 provider 진입 자체가 없다 — 기존 검증 로직 **무변경**.)

- 호출 횟수: 정확히 **N회**.
- i번째 호출 (0-indexed):
  ```python
  result_i: dict = await asyncio.to_thread(
      get_diff,
      flat_known,        # list[str] — 모든 호출에 동일한 스냅샷
      req.new_doc[i].context,  # str — i번째 new_doc 의 마크다운 원문
  )
  ```
- `flat_known` 은 **N회 호출 전체에 걸쳐 동일한 객체**를 재사용한다 (재계산 금지). list 자체는 호출 경계에서 불변으로 취급한다.

### 2.4 호출에 **넘기지 않는** 필드
다음 필드는 `get_diff()` 인자에 포함하지 않는다:
- `req.instruction`: 벤더링 내부의 `prompt_text.TEXT_INSTRUCTION` 이 **고정적으로** 프롬프트에 삽입되므로 외부 주입은 의도적으로 무시한다. `req.instruction` 값 자체는 라우터까지 정상 수락되지만 vLLM 호출 시 드롭된다 (mock/finetuned 와 일관: 계약상 instruction은 provider 재량).
- `req.convert_doc`: Phase 2 범위 밖. 응답·호출 어느 쪽에도 영향 없음. 빈 리스트든 값이 있든 무시된다 (기존 provider 동일).
- `req.source_id`: 호출 인자에는 넘기지 않고, 응답에서만 1:1 에코한다 (§3.3).

### 2.5 빈 new_doc 가드
- 라우터 층에서 `req.new_doc == []` 는 **422**. Provider 는 N==0 케이스를 방어적으로 처리할 필요 없음 (벤더링 `get_diff` 를 한 번도 호출하지 않도록 라우터가 이미 차단).
- 단, 방어적 안전장치로 `VllmProvider.analyze` 의 루프 본체가 N==0 이면 `DocdeltaResponse(source_id=req.source_id, output=DocdeltaOutput(new=[], conflict=[]))` 를 반환한다 (실행 경로상 도달 불가, 테스트 용도만).

---

## 3. `get_diff` 출력 → `DocdeltaResponse` 매핑

### 3.1 반환 형식 (N회 호출 결과)
각 `result_i` 는 다음 shape:
```json
{
  "new": ["...", "..."],
  "conflict": [
    {"known_text": "...", "new_text": "...", "reason": "..."}
  ]
}
```
- `conflict[*]` 는 **3필드만** (`known_text`, `new_text`, `reason`). `DocdeltaConflict` 의 5필드 중 나머지 2개(`doc_id`, `severity`)는 backend 가 복원·주입한다.

### 3.2 `output.new` 매핑
- 전 호출의 `result_i["new"]` 를 **호출 순서대로** concat:
  ```python
  merged_new: list[str] = []
  for r in results:
      merged_new.extend(r.get("new", []))
  ```
- 중복 제거·정렬 **하지 않는다** (원본 순서 보존). mock/finetuned provider 와 동일 원칙.

### 3.3 `output.conflict` 매핑
각 `result_i["conflict"][j]` 를 다음과 같이 `DocdeltaConflict` 로 변환:

| 출력 필드 | 소스 |
|---|---|
| `known_text` | `result_i["conflict"][j]["known_text"]` 그대로 (문자열 복사, trimming 금지) |
| `new_text` | `result_i["conflict"][j]["new_text"]` 그대로 |
| `reason` | `result_i["conflict"][j]["reason"]` 그대로 |
| `doc_id` | **§3.4 3단 폴백 규칙 적용** |
| `severity` | 상수 `"medium"` (Literal 검증 통과) |

### 3.4 `doc_id` 복원 — **3단 폴백 규칙 (Authoritative)**
입력: `conflict_item["known_text"]` (str), `flat_known` (list[str]), `flat_known_refs` (list[DocdeltaDocRef]).

```
1차: for idx in range(len(flat_known)):
         if conflict_item["known_text"] in flat_known[idx]:   # substring(in) 매칭
             return flat_known_refs[idx].doc_id              # 최초 히트 ref
     # 매칭 0건 → 2차로 폴백

2차: if flat_known_refs:                                    # 최소 1개 known 존재
         return flat_known_refs[0].doc_id                   # 첫 flat_known DocRef

3차: return "unknown"                                       # known_docs 비어있음
```

**규칙 세부사항 (wiki-qa 검증 기준):**
- 1차 매칭 연산자는 Python `in` (substring containment). 정규화(공백/대소문자/개행) **하지 않는다**. 원문 그대로 `known_text in flat_known[idx]`.
- 1차에서 복수 히트가 발생하더라도 **첫 인덱스**만 사용한다 (`range` 순회 early return).
- `flat_known` 과 `flat_known_refs` 는 §2.2에서 생성한 **동일 순서의 병렬 리스트**여야 한다 (길이·순서 일치 불변).
- 2차 폴백의 "첫 flat_known DocRef" 는 `req.known_docs` outer list 의 **첫 non-empty group 의 첫 원소** 와 동일 (Python 이중 컴프리헨션 결과).
- 3차 폴백의 리터럴 문자열은 **정확히** `"unknown"` (소문자, 따옴표 없음). 빈 문자열이나 `None` 금지.

### 3.5 concat 순서 (conflict)
```python
merged_conflict: list[DocdeltaConflict] = []
for r in results:                       # i = 0..N-1 순서
    for c in r.get("conflict", []):     # j = 호출 내부 순서
        merged_conflict.append(
            DocdeltaConflict(
                doc_id=_recover_doc_id(c["known_text"], flat_known, flat_known_refs),
                known_text=c["known_text"],
                new_text=c["new_text"],
                reason=c["reason"],
                severity="medium",
            )
        )
```
- 이중 순회 순서 **(i 외부, j 내부)** 고정. 정렬 금지.

### 3.6 최종 응답 조립
```python
DocdeltaResponse(
    source_id=req.source_id,           # 1:1 에코 (§3.3 의 표와 별개로 response 레벨)
    output=DocdeltaOutput(
        new=merged_new,
        conflict=merged_conflict,
    ),
)
```
- `source_id` 는 라우터 거치지 않고 provider 에서 직접 에코 (기존 mock/finetuned 와 동일 위치).
- `convert_doc` 은 응답 어디에도 나타나지 않는다. 요청 필드 `convert_doc` 유무와 응답은 **무관**.

### 3.7 Pydantic 재검증
최종 조립된 `DocdeltaResponse` 는 반환 직전 Pydantic 인스턴스화로 암묵 재검증된다. 재검증 실패는 §4 의 `AI_UPSTREAM / 502` 로 매핑.

---

## 4. 에러 매핑 표 (01_request.md §에러 매핑 재확인)

wiki-qa 는 본 표를 **검증 기준**으로 사용한다. FinetunedProvider 와 일관된 (status, code) 쌍을 유지한다.

| 사유 | HTTP status | error code | 비고 |
|---|---|---|---|
| `VLLM_ENDPOINT` 미설정 (None / 빈 문자열) | 500 | `AI_UPSTREAM` | provider 분기 진입 직후 즉시 실패. 메시지에 env 이름 포함. |
| `openai` / `transformers` 미설치 (ImportError) | 500 | `AI_UPSTREAM` | 메시지에 **설치 안내** 포함 (예: `pip install ".[vllm]"` 또는 `uv sync --extra vllm`). |
| `openai.APITimeoutError` | 504 | `TIMEOUT` | OpenAI SDK 의 명시적 timeout. |
| 기타 `openai.APIError` / 네트워크 오류 | 502 | `AI_UPSTREAM` | 연결 거부·5xx 업스트림·readtimeout(APITimeoutError 외) 포함. |
| `json.loads` 파싱 실패 (guided_json 출력 깨짐) | 502 | `AI_UPSTREAM` | `ValueError`/`json.JSONDecodeError` 캐치 대상. |
| `DocdeltaResponse` Pydantic 재검증 실패 | 502 | `AI_UPSTREAM` | `ValidationError` 캐치. (이 경로 진입 자체가 공급자 출력 스키마 위반을 의미) |

**에러 바디 형태 (기존 유지):**
- FastAPI `HTTPException` 매핑 경로를 재사용. 본 변경에서 에러 바디 shape 은 건드리지 않는다.

---

## 5. Env 계약 (`backend/app/env.py`)

### 5.1 `LLM_PROVIDER`
- 타입: `Literal["mock", "finetuned", "vllm"]`.
- 기본값: `"mock"`.
- 불량 값(위 3개 외): 기존 정책 그대로 `"mock"` 으로 **silent fallback** (경고 로그는 기존 정책 유지).
- dispatcher (`docdelta.py`) 는 `"vllm"` 분기 추가 1라인 외 mock/finetuned 분기 무변경.

### 5.2 VLLM_* 4개 필드
| env 이름 | 타입 | 기본값 | 용도 |
|---|---|---|---|
| `VLLM_ENDPOINT` | `Optional[str]` | `None` | 예: `"http://localhost:9983/v1"`. 미설정 시 provider 진입 즉시 500 (§4). |
| `VLLM_MODEL` | `str` | `"vllmlora"` | `client.completions.create(model=...)` 에 전달. |
| `VLLM_API_KEY` | `str` | `"EMPTY"` | OpenAI-호환 서빙은 보통 키 없이 운영 → placeholder. |
| `HF_TOKENIZER` | `str` | `"nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16"` | `AutoTokenizer.from_pretrained(...)` 인자. 로컬 경로도 가능. |

- **기본값 불변 조건**: 위 기본값은 본 계약에서 권위이며, wiki-backend 는 코드에 그대로 반영한다 (오타/대소문자 불일치 금지).
- `.env.example` 에는 위 4개 라인을 주석 포함해 추가한다 (파일이 존재하는 경우에 한함).

### 5.3 Optional extra
- `pyproject.toml`: `[project.optional-dependencies]` 에 `vllm = ["openai>=1.0", "transformers>=4.40"]` 추가.
- `httpx`·`fastapi` 등 기존 프로덕션 의존성 **건드리지 않는다**.
- extra 미설치 + `LLM_PROVIDER=vllm` 조합은 §4 의 `500 AI_UPSTREAM (설치 안내)` 로 귀결.

---

## 6. 계약 변경 체크리스트 (wiki-backend 구현 시 필수 준수)

- [ ] `DocdeltaRequest` / `DocdeltaResponse` / `DocdeltaDocRef` / `DocdeltaConflict` / `DocdeltaOutput` 의 **Pydantic 스키마 무변경** (필드명·타입·순서·default·`extra="forbid"`).
- [ ] 응답 `DocdeltaConflict` 의 5필드 **선언 순서·이름 무변경**: `doc_id`, `known_text`, `new_text`, `reason`, `severity`.
- [ ] `source_id` 1:1 에코 (`resp.source_id == req.source_id`).
- [ ] 프론트 타입(`frontend/src/types/docdelta.ts` 등) **무변경**.
- [ ] `reference/doc_scheme.json` **바이트 단위 무변경** (diff 0 bytes).
- [ ] `mock` provider 동작·fixture **byte-for-byte 무변경**.
- [ ] `finetuned` provider 동작·HTTP 호출·에러 매핑 **byte-for-byte 무변경**.
- [ ] dispatcher(`docdelta.py`) 는 `"vllm"` 분기 추가 외 diff 0.
- [ ] `env.py` 의 기존 필드(LLM_PROVIDER 기본값·기타 env) **무변경**. 신규 4개 env 만 추가.
- [ ] VLLM_* 4개 env 의 **기본값이 §5.2 표와 정확히 일치**.
- [ ] `pyproject.toml` 의 기본 dependencies 목록 **무변경**. `[project.optional-dependencies].vllm` 만 추가.
- [ ] `doc_id` 3단 폴백 구현이 §3.4 규칙과 일치 (substring `in` 매칭 · 최초 히트 · `"unknown"` 리터럴).
- [ ] `severity="medium"` 상수 하드코드 (환경변수·파라미터화 금지).
- [ ] `asyncio.to_thread(get_diff, ...)` 로 sync 호출 위임 (벤더링 파일 내부 개조 금지).
- [ ] 에러 매핑이 §4 표와 정확히 일치 (status·code 쌍 모두).

---

## 7. 의존 에이전트 지시

- **wiki-backend**: 본 계약 §2~§5 를 코드로 반영. 04_decision 의 §9 파일 목록 6개 외 파일 수정 금지. 벤더링 파일 상단 주석 헤더(§3 of 02) 필수.
- **wiki-qa**: §1 불변성 선언, §3.4 3단 폴백, §4 에러 매핑, §5.2 env 기본값, §6 체크리스트 15항목을 회귀 검증 체크 포인트로 사용.
- **wiki-docs**: `docs/04_api.md` (provider=`vllm` 및 VLLM_* env 4개), `docs/06_tech_stack.md` (optional extra), `docs/08_tradeoffs.md` (의사결정 변경 이력 신규 행)에 반영. `reference/doc_scheme.json` 은 **수정 금지**.
- **wiki-frontend**: 호출 없음 (프론트 변경 0).

---

## 8. 하위 호환 보증 요약

- `Document` 5필드: **변경 없음** → 기존 localStorage 문서 그대로 로드·저장 가능.
- `/api/ai/docdelta` 요청·응답 스킴: **변경 없음** → 기존 `mock`/`finetuned` 호출 클라이언트가 `vllm` 서버와도 동일 페이로드로 통신.
- `reference/doc_scheme.json`: **변경 없음** → AI 학습/검증 데이터셋 계약 유지.
- 신규 env 4개: 전부 기본값 제공 → 기존 배포 환경변수 미설정 상태에서도 기동 가능 (`LLM_PROVIDER` 가 `mock` 이면 VLLM_* 전혀 읽히지 않음).
- Optional extra: 기본 `pip install .` 사용자에게 설치 부담 제로.

**마이그레이션 필요?** 아니오. 런타임 계약·저장 포맷 모두 무변경.

---

**한 줄 요약:** vLLM provider 는 `DocdeltaRequest` 를 §2 매핑 규칙으로 벤더링 `get_diff(known_docs: list[str], new_doc: str)` 에 N회 분해 호출하고, 응답을 §3 (특히 §3.4 3단 폴백)으로 `DocdeltaResponse` 에 재조립하며, 5개 Pydantic 모델·`reference/doc_scheme.json`·프론트 타입·기존 2개 provider 동작은 **byte-for-byte 무변경**이다.
