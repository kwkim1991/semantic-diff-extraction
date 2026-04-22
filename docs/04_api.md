# 04. API 계약

Phase 1(현재 데모)은 **백엔드 없음** — 모든 상태는 클라이언트 `localStorage` 에 저장된다.
본 문서는 Phase 2(AI 프록시) / Phase 3(동기화) / Phase 4(협업)에서 프론트가 호출하게 될 API 계약을 정의한다.

모든 엔드포인트는 `application/json`. 인증은 Phase 3부터 (세션 쿠키 또는 `Authorization: Bearer <token>`).

---

## Phase 2 — AI 프록시

Gemini API 키를 **클라이언트에 노출하지 않기 위해** Python(FastAPI) 서버가 프록시 역할을 한다.

### `POST /api/ai/summarize`

현재 문서를 3~5줄로 요약.

#### Request
```json
{
  "content": "문서 본문 마크다운 ...",
  "style": "bullet | paragraph",
  "language": "ko | en"
}
```

#### Response `200 OK` (stream: Server-Sent Events)
```
event: token
data: {"text": "이 문서는 "}

event: token
data: {"text": "...요약을 다룹니다."}

event: done
data: {"usage": {"input_tokens": 420, "output_tokens": 85}}
```

비-stream 모드는 `Accept: application/json` 로 요청하면 완성본 1회 반환.

---

### `POST /api/ai/suggest-title`

본문을 보고 제목 후보 3개 제안.

#### Request
```json
{ "content": "...", "language": "ko" }
```

#### Response
```json
{
  "suggestions": [
    "Wiki Workspace 아키텍처 개요",
    "마크다운 기반 개인 위키 설계",
    "Phase 1 데모 구조 정리"
  ]
}
```

---

### `POST /api/ai/rewrite`

선택 영역 재작성 (톤 변경, 문장 정리).

#### Request
```json
{
  "selection": "선택된 텍스트...",
  "instruction": "좀 더 공식적인 톤으로",
  "context_before": "...",
  "context_after": "..."
}
```

#### Response
```json
{ "rewritten": "선택된 텍스트의 재작성 결과..." }
```

---

### `POST /api/ai/docdelta`

기존 문서 그룹(`known_docs`)을 기준으로 신규 문서(`new_doc`)에서 **새로운 내용**과 **충돌하는 내용**을 추출한다.

