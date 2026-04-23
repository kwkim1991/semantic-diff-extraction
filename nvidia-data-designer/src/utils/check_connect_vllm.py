# Verify vLLM — try common ports
import requests

CANDIDATE_BASES = [
    "http://localhost:5000/v1",  # build_and_run.sh
    "http://localhost:8000/v1",  # vLLM default
]

VLLM_BASE_URL = None
response = None
last_err = None
for base in CANDIDATE_BASES:
    try:
        r = requests.get(f"{base}/models", timeout=10)
        r.raise_for_status()
        VLLM_BASE_URL = base
        response = r
        break
    except Exception as e:
        last_err = e

if VLLM_BASE_URL is None:
    print("Cannot connect on :5000 or :8000.")
    print(f"Last error: {last_err}")
else:
    models = response.json()
    ids = [m["id"] for m in models.get("data", [])]
    print(f"vLLM is running at {VLLM_BASE_URL}")
    print(f"Available models: {ids}")
    if "nemotron" in ids:
        VLLM_MODEL_NAME = "nemotron"
    elif ids:
        VLLM_MODEL_NAME = ids[0]
    else:
        VLLM_MODEL_NAME = "nemotron"
