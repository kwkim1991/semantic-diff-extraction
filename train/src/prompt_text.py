"""Shared plain-text prompt formatter.

JSON 으로 직렬화된 input (instruction + known_docs + new_doc) 을 자연어 텍스트로
재구성한다. 학습 데이터의 user content 와 평가 시 prompt 양쪽에서 동일한 함수를
쓰도록 이곳에 둔다.
"""

import json

TEXT_INSTRUCTION = (
    "아래에 여러 개의 기존 문서와 한 개 이상의 신규 문서가 주어집니다. "
    "신규 문서에서 기존 문서 어디에도 나오지 않는 새로운 내용을, "
    "그리고 기존 문서의 내용과 충돌(상반되는 사실) 이 있는 내용을 찾아 정리하세요. "
    "기존 문서에 이미 있는 내용이나 단순한 재진술(paraphrase) 은 제외합니다."
)


def format_prompt_text(input_str: str) -> str:
    """input 필드를 plain text 로 재구성.

    - input 이 JSON dump 면 파싱해서 각 문서 context 를 섹션으로 풀어 쓴다.
    - input 이 이미 text 포맷이면 그대로 반환.
    - JSON 스키마 / 필드명 cue 는 넣지 않는다 (outlines 가 출력 형태를 강제하므로
      prompt 에는 과업 설명만 담는다).
    """
    stripped = input_str.lstrip()
    if not stripped.startswith("{"):
        return input_str
    try:
        obj = json.loads(input_str)
    except Exception:
        return input_str
    if not isinstance(obj, dict):
        return input_str

    known_docs = obj.get("known_docs", [])
    new_doc = obj.get("new_doc", [])

    parts: list[str] = [TEXT_INSTRUCTION, ""]

    parts.append("### 기존 문서")
    idx = 0
    for group in known_docs:
        if isinstance(group, list):
            for doc in group:
                idx += 1
                ctx = doc.get("context", "") if isinstance(doc, dict) else str(doc)
                parts.append("")
                parts.append(f"[문서 {idx}]")
                parts.append(ctx)
        else:
            idx += 1
            parts.append("")
            parts.append(f"[문서 {idx}]")
            parts.append(str(group))
    parts.append("")

    parts.append("### 신규 문서")
    for di, doc in enumerate(new_doc, 1):
        ctx = doc.get("context", "") if isinstance(doc, dict) else str(doc)
        parts.append("")
        parts.append(f"[신규 {di}]")
        parts.append(ctx)
    parts.append("")

    parts.append("### 답")
    return "\n".join(parts)
