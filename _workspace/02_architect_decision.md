# 02. 아키텍처 결정 — vLLM Provider 추가 (train/finetune/infer_diff.py 벤더링)

> 입력: `_workspace/01_request.md`. 본 문서는 wiki-architect 산출물.

## 0. 배경 / 전제
- 사용자 요청: backend에서 학습된 vLLM 모델을 `get_diff()`로 호출하고 싶다. `train/` 은 수정 금지, backend/frontend만 수정 가능, train 내부 코드 복사(벤더링) 가능.
- 현 provider 2종(`mock`, `finetuned`) 는 `env.LLM_PROVIDER` 디스패처로 동작 중 (`backend/app/services/docdelta.py`, `backend/app/services/providers/{mock,finetuned}.py`).
- `train/finetune/infer_diff.py::get_diff(known_docs: list[str], new_doc: str) -> dict` 는 sync + OpenAI SDK(sync) + HF tokenizer 로딩 + `guided_json` 강제 DiffOutput 스키마 (3필드 conflict).

## 1. Phase 분류 — **Phase 2a AI 백엔드 변형**
- `docs/07_roadmap.md` Phase 2a 의 "`/api/ai/docdelta` provider 추상화" 항목(이미 완료, 2026-04-22)의 **동일 축 위 확장**. 2번째 provider(finetuned)까지 이미 존재하므로 Provider Protocol 재사용 대상에 해당 — 추상화 "신설"이 아닌 "활용".
- Phase 3/4 범위(인증·동기화·협업)에는 들어가지 않음. Phase 2 내부에서 종결.
- Phase 경계 준수 OK — Phase 3 라이브러리/기능(DB·인증·WebSocket)을 미리 끌어오지 않음.

## 2. 불변 규칙 검토 (R1~R4 + T1~T10)
- **R1 데이터 이동성** ✓ — `Document` 무변경, 마크다운 원문 그대로.
- **R2 로컬 우선** ✓ — 백엔드 미기동/vLLM 부재 시 프론트의 localStorage 경로는 독립 동작.
- **R3 마크다운 원문** ✓ — `DocRef.context` 는 프론트 Document content 원문 그대로. 서버는 이를 벤더링된 `get_diff(known_docs=..., new_doc=...)` 에 문자열로만 넘김.
- **R4 하위 호환** ✓ — Pydantic `DocdeltaRequest/Response/DocdeltaConflict` 5필드 무변경. `reference/doc_scheme.json` 무변경.
- **T1 Local-first** ✓.
- **T2 마크다운 원문** ✓.
- **T3 단일 Document 플랫 타입** ✓ — 새 필드 없음.
- **T8 provider-agnostic 연기** — 본 결정이 T8의 "2번째 공급자" 원칙을 **위반하지 않음**: Protocol(`DocdeltaProvider`)은 이미 2번째 구현(`FinetunedProvider`)이 생길 때 정당화된 추상이다. 이번 `VllmProvider` 는 이미 존재하는 계약을 재사용하는 3번째 구현.
- **T9 Python/FastAPI** ✓ — 오히려 "파이썬 생태계(학습·추론) 1급" 전환의 T9 정당화를 강화함. Node라면 벤더링 자체가 불가능.
- **T10 CommonMark+GFM** ✓.

## 3. 벤더링 vs sys.path 트레이드오프
**선택: 벤더링(backend 안으로 복사)**
- `train/` 은 사용자 명시로 수정 금지. sys.path 주입 / editable install 은 다음 이유로 기각:
  - `train/finetune/infer_diff.py` 가 자체적으로 `sys.path.insert(0, _THIS_DIR)` 로 sibling `prompt_text.py` 를 찾음 → backend 프로세스 import 순서와 충돌 가능.
  - 배포 이미지가 train/ 전체 트리(데이터셋 포함)를 가져가야 함. 이미지 크기·보안 표면 손해.
  - train/ 경로/파일명 변경 시 backend 런타임이 잠재적으로 깨짐 (암묵 계약).
- **벤더링 장점**: backend 에만 의존성 소유권. train/ 내부 리팩토링과 backend 배포 분리.
- **벤더링 단점**: drift.

**Drift 방지 가드 (wiki-backend 지시사항):**
1. 벤더링 파일 최상단 주석 블록 **필수**:
   ```
   # Vendored from: train/finetune/{infer_diff.py,prompt_text.py}
   # Copy date: 2026-04-22
   # Reason: backend cannot depend on train/ runtime layout (architect decision §3).
   # DO NOT EDIT HERE — upstream in train/ is source of truth.
   # Re-vendor when upstream changes: copy file byte-for-byte, update this header.
   ```
