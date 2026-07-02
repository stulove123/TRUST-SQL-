from argparse import Namespace
from collections.abc import Callable, Iterator
from typing import Any, Dict, Tuple, Union

import torch
from megatron.core import mpu

from slime.utils.distributed_utils import distributed_masked_whiten
from slime.utils.misc import load_function
from slime.utils.ppo_utils import (
    calculate_log_probs_and_entropy,
    compute_approx_kl,
    compute_policy_loss,
    get_advantages_and_returns,
    get_grpo_returns,
    get_reinforce_plus_plus_baseline_advantages,
    get_reinforce_plus_plus_returns,
    get_reinforce_plus_plus_returns_with_token_rewards,
    get_reinforce_plus_plus_returns_segmented,
)
from slime.utils.types import RolloutBatch

from .cp_utils import all_gather_with_cp, get_logits_and_tokens_offset_with_cp, get_sum_of_sample_mean


# ==================== Response Utilities ====================
def get_responses(
    logits: torch.Tensor,
    *,
    args: Namespace,
    unconcat_tokens: list[torch.Tensor],
    total_lengths: list[int],
    response_lengths: list[int],
) -> Iterator[tuple[torch.Tensor, torch.Tensor]]:
    """Yield response-aligned (logits_chunk, tokens_chunk) pairs per sample."""
    assert logits.size(0) == 1, f"{logits.shape}"
    assert logits.dtype == torch.float32, f"{logits.dtype}"

    logits = logits.squeeze(0).div(args.rollout_temperature)
    cp_size = mpu.get_context_parallel_world_size()
    end = 0

    for tokens, total_length, response_length in zip(unconcat_tokens, total_lengths, response_lengths):
        if cp_size == 1:
            end += total_length
            start = end - response_length
            logits_chunk = logits[start - 1 : end - 1]
            tokens_chunk = tokens[-response_length:]
        else:
            chunk_size, chunks_offset, logits_offset, tokens_offset = get_logits_and_tokens_offset_with_cp(
                total_length, response_length
            )

            logits_0 = logits[end : end + chunk_size]
            logits_1 = logits[end + chunk_size : end + 2 * chunk_size]
            end += 2 * chunk_size

            logits_0 = logits_0[logits_offset[0][0] - chunks_offset[0][0] : logits_offset[0][1] - chunks_offset[0][0]]
            tokens_0 = tokens[tokens_offset[0][0] : tokens_offset[0][1]]

            logits_1 = logits_1[logits_offset[1][0] - chunks_offset[1][0] : logits_offset[1][1] - chunks_offset[1][0]]
            tokens_1 = tokens[tokens_offset[1][0] : tokens_offset[1][1]]

            assert logits_0.size(0) == tokens_0.size(0), f"{logits_0.size(0)} vs {tokens_0.size(0)}"
            assert logits_1.size(0) == tokens_1.size(0), f"{logits_1.size(0)} vs {tokens_1.size(0)}"

            logits_chunk = torch.cat([logits_0, logits_1], dim=0)
            tokens_chunk = torch.cat([tokens_0, tokens_1], dim=0)

        yield logits_chunk, tokens_chunk


def get_log_probs_and_entropy(
    logits: torch.Tensor,
    *,
    args: Namespace,
    unconcat_tokens: list[torch.Tensor],
    total_lengths: list[int],
    response_lengths: list[int],
    with_entropy: bool = False,
    non_loss_data: bool = True,
) -> dict[str, list[torch.Tensor]]:
    """Compute per-token log-probabilities (and optionally entropy) on responses."""
    assert non_loss_data
    log_probs_list = []
    entropy_list = []

    for logits_chunk, tokens_chunk in get_responses(
        logits,
        args=args,
        unconcat_tokens=unconcat_tokens,
        total_lengths=total_lengths,
        response_lengths=response_lengths,
    ):
        log_prob, entropy = calculate_log_probs_and_entropy(
            logits_chunk, tokens_chunk, mpu.get_tensor_model_parallel_group(), with_entropy=with_entropy
        )
        log_probs_list.append(log_prob.squeeze(-1))
        entropy_list.append(entropy)

    res = {"log_probs": log_probs_list}
    if with_entropy:
        res["entropy"] = entropy_list
    return res


def get_values(
    logits: torch.Tensor,
    *,
    args: Namespace,
    unconcat_tokens: list[torch.Tensor],
    total_lengths: list[int],
    response_lengths: list[int],
    non_loss_data: bool = True,
) -> dict[str, list[torch.Tensor]]:
    """Extract per-token value predictions over response tokens."""
    value_list = []
    for logits_chunk, _ in get_responses(
        logits,
        args=args,
        unconcat_tokens=unconcat_tokens,
        total_lengths=total_lengths,
        response_lengths=response_lengths,
    ):
        assert logits_chunk.size(-1) == 1, f"{logits_chunk.shape}"
        value_list.append(logits_chunk.squeeze(-1))
    return {"values": value_list}