> **현재 상태 (2026-04-22, provider 추상화 적용)**: FastAPI + Pydantic 입력/출력 검증과 계약 shape는 정식, 실제 LLM 호출은 아직 없음(mock 기본). 응답 포맷은 `reference/doc_scheme.json` 준수. 실제 Gemini(`google-generativeai`) 호출, SSE, rate limit 은 후속 작업.
>
> **Provider 디스패치 (2026-04-22)**: 백엔드는 `LLM_PROVIDER` env 에 따라 `MockProvider`(기본, `backend/app/services/providers/mock.py` — synthetic PoC 응답), `FinetunedProvider`(`backend/app/services/providers/finetuned.py` — 외부 finetuned HTTP 엔드포인트로 요청 body 그대로 passthrough 후 `DocdeltaResponse` 재검증), 또는 `VllmProvider`(`backend/app/services/providers/vllm.py` — OpenAI-호환 vLLM 서빙 엔드포인트를 `train/finetune/infer_diff.py::get_diff` 벤더링 코드로 호출) 로 `services/docdelta.py` 의 `get_provider()` 가 분기한다. 잘못된 값은 `mock` 으로 safe fallback. **이전에 존재했던 `source_id.startswith("DEMO-")` fixture 분기는 2026-04-22 철회·삭제됨** (`docdelta_fixtures.py` 파일 삭제, `routers/ai.py` 분기 제거). 계약 shape 는 여전히 `{source_id, output:{new, conflict}}` — 변경 없음.
>
> **백엔드 env (docdelta 관련)**:
>
> | 변수 | 필수 | 기본값 | 설명 |
> |---|---|---|---|
> | `LLM_PROVIDER` | 권장 (없으면 `mock`) | `mock` | `mock` / `finetuned` / `vllm` 3값. 그 외 값은 `mock` 으로 safe fallback. |
> | `FINETUNED_API_URL` | `LLM_PROVIDER=finetuned` 일 때 필수 | (없음) | `DocdeltaRequest` JSON 을 그대로 POST 받아 `DocdeltaResponse` JSON 을 반환해야 하는 외부 엔드포인트 URL. 미설정 시 `500 AI_UPSTREAM` 응답. |
> | `FINETUNED_API_KEY` | 선택 | (없음) | 설정 시 `Authorization: Bearer <value>` 헤더로 첨부. 미설정이면 헤더 생략. |
> | `FINETUNED_TIMEOUT_SEC` | 선택 | `30` | `httpx.AsyncClient` 타임아웃(초). Timeout 발생 시 `504 TIMEOUT`. |
> | `VLLM_ENDPOINT` | `LLM_PROVIDER=vllm` 일 때 필수 | (없음, `None`) | OpenAI-호환 vLLM 서빙 base URL (예: `http://localhost:9983/v1`). 미설정 시 provider 진입 직후 `500 AI_UPSTREAM` 응답. |
> | `VLLM_MODEL` | 선택 | `vllmlora` | `client.completions.create(model=...)` 에 전달되는 모델 이름. |
> | `VLLM_API_KEY` | 선택 | `EMPTY` | OpenAI SDK 요구 placeholder. vLLM OpenAI-호환 서빙은 보통 키 없이 운영. |
> | `HF_TOKENIZER` | 선택 | `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16` | `AutoTokenizer.from_pretrained(...)` 인자. HuggingFace 모델 ID 또는 로컬 경로 허용. |
>
> `finetuned` 스텁의 실패 매핑: 네트워크/DNS 오류 `502 AI_UPSTREAM`, upstream 4xx/5xx `502 AI_UPSTREAM`, 응답 shape 위반 `500 INTERNAL`.
>
> `vllm` provider 의 실패 매핑 (6행):
>
> | 사유 | HTTP | 에러 코드 | 비고 |
> |---|---|---|---|
> | `VLLM_ENDPOINT` 미설정 (None / 빈 문자열) | 500 | `AI_UPSTREAM` | provider 분기 진입 직후 즉시 실패. 메시지에 env 이름 포함. |
> | `[vllm]` extras 미설치 (`openai` / `transformers` `ImportError`) | 500 | `AI_UPSTREAM` | 설치 안내 문구 포함 (`pip install ".[vllm]"` / `uv sync --extra vllm`). 벤더링 내부가 함수 본문에서 지연 import 하므로 첫 `get_diff()` 호출 시 캐치. |
> | `openai.APITimeoutError` | 504 | `TIMEOUT` | OpenAI SDK 의 명시적 timeout. |
> | 기타 `openai.APIError` / 네트워크 오류 | 502 | `AI_UPSTREAM` | 연결 거부 · upstream 5xx · read-timeout(APITimeoutError 외) 포함. |
> | `json.JSONDecodeError` (guided_json 출력 깨짐) | 502 | `AI_UPSTREAM` | `_vendor/infer_diff.py` 의 `json.loads` 실패 경로. |
> | `DocdeltaResponse` Pydantic 재검증 실패 | 502 | `AI_UPSTREAM` | `ValidationError` 캐치. 공급자 출력 스키마 위반 시그널. |
>
> **외부 계약 무변경 선언 (vllm provider 내부 동작)**: vLLM provider 내부의 구현 상세 — (a) `known_docs` flatten 후 `new_doc` 원소별 `get_diff` N회 호출 · merge, (b) `conflict[].doc_id` 3단 폴백 (1차 substring `in` 매칭 · 2차 첫 flat-known DocRef · 3차 리터럴 `"unknown"`), (c) `conflict[].severity` 상수 `"medium"` 하드코드 — 은 모두 provider 내부 구현이며, **외부 계약 `reference/doc_scheme.json` 과 5개 Pydantic 모델(`DocdeltaDocRef`/`DocdeltaRequest`/`DocdeltaConflict`/`DocdeltaOutput`/`DocdeltaResponse`) 은 byte-for-byte 무변경**이다. 기존 `mock` / `finetuned` provider 의 요청·응답 shape·에러 매핑 동작도 그대로.

**계약의 권위 출처**: [`reference/doc_scheme.json`](../reference/doc_scheme.json) — 이 파일이 input/output 구조의 단일 출처이며, 학습/검증 데이터셋은 [`reference/train-validation-dataset/`](../reference/train-validation-dataset/)에 JSONL 형식으로 제공된다. 본 문서의 요약이 scheme과 어긋나면 scheme을 정답으로 간주.

#### Request
```json
{
  "source_id": "S0000437",
  "instruction": "주어진 기존 문서들(known_docs)을 기준으로 신규 문서(new_doc)에서 다음을 추출하세요. new: 기존 문서들 어디에도 없는 새로운 내용. conflict: 기존 문서들 중 어느 하나와 충돌하는 내용. 기존 문서들에 이미 있는 내용이거나 단순 paraphrase는 출력하지 않습니다.",
  "known_docs": [
    [
      { "doc_id": "C0026301", "context": "..." },
      { "doc_id": "C0026302", "context": "..." }
    ],
    [
      { "doc_id": "C0026304", "context": "..." }
    ]
  ],
  "new_doc": [
    { "doc_id": "C0026309", "context": "..." }
  ],
  "convert_doc": [
    { "doc_id": "C0026301", "context": "..." }
  ]
}
```

- `known_docs`: **문서 그룹의 배열**(2차원). 각 그룹은 같은 맥락의 `doc_id`/`context` 쌍 배열.
- `new_doc`: 비교 대상 신규 문서 조각들.
- `convert_doc`: `known_docs`에서 무작위 셔플된 레퍼런스(학습 스키마 호환용). 서버는 입력으로만 받고 출력 `conflict[].doc_id`와 매칭 가능해야 함.

