# Adapt from https://github.com/OpenRLHF/OpenRLHF/blob/10c733694ed9fbb78a0a2ff6a05efc7401584d46/openrlhf/models/utils.py
# and https://github.com/OpenRLHF/OpenRLHF/blob/10c733694ed9fbb78a0a2ff6a05efc7401584d46/openrlhf/trainer/ppo_utils/experience_maker.py
from typing import List, Optional, Tuple, Union  # ✅ 添加 Union

import torch
import torch.distributed as dist

@torch.compile(dynamic=True)
def compute_approx_kl(
    log_probs: torch.Tensor,
    log_probs_base: torch.Tensor,
    kl_loss_type: str,
) -> torch.Tensor:
    """
    Compute the approximate KL divergence between two distributions.
    Schulman blog: http://joschu.net/blog/kl-approx.html

    Args:
        log_probs: Log probabilities of the new distribution.
        log_probs_base: Log probabilities of the base distribution.
        action_mask: Mask for actions.
    """

    log_ratio = log_probs.float() - log_probs_base.float()

    if kl_loss_type == "k1":
        return log_ratio
    elif kl_loss_type == "k2":
        log_ratio = log_probs.float() - log_probs_base.float()
        log_ratio = log_ratio**2 / 2.0
        return log_ratio
    elif kl_loss_type == "k3":
        # The non negative kl approximation in
        # http://joschu.net/blog/kl-approx.html
        # Besides non negative, it is also unbiased and have lower variance.
        log_ratio = -log_ratio
        log_ratio = log_ratio.exp() - 1 - log_ratio
        return log_ratio
    elif kl_loss_type == "low_var_kl":
        log_ratio = -log_ratio
        log_ratio = log_ratio.exp() - 1 - log_ratio
        return torch.clamp(log_ratio, min=-10, max=10)
    else:
        raise ValueError(f"Unknown kl_loss_type: {kl_loss_type}")


@torch.compile(dynamic=True)
def compute_policy_loss(
    ppo_kl: torch.Tensor,
    advantages: torch.Tensor,
    eps_clip: float,
    eps_clip_high: float,
    eps_clip_c: Optional[float] = None,
):
    ratio = (-ppo_kl).exp()
    pg_losses1 = -ratio * advantages
    pg_losses2 = -ratio.clamp(1 - eps_clip, 1 + eps_clip_high) * advantages
    clip_pg_losses1 = torch.maximum(pg_losses1, pg_losses2)
    clipfrac = torch.gt(pg_losses2, pg_losses1).float()

    if eps_clip_c is not None:
        assert (
            eps_clip_c > 1.0
        ), f"The lower bound of the clip_ratio_c for dual-clip PPO should be greater than 1.0, but get the value: {eps_clip_c}."
        pg_losses3 = -eps_clip_c * advantages
        clip_pg_losses2 = torch.min(pg_losses3, clip_pg_losses1)
        pg_losses = torch.where(advantages < 0, clip_pg_losses2, clip_pg_losses1)
    else:
        pg_losses = clip_pg_losses1

    return pg_losses, clipfrac


def compute_log_probs(logits: torch.Tensor, tokens: torch.Tensor, process_group: Optional[dist.ProcessGroup]):
    from megatron.core.fusions.fused_cross_entropy import fused_vocab_parallel_cross_entropy

    # convert to [seq_len, batch_size, vocab_size] as expected by fused_vocab_parallel_cross_entropy
    logits = logits.unsqueeze(1)
    tokens = tokens.unsqueeze(1)
    return -fused_vocab_parallel_cross_entropy(logits, tokens, process_group)


