#!/bin/bash

# ==================== Job Description ====================
: ${DESC:="multiturn-nl2sql"}

# ==================== Resource Configuration ====================
: ${WORKER:=4}              # Number of machines
: ${GPU_NUM:=8}             # GPUs per machine
TOT_GPU_NUM=$(($GPU_NUM * $WORKER))
: ${HOURS:=16}              # Max runtime (hours)
: ${PRIORITY:=1}            # Job priority
use_h100=False

# ==================== Training Hyperparameters ====================
NUM_EPISODES=2

# KL Loss
KL_LOSS_COEF=0.00
ENTROPY_COEF=0.00
EPS_CLIP=0.2
EPS_CLIP_HIGH=0.28

# Optimizer
OPTIMIZER="adam"
WEIGHT_DECAY=0.1
ADAM_BETA1=0.9
ADAM_BETA2=0.98

# SGLang
ROLLOUT_NUM_GPUS_PER_ENGINE=2
SGLANG_MEM_FRACTION=0.8

# ==================== Work Directory ====================
WORK_DIR=/path/to/your/workdir
cd "$WORK_DIR"

# ==================== Algorithm & Rollout Configuration ====================
N_SAMPLES_PER_PROMPT=8
ROLLOUT_BATCH_SIZE=32
NUM_ROLLOUT=2000
MAX_TOKENS_PER_GPU=18432
ROLLOUT_TEMPERATURE=0.8
SAVE_INTERVAL=40

# Tensor Parallel
TENSOR_MODEL_PARALLEL_SIZE=4
PIPELINE_MODEL_PARALLEL_SIZE=1

ROLLOUT_NUM_GPUS=8
alg=grpo
ROLLOUT_MAX_RESPONSE_LEN=2048

# Schema configuration
use_schema=True
use_segmented_propagation=False
gamma=1
SCHEMA_WEIGHT=0.25
SCHEMA_SCORING_MODE="truematch"  # Options: totalmatch / truematch / recall_then_precision_strict

# Reward function
REWARD_FUNC="generate_sql_token"

# ==================== Model Configuration ====================
USE_ASYNC=True
LR_ACTOR=1e-6
modelName=Qwen3-8B
HF_CHECKPOINT=/path/to/your/model/checkpoint
REF_LOAD=""

# ==================== Training Script Selection ====================
SCRIPT_BASE_DIR=/path/to/your/examples/nl2sql

if [ "$USE_ASYNC" = "True" ] || [ "$USE_ASYNC" = "true" ] || [ "$USE_ASYNC" = "1" ]; then
    TRAIN_SCRIPT_PATH="${SCRIPT_BASE_DIR}/run_qwen3_async_oversampling.sh"
    echo "✓ Using ASYNC training script"
else
    TRAIN_SCRIPT_PATH="${SCRIPT_BASE_DIR}/run_qwen3_unified.sh"
    echo "✓ Using UNIFIED (sync) training script"
fi

# ==================== Data Paths ====================
DATADIR=/path/to/your/train/data/filtered_questions.jsonl
VAL_DATADIR=/path/to/your/val/data/bird_dev.parquet

# ==================== Experiment Name & Save Path ====================
experiment_name=${alg}_${modelName}_data_v7_gamma${gamma}_${SCHEMA_SCORING_MODE}

# Append async tag if enabled
if [ "$USE_ASYNC" = "True" ] || [ "$USE_ASYNC" = "true" ] || [ "$USE_ASYNC" = "1" ]; then
    experiment_name=${experiment_name}_async
fi

# Append schema-related tags if enabled
if [ "$use_schema" = "True" ] || [ "$use_schema" = "true" ]; then
    experiment_name=${experiment_name}_schema_w${SCHEMA_WEIGHT}
    if [ "$use_segmented_propagation" = "true" ] || [ "$use_segmented_propagation" = "True" ]; then
        experiment_name=${experiment_name}_segmented
    fi
fi

experiment_name=${experiment_name}_18k_${ROLLOUT_MAX_RESPONSE_LEN}_batchsize${ROLLOUT_BATCH_SIZE}_nsamples_${N_SAMPLES_PER_PROMPT}
SAVE_DIR=/path/to/your/save/dir/${modelName}/${experiment_name}

# ==================== WandB Configuration ====================
WANDB_PROJECT="nl2sql-dev"
WANDB_GROUP="nl2sql"
WANDB_KEY="your_wandb_key"

# ==================== Actor Configuration ====================
ACTOR_NUM_NODES=${WORKER}
ACTOR_NUM_GPUS_PER_NODE=8

# ==================== Build Task Name ====================
if [ "$use_schema" = "True" ] || [ "$use_schema" = "true" ]; then
    TASK_NAME="${DESC}_${modelName}_gamma${gamma}_schema_${SCHEMA_SCORING_MODE}_${SCHEMA_WEIGHT}_segmented_${use_segmented_propagation}_P${PRIORITY}_${HOURS}hours_${TOT_GPU_NUM}gcores80g"
