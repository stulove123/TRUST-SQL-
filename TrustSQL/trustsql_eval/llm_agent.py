import random
import json
import os
import time
from collections import defaultdict
import glob
from copy import deepcopy

# Critical fix: set multiprocessing start method before anything else
import multiprocessing
try:
    multiprocessing.set_start_method('spawn', force=True)
    print("Successfully set multiprocessing start method to 'spawn'")
except RuntimeError as e:
    print(f"Multiprocessing start method already set: {e}")

# Critical fix: set vLLM environment variables before importing torch
os.environ['VLLM_WORKER_MULTIPROC_METHOD'] = 'spawn'
os.environ['VLLM_TORCH_COMPILE_LEVEL'] = '0'

import torch

from vllm import LLM, SamplingParams
from file_manager import FileManager
from message_processor import MessageProcessor
from prompt_builders import get_prompt_builder


class LLMAgent:
    def __init__(self, args):
        self.args = args

        # Lazy initialization of vLLM
        self.llm = None
        self.sampling_params = None

        self.file_manager = FileManager(args)
        self.message_processor = MessageProcessor(args)

        # Initialize prompt builder
        self.prompt_builder = get_prompt_builder(args.prompt_strategy)

        self.processed_instances = defaultdict(int)

    def _initialize_vllm(self):
        """Lazily initialize the vLLM model."""
        if self.llm is not None:
            return

        print("=" * 50)
        print("Initializing vLLM model...")
        print("=" * 50)

        # Determine the number of visible GPUs
        visible_devices = os.environ.get('CUDA_VISIBLE_DEVICES', '')
        if visible_devices:
            world_size = len(visible_devices.split(','))
        else:
            world_size = torch.cuda.device_count()

        print(f"CUDA_VISIBLE_DEVICES: {visible_devices if visible_devices else 'Not set (using all GPUs)'}")
        print(f"Using {world_size} GPU(s) for tensor parallelism")

        try:
            vllm_kwargs = {
                'model': self.args.model,
                'trust_remote_code': True,
                'tensor_parallel_size': world_size,
                'gpu_memory_utilization': getattr(self.args, 'gpu_memory_utilization', 0.9),
                'max_model_len': getattr(self.args, 'max_model_len', 16384),
                'enforce_eager': getattr(self.args, 'enforce_eager', False),
                # Use multiprocessing backend to ensure spawn
                'distributed_executor_backend': 'mp',
            }

            print(f"vLLM initialization parameters:")
            for key, value in vllm_kwargs.items():
                print(f"  {key}: {value}")

            self.llm = LLM(**vllm_kwargs)
            print("✓ vLLM model loaded successfully")

        except Exception as e:
            print(f"✗ Error loading vLLM model: {e}")
            import traceback
            traceback.print_exc()
            raise

        # Configure sampling parameters
        tokenizer = self.llm.get_tokenizer()
        stop_token_ids = [tokenizer.eos_token_id]
        if hasattr(tokenizer, 'pad_token_id') and tokenizer.pad_token_id is not None:
            stop_token_ids.append(tokenizer.pad_token_id)

        self.sampling_params = SamplingParams(
            temperature=self.args.temperature,
            top_p=self.args.top_p,
            max_tokens=self.args.max_new_tokens,
            n=1,
            stop_token_ids=stop_token_ids,
        )

        print(f"Sampling parameters: {self.sampling_params}")
        print("=" * 50)

    def call_llm(self, messages, instance_id=None, round_num=None):
        """Call LLM with retry mechanism using vLLM."""
        if self.llm is None:
            self._initialize_vllm()

        max_retries = 3
        retry_count = 0

        while retry_count < max_retries:
            try:
                # Render prompt using prompt_builder
                prompt = self.prompt_builder.render_prompt(messages, self.args)

                # Generate with vLLM
                outputs = self.llm.generate([prompt], self.sampling_params)

                if outputs and len(outputs) > 0:
                    content = outputs[0].outputs[0].text.strip()
                    if content:
                        return content
                    else:
                        raise Exception("Empty response content")
                else:
                    raise Exception("No output generated")

            except Exception as e:
                retry_count += 1
                instance_info = f" for {instance_id}" if instance_id else ""
                round_info = f" (round {round_num})" if round_num is not None else ""
                print(f"LLM Error{instance_info}{round_info}: {e}. Retrying ({retry_count}/{max_retries})...")

                if retry_count >= max_retries:
                    return f"ERROR: Failed to get response after {max_retries} retries"

                time.sleep(1)

        return "ERROR: Unexpected exit from retry loop"

    def process_single_item(self, item, rollout_idx):
        """Process a single item with the specified rollout index."""
        instance_id = item["id"]

        if self.processed_instances[instance_id] >= self.args.rollout_number:
            print(f"Skipping {instance_id} rollout {rollout_idx + 1} (already completed)")
            return None

        try:
            # Initialize messages
            if isinstance(item, list):
                messages = deepcopy(item)
            elif isinstance(item, dict):
                if "prompt" in item:
                    messages = deepcopy(item["prompt"])
                else:
                    messages = self.prompt_builder.build_initial_prompt(item, self.args)
            else:
                print(f"Warning: Unexpected item type: {type(item)}")
                messages = [{"role": "user", "content": str(item)}]

            # Ensure messages is a list
            if not isinstance(messages, list):
                print(f"Warning: Converting messages to list")
                messages = [messages] if isinstance(messages, dict) else [{"role": "user", "content": str(messages)}]

            # Validate message format
            for i, msg in enumerate(messages):
                if not isinstance(msg, dict):
                    messages[i] = {"role": "user", "content": str(msg)}
                elif "role" not in msg or "content" not in msg:
                    if "role" not in msg:
                        messages[i]["role"] = "user"
                    if "content" not in msg:
                        messages[i]["content"] = ""

            print(f"✓ Initialized messages: {len(messages)} message(s)")

            conversation_history = deepcopy(messages)
            terminated = False

            for round_num in range(self.args.max_rounds):
                print(f"\n--- {instance_id} | Rollout {rollout_idx + 1} | Round {round_num + 1} ---")

                # Validate messages type
                if not isinstance(messages, list):
                    print(f"ERROR: messages is {type(messages)}, expected list")
                    messages = [messages] if isinstance(messages, dict) else [{"role": "user", "content": str(messages)}]

                llm_response = self.call_llm(messages, instance_id, round_num + 1)

                if llm_response.startswith("ERROR:"):
                    print(f"✗ Failed to get valid LLM response")
                    error_result = {
                        "instance_id": instance_id,
                        "rollout_idx": rollout_idx,
                        "error": llm_response,
                        "round_failed": round_num + 1,
                        "terminated": False
                    }
                    self.file_manager.add_single_result(error_result)
                    return error_result

                result = self.message_processor.process_round(
                    llm_response, item, messages, conversation_history
                )

                if result.get("terminated"):
                    terminated = True
                    print(f"✓ Conversation terminated")
                    break

                if result.get("continue"):
                    continue

            result = {
                "instance_id": instance_id,
                "rollout_idx": rollout_idx,
                "conversation": conversation_history,
                "final_messages": messages,
                "terminated": terminated
            }

            self.file_manager.add_single_result(result)

            status = "✓ TERMINATED" if terminated else "⚠ INCOMPLETE"
            print(f"\n{status}: {instance_id} (rollout {rollout_idx + 1}/{self.args.rollout_number})")

            return result

        except Exception as e:
            error_result = {
                "instance_id": instance_id,
                "rollout_idx": rollout_idx,
                "error": str(e),
                "terminated": False
            }

            self.file_manager.add_single_result(error_result)
            print(f"✗ Error processing {instance_id} rollout {rollout_idx + 1}: {str(e)}")
            import traceback
            traceback.print_exc()
            return error_result

    def run(self):
        """Main execution function."""
        print("\n" + "=" * 70)
        print("Starting LLM Agent")
        print("=" * 70)

        existing_results = self.file_manager.load_existing_results()
        self.processed_instances = self.file_manager.processed_instances
        os.makedirs(self.args.output_folder, exist_ok=True)

        with open(self.args.input_file, 'r', encoding='utf-8') as f:
            items = [json.loads(line) for line in f]

        random.shuffle(items)

        tasks_to_process = []
        for item in items:
            instance_id = item["id"]
            current_valid_rollouts = self.processed_instances[instance_id]

            for rollout_idx in range(current_valid_rollouts, self.args.rollout_number):
                tasks_to_process.append((item, rollout_idx))

        total_expected = len(items) * self.args.rollout_number
        total_existing = sum(self.processed_instances.values())

        print(f"\nConfiguration:")
        print(f"  Total items: {len(items)}")
        print(f"  Rollout number: {self.args.rollout_number}")
        print(f"  Prompt strategy: {self.args.prompt_strategy}")
        print(f"  Model: {self.args.model}")
        print(f"\nProgress:")
        print(f"  Total expected tasks: {total_expected}")
        print(f"  Valid completed tasks: {total_existing}")
        print(f"  Tasks to process: {len(tasks_to_process)}")

        if not tasks_to_process:
            print("\n✓ All rollouts have been completed successfully!")
            return

        # vLLM handles multi-GPU internally; use a single thread here
        num_threads = 1
        print(f"\nUsing {num_threads} thread (vLLM handles multi-GPU internally)")
        print("=" * 70 + "\n")

        completed_count = 0
        from concurrent.futures import ThreadPoolExecutor, as_completed

        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            future_to_task = {
                executor.submit(self.process_single_item, item, rollout_idx): (item, rollout_idx)
                for item, rollout_idx in tasks_to_process
            }

            for future in as_completed(future_to_task):
                item, rollout_idx = future_to_task[future]
                try:
                    result = future.result()
                    if result is not None:
                        completed_count += 1
                        progress_pct = (completed_count / len(tasks_to_process)) * 100
                        print(f"\n{'='*70}")
                        print(f"Progress: {completed_count}/{len(tasks_to_process)} ({progress_pct:.1f}%) completed")
                        print(f"{'='*70}\n")
                except Exception as e:
                    print(f"✗ Unexpected error: {item['instance_id']} rollout {rollout_idx + 1}: {str(e)}")
                    import traceback
                    traceback.print_exc()

        print("\n" + "=" * 70)
        print(f"✓ All processing completed!")
        print(f"  Results saved to: {self.args.output_folder}")
        print(f"  Total processed in this run: {completed_count}")
        print("=" * 70 + "\n")
