#!/bin/bash
set -ex

# ==================== Stage 1: Argument Parsing ====================
ALG="grpo"
USE_SCHEMA=false
use_segmented_propagation=false
gamma=1
HF_CHECKPOINT=""
REF_LOAD=""
SCHEMA_WEIGHT=0.5
REWARD_FUNC="generate_sql_token"

while [[ $# -gt 0 ]]; do
    case $1 in
        --alg)                          ALG="$2";                          shift 2 ;;
        --use_schema)                   USE_SCHEMA="$2";                   shift 2 ;;
        --use_segmented_propagation)    use_segmented_propagation="$2";    shift 2 ;;
        --schema_scoring_mode)          SCHEMA_SCORING_MODE="$2";          shift 2 ;;
        --schema_weight)                SCHEMA_WEIGHT="$2";                shift 2 ;;
        --gamma)                        gamma="$2";                        shift 2 ;;
        --reward_func)                  REWARD_FUNC="$2";                  shift 2 ;;
        --hf_checkpoint)                HF_CHECKPOINT="$2";                shift 2 ;;
        --ref_load)                     REF_LOAD="$2";                     shift 2 ;;
        --lr_actor)                     LR_ACTOR="$2";                     shift 2 ;;
        --num_episodes)                 NUM_EPISODES="$2";                 shift 2 ;;
        --n_samples_per_prompt)         N_SAMPLES_PER_PROMPT="$2";         shift 2 ;;
        --rollout_batch_size)           ROLLOUT_BATCH_SIZE="$2";           shift 2 ;;
        --num_rollout)                  NUM_ROLLOUT="$2";                  shift 2 ;;
        --max_tokens_per_gpu)           MAX_TOKENS_PER_GPU="$2";           shift 2 ;;
        --rollout_max_response_len)     ROLLOUT_MAX_RESPONSE_LEN="$2";     shift 2 ;;
        --rollout_temperature)          ROLLOUT_TEMPERATURE="$2";          shift 2 ;;
        --kl_loss_coef)                 KL_LOSS_COEF="$2";                 shift 2 ;;
        --entropy_coef)                 ENTROPY_COEF="$2";                 shift 2 ;;
        --eps_clip)                     EPS_CLIP="$2";                     shift 2 ;;
        --eps_clip_high)                EPS_CLIP_HIGH="$2";                shift 2 ;;
        --optimizer)                    OPTIMIZER="$2";                    shift 2 ;;
        --weight_decay)                 WEIGHT_DECAY="$2";                 shift 2 ;;
        --adam_beta1)                   ADAM_BETA1="$2";                   shift 2 ;;
        --adam_beta2)                   ADAM_BETA2="$2";                   shift 2 ;;
        --rollout_num_gpus_per_engine)  ROLLOUT_NUM_GPUS_PER_ENGINE="$2";  shift 2 ;;
        --sglang_mem_fraction)          SGLANG_MEM_FRACTION="$2";          shift 2 ;;
        --tensor_model_parallel_size)   TENSOR_MODEL_PARALLEL_SIZE="$2";   shift 2 ;;
        --pipeline_model_parallel_size) PIPELINE_MODEL_PARALLEL_SIZE="$2"; shift 2 ;;
        --save_dir)                     SAVE_DIR="$2";                     shift 2 ;;
        --save_interval)                SAVE_INTERVAL="$2";                shift 2 ;;
        --data)                         DATADIR="$2";                      shift 2 ;;
        --val_data)                     VAL_DATADIR="$2";                  shift 2 ;;
        --experiment_name)              EXPERIMENT_NAME="$2";              shift 2 ;;
        --wandb_project)                WANDB_PROJECT="$2";                shift 2 ;;
        --wandb_group)                  WANDB_GROUP="$2";                  shift 2 ;;
        --wandb_key)                    WANDB_KEY="$2";                    shift 2 ;;
        --actor_num_nodes)              ACTOR_NUM_NODES="$2";              shift 2 ;;
        --actor_num_gpus_per_node)      ACTOR_NUM_GPUS_PER_NODE="$2";      shift 2 ;;
        --rollout_num_gpus)             ROLLOUT_NUM_GPUS="$2";             shift 2 ;;
        *) shift ;;
    esac
done

# ==================== Stage 2: Auto-detect Model Size & Family ====================
cd /path/to/your/workdir
export PYTHONPATH=$PYTHONPATH:/path/to/Megatron-LM
export PYTHONPATH=/path/to/sglang/python:$PYTHONPATH