# ==================== Schema Advantage Helpers ====================
def _extract_schema_and_answer_reward(
    reward: Union[list, torch.Tensor, float],
    schema_end: int,
    response_len: int,
) -> tuple[float, float, bool]:
    """
    Extract (schema_reward, answer_reward, is_aborted) from a reward entry.
    Aborted samples are identified by reward[-1] == -1.0.
    """
    if isinstance(reward, list):
        if not reward:
            return 0.0, 0.0, True
        answer_reward = reward[-1]
        is_aborted = answer_reward == -1.0
        answer_reward = 0.0 if is_aborted else float(answer_reward)
        schema_reward = float(reward[schema_end - 1]) if schema_end > 0 and schema_end - 1 < len(reward) else 0.0
        return schema_reward, answer_reward, is_aborted

    if isinstance(reward, torch.Tensor):
        if reward.numel() == 0:
            return 0.0, 0.0, True
        answer_reward = reward[-1].item()
        is_aborted = answer_reward == -1.0
        answer_reward = 0.0 if is_aborted else answer_reward
        schema_reward = reward[schema_end - 1].item() if schema_end > 0 and schema_end - 1 < reward.numel() else 0.0
        return float(schema_reward), float(answer_reward), is_aborted

    # Scalar reward
    answer_reward = float(reward)
    is_aborted = answer_reward == -1.0
    answer_reward = 0.0 if is_aborted else answer_reward
    schema_reward = answer_reward * (schema_end / response_len) if response_len > 0 and schema_end > 0 else 0.0
    return schema_reward, answer_reward, is_aborted


def _compute_group_advantages(
    group_rewards: torch.Tensor,
    group_valid_mask: torch.Tensor,
) -> torch.Tensor:
    """
    Compute GRPO advantages for a group, excluding aborted samples from statistics.
    Aborted samples receive advantage = 0.
    """
    valid_indices = torch.nonzero(group_valid_mask).squeeze(-1)
    if valid_indices.numel() <= 1:
        return torch.zeros_like(group_rewards)

    valid_rewards = group_rewards[valid_indices]
    mean = valid_rewards.mean()
    std  = valid_rewards.std(unbiased=False)

    adv = (group_rewards - mean) / (std + 1e-6)
    adv = torch.clamp(adv, -10.0, 10.0)
    return adv * group_valid_mask


# ==================== Advantage Computation Functions ====================
def compute_advantages_schema_reward_weighted(
    rewards: list[list[float]],
    kl: list[torch.Tensor],
    schema_end_positions: list[int],
    response_lengths: list[int],
    n_samples_per_prompt: int,
    schema_policy_loss_weight: float,
) -> list[torch.Tensor]:
    """
    Compute token-level advantages with schema reward weighting.

    Formula:
        advantages[:] = answer_adv
        advantages[:schema_end] += schema_reward * schema_policy_loss_weight * answer_adv

    Aborted samples (reward[-1] == -1.0) are excluded from group statistics
    and receive advantage = 0.
    """
    num_samples = len(rewards)
    num_prompts = num_samples // n_samples_per_prompt

    if num_samples % n_samples_per_prompt != 0:
        print(
            f"[SCHEMA REWARD WEIGHTED] WARNING: num_samples ({num_samples}) not divisible by "
            f"n_samples_per_prompt ({n_samples_per_prompt}); truncating.",
            flush=True,
        )
        num_samples = num_prompts * n_samples_per_prompt
        rewards              = rewards[:num_samples]
        kl                   = kl[:num_samples]
        schema_end_positions = schema_end_positions[:num_samples]
        response_lengths     = response_lengths[:num_samples]

    device = kl[0].device
    returns = []
    total_aborted_count = 0

    for prompt_idx in range(num_prompts):
        start_idx = prompt_idx * n_samples_per_prompt
        end_idx   = start_idx + n_samples_per_prompt

        answer_rewards_raw = []
        is_aborted_list    = []

        for i in range(n_samples_per_prompt):
            global_idx = start_idx + i
            _, answer_reward, is_aborted = _extract_schema_and_answer_reward(
                rewards[global_idx], schema_end_positions[global_idx], response_lengths[global_idx]
            )
            answer_rewards_raw.append(answer_reward)
            is_aborted_list.append(is_aborted)

        answer_rewards_t = torch.tensor(answer_rewards_raw, dtype=torch.float32, device=device)
        valid_mask       = torch.tensor([not a for a in is_aborted_list], dtype=torch.float32, device=device)
        total_aborted_count += sum(is_aborted_list)

        answer_adv = _compute_group_advantages(answer_rewards_t, valid_mask)

        for i in range(n_samples_per_prompt):
            global_idx   = start_idx + i
            response_len = response_lengths[global_idx]
            schema_end   = schema_end_positions[global_idx]

            ret = torch.ones(response_len, device=device) * answer_adv[i]

            if schema_end > 0 and valid_mask[i] > 0:
                reward = rewards[global_idx]
                if isinstance(reward, list):
                    schema_reward = float(reward[schema_end - 1]) if schema_end <= len(reward) else 0.0
                elif isinstance(reward, torch.Tensor):
                    schema_reward = reward[schema_end - 1].item() if schema_end <= reward.numel() else 0.0
                else:
                    schema_reward = float(reward) * (schema_end / response_len) if response_len > 0 else 0.0

                ret[:schema_end] += schema_reward * schema_policy_loss_weight * answer_adv[i]

            returns.append(ret + kl[global_idx])

    if total_aborted_count > 0:
        print(
            f"[SCHEMA REWARD WEIGHTED] Masked {int(total_aborted_count)} aborted samples (adv=0).",
            flush=True,
        )
    return returns


