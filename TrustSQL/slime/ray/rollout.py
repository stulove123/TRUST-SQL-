import logging
import multiprocessing
import random
import time
from pathlib import Path
from typing import List, Union

import numpy as np
import ray
import torch
import wandb
from ray.util.scheduling_strategies import PlacementGroupSchedulingStrategy

from slime.backends.sglang_utils.sglang_engine import SGLangEngine
from slime.ray.rollout_data_source import RolloutDataSourceWithBuffer
from slime.rollout.base_types import call_rollout_fn
from slime.utils.health_monitor import RolloutHealthMonitor
from slime.utils.http_utils import find_available_port, get_host_info, init_http_client
from slime.utils.iter_utils import group_by
from slime.utils.metric_checker import MetricChecker
from slime.utils.metric_utils import compute_pass_rate, compute_statistics, dict_add_prefix
from slime.utils.misc import load_function
from slime.utils.ray_utils import Box
from slime.utils.types import Sample
from slime.utils.wandb_utils import init_wandb_secondary

from ..utils.metric_utils import has_repetition
from .utils import NOSET_VISIBLE_DEVICES_ENV_VARS_LIST, Lock

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


@ray.remote
class RolloutManager:
    """The class to run rollout and convert rollout data to training data."""

    def __init__(self, args, pg, wandb_run_id):
        self.args = args
        self.pg = pg
        _start_router(args)
        init_wandb_secondary(
            args, wandb_run_id, router_addr=f"http://{args.sglang_router_ip}:{args.sglang_router_port}"
        )
        init_http_client(args)

        self.data_source = RolloutDataSourceWithBuffer(args)

        self.generate_rollout = load_function(self.args.rollout_function_path)
        self.eval_generate_rollout = load_function(self.args.eval_function_path)
        self.custom_reward_post_process_func = None
        if self.args.custom_reward_post_process_path is not None:
            self.custom_reward_post_process_func = load_function(self.args.custom_reward_post_process_path)
        print(f"import {self.args.rollout_function_path} as generate_rollout function.")
        print(f"import {self.args.eval_function_path} as eval_generate_rollout function.")

        if self.args.debug_train_only:
            self.all_rollout_engines = []
        else:
            num_gpu_per_engine = min(args.rollout_num_gpus_per_engine, args.num_gpus_per_node)
            num_engines = args.rollout_num_gpus // num_gpu_per_engine
            self.all_rollout_engines = [None] * num_engines
        self.num_new_engines = init_rollout_engines(args, pg, self.all_rollout_engines)
        self.nodes_per_engine = max(1, args.rollout_num_gpus_per_engine // args.num_gpus_per_node)
        self.rollout_engine_lock = Lock.options(num_cpus=1, num_gpus=0).remote()

        self._metric_checker = MetricChecker.maybe_create(args)
        if self.args.use_fault_tolerance:
            self._health_monitor = RolloutHealthMonitor(self, args)

    def dispose(self):
        if self._metric_checker is not None:
            self._metric_checker.dispose()

    @property
    def rollout_engines(self):
        # When doing multi-node serving, only send requests to node-0 for each engine.
        return self.all_rollout_engines[:: self.nodes_per_engine]

    def get_rollout_engines_and_lock(self):
        return self.rollout_engines, self.rollout_engine_lock, self.num_new_engines

    def get_num_rollout_per_epoch(self):
        assert self.args.rollout_global_dataset
        return len(self.data_source.dataset) // self.args.rollout_batch_size

    def generate(self, rollout_id):
        monitor_started = self.args.use_fault_tolerance and self._health_monitor.start()
        start_time = time.time()
        try:
            data, metrics = self._get_rollout_data(rollout_id=rollout_id)
            self._save_debug_rollout_data(data, rollout_id=rollout_id, evaluation=False)
            _log_rollout_data(rollout_id, self.args, data, metrics, time.time() - start_time)
            data = self._convert_samples_to_train_data(data)
            return Box(ray.put(data))
        finally:
            if monitor_started:
                self._health_monitor.stop()
                self.num_new_engines = init_rollout_engines(self.args, self.pg, self.all_rollout_engines)
            else:
                self.num_new_engines = 0

    def eval(self, rollout_id):
        if self.args.debug_train_only:
            return
        data = call_rollout_fn(
            self.eval_generate_rollout, self.args, rollout_id, self.data_source, evaluation=True
        ).data
        self._save_debug_rollout_data(data, rollout_id=rollout_id, evaluation=True)
        metrics = _log_eval_rollout_data(rollout_id, self.args, data)
        if self._metric_checker is not None:
            self._metric_checker.on_eval(metrics)

    def save(self, rollout_id):
        self.data_source.save(rollout_id)

    def load(self, rollout_id=None):
        self.data_source.load(rollout_id)

    def offload(self):
        return ray.get([engine.release_memory_occupation.remote() for engine in self.rollout_engines])

    def onload(self, tags: List[str] = None):
        return ray.get([engine.resume_memory_occupation.remote(tags=tags) for engine in self.rollout_engines])

    def _get_rollout_data(self, rollout_id):
        if self.args.load_debug_rollout_data:
            data = torch.load(
                open(self.args.load_debug_rollout_data.format(rollout_id=rollout_id), "rb"),
                weights_only=False,
            )["samples"]
            data = [Sample.from_dict(sample) for sample in data]
            if (ratio := self.args.load_debug_rollout_data_subsample) is not None:
                original_num_rows = len(data)
                rough_subsample_num_rows = int(original_num_rows * ratio)
                data = data[: rough_subsample_num_rows // 2] + data[-rough_subsample_num_rows // 2 :]
                print(
                    f"Subsample loaded debug rollout data using {ratio=} "
                    f"and change num rows {original_num_rows} -> {len(data)}"
                )
            metrics = None
        else:
            data = call_rollout_fn(self.generate_rollout, self.args, rollout_id, self.data_source, evaluation=False)
            metrics = data.metrics
            data = data.samples

            # Flatten nested lists if necessary
            while isinstance(data[0], list):
                data = sum(data, [])

            # Trim to a multiple of global_batch_size
            if len(data) % self.args.global_batch_size != 0:
                trim_len = (len(data) // self.args.global_batch_size) * self.args.global_batch_size
                origin_data_length = len(data)
                data = data[:trim_len]
                print(f"Trimmed samples from {origin_data_length} to {trim_len}")

        return data, metrics

    def _save_debug_rollout_data(self, data, rollout_id, evaluation: bool):
        if (path_template := self.args.save_debug_rollout_data) is not None:
            path = Path(path_template.format(rollout_id=("eval_" if evaluation else "") + str(rollout_id)))
            print(f"Save debug rollout data to {path}")
            path.parent.mkdir(parents=True, exist_ok=True)

            if evaluation:
                dump_data = dict(
                    samples=[sample.to_dict() for dataset_name, info in data.items() for sample in info["samples"]]
                )
            else:
                dump_data = dict(samples=[sample.to_dict() for sample in data])

            torch.save(dict(rollout_id=rollout_id, **dump_data), path)

    def _post_process_rewards(self, samples):
        if self.custom_reward_post_process_func is not None:
            return self.custom_reward_post_process_func(self.args, samples)

        raw_rewards = []
        for idx, sample in enumerate(samples):
            try:
                reward = sample.reward
                if reward is None or not isinstance(reward, (int, float, list)):
                    reward = 0.0
                raw_rewards.append(reward)
            except Exception as e:
                print(f"[ERROR] Failed to get reward for sample {idx}: {e}")
                raw_rewards.append(0.0)

        aborted_count = sum(1 for s in samples if s.status == Sample.Status.ABORTED)
        if aborted_count > 0:
            print(f"[POST PROCESS] Found {aborted_count}/{len(samples)} ABORTED samples", flush=True)

        is_token_level = isinstance(raw_rewards[0], list) if raw_rewards else False

        if (
            self.args.advantage_estimator in ["grpo", "gspo", "reinforce_plus_plus_baseline"]
            and self.args.rewards_normalization
        ):
            if is_token_level:
                # Token-level rewards: return as-is; ABORTED handling done in loss_utils.py
                return raw_rewards, raw_rewards, None

            else:
                # Sentence-level: Masked GRPO normalization
                valid_mask = [
                    1.0 if sample.status != Sample.Status.ABORTED else 0.0
                    for sample in samples
                ]

                rewards = torch.tensor(raw_rewards, dtype=torch.float)
                mask = torch.tensor(valid_mask, dtype=torch.float)

                num_samples = len(rewards)
                n_samples_per_prompt = self.args.n_samples_per_prompt

                if num_samples % n_samples_per_prompt != 0:
                    print(
                        f"[WARNING] num_samples ({num_samples}) not divisible by "
                        f"n_samples_per_prompt ({n_samples_per_prompt}), trimming.",
                        flush=True
                    )
                    num_samples = (num_samples // n_samples_per_prompt) * n_samples_per_prompt
                    rewards = rewards[:num_samples]
                    mask = mask[:num_samples]

                rewards = rewards.view(-1, n_samples_per_prompt)
                mask = mask.view(-1, n_samples_per_prompt)

                valid_count = mask.sum(dim=-1, keepdim=True)
                safe_count = torch.clamp(valid_count, min=1.0)
                mean = (rewards * mask).sum(dim=-1, keepdim=True) / safe_count

                if self.args.advantage_estimator in ["grpo", "gspo"] and self.args.grpo_std_normalization:
                    diffs = (rewards - mean) * mask
                    std = torch.sqrt((diffs ** 2).sum(dim=-1, keepdim=True) / safe_count)
                    advantages = (rewards - mean) / (std + 1e-6)
                else:
                    advantages = rewards - mean

                advantages = advantages * mask
                return raw_rewards, advantages.flatten().tolist(), None

        return raw_rewards, raw_rewards, None

    def _convert_samples_to_train_data(self, samples: Union[list[Sample], list[list[Sample]]]):
        """Convert rollout samples to training data."""
        # Mark ABORTED token-level samples
        aborted_count = 0
        token_level_aborted = 0
        sentence_level_aborted = 0

        for sample in samples:
            if sample.status == Sample.Status.ABORTED:
                aborted_count += 1
                reward = sample.reward
                if isinstance(reward, list) and len(reward) > 0:
                    reward[-1] = -1.0
                    sample.reward = reward
                    token_level_aborted += 1
                else:
                    sentence_level_aborted += 1

        if aborted_count > 0:
            print(f"[ROLLOUT] Found {aborted_count} ABORTED samples:", flush=True)
            if token_level_aborted > 0:
                print(f"  Token-level:    {token_level_aborted} (marked reward[-1]=-1)", flush=True)
            if sentence_level_aborted > 0:
                print(f"  Sentence-level: {sentence_level_aborted} (will be masked in GRPO)", flush=True)

        raw_rewards, rewards, indices_to_keep = self._post_process_rewards(samples)

        if indices_to_keep is not None:
            original_count = len(samples)
            indices_to_keep = sorted(indices_to_keep)
            samples    = [samples[i]     for i in indices_to_keep]
            rewards    = [rewards[i]     for i in indices_to_keep]
            raw_rewards = [raw_rewards[i] for i in indices_to_keep]
            print(f"[DATA FILTER] Filtered: {original_count} -> {len(samples)} samples", flush=True)

        assert len(raw_rewards) == len(samples), \
            f"Mismatch: {len(raw_rewards)} rewards vs {len(samples)} samples"
        assert len(rewards) == len(samples), \
            f"Mismatch: {len(rewards)} normalized rewards vs {len(samples)} samples"

        # Build training data dict
        train_data = {
            "tokens":          [sample.tokens          for sample in samples],
            "response_lengths":[sample.response_length for sample in samples],
            "rewards":         rewards,
            "raw_reward":      raw_rewards,
            "truncated":       [1 if sample.status == Sample.Status.TRUNCATED else 0 for sample in samples],
            "sample_indices":  [sample.index           for sample in samples],
            "enable_tree":     [False] * len(samples),
            "sql_rewards":     [getattr(sample, 'sql_reward',    0.0) for sample in samples],
            "schema_rewards":  [getattr(sample, 'schema_reward', 0.0) for sample in samples],
        }

        # Schema end positions
        if any(hasattr(sample, 'schema_end_position') for sample in samples):
            schema_end_positions = []
            for sample in samples:
                pos = getattr(sample, 'schema_end_position', 0)
                if pos is None or not isinstance(pos, int) or pos < 0:
                    pos = 0
                elif pos > sample.response_length:
                    pos = sample.response_length
                schema_end_positions.append(pos)
            train_data["schema_end_positions"] = schema_end_positions

        # Loss masks
        loss_masks = []
        for sample in samples:
            if sample.loss_mask is None:
                sample.loss_mask = [1] * sample.response_length
            loss_masks.append(sample.loss_mask)
        train_data["loss_masks"] = loss_masks

        # Optional metadata fields
        if samples and samples[0].metadata:
            if "raw_reward" in samples[0].metadata:
                train_data["raw_reward"] = [sample.metadata["raw_reward"] for sample in samples]
            if "round_number" in samples[0].metadata:
                train_data["round_number"] = [sample.metadata["round_number"] for sample in samples]

        if samples and samples[0].rollout_log_probs is not None:
            train_data["rollout_log_probs"] = [sample.rollout_log_probs for sample in samples]

        if samples and samples[0].rollout_routed_experts is not None:
            train_data["rollout_routed_experts"] = [sample.rollout_routed_experts for sample in samples]

        if samples and samples[0].train_metadata is not None:
            train_data["metadata"] = [sample.train_metadata for sample in samples]

        if samples and hasattr(samples[0], "teacher_log_probs"):
            train_data["teacher_log_probs"] = [sample.teacher_log_probs for sample in samples]

        return train_data


# ==================== Rollout Engine Initialization ====================
def init_rollout_engines(args, pg, all_rollout_engines):
    if args.debug_train_only:
        return 0

    num_gpu_per_engine = min(args.rollout_num_gpus_per_engine, args.num_gpus_per_node)
    num_engines = args.rollout_num_gpus // num_gpu_per_engine
    assert len(all_rollout_engines) == num_engines

    pg, reordered_bundle_indices = pg
    RolloutRayActor = ray.remote(SGLangEngine)

    rollout_engines = []
    for i in range(num_engines):
        if all_rollout_engines[i] is not None:
            continue

        num_gpus = 0.2
        scheduling_strategy = PlacementGroupSchedulingStrategy(
            placement_group=pg,
            placement_group_capture_child_tasks=True,
            placement_group_bundle_index=reordered_bundle_indices[i * num_gpu_per_engine],
        )

        rollout_engine = RolloutRayActor.options(
            num_cpus=num_gpus,
            num_gpus=num_gpus,
            scheduling_strategy=scheduling_strategy,
            runtime_env={
                "env_vars": {name: "1" for name in NOSET_VISIBLE_DEVICES_ENV_VARS_LIST}
                | {
                    "SGL_JIT_DEEPGEMM_PRECOMPILE":              "false",
                    "SGLANG_JIT_DEEPGEMM_PRECOMPILE":           "false",
                    "SGL_DISABLE_TP_MEMORY_INBALANCE_CHECK":    "true",
                    "SGLANG_DISABLE_TP_MEMORY_INBALANCE_CHECK": "true",
                    "SGLANG_MEMORY_SAVER_CUDA_GRAPH":           "true",
                }
            },
        ).remote(args, rank=i)

        rollout_engines.append((i, rollout_engine))
        all_rollout_engines[i] = rollout_engine

    num_new_engines = len(rollout_engines)
    if num_new_engines == 0:
        return num_new_engines

    if args.rollout_external:
        addr_and_ports = _allocate_rollout_engine_addr_and_ports_external(args=args, rollout_engines=rollout_engines)
    else:
        addr_and_ports = _allocate_rollout_engine_addr_and_ports_normal(
            args=args, num_engines=num_engines, rollout_engines=rollout_engines
        )

    init_handles = [engine.init.remote(**(addr_and_ports[rank])) for rank, engine in rollout_engines]
    ray.get(init_handles)
    return num_new_engines


def _allocate_rollout_engine_addr_and_ports_external(args, rollout_engines):
    addr_and_ports = []
    for rank, _ in rollout_engines:
        host, port = args.rollout_external_engine_addrs[rank].split(":")
        addr_and_ports.append(dict(dist_init_addr=None, nccl_port=None, host=host, port=int(port)))
    return addr_and_ports


def _allocate_rollout_engine_addr_and_ports_normal(*, args, num_engines, rollout_engines):
    num_engines_per_node = max(
        1, min(args.num_gpus_per_node, args.rollout_num_gpus) // args.rollout_num_gpus_per_engine
    )
    addr_and_ports = [{} for _ in range(num_engines)]

    visited_nodes = set()
    for rank, engine in rollout_engines:
        if rank // num_engines_per_node in visited_nodes:
            continue
        visited_nodes.add(rank // num_engines_per_node)
        num_engines_on_this_node = num_engines_per_node - (rank % num_engines_per_node)

        def get_addr_and_ports():
            start_port = 10000

            def port(consecutive=1):
                nonlocal start_port
                _, p = ray.get(
                    engine._get_current_node_ip_and_free_port.remote(
                        start_port=start_port, consecutive=consecutive
                    )
                )
                start_port = p + consecutive
                return p

            def addr():
                a, _ = ray.get(engine._get_current_node_ip_and_free_port.remote())
                return a

            return addr, port

        get_addr, get_port = get_addr_and_ports()

        for i in range(num_engines_on_this_node):
            addr_and_ports[rank + i]["port"]      = get_port()
            addr_and_ports[rank + i]["nccl_port"] = get_port()

        if args.rollout_num_gpus_per_engine > args.num_gpus_per_node:
            num_node_per_engine = args.rollout_num_gpus_per_engine // args.num_gpus_per_node
            if rank % num_node_per_engine == 0:
                dist_init_addr = f"{get_addr()}:{get_port(6 + args.sglang_dp_size)}"
                for i in range(num_node_per_engine):
                    addr_and_ports[rank + i]["dist_init_addr"] = dist_init_addr
        else:
            for i in range(num_engines_on_this_node):
                addr_and_ports[rank + i]["dist_init_addr"] = f"{get_addr()}:{get_port(6 + args.sglang_dp_size)}"

    for i, _ in rollout_engines:
        for key in ["port", "nccl_port", "dist_init_addr"]:
            assert key in addr_and_ports[i], f"Engine {i} missing key: {key}"
        print(f"Ports for engine {i}: {addr_and_ports[i]}")

    return addr_and_ports


# ==================== Router ====================
def _start_router(args):
    """Start SGLang router and Slime router."""
    if args.sglang_router_ip is None:
        args.sglang_router_ip = get_host_info()[1]

    if args.sglang_router_port is None:
        args.sglang_router_port = find_available_port(random.randint(3000, 4000))

    print(f"Starting Router at {args.sglang_router_ip}:{args.sglang_router_port}...")

    if args.use_slime_router:
        from slime.router.router import run_router
        router_args = args
    else:
        from sglang_router.launch_router import RouterArgs
        from slime.utils.http_utils import run_router

        router_args = RouterArgs(
            host=args.sglang_router_ip,
            port=args.sglang_router_port,
            balance_abs_threshold=0,
            prometheus_port=find_available_port(random.randint(4000, 5000)),
        )
        if hasattr(router_args, "log_level"):
            router_args.log_level = "warn"
        if hasattr(router_args, "request_timeout_secs"):
            router_args.request_timeout_secs = args.sglang_router_request_timeout_secs

    process = multiprocessing.Process(target=run_router, args=(router_args,))
    process.daemon = True
    process.start()
    time.sleep(10)

    if not process.is_alive():
        print("Error: Router process died immediately!")
    else:
        print(f"Router launched successfully at port: {args.sglang_router_port}")


# ==================== Logging & Metrics ====================
def _log_eval_rollout_data(rollout_id, args, data):
    log_dict = {}
    for key in data.keys():
        rewards = data[key]["rewards"]
        log_dict[f"eval/{key}"] = sum(rewards) / len(rewards)
        if (samples := data[key].get("samples")) is not None:
            log_dict |= dict_add_prefix(_compute_metrics_from_samples(args, samples), f"eval/{key}/")
        if "truncated" in data[key]:
            truncated = data[key]["truncated"]
            log_dict[f"eval/{key}-truncated_ratio"] = sum(truncated) / len(truncated)
        if args.log_passrate:
            log_dict |= dict_add_prefix(
                compute_pass_rate(flat_rewards=rewards, group_size=args.n_samples_per_eval_prompt),
                f"eval/{key}-",
            )

    print(f"eval {rollout_id}: {log_dict}")

    step = (
        rollout_id
        if not args.wandb_always_use_train_step
        else rollout_id * args.rollout_batch_size * args.n_samples_per_prompt // args.global_batch_size
    )
    if args.use_wandb:
        log_dict["eval/step"] = step
        wandb.log(log_dict)

    if args.use_tensorboard:
        from slime.utils.tensorboard_utils import _TensorboardAdapter
        _TensorboardAdapter(args).log(data=log_dict, step=step)

    return log_dict


def _log_rollout_data(rollout_id, args, samples, rollout_extra_metrics, rollout_time):
    if args.load_debug_rollout_data:
        return

    log_dict = {**(rollout_extra_metrics or {})}
    response_lengths = [sample.effective_response_length for sample in samples]
    log_dict["perf/rollout_time"] = rollout_time
    if args.rollout_num_gpus:
        log_dict["perf/tokens_per_gpu_per_sec"] = sum(response_lengths) / rollout_time / args.rollout_num_gpus
    log_dict["perf/longest_sample_tokens_per_sec"] = max(response_lengths) / rollout_time
    log_dict |= dict_add_prefix(_compute_metrics_from_samples(args, samples), "rollout/")
    print(f"perf {rollout_id}: {log_dict}")

    step = (
        rollout_id
        if not args.wandb_always_use_train_step
        else rollout_id * args.rollout_batch_size * args.n_samples_per_prompt // args.global_batch_size
    )
    if args.use_wandb:
        log_dict["rollout/step"] = step
        wandb.log(log_dict)

    if args.use_tensorboard:
        from slime.utils.tensorboard_utils import _TensorboardAdapter
        _TensorboardAdapter(args).log(data=log_dict, step=step)


def _compute_metrics_from_samples(args, samples):
    response_lengths = [sample.effective_response_length for sample in samples]
    log_dict = {}
    log_dict |= dict_add_prefix(compute_statistics(response_lengths), "response_len/")
    log_dict |= _compute_zero_std_metrics(args, samples)
    log_dict |= _compute_spec_metrics(args, samples)
    log_dict |= _compute_reward_cat_metrics(args, samples)
    log_dict["repetition_frac"]  = np.mean([int(has_repetition(s.response)) for s in samples]).item()
    log_dict["truncated_ratio"]  = np.mean([int(s.status == Sample.Status.TRUNCATED) for s in samples]).item()
    return log_dict


def _compute_zero_std_metrics(args, all_samples: List[Sample]):
    """Compute metrics for groups with zero reward standard deviation."""
    if args.advantage_estimator == "ppo":
        return {}

    def _get_scalar_reward(sample: Sample) -> float:
        try:
            reward = sample.get_reward_value(args)
        except Exception:
            reward = getattr(sample, 'reward', None)
        if reward is None:
            return 0.0
        if isinstance(reward, list):
            return sum(reward) / len(reward) if reward else 0.0
        if isinstance(reward, (int, float)):
            return float(reward)
        return 0.0

    def _is_zero_std(samples: List[Sample]) -> bool:
        scalar_rewards = [_get_scalar_reward(s) for s in samples]
        if not scalar_rewards:
            return True
        first = scalar_rewards[0]
        return all(abs(r - first) < 1e-6 for r in scalar_rewards)

    try:
        all_sample_groups = group_by(all_samples, lambda s: getattr(s, 'group_index', 0))
        interesting_groups = [g for g in all_sample_groups.values() if _is_zero_std(g)]
        interesting_rewards = [str(round(_get_scalar_reward(g[0]), 1)) for g in interesting_groups]
        return {
            f"zero_std/count_{reward}": len(items)
            for reward, items in group_by(interesting_rewards).items()
        }
    except Exception as e:
        print(f"[WARNING] Failed to compute zero_std_metrics: {e}", flush=True)
        return {}


def _compute_spec_metrics(args, all_samples: List[Sample]):
    if args.sglang_speculative_algorithm is None:
        return {}
    num_samples = len(all_samples)
    return {
        "rollout/spec_accept_rate":   sum(s.spec_info.spec_accept_rate   for s in all_samples) / num_samples,
        "rollout/spec_accept_length": sum(s.spec_info.spec_accept_length for s in all_samples) / num_samples,
    }


def _compute_reward_cat_metrics(args, all_samples: List[Sample]):
    reward_cat_key = args.log_reward_category
    if reward_cat_key is None:
        return {}
    samples_of_reward_cat = group_by(all_samples, lambda s: s.reward[reward_cat_key])
    return {
        f"error_cat/{cat}": len(s) / len(all_samples)
        for cat, s in samples_of_reward_cat.items()
    }