else
    TASK_NAME="${DESC}_${modelName}_gamma${gamma}_P${PRIORITY}_${HOURS}hours_${TOT_GPU_NUM}gcores80g"
fi

if [ "$USE_ASYNC" = "True" ] || [ "$USE_ASYNC" = "true" ] || [ "$USE_ASYNC" = "1" ]; then
    TASK_NAME="${TASK_NAME}_async"
fi
TASK_NAME="${alg}_${TASK_NAME}"

# ==================== Build Script Arguments ====================
SCRIPT_PATH="bash ${TRAIN_SCRIPT_PATH} \
--alg ${alg} \
--use_schema ${use_schema} \
--use_segmented_propagation ${use_segmented_propagation} \
--schema_scoring_mode ${SCHEMA_SCORING_MODE} \
--schema_weight ${SCHEMA_WEIGHT} \
--gamma ${gamma} \
--reward_func ${REWARD_FUNC} \
--num_episodes ${NUM_EPISODES} \
--lr_actor ${LR_ACTOR} \
--n_samples_per_prompt ${N_SAMPLES_PER_PROMPT} \
--rollout_batch_size ${ROLLOUT_BATCH_SIZE} \
--num_rollout ${NUM_ROLLOUT} \
--max_tokens_per_gpu ${MAX_TOKENS_PER_GPU} \
--rollout_max_response_len ${ROLLOUT_MAX_RESPONSE_LEN} \
--rollout_temperature ${ROLLOUT_TEMPERATURE} \
--kl_loss_coef ${KL_LOSS_COEF} \
--entropy_coef ${ENTROPY_COEF} \
--eps_clip ${EPS_CLIP} \
--eps_clip_high ${EPS_CLIP_HIGH} \
--optimizer ${OPTIMIZER} \
--weight_decay ${WEIGHT_DECAY} \
--adam_beta1 ${ADAM_BETA1} \
--adam_beta2 ${ADAM_BETA2} \
--rollout_num_gpus_per_engine ${ROLLOUT_NUM_GPUS_PER_ENGINE} \
--sglang_mem_fraction ${SGLANG_MEM_FRACTION} \
--tensor_model_parallel_size ${TENSOR_MODEL_PARALLEL_SIZE} \
--pipeline_model_parallel_size ${PIPELINE_MODEL_PARALLEL_SIZE} \
--hf_checkpoint ${HF_CHECKPOINT}"

# Append ref_load only if non-empty
if [ -n "${REF_LOAD}" ]; then
    SCRIPT_PATH="${SCRIPT_PATH} --ref_load ${REF_LOAD}"
fi

SCRIPT_PATH="${SCRIPT_PATH} \
--save_dir ${SAVE_DIR} \
--save_interval ${SAVE_INTERVAL} \
--data ${DATADIR} \
--val_data ${VAL_DATADIR} \
--experiment_name ${experiment_name} \
--wandb_project ${WANDB_PROJECT} \
--wandb_group ${WANDB_GROUP} \
--wandb_key ${WANDB_KEY} \
--actor_num_nodes ${ACTOR_NUM_NODES} \
--actor_num_gpus_per_node ${ACTOR_NUM_GPUS_PER_NODE} \
--rollout_num_gpus ${ROLLOUT_NUM_GPUS}"

# ==================== Print Configuration Summary ====================
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📋 Training Configuration Summary"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Algorithm:              ${alg}"
echo "  Model:                  ${modelName}"
echo "  HF Checkpoint:          ${HF_CHECKPOINT}"
echo "  Schema Mode:            ${use_schema}"
echo "  Segmented Propagation:  ${use_segmented_propagation}"
echo "  Workers:                ${WORKER} x ${GPU_NUM} GPUs = ${TOT_GPU_NUM} GPUs"
echo "  Experiment:             ${experiment_name}"
echo "  Save Dir:               ${SAVE_DIR}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ==================== Warning Check ====================
if [ "$alg" = "rpp" ] && [ "$use_schema" = "True" ] && [ "$SCHEMA_SCORING_MODE" = "truematch" ] && [ "$use_segmented_propagation" != "True" ]; then
    echo ""
    echo "⚠️  WARNING: REINFORCE++ with Schema but without Segmented Propagation"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  You are using:"
    echo "    • Algorithm: REINFORCE++ (rpp)"
    echo "    • Schema Mode: Enabled"
    echo "    • Segmented Propagation: Disabled"
    echo ""
    echo "  This means:"
    echo "    • SQL rewards will propagate to Schema tokens (global propagation)"
    echo "    • Schema and SQL will NOT be independently normalized"
    echo ""
    echo "  Recommended:"
    echo "    • Set use_segmented_propagation=True for better Schema learning"
    echo "    • Or use alg=grpo for group-based comparison"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    read -p "  Continue anyway? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "❌ Aborted by user"
        exit 1
    fi
fi