def get_grpo_returns_weighted_schema_answer(
    rewards: list[Union[list[float], torch.Tensor, float]],
    kl: list[torch.Tensor],
    schema_end_positions: list[int],
    response_lengths: list[int],
    n_samples_per_prompt: int,
    schema_advantage_weight: float = 1.0,
) -> list[torch.Tensor]:
    """
    Compute GRPO returns with separate schema and answer advantages combined as:
        ret[:] = answer_adv
        ret[:schema_end] += schema_advantage_weight * schema_adv

    Aborted samples (reward[-1] == -1.0) are excluded from group statistics.
    """
    num_samples = len(rewards)
    num_prompts = num_samples // n_samples_per_prompt

    if num_samples % n_samples_per_prompt != 0:
        print(
            f"[WEIGHTED GRPO] WARNING: num_samples ({num_samples}) not divisible by "
            f"n_samples_per_prompt ({n_samples_per_prompt}); truncating.",
            flush=True,
        )
        num_samples = num_prompts * n_samples_per_prompt
        rewards              = rewards[:num_samples]
        kl                   = kl[:num_samples]
        schema_end_positions = schema_end_positions[:num_samples]
        response_lengths     = response_lengths[:num_samples]

    device = kl[0].device
    returns = []
    total_aborted_count = 0

    for prompt_idx in range(num_prompts):
        start_idx = prompt_idx * n_samples_per_prompt
        end_idx   = start_idx + n_samples_per_prompt

        schema_rewards_raw, answer_rewards_raw, is_aborted_list = [], [], []

        for reward, schema_end, response_len in zip(
            rewards[start_idx:end_idx],
            schema_end_positions[start_idx:end_idx],
            response_lengths[start_idx:end_idx],
        ):
            s, a, aborted = _extract_schema_and_answer_reward(reward, schema_end, response_len)
            schema_rewards_raw.append(s)
            answer_rewards_raw.append(a)
            is_aborted_list.append(aborted)

        schema_rewards_t = torch.tensor(schema_rewards_raw, dtype=torch.float32, device=device)
        answer_rewards_t = torch.tensor(answer_rewards_raw, dtype=torch.float32, device=device)
        valid_mask       = torch.tensor([not a for a in is_aborted_list], dtype=torch.float32, device=device)
        total_aborted_count += sum(is_aborted_list)

        schema_adv = _compute_group_advantages(schema_rewards_t, valid_mask)
        answer_adv = _compute_group_advantages(answer_rewards_t, valid_mask)

        for i in range(n_samples_per_prompt):
            response_len = response_lengths[start_idx + i]
            schema_end   = schema_end_positions[start_idx + i]

            ret = torch.zeros(response_len, device=kl[start_idx + i].device)
            if response_len > 0:
                ret[:] = answer_adv[i]
                if schema_end > 0:
                    ret[:schema_end] += schema_advantage_weight * schema_adv[i]

            returns.append(ret + kl[start_idx + i])

    if total_aborted_count > 0:
        print(f"[WEIGHTED GRPO] Masked {int(total_aborted_count)} aborted samples.", flush=True)
    return returns


def get_grpo_returns_schema_answer_separate(
    rewards: list[Union[list[float], torch.Tensor, float]],
    kl: list[torch.Tensor],
    schema_end_positions: list[int],
    response_lengths: list[int],
    n_samples_per_prompt: int,
) -> tuple[list[torch.Tensor], list[torch.Tensor]]:
    """
    Compute GRPO returns separately for schema and answer rewards.
    Returns (schema_returns, answer_returns) for use with weighted policy loss.
    Aborted samples (reward[-1] == -1.0) are excluded from group statistics.
    """
    num_samples = len(rewards)
    num_prompts = num_samples // n_samples_per_prompt

    if num_samples % n_samples_per_prompt != 0:
        print(
            f"[SEPARATE GRPO] WARNING: num_samples ({num_samples}) not divisible by "
            f"n_samples_per_prompt ({n_samples_per_prompt}); truncating.",
            flush=True,
        )
        num_samples = num_prompts * n_samples_per_prompt
        rewards              = rewards[:num_samples]
        kl                   = kl[:num_samples]
        schema_end_positions = schema_end_positions[:num_samples]
        response_lengths     = response_lengths[:num_samples]

    device = kl[0].device
    schema_returns: list[torch.Tensor] = []
    answer_returns: list[torch.Tensor] = []
    total_aborted_count = 0

    for prompt_idx in range(num_prompts):
        start_idx = prompt_idx * n_samples_per_prompt

        schema_rewards_raw, answer_rewards_raw, is_aborted_list = [], [], []

        for reward, schema_end, response_len in zip(
            rewards[start_idx : start_idx + n_samples_per_prompt],
            schema_end_positions[start_idx : start_idx + n_samples_per_prompt],
            response_lengths[start_idx : start_idx + n_samples_per_prompt],
        ):
            s, a, aborted = _extract_schema_and_answer_reward(reward, schema_end, response_len)
            schema_rewards_raw.append(s)
            answer_rewards_raw.append(a)
            is_aborted_list.append(aborted)

        schema_rewards_t = torch.tensor(schema_rewards_raw, dtype=torch.float32, device=device)
        answer_rewards_t = torch.tensor(answer_rewards_raw, dtype=torch.float32, device=device)
        valid_mask       = torch.tensor([not a for a in is_aborted_list], dtype=torch.float32, device=device)
        total_aborted_count += sum(is_aborted_list)

        schema_adv = _compute_group_advantages(schema_rewards_t, valid_mask)
        answer_adv = _compute_group_advantages(answer_rewards_t, valid_mask)

        for i in range(n_samples_per_prompt):
            global_idx   = start_idx + i
            response_len = response_lengths[global_idx]
            schema_end   = min(schema_end_positions[global_idx], response_len)
            kl_i         = kl[global_idx]

            schema_ret = torch.zeros(response_len, device=kl_i.device)
            answer_ret = torch.zeros(response_len, device=kl_i.device)

            if response_len > 0:
                answer_ret[:] = answer_adv[i]
                if schema_end > 0:
                    schema_ret[:schema_end] = schema_adv[i]

            schema_returns.append(schema_ret + kl_i)
            answer_returns.append(answer_ret + kl_i)

    if total_aborted_count > 0:
        print(f"[SEPARATE GRPO] Masked {int(total_aborted_count)} aborted samples.", flush=True)
    return schema_returns, answer_returns