extract_model_size() {
    local hf_path="$1"
    local path_lower=$(echo "${hf_path}" | tr '[:upper:]' '[:lower:]')

    local -a size_patterns=(
        "0.5b:0.5B" "1b:1B" "1.5b:1.5B" "3b:3B"  "4b:4B"
        "7b:7B"     "8b:8B" "14b:14B"   "32b:32B"
        "70b:70B"   "72b:72B"
    )

    for pattern_pair in "${size_patterns[@]}"; do
        local pattern="${pattern_pair%%:*}"
        local size="${pattern_pair##*:}"

        if [[ "${path_lower}" =~ (qwen|llama|mistral|deepseek|yi)[-_]${pattern} ]] || \
           [[ "${hf_path}"    =~ (Qwen|Llama|Mistral|DeepSeek|Yi)[-_]${size} ]]   || \
           [[ "${path_lower}" =~ (^|[/_-])${pattern}([/_-]|$) ]]; then
            echo "${size}"
            return 0
        fi
    done
    return 1
}

extract_model_family() {
    local hf_path="$1"
    local path_lower=$(echo "${hf_path}" | tr '[:upper:]' '[:lower:]')

    # Match longest patterns first to avoid qwen2.5 being truncated to qwen2
    local -a family_patterns=(
        "qwen2.5:qwen2.5"
        "qwen2:qwen2"
        "qwen3:qwen3"
        "qwen:qwen"
        "llama-3:llama3"
        "llama-2:llama2"
        "llama:llama"
        "mistral:mistral"
        "deepseek:deepseek"
        "yi:yi"
    )

    for pair in "${family_patterns[@]}"; do
        local pat="${pair%%:*}"
        local name="${pair##*:}"
        if [[ "${path_lower}" == *"${pat}"* ]]; then
            echo "${name}"
            return 0
        fi
    done

    # Fallback: use first segment of the last path component
    local fallback
    fallback=$(basename "${hf_path%/}" | cut -d'-' -f1 | tr '[:upper:]' '[:lower:]')
    echo "${fallback}"
    return 0
}

if [ -z "${HF_CHECKPOINT}" ]; then
    echo "❌ Error: HF_CHECKPOINT not provided"
    exit 1
fi

MODEL_SIZE=$(extract_model_size "${HF_CHECKPOINT}")
if [ -z "${MODEL_SIZE}" ]; then
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "❌ Error: Cannot auto-detect model size from HF_CHECKPOINT"
    echo "   HF_CHECKPOINT: ${HF_CHECKPOINT}"
    echo "   Supported sizes: 0.5B 1B 1.5B 3B 4B 7B 8B 14B 32B 70B 72B"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    exit 1
fi

MODEL_FAMILY=$(extract_model_family "${HF_CHECKPOINT}")

echo "✓ Auto-detected MODEL_SIZE:   ${MODEL_SIZE}"
echo "✓ Auto-detected MODEL_FAMILY: ${MODEL_FAMILY}"
echo "  From: ${HF_CHECKPOINT}"

# ==================== Stage 3: Load Model Config ====================
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"

load_model_config() {
    local model_family="$1"
    local model_size="$2"
    local models_dir="${SCRIPT_DIR}/../../scripts/models"

    local specific_config="${models_dir}/${model_family}-${model_size}.sh"
    local family_generic="${models_dir}/${model_family}-generic.sh"
    local global_generic="${models_dir}/generic.sh"

    if [ -f "${specific_config}" ]; then
        echo "✓ Loading model config: ${specific_config}"
        source "${specific_config}"
        return 0
    fi

    if [ -f "${family_generic}" ]; then
        echo "⚠ Specific config not found, using family generic: ${family_generic}"
        source "${family_generic}"
        return 0
    fi

    if [ -f "${global_generic}" ]; then
        echo "⚠ Using global generic config: ${global_generic}"
        source "${global_generic}"
        return 0
    fi

    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "❌ Error: Model configuration not found"
    echo "   Model Family : ${model_family}"
    echo "   Model Size   : ${model_size}"
    echo "   Searched (in order):"
    echo "     1. ${specific_config}"
    echo "     2. ${family_generic}"
    echo "     3. ${global_generic}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    return 1
}

if ! load_model_config "${MODEL_FAMILY}" "${MODEL_SIZE}"; then
    exit 1
fi

