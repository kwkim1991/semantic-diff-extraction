#!/usr/bin/env python3
"""LoRA SFT via Megatron-Bridge — 로드한 체크포인트 기반 (모델 고정 아님).

Manual ConfigContainer + AutoBridge construction — mirrors guide sections 3.1
(AutoBridge.from_hf_pretrained -> to_megatron_provider) and 4.1 (LoRA PEFT).

Pipeline:
    1) AutoBridge 가 `--hf-model` 의 HF config/tokenizer 를 로드. 그래서 어떤
       HF 모델 ID 든 provider 를 만들 수 있음 (Transformer/MoE/Mamba hybrid).
    2) to_megatron_provider() 가 모델 native 구조로 provider 를 materialize.
       parallelism 만 override (TP=PP=CP=1, EP 는 MoE 일 때만 적용).
    3) LoRA target modules 는 provider 를 보고 자동 선택: Transformer 선형 4개
       기본, hybrid_override_pattern 에 Mamba(M) 가 있으면 in_proj/out_proj 추가.
       `--lora-targets` 로 수동 override 가능.
    4) ConfigContainer 구성 후 megatron.bridge.training.finetune 실행.
"""

import argparse
import math
import os
from pathlib import Path

from megatron.bridge import AutoBridge
from megatron.bridge.peft.lora import LoRA
from megatron.bridge.recipes.utils.optimizer_utils import (
    distributed_fused_adam_with_cosine_annealing,
)
from megatron.bridge.training.finetune import finetune
from megatron.bridge.training.gpt_step import forward_step
from megatron.bridge.training.config import (
    CheckpointConfig,
    ConfigContainer,
    FinetuningDatasetConfig,
    LoggerConfig,
    TrainingConfig,
)
from megatron.bridge.training.tokenizers.config import TokenizerConfig
from megatron.core.distributed import DistributedDataParallelConfig

DEFAULT_HF_MODEL = "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16"
# 학습 데이터 (known_docs + new_doc 직렬화) p95 ~12k, p99 ~17.8k (cl100k 기준).
# 2048 이면 샘플 100% 가 truncate 되어 output 이 잘려 모델이 empty 출력만 학습함.
# 16384 로 상향하면 p95 커버, p99 초과(~1.7%)는 잘리되 output 보존을 위해
# dataset truncation_method 를 "left" 로 지정해야 안전 (아래 build_config 참조).
SEQ_LENGTH = 16384
TRANSFORMER_LORA_TARGETS = ["linear_qkv", "linear_proj", "linear_fc1", "linear_fc2"]
MAMBA_LORA_TARGETS = ["in_proj", "out_proj"]


def provider_has_mamba(provider) -> bool:
    pattern = getattr(provider, "hybrid_override_pattern", None)
    return bool(pattern) and "M" in pattern


def provider_has_moe(provider) -> bool:
    return bool(getattr(provider, "num_moe_experts", 0))


def default_lora_targets(provider) -> list[str]:
    targets = list(TRANSFORMER_LORA_TARGETS)
    if provider_has_mamba(provider):
        targets += MAMBA_LORA_TARGETS
    return targets


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--pretrained-checkpoint", required=True,
                   help="Megatron-format checkpoint dir (from convert_hf_ckpt.py)")
    p.add_argument("--dataset-root", default="data/sft",
                   help="Dir containing {training,validation,test}.jsonl")
    p.add_argument("--save-path", default="nemo_experiments/hcdiff_nano3_lora")
    p.add_argument("--hf-model", default=DEFAULT_HF_MODEL,
                   help="HF model ID used for AutoBridge + HF tokenizer")
    p.add_argument("--epochs", type=float, default=3.0,
                   help="학습 에폭 수 (float 허용). train_iters 는 "
                        "ceil(N_train * epochs / global_batch_size) 로 계산.")
    p.add_argument("--global-batch-size", type=int, default=32)
    p.add_argument("--micro-batch-size", type=int, default=1)
    p.add_argument("--lr", type=float, default=1e-4)
    p.add_argument("--lora-dim", type=int, default=16)
    p.add_argument("--lora-alpha", type=int, default=32)
    p.add_argument("--lora-dropout", type=float, default=0.1)
    p.add_argument("--expert-parallel-size", type=int, default=1,
                   help="expert_model_parallel_size. MoE 모델에만 적용됨 "
                        "(non-MoE 체크포인트면 1 이 아닌 값은 무시 + 경고).")
    p.add_argument("--lora-targets", default=None,
                   help="쉼표로 구분한 LoRA target module 이름. 지정하지 않으면 "
                        "provider 를 보고 Transformer/ (hybrid 인 경우) Mamba 타겟을 자동 선택.")
    p.add_argument("--seq-length", type=int, default=SEQ_LENGTH)
    p.add_argument("--save-interval", type=int, default=50)
    p.add_argument("--eval-interval", type=int, default=50)
    p.add_argument("--eval-iters", type=int, default=5)
    p.add_argument("--seed", type=int, default=1234,
                   help="FinetuningDatasetConfig.seed — shuffle RNG seed")
    return p.parse_args()


def count_training_samples(dataset_root: str) -> int:
    path = Path(dataset_root) / "training.jsonl"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} 가 없습니다. --dataset-root 확인 또는 convert_data.py 먼저 실행."
        )
    n = 0
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                n += 1
    if n == 0:
        raise ValueError(f"{path} 에 샘플이 없습니다.")
    return n