2. 벤더링 위치 고정: `backend/app/services/providers/_vendor/{infer_diff.py, prompt_text.py, __init__.py}`. 언더스코어 prefix `_vendor` 로 외부 import 금지 의도 시그널.
3. 재벤더링 프로세스: train/ 변경 시 wiki-qa가 diff를 벤더링본과 대조 → wiki-backend가 byte-for-byte 재복사.
4. 개조 최소화 원칙: 벤더링 시 **필요한 최소 수정**만 허용.
   - `from prompt_text import format_prompt_text` 의 sys.path 해킹은 그대로 둔다(같은 디렉토리 sibling이므로 동작).
   - `if __name__ == "__main__":` smoke test 블록 유지.

## 4. 공존(3rd provider) vs 교체(finetuned 대체) 트레이드오프
**선택: 공존 — `mock` / `finetuned` / `vllm` 3종.**
- finetuned 교체 기각 근거:
  - `FinetunedProvider` 는 사용자 정의 HTTP 엔드포인트를 소유한 사람의 탈출구. vLLM 은 매우 특정한 OpenAI-호환 서빙 가정이므로, 임의 finetuned API를 필요로 하는 사용자 차단.
  - 공존 비용은 provider 파일 1개 + dispatcher 분기 1줄. YAGNI 관점 비용 미미.
  - **byte-for-byte 동작 유지**: mock/finetuned provider의 분기·동작·에러 매핑 전혀 건드리지 않는다. dispatcher 변경 1라인만 추가.

## 5. 동기→비동기 경계
**선택: `asyncio.to_thread(get_diff, ...)` 로 sync 함수를 워커 스레드에 위임.**
- `get_diff()` 는 sync + heavy:
  - 최초 호출 시 `AutoTokenizer.from_pretrained(...)` (수백MB 다운로드 가능).
  - OpenAI SDK 의 sync `client.completions.create(...)` 는 이벤트 루프 블로킹.
- **AsyncOpenAI 교체 → 기각**: 벤더링 파일 개조 필요. §3의 "개조 최소화" 원칙 위반.
- **라우터 sync 전환 → 기각**: 다른 provider의 `async def analyze` 계약 깨짐.
- 구현 요약:
  ```
  # VllmProvider.analyze (async):
  # 1) req.known_docs flatten -> list[str]
  # 2) for each new_doc item:
  #      result = await asyncio.to_thread(get_diff, flat_known, item.context, ...)
  # 3) merge: new concat, conflict 는 doc_id substring 복원 후 concat
  # 4) DocdeltaResponse 재조립
  ```

## 6. 의존성 전략
**선택: `openai>=1.0`, `transformers>=4.40` 을 `[project.optional-dependencies].vllm` extra 로 격리.**
- `transformers` 전이 의존성이 100MB+ 수준. PoC mock 서버 부팅/이미지 크기 손해.
- `openai` SDK 도 vllm 프로바이더를 쓰지 않는 사용자에게 요구할 이유 없음.
- `httpx` 는 이미 `FinetunedProvider` 프로덕션 의존성 유지.
- `LLM_PROVIDER=vllm` 인데 extra 미설치 → import 실패 시 **500 AI_UPSTREAM + 설치 안내 메시지** (01_request.md 에러 매핑 표와 일치).
- `pyproject.toml` 외 lockfile/requirements.txt 는 이번 변경에서 건드리지 않는다. `pip install ".[vllm]"` / `uv sync --extra vllm` 으로 명시적 opt-in.

## 7. 계약 매핑 승인
`_workspace/01_request.md` §계약 매핑 규칙 전반 **승인**.
- **known_docs flatten**: `flat_known: list[str] = [ref.context for group in known_docs for ref in group]`. 순서 보존.
- **new_doc iterate**: `req.new_doc: list[DocRef]` 각 원소별 `get_diff` 호출 후 merge. PoC 단계 수용.
- **doc_id 복원**:
  - 1차: `known_text` 를 flat_known 각 항목에 `in`(substring) 매칭. 최초 히트한 known DocRef의 `doc_id`.
  - 2차 폴백: 매칭 실패 시 첫 flat_known DocRef의 `doc_id`.
  - 3차 폴백: known_docs 비어있으면 `"unknown"`.
- **severity 기본값**: `"medium"` 고정. 자동 분류는 Phase 3+ 과제.
- **source_id 에코**: `DocdeltaResponse.source_id == req.source_id` (기존 provider 2종과 동일).

### 7.1 숨겨진 비용
- new_doc N개 → vLLM N회 호출. tokenizer 캐시 재사용되나 네트워크/GPU inference 는 매 호출. PoC 단계 new_doc=1 가정. 향후 배치화 필요 시 **train/ 원본의 get_diff 시그니처 확장 후 재벤더링** (backend 개조 금지).