# ==================== Stage 4: Model Conversion ====================
find_or_convert_model() {
    local hf_path="$1"
    local model_base_dir="/path/to/your/model/dir"

    echo "HF_CHECKPOINT: ${hf_path}" >&2

    if [[ "${hf_path}" == *"huggingface.co"* ]]; then
        MODEL_NAME=$(echo "${hf_path}" | grep -oP 'huggingface\.co/[^/]+/\K[^/]+' | head -1)
        [ -z "${MODEL_NAME}" ] && MODEL_NAME=$(basename "${hf_path%/}")
        TORCH_DIST_MODEL_PATH="${model_base_dir}/${MODEL_NAME}_torch_dist"

    elif [[ "${hf_path}" == *"iter_"* ]] || [[ "${hf_path}" == *"huggingface_format"* ]]; then
        if [[ "${hf_path}" =~ (qwen[^/]*) ]]; then
            MODEL_IDENTIFIER="${BASH_REMATCH[1]}"
        else
            MODEL_IDENTIFIER=$(echo "${hf_path}" | awk -F'/' '{print $(NF-2)}')
        fi
        ITER_NUM=$(echo "${hf_path}" | grep -oP 'iter_\K[0-9]+' || echo "unknown")
        TORCH_DIST_MODEL_PATH="${model_base_dir}/${MODEL_IDENTIFIER}_iter_${ITER_NUM}_torch_dist"

    else
        MODEL_NAME=$(basename "${hf_path%/}")
        TORCH_DIST_MODEL_PATH="${model_base_dir}/${MODEL_NAME}_torch_dist"
    fi

    echo "Determined torch_dist path: ${TORCH_DIST_MODEL_PATH}" >&2

    if [ -d "${TORCH_DIST_MODEL_PATH}" ]; then
        echo "Found existing converted model at: ${TORCH_DIST_MODEL_PATH}" >&2
        echo "${TORCH_DIST_MODEL_PATH}"
        return 0
    fi

    echo "Starting conversion from: ${hf_path}" >&2

    # Temporarily reset distributed env vars for single-GPU conversion
    local SAVED_WORLD_SIZE=$WORLD_SIZE
    local SAVED_RANK=$RANK
    local SAVED_LOCAL_RANK=$LOCAL_RANK
    export WORLD_SIZE=1 RANK=0 LOCAL_RANK=0

    CUDA_VISIBLE_DEVICES=0 python tools/convert_hf_to_torch_dist.py \
        ${MODEL_ARGS[@]} \
        --hf-checkpoint "${hf_path}" \
        --save "${TORCH_DIST_MODEL_PATH}" 1>&2

    local conversion_status=$?
    export WORLD_SIZE=$SAVED_WORLD_SIZE RANK=$SAVED_RANK LOCAL_RANK=$SAVED_LOCAL_RANK

    if [ $conversion_status -eq 0 ] && [ -d "${TORCH_DIST_MODEL_PATH}" ]; then
        echo "Model conversion successful!" >&2
        echo "${TORCH_DIST_MODEL_PATH}"
        return 0
    else
        echo "ERROR: Model conversion failed!" >&2
        return 1
    fi
}

if [ -z "${REF_LOAD}" ]; then
    echo "REF_LOAD not provided, attempting to find or convert model..."
    REF_LOAD=$(find_or_convert_model "${HF_CHECKPOINT}")
    local_exit_code=$?

    if [ $local_exit_code -ne 0 ] || [ -z "${REF_LOAD}" ] || [ ! -d "${REF_LOAD}" ]; then
        echo "ERROR: Failed to find or convert model (REF_LOAD=${REF_LOAD})"
        exit 1
    fi
else
    echo "Using provided REF_LOAD: ${REF_LOAD}"
fi

echo "Final REF_LOAD: ${REF_LOAD}"

# ==================== Stage 5: Load Distributed Environment ====================
echo "Loading distributed training environment..."
cd /path/to/your/workdir

source /path/to/your/utils/export_env_slime.sh

export WANDB_MODE=offline
export PYTHONPATH=/path/to/your/examples/nl2sql:$PYTHONPATH
export CUDA_DEVICE_MAX_CONNECTIONS=1
export PYTHONBUFFERED=16

python3 /path/to/your/utils/low_gpu_utilization.py --gpu_number $GPUS_PER_NODE &
echo "low_gpu_utilization.py started"

# ==================== Stage 6: Build Argument Arrays ====================
CKPT_ARGS=(
    --hf-checkpoint  ${HF_CHECKPOINT}
    --ref-load       ${REF_LOAD}
    --load           ${SAVE_DIR}
    --save           ${SAVE_DIR}
    --save-interval  ${SAVE_INTERVAL}
)

