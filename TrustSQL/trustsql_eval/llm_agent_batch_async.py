import random
import json
import os
import time
import asyncio
import uuid
import traceback
from collections import defaultdict
from copy import deepcopy
from dataclasses import dataclass
from typing import List, Dict, Any, Optional

import torch
# Import vLLM async engine components
from vllm import AsyncLLMEngine, SamplingParams
from vllm.engine.arg_utils import AsyncEngineArgs

from file_manager import FileManager
from message_processor import MessageProcessor
from prompt_builders import get_prompt_builder


@dataclass
class ConversationState:
    """Manages the state of a single conversation."""
    instance_id: str
    rollout_idx: int
    item: Dict[str, Any]
    messages: List[Dict[str, str]]
    conversation_history: List[Dict[str, str]]
    current_round: int
    terminated: bool
    error: Optional[str] = None
    retry_count: int = 0

    def to_result(self) -> Dict[str, Any]:
        """Convert conversation state to result dict."""
        result = {
            "instance_id": self.instance_id,
            "rollout_idx": self.rollout_idx,
            "conversation": self.conversation_history,
            "final_messages": self.messages,
            "terminated": self.terminated,
            "rounds_completed": self.current_round
        }
        if self.error:
            result["error"] = self.error
        return result


class BatchLLMAgent:
    def __init__(self, args):
        self.args = args

        # Set environment variables at init time if needed
        if hasattr(args, 'cuda_visible_devices'):
            os.environ['CUDA_VISIBLE_DEVICES'] = str(args.cuda_visible_devices)
        # Disable V1 engine
        os.environ['VLLM_USE_V1'] = '0'

        # Lazy initialization of vLLM async engine
        self.llm_engine = None
        self.sampling_params = None

        self.file_manager = FileManager(args)
        self.message_processor = MessageProcessor(args)

        # Initialize prompt builder
        self.prompt_builder = get_prompt_builder(args.prompt_strategy)

        self.processed_instances = defaultdict(int)

        # Concurrency control
        self.concurrency_limit = getattr(args, 'batch_size', 128)
        self.max_retries = getattr(args, 'max_retries', 5)

    def _load_rope_config_from_model(self) -> Dict[str, Any]:
        """
        Read RoPE-related configuration from the model's config.json.
        """
        import json
        from pathlib import Path

        model_path = Path(self.args.model)
        config_file = model_path / "config.json"

        rope_config = {}

        if not config_file.exists():
            print(f"⚠ Warning: config.json not found at {config_file}")
            return rope_config

        try:
            with open(config_file, 'r') as f:
                config = json.load(f)

            print("\n" + "=" * 70)
            print("Reading RoPE config from model config.json:")

            # 1. max_position_embeddings
            if 'max_position_embeddings' in config:
                max_pos_emb = config['max_position_embeddings']
                rope_config['max_model_len'] = max_pos_emb
                print(f"  max_position_embeddings: {max_pos_emb}")
            else:
                rope_config['max_model_len'] = 32768

            # 2. rope_scaling
            if 'rope_scaling' in config and config['rope_scaling']:
                rope_scaling_config = config['rope_scaling']
                vllm_rope_scaling = {}

                if 'rope_type' in rope_scaling_config:
                    vllm_rope_scaling['rope_type'] = rope_scaling_config['rope_type']
                elif 'type' in rope_scaling_config:
                    vllm_rope_scaling['rope_type'] = rope_scaling_config['type']
                else:
                    vllm_rope_scaling['rope_type'] = 'linear'

                if 'factor' in rope_scaling_config:
                    vllm_rope_scaling['factor'] = float(rope_scaling_config['factor'])
                else:
                    vllm_rope_scaling['factor'] = 1.0

                if 'original_max_position_embeddings' in rope_scaling_config:
                    vllm_rope_scaling['original_max_position_embeddings'] = \
                        rope_scaling_config['original_max_position_embeddings']

                rope_config['rope_scaling'] = vllm_rope_scaling
                print(f"  rope_scaling configured: {vllm_rope_scaling['rope_type']}")

            # 3. rope_theta
            if 'rope_theta' in config:
                rope_config['rope_theta'] = float(config['rope_theta'])

            print("=" * 70 + "\n")
            return rope_config

        except Exception as e:
            print(f"⚠ Warning: Could not read config.json: {e}")
            return rope_config

    def _initialize_vllm(self):
        """
        Initialize the vLLM async engine (AsyncLLMEngine).
        Includes full stop-token configuration.
        """
        if self.llm_engine is not None:
            return

        print("=" * 70)
        print("Initializing vLLM Async Engine (Continuous Batching)...")
        print("=" * 70)

        # 1. Load RoPE configuration
        rope_config = self._load_rope_config_from_model()

        # 2. Determine GPU configuration
        visible_devices = os.environ.get('CUDA_VISIBLE_DEVICES', '')
        if visible_devices:
            world_size = len(visible_devices.split(','))
        else:
            world_size = torch.cuda.device_count()

        print(f"\nGPU Configuration:")
        print(f"  CUDA_VISIBLE_DEVICES: {visible_devices if visible_devices else 'Not set'}")
        print(f"  Tensor Parallel Size: {world_size}")

        # 3. Build engine arguments
        try:
            engine_args_dict = {
                'model': self.args.model,
                'trust_remote_code': True,
                'tensor_parallel_size': world_size,
                'disable_log_requests': False,
            }

            # Apply RoPE configuration
            if rope_config.get('max_model_len'):
                engine_args_dict['max_model_len'] = rope_config['max_model_len']
                print(f"  Max model length: {rope_config['max_model_len']}")
            else:
                engine_args_dict['max_model_len'] = 32768
                print(f"  Max model length: 32768 (default)")

            if rope_config.get('rope_scaling'):
                engine_args_dict['rope_scaling'] = rope_config['rope_scaling']
                print(f"  RoPE scaling: {rope_config['rope_scaling']}")

            if rope_config.get('rope_theta'):
                engine_args_dict['rope_theta'] = rope_config['rope_theta']
                print(f"  RoPE theta: {rope_config['rope_theta']}")

            # GPU memory utilization
            if hasattr(self.args, 'gpu_memory_utilization'):
                engine_args_dict['gpu_memory_utilization'] = self.args.gpu_memory_utilization
            else:
                engine_args_dict['gpu_memory_utilization'] = 0.9

            print(f"  GPU memory utilization: {engine_args_dict['gpu_memory_utilization']}")

            # 4. Initialize async engine
            print(f"\nInitializing AsyncLLMEngine...")
            print(f"Engine configuration: {engine_args_dict}")

            engine_args = AsyncEngineArgs(**engine_args_dict)
            self.llm_engine = AsyncLLMEngine.from_engine_args(engine_args)

            print("✓ vLLM Async Engine loaded successfully")

        except Exception as e:
            print(f"✗ Error loading vLLM engine: {e}")
            traceback.print_exc()
            raise

        # 5. Configure stop conditions
        print("\n" + "=" * 70)
        print("Configuring Stop Conditions")
        print("=" * 70)

        stop_token_ids = []
        stop_strings = []

        # Priority 1: use stop tokens from args (user-specified)
        if hasattr(self.args, 'stop_token_ids') and self.args.stop_token_ids:
            stop_token_ids = self.args.stop_token_ids
            print(f"\n[Priority 1] Using stop_token_ids from args:")
            print(f"  {stop_token_ids}")

        if hasattr(self.args, 'stop_strings') and self.args.stop_strings:
            stop_strings = self.args.stop_strings
            print(f"\n[Priority 1] Using stop_strings from args:")
            print(f"  {stop_strings}")

        # Priority 2: auto-read from tokenizer config
        if not stop_token_ids or not stop_strings:
            print(f"\n[Priority 2] Reading from tokenizer config...")
            try:
                stop_config = self.prompt_builder.get_comprehensive_stop_config(self.args)

                if not stop_token_ids:
                    stop_token_ids = stop_config["token_ids"]
                    if stop_token_ids:
                        print(f"  ✓ Loaded {len(stop_token_ids)} stop token IDs from config")

                if not stop_strings:
                    stop_strings = stop_config["strings"]
                    if stop_strings:
                        print(f"  ✓ Loaded {len(stop_strings)} stop strings from config")

            except Exception as e:
                print(f"  ✗ Warning: Could not get stop config from tokenizer: {e}")
                import traceback
                traceback.print_exc()

        # Priority 3: hardcoded fallback for Qwen3
        if not stop_token_ids:
            print(f"\n[Priority 3] Using hardcoded fallback stop token IDs for Qwen3")
            stop_token_ids = [
                151643,  # <|endoftext|>
                151645,  # <|im_end|>
                151644,  # <|im_start|> (prevent model from starting a new dialogue turn)
            ]
            print(f"  Fallback IDs: {stop_token_ids}")

        if not stop_strings:
            print(f"\n[Priority 3] Using hardcoded fallback stop strings")
            stop_strings = [
                "<|im_end|>",
                "<|endoftext|>",
                "<|im_start|>",
            ]
            print(f"  Fallback strings: {stop_strings}")

        # 6. Configure sampling parameters
        print("\n" + "=" * 70)
        print("Configuring Sampling Parameters")
        print("=" * 70)

        sampling_params_dict = {
            'temperature': self.args.temperature,
            'top_p': self.args.top_p,
            'max_tokens': self.args.max_new_tokens,
            'n': 1,
        }

        if stop_token_ids:
            sampling_params_dict['stop_token_ids'] = stop_token_ids

        if stop_strings:
            sampling_params_dict['stop'] = stop_strings

        # repetition_penalty: use args value if provided, otherwise default to 1.05
        sampling_params_dict['repetition_penalty'] = getattr(
            self.args, 'repetition_penalty', 1.05
        )

        # presence_penalty: use args value if provided, otherwise default to 0.1
        sampling_params_dict['presence_penalty'] = getattr(
            self.args, 'presence_penalty', 0.1
        )

        try:
            self.sampling_params = SamplingParams(**sampling_params_dict)
            print("\n✓ Sampling parameters configured successfully")
        except Exception as e:
            print(f"\n✗ Error creating SamplingParams: {e}")
            print(f"   Params dict: {sampling_params_dict}")
            raise

        # 7. Print final configuration summary
        print("\n" + "=" * 70)
        print("Final Configuration Summary")
        print("=" * 70)

        print("\n[Model Configuration]")
        print(f"  Model path: {self.args.model}")
        print(f"  Max model length: {engine_args_dict.get('max_model_len', 'N/A')}")
        print(f"  Tensor parallel size: {world_size}")
        print(f"  GPU memory utilization: {engine_args_dict.get('gpu_memory_utilization', 'N/A')}")

        print("\n[Sampling Configuration]")
        print(f"  Temperature: {self.args.temperature}")
        print(f"  Top-p: {self.args.top_p}")
        print(f"  Max new tokens: {self.args.max_new_tokens}")

        if hasattr(self.args, 'repetition_penalty'):
            print(f"  Repetition penalty: {self.args.repetition_penalty}")
        if hasattr(self.args, 'frequency_penalty'):
            print(f"  Frequency penalty: {self.args.frequency_penalty}")
        if hasattr(self.args, 'presence_penalty'):
            print(f"  Presence penalty: {self.args.presence_penalty}")

        print("\n[Stop Conditions]")
        print(f"  Stop token IDs ({len(stop_token_ids)}): {stop_token_ids}")
        print(f"  Stop strings ({len(stop_strings)}): {stop_strings}")

        if stop_token_ids or stop_strings:
            print("\n  ✓ Stop conditions configured")
        else:
            print("\n  ⚠️  WARNING: No stop conditions configured!")
            print("     Model may generate indefinitely for Base models")

        print("\n" + "=" * 70)
        print("vLLM Initialization Complete")
        print("=" * 70 + "\n")

    def _get_result_file_path(self, instance_id: str) -> str:
        return os.path.join(self.args.output_folder, f"{instance_id}.json")

    def _load_completed_instances(self) -> set:
        completed = set()
        if not os.path.exists(self.args.output_folder):
            return completed
        for filename in os.listdir(self.args.output_folder):
            if filename.endswith('.json'):
                completed.add(filename[:-5])
        return completed

    def initialize_conversation(self, item: Dict[str, Any], rollout_idx: int) -> ConversationState:
        """Initialize the conversation state for a single item."""
        instance_id = item["id"]

        if isinstance(item, list):
            messages = deepcopy(item)
        elif isinstance(item, dict):
            if "prompt" in item:
                messages = deepcopy(item["prompt"])
            else:
                messages = self.prompt_builder.build_initial_prompt(item, self.args)
        else:
            messages = [{"role": "user", "content": str(item)}]

        if not isinstance(messages, list):
            messages = [messages] if isinstance(messages, dict) else [{"role": "user", "content": str(messages)}]

        for i, msg in enumerate(messages):
            if not isinstance(msg, dict):
                messages[i] = {"role": "user", "content": str(msg)}
            elif "role" not in msg or "content" not in msg:
                if "role" not in msg: messages[i]["role"] = "user"
                if "content" not in msg: messages[i]["content"] = ""

        return ConversationState(
            instance_id=instance_id,
            rollout_idx=rollout_idx,
            item=item,
            messages=messages,
            conversation_history=deepcopy(messages),
            current_round=0,
            terminated=False
        )

    async def generate_response(self, prompt: str, request_id: str) -> Optional[str]:
        """
        Wrap a vLLM async inference request.
        """
        try:
            # engine.generate returns an async generator
            results_generator = self.llm_engine.generate(
                prompt,
                self.sampling_params,
                request_id
            )

            # Iterate the generator to get the final result
            final_output = None
            async for request_output in results_generator:
                final_output = request_output

            if final_output and len(final_output.outputs) > 0:
                return final_output.outputs[0].text.strip()
            return None

        except Exception as e:
            print(f"\n✗ Generation error [ReqID: {request_id}]: {e}")
            traceback.print_exc()
            return None

    async def process_single_conversation(self, conv: ConversationState, semaphore: asyncio.Semaphore):
        """Process the full multi-turn loop for a single conversation."""
        async with semaphore:
            while not conv.terminated and conv.current_round < self.args.max_rounds:
                try:
                    # 1. Build prompt
                    prompt = self.prompt_builder.render_prompt(conv.messages, self.args)

                    # 2. Async generation
                    request_id = f"{conv.instance_id}-r{conv.rollout_idx}-t{conv.current_round}-{uuid.uuid4().hex[:8]}"

                    response = await self.generate_response(prompt, request_id)

                    if not response:
                        conv.retry_count += 1
                        if conv.retry_count >= self.max_retries:
                            conv.error = f"Failed to generate after {self.max_retries} retries"
                            conv.terminated = True
                            break
                        await asyncio.sleep(min(2 ** conv.retry_count, 10))
                        continue

                    conv.retry_count = 0

                    # 3. Process business logic
                    if asyncio.iscoroutinefunction(self.message_processor.process_round):
                        result = await self.message_processor.process_round(
                            response,
                            conv.item,
                            conv.messages,
                            conv.conversation_history,
                            current_round=conv.current_round
                        )
                    else:
                        result = self.message_processor.process_round(
                            response,
                            conv.item,
                            conv.messages,
                            conv.conversation_history,
                            current_round=conv.current_round
                        )

                    # 4. Update state
                    conv.current_round += 1

                    if isinstance(result, Exception):
                        conv.error = str(result)
                        conv.terminated = True
                        print(f"\n✗ Logic Error {conv.instance_id}: {result}")
                        break

                    if result.get("terminated"):
                        conv.terminated = True

                except Exception as e:
                    conv.error = f"Unexpected runtime error: {str(e)}"
                    conv.terminated = True
                    print(f"\n✗ Critical Error {conv.instance_id}: {e}")
                    traceback.print_exc()
                    break

            self.save_conversation(conv)

            if conv.terminated and not conv.error:
                print(".", end="", flush=True)
            elif conv.error:
                print("x", end="", flush=True)
            else:
                print("m", end="", flush=True)

    def save_conversation(self, conv: ConversationState):
        """Save conversation result to file."""
        result = conv.to_result()
        self.file_manager.add_single_result(result)

        if conv.terminated and not conv.error:
            self.processed_instances[conv.instance_id] += 1

    async def run_async(self):
        """
        Async main entry point: uses continuous batching mode.
        """
        print("\n" + "=" * 70)
        print("Starting Batch LLM Agent (Async/Continuous Batching Mode)")
        print("=" * 70)

        os.makedirs(self.args.output_folder, exist_ok=True)

        # 1. Load and filter data
        completed_instances = self._load_completed_instances()
        print(f"\n✓ Found {len(completed_instances)} completed instances")

        with open(self.args.input_file, 'r', encoding='utf-8') as f:
            items = [json.loads(line) for line in f]

        original_count = len(items)
        items = [item for item in items if item["id"] not in completed_instances]

        if not items:
            print("\n✓ All instances have been completed successfully!")
            return

        random.shuffle(items)

        # 2. Initialize vLLM async engine
        self._initialize_vllm()

        # 3. Prepare task pool
        semaphore = asyncio.Semaphore(self.concurrency_limit)
        tasks = []

        print(f"\nConfiguration:")
        print(f"  Total items to process: {len(items)}")
        print(f"  Rollouts per item: {self.args.rollout_number}")
        print(f"  Max concurrency: {self.concurrency_limit}")
        print(f"  Max rounds: {self.args.max_rounds}")
        print("-" * 70)
        print("Processing started (. = success, x = error, m = max rounds)...")

        start_time = time.time()

        # Create all coroutine tasks
        for item in items:
            for rollout_idx in range(self.args.rollout_number):
                conv = self.initialize_conversation(item, rollout_idx)
                task = asyncio.create_task(
                    self.process_single_conversation(conv, semaphore)
                )
                tasks.append(task)

        # 4. Wait for all tasks to complete
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        total_time = time.time() - start_time
        total_processed = len(tasks)

        print("\n" + "=" * 70)
        print(f"✓ All processing completed!")
        print(f"  Results saved to: {self.args.output_folder}")
        print(f"  Total conversations: {total_processed}")
        print(f"  Total time: {total_time/60:.1f} minutes")
        if total_time > 0:
            print(f"  Throughput: {total_processed/total_time:.2f} conv/s")
        print("=" * 70)

        # Exit directly without cleaning up vLLM to avoid hangs
        os._exit(0)

    def run(self):
        """Synchronous entry point."""
        try:
            asyncio.run(self.run_async())
        except KeyboardInterrupt:
            print("\n\n✗ Interrupted by user")
        except Exception as e:
            print(f"\n✗ Fatal error: {e}")
            traceback.print_exc()
        finally:
            import gc
            gc.collect()
            torch.cuda.empty_cache()


# Backward-compatible alias
class LLMAgent(BatchLLMAgent):
    pass