# ==================== Advantage Normalization ====================
def normalize_advantages_global(
    advantages: list[torch.Tensor],
    loss_masks: list[torch.Tensor],
    response_lengths: list[int],
    total_lengths: list[int],
    dp_group,
    cp_size: int,
) -> list[torch.Tensor]:
    """Global advantage whitening across all tokens."""
    all_advs = torch.cat(advantages)

    if cp_size == 1:
        all_masks = torch.cat(loss_masks)
    else:
        mask_chunks = []
        for i in range(len(advantages)):
            total_len    = total_lengths[i]
            response_len = response_lengths[i]
            prompt_len   = total_len - response_len

            _, _, _, token_offsets = get_logits_and_tokens_offset_with_cp(total_len, response_len)
            s0, e0 = token_offsets[0]
            s1, e1 = token_offsets[1]
            res_s0, res_e0 = max(0, s0 - prompt_len), max(0, e0 - prompt_len)
            res_s1, res_e1 = max(0, s1 - prompt_len), max(0, e1 - prompt_len)

            full_mask = loss_masks[i]
            parts = []
            if res_e0 > res_s0:
                parts.append(full_mask[res_s0:res_e0])
            if res_e1 > res_s1:
                parts.append(full_mask[res_s1:res_e1])

            mask_chunks.append(
                torch.cat(parts) if parts
                else torch.tensor([], device=all_advs.device, dtype=full_mask.dtype)
            )
        all_masks = torch.cat(mask_chunks)

    if all_masks.numel() > 0:
        assert all_advs.size() == all_masks.size(), (
            f"Shape mismatch: advantages {all_advs.size()}, masks {all_masks.size()}"
        )
        whitened = distributed_masked_whiten(all_advs, all_masks, process_group=dp_group, shift_mean=True)
        advantages = list(torch.split(whitened, [c.size(0) for c in advantages]))

    return advantages


def normalize_advantages_segmented(
    advantages: list[torch.Tensor],
    loss_masks: list[torch.Tensor],
    schema_end_positions: list[int],
    response_lengths: list[int],
    total_lengths: list[int],
    dp_group,
    cp_size: int,
) -> list[torch.Tensor]:
    """Independently whiten schema-segment and SQL-segment advantages."""
    if cp_size > 1:
        print("[WARNING] Context Parallel with segmented normalization is not fully tested.", flush=True)

    schema_advs, schema_masks, sql_advs, sql_masks = [], [], [], []

    for adv, loss_mask, schema_end in zip(advantages, loss_masks, schema_end_positions):
        schema_advs.append(adv[:schema_end])
        schema_masks.append(loss_mask[:schema_end])
        sql_advs.append(adv[schema_end:])
        sql_masks.append(loss_mask[schema_end:])

    all_schema_advs  = torch.cat(schema_advs)
    all_schema_masks = torch.cat(schema_masks)
    all_sql_advs     = torch.cat(sql_advs)
    all_sql_masks    = torch.cat(sql_masks)

    def _whiten_if_nonzero(flat_advs, flat_masks, chunks):
        if flat_masks.sum() > 0:
            whitened = distributed_masked_whiten(flat_advs, flat_masks, process_group=dp_group, shift_mean=True)
            return list(torch.split(whitened, [c.size(0) for c in chunks]))
        return chunks

    norm_schema_advs = _whiten_if_nonzero(all_schema_advs, all_schema_masks, schema_advs)
    norm_sql_advs    = _whiten_if_nonzero(all_sql_advs,    all_sql_masks,    sql_advs)

    return [torch.cat([s, q]) for s, q in zip(norm_schema_advs, norm_sql_advs)]