GLOBAL_BATCH_SIZE=$((N_SAMPLES_PER_PROMPT * ROLLOUT_BATCH_SIZE))

ROLLOUT_ARGS=(
    --prompt-data               ${DATADIR}
    --input-key                 prompt
    --label-key                 reward_model
    --tool-key                  tools
    --apply-chat-template
    --rollout-shuffle
    --num-rollout               ${NUM_ROLLOUT}
    --rollout-batch-size        ${ROLLOUT_BATCH_SIZE}
    --n-samples-per-prompt      ${N_SAMPLES_PER_PROMPT}
    --rollout-max-response-len  ${ROLLOUT_MAX_RESPONSE_LEN}
    --rollout-temperature       ${ROLLOUT_TEMPERATURE}
    --balance-data
    --global-batch-size         ${GLOBAL_BATCH_SIZE}
)

if [ "$USE_SCHEMA" = "True" ] || [ "$USE_SCHEMA" = "true" ] || [ "$USE_SCHEMA" = "1" ]; then
    ROLLOUT_ARGS+=(
        --enable_schema
        --schema_scoring_mode        ${SCHEMA_SCORING_MODE}
        --use_weighted_schema_policy_loss
        --answer_policy_loss_weight  1.0
        --schema_policy_loss_weight  ${SCHEMA_WEIGHT}
    )
    echo "✓ Schema mode enabled (scoring: ${SCHEMA_SCORING_MODE}, weight: ${SCHEMA_WEIGHT})"

    if [ "$use_segmented_propagation" = "True" ] || [ "$use_segmented_propagation" = "true" ] || [ "$use_segmented_propagation" = "1" ]; then
        ROLLOUT_ARGS+=(--use_segmented_propagation)
        echo "✓ Segmented advantage normalization enabled"
    fi
fi

EVAL_ARGS=(
    --eval-interval             20
    --eval-prompt-data          ${VAL_DATADIR}
    --n-samples-per-eval-prompt 1
    --eval-max-response-len     1024
    --eval-top-p                0.7
)

PERF_ARGS=(
    --tensor-model-parallel-size   ${TENSOR_MODEL_PARALLEL_SIZE}
    --sequence-parallel
    --pipeline-model-parallel-size ${PIPELINE_MODEL_PARALLEL_SIZE}
    --context-parallel-size        1
    --expert-model-parallel-size   1
    --expert-tensor-parallel-size  1
    --use-dynamic-batch-size
    --max-tokens-per-gpu           ${MAX_TOKENS_PER_GPU}
    --micro-batch-size             1
)

# Algorithm selection (supported: grpo, gspo, ppo)
case "$ALG" in
    grpo)
        ADVANTAGE_ESTIMATOR="grpo"
        USE_NORMALIZE_ADVANTAGES=false
        echo "✓ Using GRPO algorithm (group-wise advantage, no normalization)"
        ;;
    gspo)
        ADVANTAGE_ESTIMATOR="gspo"
        USE_NORMALIZE_ADVANTAGES=false
        echo "✓ Using GSPO algorithm (group-wise advantage, no normalization)"
        ;;
    ppo)
        ADVANTAGE_ESTIMATOR="ppo"
        USE_NORMALIZE_ADVANTAGES=true
        echo "✓ Using PPO algorithm (advantage normalization enabled)"
        ;;
    *)
        echo "❌ Error: Unknown algorithm '${ALG}'. Supported: grpo, gspo, ppo"
        exit 1
        ;;
esac

GRPO_ARGS=(
    --advantage-estimator  ${ADVANTAGE_ESTIMATOR}
    --gamma                ${gamma}
    --use-kl-loss
    --kl-loss-coef         ${KL_LOSS_COEF}
    --kl-loss-type         low_var_kl
    --entropy-coef         ${ENTROPY_COEF}
    --eps-clip             ${EPS_CLIP}
    --eps-clip-high        ${EPS_CLIP_HIGH}
)

if [ "$USE_NORMALIZE_ADVANTAGES" = "true" ]; then
    GRPO_ARGS+=(--normalize-advantages)
fi

OPTIMIZER_ARGS=(
    --optimizer      ${OPTIMIZER}
    --lr             ${LR_ACTOR}
    --lr-decay-style constant
    --weight-decay   ${WEIGHT_DECAY}
    --adam-beta1     ${ADAM_BETA1}
    --adam-beta2     ${ADAM_BETA2}
)

