#!/usr/bin/env bash
# src/infer_diff.py::get_diff 를 짧은 샘플 입력으로 호출해서 결과를 출력.
#
# Usage:
#   VLLM_ENDPOINT=http://localhost:9983/v1 bash scripts/check_infer_diff.sh
#
# Env:
#   VLLM_ENDPOINT  required (OpenAI-호환 vLLM URL)
#   VLLM_MODEL     default vllmlora
#   VLLM_API_KEY   default EMPTY

set -euo pipefail

python3 - <<'PY'
import json
import sys

sys.path.insert(0, "src")
from infer_diff import get_diff

result = get_diff(
    known_docs=[
        "회의일시: 2025-03-10. 결론: 4/1 착수, 박경태 PM. 개발 인력 3명.",
    ],
    new_doc=(
        "회의일시: 2025-03-24. 결론: 4/15 로 연기, PM 은 김주은. "
        "개발 인력 5명으로 증원."
    ),
)
print(json.dumps(result, ensure_ascii=False, indent=2))
PY