# ==================== Main Advantage Entry Point ====================
def compute_advantages_and_returns(args: Namespace, rollout_data: RolloutBatch) -> None:
    """Compute advantages and returns in-place based on args.advantage_estimator."""
    from megatron.core import mpu

    # Snapshot original fields before any modification
    if "original_response_lens" not in rollout_data:
        rollout_data["original_response_lens"] = rollout_data.get("response_lengths").copy()
    if "original_schema_ends" not in rollout_data:
        schema_end_positions = rollout_data.get("schema_end_positions")
        if schema_end_positions is not None:
            rollout_data["original_schema_ends"] = schema_end_positions.copy()

    log_probs:        list[torch.Tensor]               = rollout_data.get("log_probs")
    ref_log_probs:    list[torch.Tensor]               = rollout_data.get("ref_log_probs")
    rewards:          Union[list[float], list[list]]   = rollout_data.get("rewards")
    values:           Union[None, list[torch.Tensor]]  = rollout_data.get("values")
    response_lengths: list[int]                        = rollout_data.get("response_lengths")
    loss_masks:       list[torch.Tensor]               = rollout_data.get("loss_masks")
    total_lengths:    list[int]                        = rollout_data.get("total_lengths")

    if log_probs is None and values is None:
        return

    is_token_level = isinstance(rewards[0], list) if rewards else False

    if args.kl_coef == 0 or not log_probs:
        xs = log_probs if log_probs is not None else values
        kl = [torch.zeros_like(x, dtype=torch.float32, device=x.device) for x in xs]
    else:
        kl = [
            compute_approx_kl(log_probs[i], ref_log_probs[i], kl_loss_type=args.kl_loss_type)
            for i in range(len(log_probs))
        ]

    # ===== Token-level + REINFORCE++ =====
    if is_token_level and args.advantage_estimator == "reinforce_plus_plus":
        use_segmented = getattr(args, 'use_segmented_propagation', False)
        schema_end_positions = rollout_data.get("schema_end_positions") if use_segmented else None

        if use_segmented and schema_end_positions is None:
            print("[WARNING] schema_end_positions not found, falling back to global propagation.", flush=True)
            use_segmented = False

        if use_segmented:
            returns = get_reinforce_plus_plus_returns_segmented(
                token_rewards=rewards,
                schema_end_positions=schema_end_positions,
                kl=kl,
                loss_masks=loss_masks,
                response_lengths=response_lengths,
                total_lengths=total_lengths,
                kl_coef=args.kl_coef,
                gamma=args.gamma,
            )
        else:
            returns = get_reinforce_plus_plus_returns_with_token_rewards(
                token_rewards=rewards,
                kl=kl,
                loss_masks=loss_masks,
                response_lengths=response_lengths,
                total_lengths=total_lengths,
                kl_coef=args.kl_coef,
                gamma=args.gamma,
            )

        advantages = list(returns)

        if args.normalize_advantages:
            norm_fn = normalize_advantages_segmented if use_segmented else normalize_advantages_global
            norm_kwargs = dict(
                advantages=advantages,
                loss_masks=loss_masks,
                response_lengths=response_lengths,
                total_lengths=total_lengths,
                dp_group=mpu.get_data_parallel_group(),
                cp_size=mpu.get_context_parallel_world_size(),
            )
            if use_segmented:
                norm_kwargs["schema_end_positions"] = schema_end_positions
            advantages = norm_fn(**norm_kwargs)

        rollout_data["advantages"] = advantages
        rollout_data["returns"]    = returns
        return

    # ===== Token-level + GRPO/GSPO =====
    if is_token_level and args.advantage_estimator in ("grpo", "gspo"):
        schema_end_positions = rollout_data.get("schema_end_positions")
        use_segmented_grpo = (
            schema_end_positions is not None
            and len(schema_end_positions) == len(rewards)
            and getattr(args, 'n_samples_per_prompt', 1) > 1
        )

        use_weighted_policy_loss   = getattr(args, "use_weighted_schema_policy_loss", False)
        use_weighted_schema_adv    = getattr(args, "use_weighted_schema_advantage", False)

        if use_weighted_policy_loss and not use_segmented_grpo:
            raise ValueError(
                "use_weighted_schema_policy_loss requires token-level rewards with valid "
                "schema_end_positions and n_samples_per_prompt > 1."
            )

        if use_segmented_grpo:
            if use_weighted_policy_loss and use_weighted_schema_adv:
                raise ValueError(
                    "Both --use_weighted_schema_policy_loss and --use_weighted_schema_advantage "
                    "are enabled. Please enable only one."
                )

            if use_weighted_policy_loss:
                schema_returns, answer_returns = get_grpo_returns_schema_answer_separate(
                    rewards=rewards,
                    kl=kl,
                    schema_end_positions=schema_end_positions,
                    response_lengths=response_lengths,
                    n_samples_per_prompt=args.n_samples_per_prompt,
                )
                rollout_data["schema_advantages"] = schema_returns
                rollout_data["answer_advantages"] = answer_returns
                rollout_data["advantages"]        = answer_returns
                rollout_data["returns"]           = answer_returns
                return

            if use_weighted_schema_adv:
                returns = get_grpo_returns_weighted_schema_answer(
                    rewards=rewards,
                    kl=kl,
                    schema_end_positions=schema_end_positions,
                    response_lengths=response_lengths,
                    n_samples_per_prompt=args.n_samples_per_prompt,
                    schema_advantage_weight=getattr(args, "schema_advantage_weight", 1.0),
                )
                rollout_data["advantages"] = list(returns)
                rollout_data["returns"]    = returns
                return

            # Default: schema reward weighting
            returns = compute_advantages_schema_reward_weighted(
                rewards=rewards,
                kl=kl,
                schema_end_positions=schema_end_positions,
                response_lengths=response_lengths,
                n_samples_per_prompt=args.n_samples_per_prompt,
                schema_policy_loss_weight=getattr(args, "schema_policy_loss_weight", 1.0),
            )
            advantages = list(returns)

            if args.normalize_advantages:
                advantages = normalize_advantages_global(
                    advantages=advantages,
                    loss_masks=loss_masks,
                    response_lengths=response_lengths,
                    total_lengths=total_lengths,
                    dp_group=mpu.get_data_parallel_group(),
                    cp_size=mpu.get_context_parallel_world_size(),
                )

            rollout_data["advantages"] = advantages
            rollout_data["returns"]    = returns
            return

    # ===== Token-level + unsupported estimator =====
    if is_token_level:
        raise ValueError(
            f"Token-level rewards are not supported with '{args.advantage_estimator}' estimator.\n"
            f"Supported: reinforce_plus_plus, grpo (with schema_end_positions), gspo (with schema_end_positions)."
        )

    # ===== Sentence-level rewards =====
    if args.advantage_estimator in ("grpo", "gspo"):
        rewards_t = torch.tensor(rewards, dtype=torch.float32, device=kl[0].device)
        returns   = get_grpo_returns(rewards_t, kl)
        advantages = list(returns)

    elif args.advantage_estimator == "ppo":
        processed_rewards = []
        for reward, k in zip(rewards, kl):
            k = k * (-args.kl_coef)
            if mpu.get_context_parallel_rank() == 0:
                k[-1] += reward
            processed_rewards.append(k)
        advantages, returns = zip(*[
            get_advantages_and_returns(tl, rl, v, r, args.gamma, args.lambd)
            for tl, rl, v, r in zip(total_lengths, response_lengths, values, processed_rewards)
        ])
        advantages = list(advantages)
        returns    = list(returns)

    elif args.advantage_estimator == "reinforce_plus_plus":
        rewards_t = torch.tensor(rewards, dtype=torch.float32, device=kl[0].device)
        returns   = get_reinforce_plus_plus_returns(
            rewards=rewards_t,
            kl=kl,
            loss_masks=loss_masks,
            response_lengths=response_lengths,
            total_lengths=total_lengths,
            kl_coef=args.kl_coef,
            gamma=args.gamma,
        )
        advantages = list(returns)

    elif args.advantage_estimator == "reinforce_plus_plus_baseline":
        rewards_t  = torch.tensor(rewards, dtype=torch.float32, device=kl[0].device)
        advantages = get_reinforce_plus_plus_baseline_advantages(
            rewards=rewards_t, kl=kl, loss_masks=loss_masks, kl_coef=args.kl_coef
        )
        returns = advantages

    elif args.advantage_estimator == "on_policy_distillation":
        teacher_log_probs = [
            t.to(device=log_probs[0].device)[-rl:]
            for t, rl in zip(rollout_data.get("teacher_log_probs"), response_lengths)
        ]
        advantages = [t - s for t, s in zip(teacher_log_probs, log_probs)]
        returns    = advantages

    else:
        raise NotImplementedError(f"advantage_estimator '{args.advantage_estimator}' is not supported.")

    if args.normalize_advantages:
        advantages = normalize_advantages_global(
            advantages=advantages,
            loss_masks=loss_masks,
            response_lengths=response_lengths,
            total_lengths=total_lengths,
            dp_group=mpu.get_data_parallel_group(),
            cp_size=mpu.get_context_parallel_world_size(),
        )

    rollout_data["advantages"] = advantages
    rollout_data["returns"]    = returns