WANDB_ARGS=(
    --use-wandb
    --wandb-project  ${WANDB_PROJECT}
    --wandb-group    ${WANDB_GROUP}
    --wandb-key      ${WANDB_KEY}
    --wandb-dir      ${SAVE_DIR}
)

SGLANG_ARGS=(
    --use-slime-router
    --rollout-num-gpus-per-engine  ${ROLLOUT_NUM_GPUS_PER_ENGINE}
    --sglang-mem-fraction-static   ${SGLANG_MEM_FRACTION}
    --sglang-router-ip             ${MASTER_ADDR}
    --sglang-tensor-parallel-size  2
)

MISC_ARGS=(
    --attention-dropout              0.0
    --hidden-dropout                 0.0
    --accumulate-allreduce-grads-in-fp32
    --attention-softmax-in-fp32
    --attention-backend              flash
)

CUSTOM_ARGS=(
    --custom-generate-function-path  "${REWARD_FUNC}.generate"
    --custom-rm-path                 "${REWARD_FUNC}.reward_func"
)

# ==================== Stage 7: Launch Ray & Submit Job ====================
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🚀 Starting Training"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Algorithm:             ${ALG}"
echo "  Model Size:            ${MODEL_SIZE}"
echo "  Model Family:          ${MODEL_FAMILY}"
echo "  Schema Mode:           ${USE_SCHEMA}"
if [ "$USE_SCHEMA" = "True" ] || [ "$USE_SCHEMA" = "true" ]; then
    echo "  Schema Scoring Mode:   ${SCHEMA_SCORING_MODE}"
    echo "  Schema Weight:         ${SCHEMA_WEIGHT}"
fi
echo "  Segmented Propagation: ${use_segmented_propagation}"
echo "  Nodes:                 ${ACTOR_NUM_NODES}"
echo "  GPUs per Node:         ${GPUS_PER_NODE}"
echo "  NVIDIA Driver:         $(nvidia-smi --query-gpu=driver_version --format=csv,noheader | head -1)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

export POD_IP=$(hostname -i)
export NO_PROXY="localhost,127.0.0.1,0.0.0.0,${POD_IP},${MASTER_ADDR},.cluster.local"
export no_proxy=$NO_PROXY

if [ "$NODE_RANK" -eq 0 ]; then
    echo "HEAD NODE: Starting Ray..."
    ray start --head \
        --node-ip-address  $MASTER_ADDR \
        --port=6379 \
        --dashboard-host=0.0.0.0 \
        --num-gpus         $GPUS_PER_NODE \
        --disable-usage-stats \
        --block &

    CUR_DIR=$(pwd)
    echo "Working directory: $CUR_DIR"

    echo "Waiting for Ray Dashboard to start..."
    sleep 30

    if ! curl -s http://${MASTER_ADDR}:8265 > /dev/null; then
        echo "Ray Dashboard not ready, waiting 10 more seconds..."
        sleep 10
    fi

    echo "Submitting Ray job..."
    http_proxy="" https_proxy="" HTTP_PROXY="" HTTPS_PROXY="" \
    ray job submit --address="http://${MASTER_ADDR}:8265" \
        --runtime-env-json="{
            \"working_dir\": \"$CUR_DIR\",
            \"env_vars\": {
                \"PATH\": \"$PATH\",
                \"PYTHONPATH\": \"$PYTHONPATH\",
                \"CUDA_DEVICE_MAX_CONNECTIONS\": \"1\",
                \"PYTHONBUFFERED\": \"16\",
                \"WANDB_MODE\": \"offline\"
            },
            \"excludes\": [
                \"data/*\",
                \"results/*\"
            ]}" \
        -- python3 train_async.py \
        --actor-num-nodes         1 \
        --actor-num-gpus-per-node 8 \
        --rollout-num-gpus        8 \
        --partial-rollout \
        ${MODEL_ARGS[@]} \
        ${CKPT_ARGS[@]} \
        ${ROLLOUT_ARGS[@]} \
        ${OPTIMIZER_ARGS[@]} \
        ${GRPO_ARGS[@]} \
        ${DISTRIBUTED_ARGS[@]} \
        ${WANDB_ARGS[@]} \
        ${PERF_ARGS[@]} \
        ${SGLANG_ARGS[@]} \
        ${MISC_ARGS[@]} \
        ${CUSTOM_ARGS[@]}

    wait $RAY_PID

else
    echo "WORKER NODE: Joining Ray cluster..."
    ray start --block \
        --address=${MASTER_ADDR}:6379 \
        --num-gpus ${GPUS_PER_NODE}
fi