# from https://github.com/volcengine/verl/blob/0bdf7f469854815177e73dcfe9e420836c952e6e/verl/utils/megatron/tensor_parallel.py#L99
class _VocabParallelEntropy(torch.autograd.Function):

    @staticmethod
    def forward(ctx, vocab_parallel_logits: torch.Tensor, process_group: dist.ProcessGroup) -> torch.Tensor:

        @torch.compile(dynamic=True)
        def mul_reduce(a, b):
            return (a * b).sum(dim=-1, keepdim=True)

        logits_max = vocab_parallel_logits.max(dim=-1, keepdim=True).values
        dist.all_reduce(logits_max, op=dist.ReduceOp.MAX, group=process_group)
        normalized_vocab_parallel_logits = vocab_parallel_logits - logits_max
        normalized_exp_logits = normalized_vocab_parallel_logits.exp_()
        normalized_sum_exp_logits = normalized_exp_logits.sum(dim=-1, keepdim=True)
        dist.all_reduce(normalized_sum_exp_logits, group=process_group)
        softmax_logits = normalized_exp_logits.div_(normalized_sum_exp_logits)
        sum_softmax_times_logits = mul_reduce(softmax_logits, vocab_parallel_logits)
        dist.all_reduce(sum_softmax_times_logits, group=process_group)
        entropy = logits_max + normalized_sum_exp_logits.log() - sum_softmax_times_logits
        ctx.save_for_backward(vocab_parallel_logits, softmax_logits, sum_softmax_times_logits)
        return entropy.squeeze(dim=-1)

    @staticmethod
    def backward(ctx, grad_output: torch.Tensor) -> torch.Tensor:
        vocab_parallel_logits, softmax_logits, sum_softmax_times_logits = ctx.saved_tensors
        # reuse softmax_logits as grad
        vocab_parallel_logits.sub_(sum_softmax_times_logits)
        softmax_logits.mul_(vocab_parallel_logits)
        softmax_logits.mul_(grad_output.unsqueeze(dim=-1))
        # recover vocab_parallel_logits
        vocab_parallel_logits.add_(sum_softmax_times_logits)
        softmax_logits.mul_(-1)
        return softmax_logits, None


def compute_entropy_from_logits(logits: torch.Tensor, process_group) -> torch.Tensor:
    return _VocabParallelEntropy.apply(logits, process_group)


def get_grpo_returns(
    rewards: torch.Tensor,
    kl: list[torch.Tensor],
):
    returns = []
    for i in range(len(rewards)):
        returns.append(torch.ones_like(kl[i]) * rewards[i])
    return returns


def get_reinforce_plus_plus_returns(
    rewards: torch.Tensor,
    kl: List[torch.Tensor],
    loss_masks: List[torch.Tensor],
    response_lengths: List[int],
    total_lengths: List[int],
    kl_coef: float,
    gamma: float,
) -> List[torch.Tensor]:
    """
    Calculates discounted returns for REINFORCE++ (https://arxiv.org/pdf/2501.03262)

    Args:
        rewards (Tensor): A tensor of scalar rewards for each sequence.
        kl (List[Tensor]): List of per-token KL divergence tensors for sequence chunks.
        loss_masks (List[Tensor]): List of response-only loss masks for each full sequence.
        response_lengths (List[int]): The full length of each response sequence.
        total_lengths (List[int]): The full length of each sequence (prompt + response).
        kl_coef (float): Coefficient for the KL penalty.
        gamma (float): The discount factor.

    Returns:
        List[torch.Tensor]: A list of return (G_t) tensors for the
                            local sequence chunks owned by the current GPU rank.
    """
    from megatron.core import mpu

    cp_size = mpu.get_context_parallel_world_size()
    cp_rank = mpu.get_context_parallel_rank()

    final_returns_chunks = []
    for i in range(len(rewards)):
        local_kl_chunk = kl[i]
        total_len, response_len = total_lengths[i], response_lengths[i]

        if cp_size > 1:
            # Step 1,2:Gather all chunks and token_offsets from all ranks and reconstruct the full response tensor by splitting and placing each part
            from slime.backends.megatron_utils.cp_utils import all_gather_with_cp

            full_kl_response = all_gather_with_cp(local_kl_chunk, total_len, response_len)
        else:
            full_kl_response = local_kl_chunk

        # Step 3: Compute returns on full response kl tensor.
        token_level_rewards = -kl_coef * full_kl_response
        full_mask = loss_masks[i]
        assert full_mask.sum().item() > 0, f"Sequence at index {i} is fully masked."
        last_idx = full_mask.nonzero(as_tuple=True)[0][-1]
        token_level_rewards[last_idx] += rewards[i]

        returns_for_seq = torch.zeros_like(token_level_rewards)
        running_return = 0.0
        for t in reversed(range(token_level_rewards.size(0))):
            # G_t = r_t + gamma * G_{t+1}
            running_return = token_level_rewards[t] + gamma * running_return
            returns_for_seq[t] = running_return

        # Step 4: Pick up the results corresponding to our local chunk's parts.
        if cp_size > 1:
            from slime.backends.megatron_utils.cp_utils import slice_log_prob_with_cp

            local_returns_chunk = slice_log_prob_with_cp(returns_for_seq, total_len, response_len)
        else:
            local_returns_chunk = returns_for_seq

        final_returns_chunks.append(local_returns_chunk)

    return final_returns_chunks