# ==================== Loss Functions ====================
def policy_loss_function(
    args: Namespace,
    batch: RolloutBatch,
    logits: torch.Tensor,
    sum_of_sample_mean: Callable[[torch.Tensor], torch.Tensor],
) -> tuple[torch.Tensor, dict[str, torch.Tensor]]:
    """
    Compute policy loss (PPO/GRPO/GSPO) and metrics.

    Args:
        args: Configuration controlling advantage estimator, clipping, entropy/KL coefficients.
        batch: Mini-batch with advantages, log_probs, tokens, lengths, masks, etc.
        logits: Policy logits [1, T, V].
        sum_of_sample_mean: Reduction function averaging per-sample values.

    Returns:
        (loss, metrics) where metrics contains detached scalars.
    """
    use_weighted_policy_loss = getattr(args, "use_weighted_schema_policy_loss", False)

    if use_weighted_policy_loss:
        if batch.get("schema_advantages") is None or batch.get("answer_advantages") is None:
            raise ValueError(
                "use_weighted_schema_policy_loss is enabled but schema_advantages/answer_advantages "
                "are missing from batch."
            )
        schema_advantages = torch.cat(batch["schema_advantages"], dim=0)
        answer_advantages = torch.cat(batch["answer_advantages"],  dim=0)
    else:
        advantages = torch.cat(batch["advantages"], dim=0)

    old_log_probs    = batch["rollout_log_probs"] if args.use_rollout_logprobs else batch["log_probs"]
    response_lengths = batch["response_lengths"]
    total_lengths    = batch["total_lengths"]
    loss_masks       = batch["loss_masks"]

    sum_of_sample_mean_answer = sum_of_sample_mean
    sum_of_sample_mean_schema = None
    schema_loss_masks         = None

    if use_weighted_policy_loss:
        schema_end_positions = batch.get("schema_end_positions")
        if schema_end_positions is None:
            raise ValueError("use_weighted_schema_policy_loss requires schema_end_positions in batch.")

        schema_loss_masks = []
        for loss_mask, schema_end in zip(loss_masks, schema_end_positions):
            schema_end  = max(0, min(schema_end, loss_mask.numel()))
            schema_mask = loss_mask.clone()
            if schema_end < schema_mask.numel():
                schema_mask[schema_end:] = 0
            schema_loss_masks.append(schema_mask)

        sum_of_sample_mean_schema = get_sum_of_sample_mean(
            total_lengths, response_lengths, schema_loss_masks, args.calculate_per_token_loss
        )

    log_probs_and_entropy = get_log_probs_and_entropy(
        logits,
        args=args,
        unconcat_tokens=batch["unconcat_tokens"],
        total_lengths=total_lengths,
        response_lengths=response_lengths,
        with_entropy=True,
    )
    log_probs = log_probs_and_entropy["log_probs"]

    if args.advantage_estimator == "gspo":
        full_log_probs = [
            all_gather_with_cp(lp, tl, rl)
            for lp, tl, rl in zip(log_probs, total_lengths, response_lengths)
        ]
        full_old_log_probs = [
            all_gather_with_cp(olp, tl, rl)
            for olp, tl, rl in zip(old_log_probs, total_lengths, response_lengths)
        ]

        def _compute_gspo_kl(full_lp, full_olp, masks):
            per_sample_kl = [
                ((olp - lp) * m).sum() / torch.clamp_min(m.sum(), 1)
                for lp, olp, m in zip(full_lp, full_olp, masks)
            ]
            return torch.cat([kl.expand_as(lp) for kl, lp in zip(per_sample_kl, log_probs)])

        if use_weighted_policy_loss:
            ppo_kl_answer = _compute_gspo_kl(full_log_probs, full_old_log_probs, loss_masks)
            ppo_kl_schema = _compute_gspo_kl(full_log_probs, full_old_log_probs, schema_loss_masks)
        else:
            ppo_kl = _compute_gspo_kl(full_log_probs, full_old_log_probs, loss_masks)

        old_log_probs = torch.cat(old_log_probs, dim=0)
        log_probs     = torch.cat(log_probs,     dim=0)
    else:
        old_log_probs = torch.cat(old_log_probs, dim=0)
        log_probs     = torch.cat(log_probs,     dim=0)
        ppo_kl = old_log_probs - log_probs
        if use_weighted_policy_loss:
            ppo_kl_answer = ppo_kl
            ppo_kl_schema = ppo_kl

    if use_weighted_policy_loss:
        pg_loss_schema, pg_clipfrac_schema = compute_policy_loss(
            ppo_kl_schema, schema_advantages, args.eps_clip, args.eps_clip_high
        )
        pg_loss_answer, pg_clipfrac_answer = compute_policy_loss(
            ppo_kl_answer, answer_advantages, args.eps_clip, args.eps_clip_high
        )
    else:
        pg_loss, pg_clipfrac = compute_policy_loss(ppo_kl, advantages, args.eps_clip, args.eps_clip_high)

    # Off-policy correction via importance sampling
    tis_metrics = {}
    if args.use_tis:
        def vanilla_tis_function(
            args,
            *,
            pg_loss: torch.Tensor,
            train_log_probs: list[torch.Tensor],
            rollout_log_probs: list[torch.Tensor],
            loss_masks: list[torch.Tensor],
            **kwargs: Any,
        ) -> Tuple[torch.Tensor, list[torch.Tensor], Dict[str, torch.Tensor]]:
            rollout_lp  = torch.cat(rollout_log_probs, dim=0)
            old_lp      = torch.cat(train_log_probs,   dim=0)
            tis         = torch.exp(old_lp - rollout_lp)
            tis_abs     = torch.exp((old_lp - rollout_lp).abs())
            tis_weights = torch.clamp(tis, min=args.tis_clip_low, max=args.tis_clip)
            tis_clipfrac = (tis_weights != tis).float()
            metrics = {
                "tis":         tis.clone().detach(),
                "tis_clipfrac": tis_clipfrac.clone().detach(),
                "tis_abs":     tis_abs.clone().detach(),
            }
            return pg_loss * tis_weights, loss_masks, metrics

        assert "rollout_log_probs" in batch, "rollout_log_probs must be provided for TIS"
        tis_func = (
            load_function(args.custom_tis_function_path)
            if args.custom_tis_function_path is not None
            else vanilla_tis_function
        )

        tis_base_kwargs = dict(
            args=args,
            train_log_probs=batch["log_probs"],
            rollout_log_probs=batch["rollout_log_probs"],
            total_lengths=total_lengths,
            response_lengths=response_lengths,
        )

        if use_weighted_policy_loss:
            ois = (-ppo_kl_answer).exp()
            pg_loss_answer, modified_answer_masks, tis_metrics = tis_func(
                pg_loss=pg_loss_answer, loss_masks=loss_masks, **tis_base_kwargs
            )
            sum_of_sample_mean_answer = get_sum_of_sample_mean(
                total_lengths, response_lengths, modified_answer_masks, args.calculate_per_token_loss
            )
            pg_loss_schema, modified_schema_masks, _ = tis_func(
                pg_loss=pg_loss_schema, loss_masks=schema_loss_masks, **tis_base_kwargs
            )
            sum_of_sample_mean_schema = get_sum_of_sample_mean(
                total_lengths, response_lengths, modified_schema_masks, args.calculate_per_token_loss
            )
        else:
            ois = (-ppo_kl).exp()
            pg_loss, modified_masks, tis_metrics = tis_func(
                pg_loss=pg_loss, loss_masks=loss_masks, **tis_base_kwargs
            )
            sum_of_sample_mean = get_sum_of_sample_mean(
                total_lengths, response_lengths, modified_masks, args.calculate_per_token_loss
            )

    # Reduce losses
    reducer = sum_of_sample_mean_answer if use_weighted_policy_loss else sum_of_sample_mean

    if use_weighted_policy_loss:
        assert sum_of_sample_mean_schema is not None
        schema_loss_weight = getattr(args, "schema_policy_loss_weight", 1.0)
        answer_loss_weight = getattr(args, "answer_policy_loss_weight", 1.0)

        pg_loss_schema   = sum_of_sample_mean_schema(pg_loss_schema)
        pg_loss_answer   = sum_of_sample_mean_answer(pg_loss_answer)
        pg_clipfrac_schema = sum_of_sample_mean_schema(pg_clipfrac_schema)
        pg_clipfrac_answer = sum_of_sample_mean_answer(pg_clipfrac_answer)
        ppo_kl_schema    = sum_of_sample_mean_schema(ppo_kl_schema)
        ppo_kl_answer    = sum_of_sample_mean_answer(ppo_kl_answer)

        pg_loss    = schema_loss_weight * pg_loss_schema + answer_loss_weight * pg_loss_answer
        pg_clipfrac = pg_clipfrac_answer
        ppo_kl     = ppo_kl_answer
    else:
        pg_loss    = sum_of_sample_mean(pg_loss)
        pg_clipfrac = sum_of_sample_mean(pg_clipfrac)
        ppo_kl     = sum_of_sample_mean(ppo_kl)

    entropy      = torch.cat(log_probs_and_entropy["entropy"], dim=0)
    entropy_loss = reducer(entropy)
    loss         = pg_loss - args.entropy_coef * entropy_loss

    if args.use_kl_loss:
        ref_log_probs = torch.cat(batch["ref_log_probs"], dim=0)
        kl_loss = reducer(compute_approx_kl(log_probs, ref_log_probs, kl_loss_type=args.kl_loss_type))
        loss = loss + args.kl_loss_coef * kl_loss

    if log_probs.numel() == 0:
        loss = loss + 0 * logits.sum()

    train_rollout_logprob_abs_diff = None
    if "rollout_log_probs" in batch:
        rollout_lp = torch.cat(batch["rollout_log_probs"], dim=0)
        train_rollout_logprob_abs_diff = reducer((old_log_probs - rollout_lp).abs())

    reported_loss = {
        "loss":         loss.clone().detach(),
        "pg_loss":      pg_loss.clone().detach(),
        "entropy_loss": entropy_loss.clone().detach(),
        "pg_clipfrac":  pg_clipfrac.clone().detach(),
        "ppo_kl":       ppo_kl.clone().detach(),
    }

    if use_weighted_policy_loss:
        reported_loss.update({
            "schema_pg_loss":              pg_loss_schema.clone().detach(),
            "answer_pg_loss":              pg_loss_answer.clone().detach(),
            "schema_pg_clipfrac":          pg_clipfrac_schema.clone().detach(),
            "answer_pg_clipfrac":          pg_clipfrac_answer.clone().detach(),
            "schema_ppo_kl":               ppo_kl_schema.clone().detach(),
            "answer_ppo_kl":               ppo_kl_answer.clone().detach(),
            "schema_policy_loss_weight":   torch.tensor(schema_loss_weight, device=loss.device, dtype=loss.dtype),
            "answer_policy_loss_weight":   torch.tensor(answer_loss_weight, device=loss.device, dtype=loss.dtype),
        })

    if train_rollout_logprob_abs_diff is not None:
        reported_loss["train_rollout_logprob_abs_diff"] = train_rollout_logprob_abs_diff.clone().detach()

    if args.use_kl_loss:
        reported_loss["kl_loss"] = kl_loss.clone().detach()

    if args.use_tis:
        reported_loss["ois"] = reducer(ois).clone().detach()
        for k, v in tis_metrics.items():
            reported_loss[k] = reducer(v)

    return loss, reported_loss


