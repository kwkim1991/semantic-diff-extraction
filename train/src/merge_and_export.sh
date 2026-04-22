#!/usr/bin/env bash
# Merge LoRA adapter into the base model and export to HuggingFace format.
#
# Two steps (guide sections 4.2 and 5):
#   1) merge_lora.py  — requires Megatron-Bridge repo cloned at /opt/Megatron-Bridge
#   2) AutoBridge.export_ckpt — Python API, no repo clone required
#
# Usage:
#   bash finetune/merge_and_export.sh <LORA_CKPT_ITER_DIR> [HF_OUT_DIR]
#   e.g. bash finetune/merge_and_export.sh nemo_experiments/hcdiff_nano3_lora/iter_0000200

set -euo pipefail

LORA_CKPT="${1:?Path to iter_xxxxxxx LoRA checkpoint dir required}"
HF_OUT="${2:-exports/nemotron_3_nano_diff_hf}"
HF_MODEL="${HF_MODEL:-nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16}"
MEGATRON_REPO="${MEGATRON_REPO:-/opt/Megatron-Bridge}"
MERGED_MCORE="${MERGED_MCORE:-nemo_experiments/merged_mcore}"
# Must match the EP used at training (so the sharded LoRA ckpt re-assembles).
NGPU="${NGPU:-4}"

set -x 
# Step 1: merge LoRA -> merged Megatron checkpoint
# merge_lora.py calls torch.distributed.init_process_group("nccl") internally,
# so it must be launched under torchrun (even for a single-process run).
torchrun --nproc_per_node="${NGPU}" \
    "${MEGATRON_REPO}/examples/peft/merge_lora.py" \
    --hf-model-path "${HF_MODEL}" \
    --lora-checkpoint "${LORA_CKPT}" \
    --output "${MERGED_MCORE}"

# Step 2: export merged Megatron checkpoint -> HF format
python - <<PY
import warnings
from transformers.generation.configuration_utils import GenerationConfig

# Patch: Nemotron HF repo 의 generation_config.json 은 do_sample=False 인데
# top_p / top_k / temperature 가 함께 세팅돼 있어서 transformers 최신 버전의
# strict validation 에서 거부됨. validate 를 lenient 로 덮고, save 직전에
# do_sample=False 경로의 sampling 파라미터를 disable 기본값으로 정규화한다.
_orig_validate = GenerationConfig.validate
def _lenient_validate(self, *args, **kwargs):
    kwargs["strict"] = False
    try:
        return _orig_validate(self, *args, **kwargs)
    except TypeError:
        return _orig_validate(self)
    except Exception as e:
        warnings.warn(f"[gen_cfg] validate bypassed: {e}")
GenerationConfig.validate = _lenient_validate

_orig_save = GenerationConfig.save_pretrained
# GenerationConfig class-level default 값 — strict validate 는 "default 와 다른지"
# 로 판단하므로, disable 하려면 정확히 이 값들로 복원해야 함.
_SAMPLE_DEFAULTS = {
    "top_p": 1.0,
    "top_k": 50,
    "temperature": 1.0,
    "typical_p": 1.0,
    "min_p": None,
    "epsilon_cutoff": 0.0,
    "eta_cutoff": 0.0,
}
def _patched_save(self, *args, **kwargs):
    if not bool(getattr(self, "do_sample", False)):
        for attr, default in _SAMPLE_DEFAULTS.items():
            if hasattr(self, attr):
                try:
                    setattr(self, attr, default)
                except Exception:
                    pass
    return _orig_save(self, *args, **kwargs)
GenerationConfig.save_pretrained = _patched_save

from megatron.bridge import AutoBridge

bridge = AutoBridge.from_hf_pretrained("${HF_MODEL}", trust_remote_code=True)
bridge.export_ckpt(
    megatron_path="${MERGED_MCORE}",
    hf_path="${HF_OUT}",
    show_progress=True,
)
print("Exported HF model at: ${HF_OUT}")
PY