def get_reinforce_plus_plus_baseline_advantages(
    rewards: torch.Tensor,
    kl: List[torch.Tensor],
    loss_masks: List[torch.Tensor],
    kl_coef: float,
) -> List[torch.Tensor]:
    """
    Calculates the unwhitened advantages for the REINFORCE++-baseline algorithm.
    Broadcasting the scalar (reward - group_baseline) to each token.

    Args:
        rewards (Tensor): A tensor of scalar rewards, where the group-wise
                                baseline has already been subtracted.
        kl (list[Tensor]): A list of per-token KL divergence tensors. Used to
                                 get the shape for broadcasting.
        loss_masks (list[Tensor]): A list of per-token loss masks.
        kl_coef (float): Coefficient for the KL penalty.

    Returns:
        list[Tensor]: A list of tensors containing the unwhitened advantages.
    """
    # Broadcast to get unwhitened advantages
    unwhitened_advantages = [
        torch.ones_like(kl_tensor) * reward_val - kl_coef * kl_tensor for kl_tensor, reward_val in zip(kl, rewards)
    ]

    return unwhitened_advantages


def get_advantages_and_returns(
    total_len: int,
    response_len: int,
    values: torch.Tensor,
    rewards: torch.Tensor,
    gamma: float,
    lambd: float,
) -> Tuple[torch.Tensor, torch.Tensor]:
    """Function that computes advantages and returns from rewards and values.
    Calculated as in the original PPO paper: https://arxiv.org/abs/1707.06347
    Note that rewards may include a KL divergence loss term.

    Advantages looks like this:
    Adv1 =  R1 + γ * λ * R2     + γ^2 * λ^2 * R3       + ...
            - V1 + γ * (1 - λ) V2 + γ^2 * λ * (1 - λ) V3 + ...

    Returns looks like this:
    Ret1 =  R1 + γ * λ * R2     + γ^2 * λ^2 * R3       + ...
                + γ * (1 - λ) V2 + γ^2 * λ * (1 - λ) V3 + ...

    Input:
    - values: Tensor of shape (response_size,)
    - rewards: Tensor of shape (response_size,)

    Output:
    - advantages: Tensor of shape (response_size,)
    - returns: Tensor of shape (response_size,)
    """
    from megatron.core import mpu

    cp_size = mpu.get_context_parallel_world_size()
    if cp_size > 1:
        from slime.backends.megatron_utils.cp_utils import all_gather_with_cp

        full_rewards = all_gather_with_cp(rewards, total_len, response_len)
        full_values = all_gather_with_cp(values, total_len, response_len)
    else:
        full_rewards = rewards
        full_values = values

    lastgaelam = 0
    advantages_reversed = []

    for t in reversed(range(response_len)):
        nextvalues = full_values[t + 1] if t < response_len - 1 else 0.0
        delta = full_rewards[t] + gamma * nextvalues - full_values[t]
        lastgaelam = delta + gamma * lambd * lastgaelam
        advantages_reversed.append(lastgaelam)
    full_advantages = torch.tensor(advantages_reversed[::-1], dtype=full_values.dtype, device=full_values.device)
    full_returns = full_advantages + full_values

    if cp_size > 0:
        from slime.backends.megatron_utils.cp_utils import slice_log_prob_with_cp

        advantages = slice_log_prob_with_cp(full_advantages, total_len, response_len)
        returns = slice_log_prob_with_cp(full_returns, total_len, response_len)
    else:
        advantages = full_advantages
        returns = full_returns

    return advantages.detach(), returns


def calculate_log_probs_and_entropy(logits, tokens, tp_group, with_entropy: bool = False):
    logits = logits.contiguous()
    # TODO: not sure why we need to clone the logits here.
    # Without the clone, the backward will trigger inplace edit error.
    # It seems that the function with tp will modify the logits inplace.
    if logits.size(0) != 0:
        log_prob = compute_log_probs(logits.clone(), tokens, tp_group)
    else:
        log_prob = logits.new_zeros((0,))

    if with_entropy:
        if logits.size(0) != 0:
            entropy = compute_entropy_from_logits(logits.clone(), tp_group)
        else:
            entropy = logits.new_zeros((0,))
    else:
        entropy = None
    return log_prob, entropy