## 8. 남은 리스크 / 추후 과제
| # | 리스크 | 완화 (현재) | 추후 과제 |
|---|---|---|---|
| R-1 | tokenizer 최초 호출 지연(수초~수십초) | 프로세스 전역 `_tokenizer_cache` 로 2회차부터 무시 가능 | backend 기동 시 워밍업 — 본 작업 밖 |
| R-2 | `guided_json` 으로도 파싱 실패 가능 | `json.loads` 실패 시 502 AI_UPSTREAM 매핑 | 재시도·fallback schema 는 Phase 2b 이후 |
| R-3 | vLLM 서버 미기동 / 네트워크 오류 | OpenAI SDK timeout → 504 TIMEOUT, 기타 → 502 AI_UPSTREAM | `/api/health` 에 vllm ping 추가 **안 함** |
| R-4 | HF tokenizer 다운로드 첫 호출 수십 MB | 운영자가 `HF_TOKENIZER` 로컬 경로 지정 가능 | 컨테이너 빌드 시 tokenizer 프리-페치 → Phase 2b |
| R-5 | 벤더링 drift | §3 주석 가드 + wiki-qa 교차검증 | train/ 변경 감지 CI — Phase 3 |
| R-6 | `transformers` import 자체가 무거움 | 벤더링 코드의 함수 내부 import 지연 유지 | 모니터링만 |

## 9. 선택 (요약)
- 벤더링 경로: `backend/app/services/providers/_vendor/{__init__.py, infer_diff.py, prompt_text.py}` 신설.
- provider 신설: `backend/app/services/providers/vllm.py` — `VllmProvider.analyze()` 는 `asyncio.to_thread` 로 벤더링 `get_diff` 호출 + 매핑.
- dispatcher: `backend/app/services/docdelta.py` 에 `"vllm"` 분기 추가. mock/finetuned 분기 무변경.
- env: `backend/app/env.py` 의 `_PROVIDER_VALUES` 에 `"vllm"` 추가 + `Literal` 확장 + `VLLM_ENDPOINT` / `VLLM_MODEL` / `VLLM_API_KEY` / `HF_TOKENIZER` 4개 필드. 잘못된 값 fallback 로직은 그대로(mock 으로 회귀).
- pyproject: `[project.optional-dependencies]` 에 `vllm = ["openai>=1.0", "transformers>=4.40"]`.
- `.env.example` (존재 시): VLLM_* 4개 라인 추가.
- 프론트: **변경 없음**.

## 10. 버리는 것
- train/ editable install · sys.path 주입.
- AsyncOpenAI 로의 벤더링 내부 개조.
- finetuned provider 대체.
- provider 선택 UI (프론트).
- 모델 기반 severity 자동 분류 — severity="medium" 고정.
- new_doc 배치 호출 최적화 (벤더링 개조 필요).
- DynamoDB / 저장소 변경.

## 11. 의존 에이전트 지시 요약
- **wiki-data**: §7 매핑 계약을 `_workspace/03_data_contract.md` 명문화. `reference/doc_scheme.json` 무변경 확인.
- **wiki-backend**: §9의 6개 파일 변경 구현. 벤더링 헤더 주석 §3 준수. mock/finetuned byte-for-byte 유지.
- **wiki-qa**: 불변 규칙 R1~R4 + `Document` 5필드 + `reference/doc_scheme.json` 무변경 + mock/finetuned 무변경 + env 4개 일치 + extra 미설치 환경에서 mock 기본 부팅 검증.
- **wiki-docs**: `docs/04_api.md`(provider 3번째 옵션·env 4개), `docs/06_tech_stack.md`(optional extra), `docs/08_tradeoffs.md`(의사결정 변경 이력 **신규 행 추가**), `CLAUDE.md` 변경 이력 표 1행 추가.

## 12. 이 선택을 뒤집을 조건
- vLLM 서버가 multi-tenant → provider 선택 UI 도입 검토.
- new_doc 배치 입력 일상화 → train/ 업스트림에 배치 시그니처 추가 요청 후 재벤더링.
- `transformers` / `openai` 가 backend 핵심 기능으로 승격 → extra → 기본 의존성 승격.
- train/ 월 1회 이상 drift → 벤더링 포기, train/ 을 파이썬 패키지로 승격 (사용자 재확인 필요).

## 13. Flag (오케스트레이터용)
- 불변 규칙 위반 없음. 제안 그대로 진행 가능.
- 벤더링 파일 상단 헤더 주석 추가는 **backend 쪽 파일만** 수정하므로 "train/ 수정 금지" 명령에 위배되지 않음. 본 결정은 이 해석 전제.

---

**한 줄 요약:** vLLM provider 추가는 Phase 2a 내부 변형이며 불변 규칙(R1~R4, T1/T2/T3/T8/T9/T10) 어느 것도 위반하지 않는다. 벤더링 + `_vendor/` 격리 + `asyncio.to_thread` + optional extra + 3-provider 공존 구조로 승인.