def value_loss_function(
    args: Namespace,
    batch: RolloutBatch,
    logits: torch.Tensor,
    sum_of_sample_mean: Callable[[torch.Tensor], torch.Tensor],
) -> tuple[torch.Tensor, dict[str, torch.Tensor]]:
    """Compute clipped value loss and metrics."""
    old_values = torch.cat(batch["values"], dim=0)
    values     = torch.cat([
        v.flatten() for v in get_values(
            logits,
            args=args,
            unconcat_tokens=batch["unconcat_tokens"],
            total_lengths=batch["total_lengths"],
            response_lengths=batch["response_lengths"],
        )["values"]
    ], dim=0)
    returns = torch.cat(batch["returns"], dim=0)

    values_clipped  = old_values + (values - old_values).clamp(-args.value_clip, args.value_clip)
    loss            = sum_of_sample_mean(torch.max((values_clipped - returns) ** 2, (values - returns) ** 2))
    values_clipfrac = sum_of_sample_mean((torch.abs(values - old_values) > args.value_clip).float())

    if values.numel() == 0:
        loss = loss + 0 * values.sum()

    return loss, {
        "value_loss":     loss.clone().detach(),
        "value_clipfrac": values_clipfrac.clone().detach(),
    }


def sft_loss_function(
    args: Namespace,
    batch: RolloutBatch,
    logits: torch.Tensor,
    sum_of_sample_mean: Callable[[torch.Tensor], torch.Tensor],
) -> tuple[torch.Tensor, dict[str, torch.Tensor]]:
    """Compute supervised fine-tuning loss over response tokens."""
    log_probs = torch.cat(
        get_log_probs_and_entropy(
            logits,
            args=args,
            unconcat_tokens=batch["unconcat_tokens"],
            total_lengths=batch["total_lengths"],
            response_lengths=batch["response_lengths"],
            with_entropy=False,
        )["log_probs"],
        dim=0,
    )
    loss = -sum_of_sample_mean(log_probs)

    if log_probs.numel() == 0:
        loss = loss + 0 * logits.sum()

    return loss, {"loss": loss.clone().detach()}