def compute_train_iters(n_samples: int, global_batch_size: int, epochs: float) -> int:
    iters = math.ceil(n_samples * epochs / global_batch_size)
    return max(1, iters)


def build_model_provider(hf_model: str, seq_length: int, ep: int):
    bridge = AutoBridge.from_hf_pretrained(hf_model, trust_remote_code=True)
    provider = bridge.to_megatron_provider()
    provider.tensor_model_parallel_size = 1
    provider.pipeline_model_parallel_size = 1
    provider.context_parallel_size = 1
    provider.sequence_parallel = False
    provider.seq_length = seq_length

    if provider_has_moe(provider):
        provider.expert_model_parallel_size = ep
    elif ep > 1:
        print(f"[warn] {hf_model} 은 MoE 가 아닙니다. --expert-parallel-size={ep} 무시.")

    if hasattr(provider, "finalize"):
        provider.finalize()
    return provider


def main() -> None:
    args = parse_args()

    n_train = count_training_samples(args.dataset_root)
    train_iters = compute_train_iters(n_train, args.global_batch_size, args.epochs)
    print(
        f"[plan] n_train={n_train}  epochs={args.epochs}  "
        f"global_batch_size={args.global_batch_size}  -> train_iters={train_iters}"
    )

    provider = build_model_provider(args.hf_model, args.seq_length,
                                    args.expert_parallel_size)

    if args.lora_targets:
        lora_targets = [t.strip() for t in args.lora_targets.split(",") if t.strip()]
    else:
        lora_targets = default_lora_targets(provider)
    print(f"[plan] lora_targets={lora_targets}  "
          f"moe={provider_has_moe(provider)}  mamba={provider_has_mamba(provider)}")

    optimizer_cfg, scheduler_cfg = distributed_fused_adam_with_cosine_annealing(
        precision="bf16-mixed",
        max_lr=args.lr,
        min_lr=args.lr * 0.1,
        lr_warmup_iters=max(1, train_iters // 10),
        lr_decay_iters=train_iters,
        adam_beta2=0.95,
        adam_eps=1e-8,
        weight_decay=0.1,
        start_weight_decay=0.1,
        end_weight_decay=0.1,
        lr_decay_style="cosine",
    )

    run_dir = args.save_path
    tb_dir = os.path.join(run_dir, "tb_logs")

    cfg = ConfigContainer(
        model=provider,
        train=TrainingConfig(
            train_iters=train_iters,
            global_batch_size=args.global_batch_size,
            micro_batch_size=args.micro_batch_size,
            eval_interval=args.eval_interval,
            eval_iters=args.eval_iters,
        ),
        optimizer=optimizer_cfg,
        scheduler=scheduler_cfg,
        ddp=DistributedDataParallelConfig(
            check_for_nan_in_grad=True,
            grad_reduce_in_fp32=True,
        ),
        dataset=FinetuningDatasetConfig(
            dataset_root=args.dataset_root,
            seq_length=args.seq_length,
            do_validation=False,
            do_test=False,
            # Per-epoch shuffle 활성화.
            # Megatron-Bridge 의 `GPTSFTDataset` 는 `max_num_samples` 가 None 이면
            # samples_mapping 을 만들지 않고 파일 순서대로 인덱싱한다 (매 에폭 동일
            # 순서). `max_train_samples` 를 세팅하면 `_OnlineSampleMapping(shuffle=True,
            # seed=cfg.dataset.seed)` 이 걸려서 에폭 블록 단위로 셔플됨.
            # train_iters × global_batch_size 는 학습이 소비할 전체 샘플 수.
            max_train_samples=train_iters * args.global_batch_size,
            seed=args.seed,
            # Overflow (seq_length 초과) 샘플에서 output 이 잘리면 모델이 empty 만 학습함.
            # input 앞쪽부터 잘라서 output 은 온전히 남기도록 강제.
            # prompt_template 기본값은 "{input} {output}" 인데 chat-template 으로
            # 전처리된 input/output 사이에 literal 공백이 끼면 template 경계가
            # 깨진다 (assistant turn 토큰 직후 공백 등). 공백 없이 concat 하도록
            # "{input}{output}" 로 override — plain JSON 학습에도 안전.
            dataset_kwargs={
                "truncation_method": "left",
                "truncation_field": "input",
                "prompt_template": "{input}{output}",
            },
        ),
        logger=LoggerConfig(
            log_interval=10,
            tensorboard_dir=tb_dir,
            log_timers_to_tensorboard=True,
            wandb_project=os.environ.get("WANDB_PROJECT") or None,
            wandb_exp_name=os.environ.get("WANDB_NAME")
            or os.path.basename(run_dir.rstrip("/")),
            wandb_entity=os.environ.get("WANDB_ENTITY") or None,
            wandb_save_dir=run_dir,
        ),
        tokenizer=TokenizerConfig(
            tokenizer_type="HuggingFaceTokenizer",
            tokenizer_model=args.hf_model,
        ),
        checkpoint=CheckpointConfig(
            save=run_dir,
            load=run_dir,
            pretrained_checkpoint=args.pretrained_checkpoint,
            save_interval=args.save_interval,
            ckpt_format="torch_dist",
            fully_parallel_save=True,
            load_optim=False,
        ),
        mixed_precision="bf16_mixed",
        peft=LoRA(
            target_modules=lora_targets,
            dim=args.lora_dim,
            alpha=args.lora_alpha,
            dropout=args.lora_dropout,
        ),
    )

    finetune(config=cfg, forward_step_func=forward_step)


if __name__ == "__main__":
    main()
