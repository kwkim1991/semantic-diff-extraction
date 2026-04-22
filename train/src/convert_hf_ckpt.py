#!/usr/bin/env python3
"""Import a HuggingFace Nemotron checkpoint into Megatron-Bridge format.

Wraps AutoBridge.import_ckpt (section 2.2 of the Megatron-Bridge Nano SFT guide).
Works as long as the `megatron-bridge` package is installed — no repo clone needed.

Usage:
    # default target (Nemotron 3 Nano 30B-A3B)
    python src/convert_hf_ckpt.py --megatron-path ./checkpoints/nemotron_3_nano_mcore

    # explicit HF model ID
    python src/convert_hf_ckpt.py \
        --hf-model nvidia/NVIDIA-Nemotron-Nano-9B-v2-Base \
        --megatron-path ./checkpoints/nano-9b-v2_mcore
"""

import argparse

DEFAULT_HF_MODEL = "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--hf-model", default=DEFAULT_HF_MODEL,
                   help=f"HF model ID or local path (default: {DEFAULT_HF_MODEL})")
    p.add_argument("--megatron-path", required=True)
    p.add_argument("--torch-dtype", choices=["float32", "float16", "bfloat16"], default=None)
    p.add_argument("--device-map", default=None)
    p.add_argument("--no-trust-remote-code", action="store_true",
                   help="Disable trust_remote_code (Nemotron usually needs it ON)")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    from megatron.bridge import AutoBridge

    kwargs: dict = {"trust_remote_code": not args.no_trust_remote_code}
    if args.torch_dtype:
        kwargs["torch_dtype"] = args.torch_dtype
    if args.device_map:
        kwargs["device_map"] = args.device_map

    AutoBridge.import_ckpt(
        hf_model_id=args.hf_model,
        megatron_path=args.megatron_path,
        **kwargs,
    )
    print(f"Converted: {args.hf_model} -> {args.megatron_path}")


if __name__ == "__main__":
    main()