def loss_function(
    args: Namespace,
    batch: RolloutBatch,
    num_microbatches: int,
    logits: torch.Tensor,
) -> tuple[torch.Tensor, int | torch.Tensor, dict[str, list[str] | torch.Tensor]]:
    """Dispatch to the configured loss function and rescale for Megatron integration."""
    num_tokens  = sum(torch.clamp_min(m.sum(), 1) for m in batch["loss_masks"])
    num_samples = len(batch["response_lengths"])

    sum_of_sample_mean = get_sum_of_sample_mean(
        batch["total_lengths"],
        batch["response_lengths"],
        batch["loss_masks"],
        args.calculate_per_token_loss,
    )

    loss_fn_kwargs = dict(args=args, batch=batch, logits=logits, sum_of_sample_mean=sum_of_sample_mean)

    match args.loss_type:
        case "policy_loss":
            loss, log = policy_loss_function(**loss_fn_kwargs)
        case "value_loss":
            loss, log = value_loss_function(**loss_fn_kwargs)
        case "sft_loss":
            loss, log = sft_loss_function(**loss_fn_kwargs)
        case "custom_loss":
            loss, log = load_function(args.custom_loss_function_path)(**loss_fn_kwargs)
        case _:
            raise ValueError(f"Unknown loss type: {args.loss_type}")

    loss = (
        loss
        * num_microbatches
        / args.global_batch_size
        * mpu.get_data_parallel_world_size(with_context_parallel=True)
    )

    return (
        loss,
        num_tokens if args.calculate_per_token_loss else 1,
        {
            "keys":   list(log.keys()),
            "values": torch.tensor(
                [num_samples if not args.calculate_per_token_loss else num_tokens] + list(log.values()),
                device=logits.device,
            ),
        },
    )