def get_reinforce_plus_plus_returns_with_token_rewards(
    token_rewards: Union[torch.Tensor, List[List[float]]],
    kl: List[torch.Tensor],
    loss_masks: List[torch.Tensor],
    response_lengths: List[int],
    total_lengths: List[int],
    kl_coef: float,
    gamma: float,
) -> List[torch.Tensor]:
    """
    机制 1：全局传播 - 支持 token-level rewards
    
    Calculates discounted returns for REINFORCE++ with token-level rewards.
    SQL reward propagates to Schema tokens through discount mechanism.
    
    Args:
        token_rewards: Either:
            - torch.Tensor: sentence-level rewards [batch_size] (backward compatible)
            - List[List[float]]: token-level rewards, sparse format
        kl: List of per-token KL divergence tensors for sequence chunks.
        loss_masks: List of response-only loss masks for each full sequence.
        response_lengths: The full length of each response sequence.
        total_lengths: The full length of each sequence (prompt + response).
        kl_coef: Coefficient for the KL penalty.
        gamma: The discount factor.
    
    Returns:
        List[torch.Tensor]: A list of return (G_t) tensors for the
                            local sequence chunks owned by the current GPU rank.
    """
    from megatron.core import mpu

    cp_size = mpu.get_context_parallel_world_size()
    
    # ✅ 检测输入类型
    is_token_level = isinstance(token_rewards, list)
    
    final_returns_chunks = []
    for i in range(len(kl)):
        local_kl_chunk = kl[i]
        total_len, response_len = total_lengths[i], response_lengths[i]

        # 处理 Context Parallelism
        if cp_size > 1:
            from slime.backends.megatron_utils.cp_utils import all_gather_with_cp
            full_kl_response = all_gather_with_cp(local_kl_chunk, total_len, response_len)
        else:
            full_kl_response = local_kl_chunk

        # ✅ 根据输入类型构建 token_level_rewards
        if is_token_level:
            # Token-level: 直接使用 sparse rewards
            device = full_kl_response.device
            full_token_rewards = torch.tensor(token_rewards[i], dtype=torch.float32, device=device)
            
            # 处理 CP
            if cp_size > 1:
                full_token_rewards = all_gather_with_cp(full_token_rewards, total_len, response_len)
            
            # token_level_rewards = sparse_rewards - kl_penalty
            token_level_rewards = full_token_rewards - kl_coef * full_kl_response
            
            # ✅ 调试：打印 sparse rewards 的非零位置
            non_zero_mask = full_token_rewards != 0.0
            if non_zero_mask.any():
                non_zero_indices = non_zero_mask.nonzero(as_tuple=True)[0]
                if i == 0:  # 只打印第一个 sample
                    print(f"[REINFORCE++] Sample {i}: Sparse rewards at positions {non_zero_indices.tolist()[:5]}...", flush=True)
                    for idx in non_zero_indices[:3]:  # 只打印前3个
                        print(f"  Position {idx.item()}: reward={full_token_rewards[idx].item():.3f}, kl={full_kl_response[idx].item():.3f}", flush=True)
        else:
            # Sentence-level: 原有逻辑（向后兼容）
            token_level_rewards = -kl_coef * full_kl_response
            full_mask = loss_masks[i]
            assert full_mask.sum().item() > 0, f"Sequence at index {i} is fully masked."
            last_idx = full_mask.nonzero(as_tuple=True)[0][-1]
            token_level_rewards[last_idx] += token_rewards[i]

        # ✅ 计算折扣回报（从后向前）
        returns_for_seq = torch.zeros_like(token_level_rewards)
        running_return = 0.0
        for t in reversed(range(token_level_rewards.size(0))):
            # G_t = r_t + gamma * G_{t+1}
            running_return = token_level_rewards[t] + gamma * running_return
            returns_for_seq[t] = running_return
        
        # ✅ 调试：打印回报传播情况
        if is_token_level and i == 0:
            print(f"[REINFORCE++] Sample {i}: Returns range [{returns_for_seq.min().item():.3f}, {returns_for_seq.max().item():.3f}]", flush=True)

        # 提取本地 chunk
        if cp_size > 1:
            from slime.backends.megatron_utils.cp_utils import slice_log_prob_with_cp
            local_returns_chunk = slice_log_prob_with_cp(returns_for_seq, total_len, response_len)
        else:
            local_returns_chunk = returns_for_seq

        final_returns_chunks.append(local_returns_chunk)

    return final_returns_chunks


