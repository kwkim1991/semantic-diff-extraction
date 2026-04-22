# 01. 요청 정리 (오케스트레이터) — vLLM provider 추가

## 사용자 원문
> "backend에서 학습된 vllm을 호출할려면 infer_diff.py 내부 함수가 필요한데 적용시킬수있어?"
> "train 내부는 수정하지말고 backend나 front를 수정해야될거야. 필요하다면 말이야. train 내부 코드를 가지고와서 다시 쓰던지 하는건 가능해"

## 결정된 방향 (사용자 명시 + 오케스트레이터 사전 제시)
- **벤더링 방식**: `train/finetune/infer_diff.py` + `prompt_text.py` 를 backend 하위로 복사. train/ 은 절대 수정하지 않음.
- **새 provider 추가 (공존)**: 기존 `mock`, `finetuned` provider는 그대로 두고 **세 번째 `vllm` provider**를 추가한다. finetuned 교체 아님.
- **프론트 무변경**: provider 선택은 서버 env(`LLM_PROVIDER`) 로만 결정. 프론트는 `/api/ai/docdelta` 를 동일하게 호출.
- **optional extra 로 무거운 의존성 격리**: `openai`, `transformers` 는 `[vllm]` extra 로 두고 기본 설치에는 포함하지 않는다.

## 범위 (6개 경계면 + 1개 문서)
| # | 파일/경로 | 변경 성격 |
|---|---|---|
| 1 | `backend/app/services/providers/vllm.py` | **신설** — VllmProvider. `asyncio.to_thread` 로 sync `get_diff` 호출. |
| 2 | `backend/app/services/providers/_vendor/infer_diff.py` + `prompt_text.py` + `__init__.py` | **신설 (벤더링)** — train/finetune/ 에서 복사. 원본 경로·복사 사유 주석 포함. |
| 3 | `backend/app/services/docdelta.py` | **수정** — dispatcher에 `"vllm"` 분기 추가. |
| 4 | `backend/app/env.py` | **수정** — `LLM_PROVIDER` literal 에 `"vllm"` 추가 + `VLLM_ENDPOINT` / `VLLM_MODEL` / `VLLM_API_KEY` / `HF_TOKENIZER` 4개 env. |
| 5 | `backend/pyproject.toml` | **수정** — `[project.optional-dependencies]` 에 `vllm = ["openai>=1.0", "transformers>=4.40"]` 추가. |
| 6 | `docs/04_api.md`, `docs/06_tech_stack.md`, `docs/08_tradeoffs.md`, `CLAUDE.md` | **수정** — provider 세 번째 옵션 / env / 결정 이력 반영. |
| 7 | `.env.example` | **수정 (있으면)** — VLLM_* 네 줄 추가. |

## 계약 매핑 (핵심)
- `req.known_docs: list[list[DocRef]]` → flatten 해서 `list[str]` (각 DocRef 의 context) 로 변환.
- `req.new_doc: list[DocRef]` → vLLM `get_diff` 는 단일 문자열만 받음. **new_doc 원소별로 `get_diff` 호출 후 결과 merge**.
- vLLM conflict 는 `{known_text, new_text, reason}` 3필드만. `DocdeltaConflict` 는 `{doc_id, known_text, new_text, reason, severity}` 5필드 → **doc_id**: known_text 를 flat_known 에 substring 매칭해 복원 (실패 시 첫 known doc id 폴백, 그마저 없으면 `"unknown"`), **severity**: 기본 `"medium"`.

## 에러 매핑 (기존 FinetunedProvider 일관)
| 사유 | status | code |
|---|---|---|
| `VLLM_ENDPOINT` 미설정 | 500 | AI_UPSTREAM |
| `openai`/`transformers` import 실패 (extra 미설치) | 500 | AI_UPSTREAM (설치 안내 포함) |
| OpenAI SDK timeout | 504 | TIMEOUT |
| 기타 OpenAI/네트워크 오류 | 502 | AI_UPSTREAM |
| guided_json 출력 파싱 실패 | 502 | AI_UPSTREAM |

## 제약 (불변 규칙·기존 계약)
- `Document` 5필드 무변경 (T2).
- `reference/doc_scheme.json` 무변경 — 외부 계약 동일.
- **기존 `mock` / `finetuned` provider 동작 · 계약 무변경** (byte-for-byte).
- train/ 디렉토리 수정 금지.
- localStorage 단일 SoT 유지 (T1) — 영향 없음.
- 마크다운 원문 보관 (T10) — 영향 없음.

## 팀 구성 & 순서
**Phase 2 AI 기능 (백엔드 전용) 변형** → 파이프라인:
1. `wiki-architect` — 벤더링 + 3rd provider 의 불변 규칙/트레이드오프 승인.
2. `wiki-data` — 요청/응답 매핑 계약 (doc_id 복원 규칙) 확정.
3. `wiki-backend` — 벤더링 + VllmProvider + env/dispatcher/pyproject 수정.
4. `wiki-qa` — 통합 정합성 (경로·env·provider 일치·불변 규칙) 검증.
5. `wiki-docs` — docs/04,06,08 + CLAUDE.md 이력 동기화.

프론트 변경 없음 → `wiki-frontend` 제외.

## 출력
- `_workspace/02_architect_decision.md` → 05, 06, 07 까지 파이프라인 산출물.
- 실제 코드: `backend/app/`, `backend/pyproject.toml`.
- 문서: `docs/`, `CLAUDE.md`.