#### Response `200 OK`
```json
{
  "source_id": "S0000437",
  "output": {
    "new": [
      "배경: 문서 수동 분류에 연간 8,000 man-hour 투입",
      "기술 스택: OpenAI API + 사내 벡터 DB"
    ],
    "conflict": [
      {
        "doc_id": "C0026301",
        "known_text": "...known_docs의 해당 구간...",
        "new_text": "...new_doc의 해당 구간...",
        "reason": "...충돌 이유...",
        "severity": "low | medium | high"
      }
    ]
  }
}
```

- `new`: 기존에 없던 신규 사실의 문자열 배열. 단순 paraphrase는 포함 금지.
- `conflict[]`: 충돌 건별 객체. `severity`는 `low`/`medium`/`high` 셋 중 하나로 정규화.

#### 에러 코드
- `VALIDATION` (422): `known_docs` 또는 `new_doc` 누락·빈 배열
- `AI_UPSTREAM` (502): LLM 호출 실패
- `TIMEOUT` (504): 긴 컨텍스트로 인한 타임아웃

#### 스트리밍
`Accept: text/event-stream`으로 요청 시, `new`·`conflict` 항목별로 SSE 이벤트 스트리밍. 완료 시 `event: done` + `usage`.

---

## Phase 3 — Document Sync

### `GET /api/documents`

사용자의 문서 목록(메타만, 본문 제외).

#### Query Params
- `cursor` (optional): 다음 페이지 커서
- `limit` (default 50, max 200)
- `updated_since` (ISO 8601, optional): 증분 동기화

#### Response
```json
{
  "documents": [
    {
      "id": "uuid",
      "title": "...",
      "createdAt": 1714345678000,
      "updatedAt": 1714456789000
    }
  ],
  "next_cursor": "..."
}
```

---

### `GET /api/documents/:id`

단일 문서 전체.

#### Response
```json
{
  "id": "uuid",
  "title": "...",
  "content": "# 마크다운 본문...",
  "createdAt": 1714345678000,
  "updatedAt": 1714456789000,
  "version": 42
}
```

---

### `POST /api/documents`

새 문서 생성.

#### Request
```json
{
  "id": "client-generated-uuid",
  "title": "",
  "content": ""
}
```

`id`는 클라이언트가 발급해(offline-first) 서버는 검증만.

#### Response `201 Created`
동일한 문서를 `GET /api/documents/:id` 응답 포맷으로 반환.

---

### `PUT /api/documents/:id`

문서 전체 교체. 낙관적 동시성 제어.

#### Request
```json
{
  "title": "...",
  "content": "...",
  "base_version": 42
}
```

#### Response
- `200 OK` + `{ version: 43 }`
- `409 Conflict` + `{ current: { ...server version... } }` — 클라이언트가 머지 UI 표시

---

### `DELETE /api/documents/:id`

#### Response `204 No Content`

---

## Phase 4 — 협업

### `POST /api/documents/:id/share`

#### Request
```json
{
  "invitee_email": "teammate@example.com",
  "role": "viewer | commenter | editor"
}
```

#### Response `201 Created`
```json
{ "share_id": "...", "link": "https://.../d/:id?t=..." }
```

---

### `GET /api/documents/:id/ws` (WebSocket)

실시간 편집 채널. 메시지 프로토콜:

```ts
// Client → Server
{ type: "op", doc_id, version, patch: JSONPatch[] }
{ type: "cursor", doc_id, position }

// Server → Client
{ type: "op", from_user_id, patch: JSONPatch[], version }
{ type: "presence", users: [{ user_id, name, color, cursor }] }
{ type: "ack", version }
```

CRDT(Y.js) 도입 시 위 프로토콜은 `y-websocket` 표준으로 교체 — [08_tradeoffs.md](08_tradeoffs.md) T7 참고.

---

## 공통 사항

- 모든 응답에 `X-Request-ID` 헤더.
- 에러 응답 통일 포맷:
  ```json
  { "error": { "code": "NOT_FOUND", "message": "..." } }
  ```
- 타임스탬프는 epoch ms(숫자) — 클라이언트의 `Document.createdAt/updatedAt` 과 일치([05_data_schema.md](05_data_schema.md)).
- Rate limit: AI 계열은 per-user 분당 20회, 동기화 계열은 분당 600회 (Phase 3 진입 시 재조정).

---

## 에러 코드

| Code | HTTP | 의미 |
|---|---|---|
| `UNAUTHORIZED` | 401 | 인증 필요 |
| `FORBIDDEN` | 403 | 권한 부족 (공유 문서 역할 불일치) |
| `NOT_FOUND` | 404 | 문서 없음 |
| `VERSION_CONFLICT` | 409 | `base_version` 불일치 |
| `VALIDATION` | 422 | 필드 검증 실패 |
| `RATE_LIMITED` | 429 | `Retry-After` 헤더 포함 |
| `AI_UPSTREAM` | 502 | Gemini 호출 실패 |
| `TIMEOUT` | 504 | — |