def get_reinforce_plus_plus_returns_segmented(
    token_rewards: List[List[float]],
    schema_end_positions: List[int],
    kl: List[torch.Tensor],
    loss_masks: List[torch.Tensor],
    response_lengths: List[int],
    total_lengths: List[int],
    kl_coef: float,
    gamma: float,
) -> List[torch.Tensor]:
    """
    机制 2：分段传播 - Schema 和 SQL 独立计算折扣回报
    
    Calculates discounted returns for REINFORCE++ with segmented propagation.
    Schema and SQL parts are computed independently (no cross-influence).
    
    Args:
        token_rewards: List[List[float]] - token-level rewards (sparse format)
        schema_end_positions: List[int] - position where schema ends for each sample
        kl: List of per-token KL divergence tensors for sequence chunks.
        loss_masks: List of response-only loss masks for each full sequence.
        response_lengths: The full length of each response sequence.
        total_lengths: The full length of each sequence (prompt + response).
        kl_coef: Coefficient for the KL penalty.
        gamma: The discount factor.
    
    Returns:
        List[torch.Tensor]: A list of return (G_t) tensors for the
                            local sequence chunks owned by the current GPU rank.
    """
    from megatron.core import mpu

    cp_size = mpu.get_context_parallel_world_size()
    
    final_returns_chunks = []
    for i in range(len(kl)):
        local_kl_chunk = kl[i]
        total_len, response_len = total_lengths[i], response_lengths[i]
        schema_end_pos = schema_end_positions[i]
        
        # 处理 None 的情况
        if schema_end_pos is None:
            schema_end_pos = response_len  # 如果没有 schema，整个都是 SQL

        # 处理 Context Parallelism
        if cp_size > 1:
            from slime.backends.megatron_utils.cp_utils import all_gather_with_cp
            full_kl_response = all_gather_with_cp(local_kl_chunk, total_len, response_len)
        else:
            full_kl_response = local_kl_chunk

        # 转换 token_rewards 为 tensor
        device = full_kl_response.device
        full_token_rewards = torch.tensor(token_rewards[i], dtype=torch.float32, device=device)
        
        if cp_size > 1:
            full_token_rewards = all_gather_with_cp(full_token_rewards, total_len, response_len)
        
        # 计算 token_level_rewards = sparse_rewards - kl_penalty
        token_level_rewards = full_token_rewards - kl_coef * full_kl_response
        
        # ✅ 分段计算折扣回报
        returns_for_seq = torch.zeros_like(token_level_rewards)
        
        # SQL 部分（从后向前）
        running_return = 0.0
        for t in reversed(range(schema_end_pos, response_len)):
            running_return = token_level_rewards[t] + gamma * running_return
            returns_for_seq[t] = running_return
        
        # Schema 部分（独立计算，从 schema_end 向前）
        running_return = 0.0
        for t in reversed(range(0, schema_end_pos)):
            running_return = token_level_rewards[t] + gamma * running_return
            returns_for_seq[t] = running_return
        
        # ✅ 调试：打印分段信息
        if i == 0:
            schema_returns = returns_for_seq[:schema_end_pos]
            sql_returns = returns_for_seq[schema_end_pos:]
            print(f"[REINFORCE++ SEGMENTED] Sample {i}:", flush=True)
            print(f"  Schema end position: {schema_end_pos}", flush=True)
            if len(schema_returns) > 0:
                print(f"  Schema returns: [{schema_returns.min().item():.3f}, {schema_returns.max().item():.3f}]", flush=True)
            if len(sql_returns) > 0:
                print(f"  SQL returns: [{sql_returns.min().item():.3f}, {sql_returns.max().item():.3f}]", flush=True)

        # 提取本地 chunk
        if cp_size > 1:
            from slime.backends.megatron_utils.cp_utils import slice_log_prob_with_cp
            local_returns_chunk = slice_log_prob_with_cp(returns_for_seq, total_len, response_len)
        else:
            local_returns_chunk = returns_for_seq

        final_returns_chunks.append(local_returns_chunk)

    return final_returns_chunks