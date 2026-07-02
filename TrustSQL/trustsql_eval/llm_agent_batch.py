import random
import json
import os
import time
import asyncio
from collections import defaultdict
from copy import deepcopy
from dataclasses import dataclass
from typing import List, Dict, Any, Optional

import torch
from vllm import LLM, SamplingParams
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

        # Lazy initialization of vLLM
        self.llm = None
        self.sampling_params = None

        self.file_manager = FileManager(args)
        self.message_processor = MessageProcessor(args)

        # Initialize prompt builder
        self.prompt_builder = get_prompt_builder(args.prompt_strategy)

        self.processed_instances = defaultdict(int)

        # Batch processing configuration
        self.batch_size = getattr(args, 'batch_size', 32)
        self.max_retries = getattr(args, 'max_retries', 5)

    def _load_rope_config_from_model(self) -> Dict[str, Any]:
        """
        Read RoPE-related configuration from the model's config.json.
        Follows the official vLLM format.

        Returns:
            dict containing RoPE configuration.
        """
        import json
        from pathlib import Path

        model_path = Path(self.args.model)
        config_file = model_path / "config.json"

        rope_config = {}

        if not config_file.exists():
            print(f"⚠ Warning: config.json not found at {config_file}")
            print(f"  Will use default parameters")
            return rope_config

        try:
            with open(config_file, 'r') as f:
                config = json.load(f)

            print("\n" + "=" * 70)
            print("Reading RoPE config from model config.json:")
            print("=" * 70)

            # 1. max_position_embeddings (required)
            if 'max_position_embeddings' in config:
                max_pos_emb = config['max_position_embeddings']
                rope_config['max_model_len'] = max_pos_emb
                print(f"  max_position_embeddings: {max_pos_emb}")
                print(f"  → max_model_len: {max_pos_emb}")
            else:
                print(f"  ⚠ max_position_embeddings not found, using default 32768")
                rope_config['max_model_len'] = 32768

            # 2. rope_scaling (vLLM official format)
            if 'rope_scaling' in config and config['rope_scaling']:
                rope_scaling_config = config['rope_scaling']

                vllm_rope_scaling = {}

                # rope_type (required)
                if 'rope_type' in rope_scaling_config:
                    vllm_rope_scaling['rope_type'] = rope_scaling_config['rope_type']
                elif 'type' in rope_scaling_config:
                    vllm_rope_scaling['rope_type'] = rope_scaling_config['type']
                else:
                    vllm_rope_scaling['rope_type'] = 'linear'  # default

                # factor (required)
                if 'factor' in rope_scaling_config:
                    vllm_rope_scaling['factor'] = float(rope_scaling_config['factor'])
                else:
                    vllm_rope_scaling['factor'] = 1.0

                # original_max_position_embeddings (required for YaRN)
                if 'original_max_position_embeddings' in rope_scaling_config:
                    vllm_rope_scaling['original_max_position_embeddings'] = \
                        rope_scaling_config['original_max_position_embeddings']

                rope_config['rope_scaling'] = vllm_rope_scaling

                print(f"  rope_scaling:")
                for key, value in vllm_rope_scaling.items():
                    print(f"    {key}: {value}")
            else:
                print(f"  rope_scaling: Not configured")

            # 3. rope_theta (optional)
            if 'rope_theta' in config:
                rope_config['rope_theta'] = float(config['rope_theta'])
                print(f"  rope_theta: {config['rope_theta']}")

            # 4. Display computed context length
            if 'rope_scaling' in rope_config:
                original_len = rope_config['rope_scaling'].get(
                    'original_max_position_embeddings',
                    rope_config.get('max_model_len', 32768)
                )
                factor = rope_config['rope_scaling'].get('factor', 1.0)
                extended_len = rope_config.get('max_model_len', 32768)

                print(f"\n  Context length calculation:")
                print(f"    Original: {original_len}")
                print(f"    Factor: {factor}x")
                print(f"    Extended: {extended_len}")

                if extended_len == int(original_len * factor):
                    print(f"    ✓ Matches expected: {original_len} × {factor} = {extended_len}")
                else:
                    print(f"    ⚠ Note: max_position_embeddings ({extended_len}) "
                          f"!= original × factor ({int(original_len * factor)})")

            print("=" * 70 + "\n")

            return rope_config

        except Exception as e:
            print(f"⚠ Warning: Could not read config.json: {e}")
            import traceback
            traceback.print_exc()
            return rope_config

    def _verify_rope_config(self):
        """Verify that the RoPE configuration has been applied correctly."""
        try:
            model_config = self.llm.llm_engine.model_config

            print("\n" + "=" * 70)
            print("Verifying Applied RoPE Configuration:")
            print("=" * 70)

            # 1. max_model_len
            print(f"✓ Max model length: {model_config.max_model_len}")

            # 2. rope_scaling
            if hasattr(model_config, 'rope_scaling') and model_config.rope_scaling:
                print(f"✓ RoPE scaling:")
                if isinstance(model_config.rope_scaling, dict):
                    for key, value in model_config.rope_scaling.items():
                        print(f"    {key}: {value}")
                else:
                    print(f"    {model_config.rope_scaling}")
            else:
                print(f"✗ RoPE scaling: Not enabled")

            # 3. rope_theta
            if hasattr(model_config, 'rope_theta'):
                print(f"✓ RoPE theta: {model_config.rope_theta}")

            # 4. Compare original vs current context length
            if hasattr(model_config, 'max_position_embeddings'):
                original_len = model_config.max_position_embeddings
                current_len = model_config.max_model_len

                print(f"\nContext length:")
                print(f"  Original max_position_embeddings: {original_len}")
                print(f"  Current max_model_len: {current_len}")

                if current_len > original_len:
                    extension_factor = current_len / original_len
                    print(f"  ✓ Extended by {extension_factor:.2f}x")
                elif current_len == original_len:
                    print(f"  ℹ Using original length (no extension)")
                else:
                    print(f"  ⚠ Warning: Current < Original")

            # 5. Verify consistency with config.json
            if hasattr(model_config, 'rope_scaling') and model_config.rope_scaling:
                rope_scaling = model_config.rope_scaling
                if isinstance(rope_scaling, dict):
                    rope_type = rope_scaling.get('rope_type', 'N/A')
                    factor = rope_scaling.get('factor', 'N/A')
                    original_max = rope_scaling.get('original_max_position_embeddings', 'N/A')

                    print(f"\nRoPE configuration summary:")
                    print(f"  Type: {rope_type}")
                    print(f"  Factor: {factor}")
                    print(f"  Original max: {original_max}")

                    if rope_type == 'yarn' and original_max != 'N/A':
                        print(f"  ✓ YaRN configuration complete")
                    elif rope_type == 'linear':
                        print(f"  ✓ Linear scaling configuration")

            print("=" * 70 + "\n")

        except Exception as e:
            print(f"⚠ Warning: Could not verify RoPE config: {e}")
            import traceback
            traceback.print_exc()

    def _initialize_vllm(self):
        """
        Initialize the vLLM model (synchronous version).
        Automatically reads RoPE config from config.json and stop tokens from tokenizer config.
        """
        if self.llm is not None:
            return

        print("=" * 70)
        print("Initializing vLLM Model (Synchronous Mode)...")
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
        print(f"  CUDA_VISIBLE_DEVICES: {visible_devices if visible_devices else 'Not set (using all GPUs)'}")
        print(f"  Tensor parallel size: {world_size}")

        # 3. Build vLLM initialization parameters
        try:
            vllm_kwargs = {
                'model': self.args.model,
                'trust_remote_code': True,
                'tensor_parallel_size': world_size,
            }

            # Apply RoPE configuration
            if rope_config.get('max_model_len'):
                vllm_kwargs['max_model_len'] = rope_config['max_model_len']
                print(f"\n✓ max_model_len: {rope_config['max_model_len']} (from max_position_embeddings)")
            else:
                vllm_kwargs['max_model_len'] = 32768
                print(f"\n✓ max_model_len: 32768 (default)")

            if rope_config.get('rope_scaling'):
                vllm_kwargs['rope_scaling'] = rope_config['rope_scaling']
                print(f"✓ rope_scaling: {rope_config['rope_scaling']}")
            else:
                print(f"✗ rope_scaling: Not configured (using model default)")

            if rope_config.get('rope_theta'):
                vllm_kwargs['rope_theta'] = rope_config['rope_theta']
                print(f"✓ rope_theta: {rope_config['rope_theta']}")

            # GPU memory utilization
            if hasattr(self.args, 'gpu_memory_utilization'):
                vllm_kwargs['gpu_memory_utilization'] = self.args.gpu_memory_utilization
            else:
                vllm_kwargs['gpu_memory_utilization'] = 0.9

            print(f"✓ GPU memory utilization: {vllm_kwargs['gpu_memory_utilization']}")

            print(f"\nvLLM initialization parameters:")
            for key, value in vllm_kwargs.items():
                if key == 'rope_scaling' and isinstance(value, dict):
                    print(f"  {key}:")
                    for k, v in value.items():
                        print(f"    {k}: {v}")
                else:
                    print(f"  {key}: {value}")

            # 4. Initialize model
            print(f"\nLoading model...")
            from vllm import LLM
            self.llm = LLM(**vllm_kwargs)
            print("✓ vLLM model loaded successfully")

            # 5. Verify RoPE configuration
            self._verify_rope_config()

        except Exception as e:
            print(f"✗ Error loading vLLM model: {e}")
            import traceback
            traceback.print_exc()
            raise

        # 6. Configure stop conditions
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
                tokenizer = self.llm.get_tokenizer()

                if not hasattr(self.args, 'tokenizer') or self.args.tokenizer is None:
                    self.args.tokenizer = tokenizer

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

        # Priority 3: read basic stop tokens directly from vLLM tokenizer
        if not stop_token_ids:
            print(f"\n[Priority 3] Reading from vLLM tokenizer attributes...")
            try:
                tokenizer = self.llm.get_tokenizer()

                if hasattr(tokenizer, 'eos_token_id') and tokenizer.eos_token_id is not None:
                    stop_token_ids.append(tokenizer.eos_token_id)
                    eos_token = tokenizer.eos_token if hasattr(tokenizer, 'eos_token') else 'N/A'
                    print(f"  ✓ EOS token: {eos_token} -> ID {tokenizer.eos_token_id}")

                if hasattr(tokenizer, 'pad_token_id') and tokenizer.pad_token_id is not None:
                    if tokenizer.pad_token_id not in stop_token_ids:
                        stop_token_ids.append(tokenizer.pad_token_id)
                        pad_token = tokenizer.pad_token if hasattr(tokenizer, 'pad_token') else 'N/A'
                        print(f"  ✓ PAD token: {pad_token} -> ID {tokenizer.pad_token_id}")

            except Exception as e:
                print(f"  ✗ Warning: Could not read tokenizer attributes: {e}")

        # Priority 4: hardcoded fallback for Qwen3
        if not stop_token_ids:
            print(f"\n[Priority 4] Using hardcoded fallback stop token IDs for Qwen3")
            stop_token_ids = [
                151643,  # <|endoftext|>
                151645,  # <|im_end|>
                151644,  # <|im_start|>
            ]
            print(f"  Fallback IDs: {stop_token_ids}")

        if not stop_strings:
            print(f"\n[Priority 4] Using hardcoded fallback stop strings")
            stop_strings = [
                "<|im_end|>",
                "<|endoftext|>",
                "<|im_start|>",
            ]
            print(f"  Fallback strings: {stop_strings}")

        # 7. Configure sampling parameters
        print("\n" + "=" * 70)
        print("Configuring Sampling Parameters")
        print("=" * 70)

        from vllm import SamplingParams

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

        if hasattr(self.args, 'repetition_penalty'):
            sampling_params_dict['repetition_penalty'] = self.args.repetition_penalty

        if hasattr(self.args, 'frequency_penalty'):
            sampling_params_dict['frequency_penalty'] = self.args.frequency_penalty

        if hasattr(self.args, 'presence_penalty'):
            sampling_params_dict['presence_penalty'] = self.args.presence_penalty

        try:
            self.sampling_params = SamplingParams(**sampling_params_dict)
            print("\n✓ Sampling parameters configured successfully")
        except Exception as e:
            print(f"\n✗ Error creating SamplingParams: {e}")
            print(f"   Params dict: {sampling_params_dict}")
            raise

        # 8. Print final configuration summary
        print("\n" + "=" * 70)
        print("Final Configuration Summary")
        print("=" * 70)

        print("\n[Model Configuration]")
        print(f"  Model path: {self.args.model}")
        print(f"  Max model length: {vllm_kwargs.get('max_model_len', 'N/A')}")
        print(f"  Tensor parallel size: {world_size}")
        print(f"  GPU memory utilization: {vllm_kwargs.get('gpu_memory_utilization', 'N/A')}")

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

        if hasattr(self, 'batch_size'):
            print(f"\n[Batch Configuration]")
            print(f"  Batch size: {self.batch_size}")

        print("\n" + "=" * 70)
        print("vLLM Initialization Complete")
        print("=" * 70 + "\n")

    def _get_result_file_path(self, instance_id: str) -> str:
        """Get the result file path for a given instance."""
        return os.path.join(self.args.output_folder, f"{instance_id}.json")

    def _is_instance_completed(self, instance_id: str) -> bool:
        """Check whether a given instance has already been completed."""
        result_file = self._get_result_file_path(instance_id)
        return os.path.exists(result_file)

    def _load_completed_instances(self) -> set:
        """Load all completed instance IDs from the output folder."""
        completed = set()
        if not os.path.exists(self.args.output_folder):
            return completed

        for filename in os.listdir(self.args.output_folder):
            if filename.endswith('.json'):
                # Strip the .json suffix to get the instance_id
                instance_id = filename[:-5]
                completed.add(instance_id)

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
                if "role" not in msg:
                    messages[i]["role"] = "user"
                if "content" not in msg:
                    messages[i]["content"] = ""

        return ConversationState(
            instance_id=instance_id,
            rollout_idx=rollout_idx,
            item=item,
            messages=messages,
            conversation_history=deepcopy(messages),
            current_round=0,
            terminated=False
        )

    def batch_generate(self, conversations: List[ConversationState]) -> List[Optional[str]]:
        """Batch-generate responses (synchronous; vLLM is synchronous)."""
        if not conversations:
            return []

        try:
            prompts = []
            for conv in conversations:
                prompt = self.prompt_builder.render_prompt(conv.messages, self.args)
                prompts.append(prompt)

            outputs = self.llm.generate(prompts, self.sampling_params)

            responses = []
            for output in outputs:
                if output and len(output.outputs) > 0:
                    content = output.outputs[0].text.strip()
                    responses.append(content if content else None)
                else:
                    responses.append(None)

            return responses

        except Exception as e:
            print(f"Batch generation error: {e}")
            import traceback
            traceback.print_exc()
            return [None] * len(conversations)

    async def process_batch_responses(self, conversations: List[ConversationState],
                                      responses: List[Optional[str]]) -> List[ConversationState]:
        """
        Asynchronously process batch responses and return conversations that should continue.
        """
        continue_conversations = []

        tasks = []
        valid_conversations = []

        for conv, response in zip(conversations, responses):
            # Handle failed responses
            if response is None or response == "":
                conv.retry_count += 1
                if conv.retry_count >= self.max_retries:
                    conv.error = f"Failed after {self.max_retries} retries"
                    conv.terminated = False
                    self.save_conversation(conv)
                    print(f"✗ {conv.instance_id} rollout {conv.rollout_idx + 1} failed at round {conv.current_round + 1}")
                else:
                    # Retry
                    continue_conversations.append(conv)
                    print(f"⚠ {conv.instance_id} rollout {conv.rollout_idx + 1} retry {conv.retry_count}/{self.max_retries}")
                continue

            conv.retry_count = 0

            # Create async task for business logic
            task = self.message_processor.process_round(
                response,
                conv.item,
                conv.messages,
                conv.conversation_history
            )
            tasks.append(task)
            valid_conversations.append(conv)

        # Execute all async tasks concurrently
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for conv, result in zip(valid_conversations, results):
                if isinstance(result, Exception):
                    conv.error = str(result)
                    conv.terminated = False
                    self.save_conversation(conv)
                    print(f"✗ {conv.instance_id} rollout {conv.rollout_idx + 1} error: {result}")
                    import traceback
                    traceback.print_exc()
                    continue

                conv.current_round += 1

                if result.get("terminated"):
                    conv.terminated = True
                    self.save_conversation(conv)
                    print(f"✓ {conv.instance_id} rollout {conv.rollout_idx + 1} TERMINATED at round {conv.current_round}")
                    continue

                if conv.current_round >= self.args.max_rounds:
                    conv.terminated = False
                    self.save_conversation(conv)
                    print(f"⚠ {conv.instance_id} rollout {conv.rollout_idx + 1} INCOMPLETE (max rounds)")
                    continue

                if result.get("continue"):
                    continue_conversations.append(conv)
                else:
                    continue_conversations.append(conv)

        return continue_conversations

    def save_conversation(self, conv: ConversationState):
        """Save conversation result to file."""
        result = conv.to_result()
        self.file_manager.add_single_result(result)

        # Only count successfully terminated conversations
        if conv.terminated and not conv.error:
            self.processed_instances[conv.instance_id] += 1

    async def run_async(self):
        """
        Async main entry point — batch processing with resume support.
        """
        print("\n" + "=" * 70)
        print("Starting Batch LLM Agent with Resume Support (Async Mode)")
        print("=" * 70)

        os.makedirs(self.args.output_folder, exist_ok=True)

        # Load completed instances
        completed_instances = self._load_completed_instances()
        print(f"\n✓ Found {len(completed_instances)} completed instances")

        with open(self.args.input_file, 'r', encoding='utf-8') as f:
            items = [json.loads(line) for line in f]

        # Filter out already-completed items
        original_count = len(items)
        items = [item for item in items if item["id"] not in completed_instances]
        skipped_count = original_count - len(items)

        if skipped_count > 0:
            print(f"✓ Skipped {skipped_count} already completed instances")

        if not items:
            print("\n✓ All instances have been completed successfully!")
            return

        random.shuffle(items)

        # Initialize all conversations to process
        all_conversations = []
        for item in items:
            instance_id = item["id"]
            for rollout_idx in range(self.args.rollout_number):
                conv = self.initialize_conversation(item, rollout_idx)
                all_conversations.append(conv)

        total_expected = original_count * self.args.rollout_number
        total_completed = len(completed_instances) * self.args.rollout_number
        total_to_process = len(all_conversations)

        print(f"\nConfiguration:")
        print(f"  Total items: {original_count}")
        print(f"  Rollout number: {self.args.rollout_number}")
        print(f"  Max rounds: {self.args.max_rounds}")
        print(f"  Batch size: {self.batch_size}")
        print(f"  Prompt strategy: {self.args.prompt_strategy}")
        print(f"  Model: {self.args.model}")
        print(f"\nProgress:")
        print(f"  Total expected tasks: {total_expected}")
        print(f"  Completed tasks: {total_completed}")
        print(f"  Remaining tasks: {total_to_process}")
        print(f"  Remaining items: {len(items)}")

        # Initialize vLLM
        self._initialize_vllm()

        print("=" * 70 + "\n")

        total_conversations = len(all_conversations)
        completed_conversations = 0
        start_time = time.time()

        num_batches = (total_conversations + self.batch_size - 1) // self.batch_size

        for batch_idx in range(num_batches):
            batch_start_idx = batch_idx * self.batch_size
            batch_end_idx = min(batch_start_idx + self.batch_size, total_conversations)
            current_batch = all_conversations[batch_start_idx:batch_end_idx]

            print(f"\n{'='*70}")
            print(f"Processing Batch {batch_idx + 1}/{num_batches}")
            print(f"  Conversations in this batch: {len(current_batch)}")
            print(f"  Overall progress: {completed_conversations}/{total_conversations} completed")
            print(f"{'='*70}")

            active_in_batch = current_batch
            round_num = 0

            while active_in_batch:
                round_num += 1
                print(f"\n  --- Batch {batch_idx + 1}, Round {round_num} ---")
                print(f"  Active conversations in batch: {len(active_in_batch)}")

                # Batch generation (synchronous; vLLM is synchronous)
                batch_start = time.time()
                responses = self.batch_generate(active_in_batch)
                batch_time = time.time() - batch_start

                print(f"  Generation time: {batch_time:.2f}s "
                      f"({len(active_in_batch)/batch_time:.2f} conv/s)")

                # Async response processing (concurrent SQL/IO operations)
                process_start = time.time()
                active_in_batch = await self.process_batch_responses(active_in_batch, responses)
                process_time = time.time() - process_start

                completed_in_round = len(current_batch) - len(active_in_batch) - \
                                     (len(current_batch) - len(active_in_batch) if round_num == 1 else 0)

                print(f"  Processing time: {process_time:.2f}s")
                print(f"  Completed in this round: {completed_in_round}")
                print(f"  Remaining in batch: {len(active_in_batch)}")

            batch_completed = len(current_batch)
            completed_conversations += batch_completed

            elapsed_time = time.time() - start_time
            progress_pct = (completed_conversations / total_conversations) * 100
            avg_time_per_conv = elapsed_time / max(completed_conversations, 1)
            eta_seconds = avg_time_per_conv * (total_conversations - completed_conversations)

            print(f"\n{'='*70}")
            print(f"Batch {batch_idx + 1}/{num_batches} Completed!")
            print(f"  Conversations completed in this batch: {batch_completed}")
            print(f"  Total completed: {completed_conversations}/{total_conversations} ({progress_pct:.1f}%)")
            print(f"  Elapsed time: {elapsed_time/60:.1f} min")
            print(f"  ETA: {eta_seconds/60:.1f} min")
            print(f"  Avg speed: {completed_conversations/elapsed_time:.2f} conv/s")
            print(f"{'='*70}\n")

        total_time = time.time() - start_time

        print("\n" + "=" * 70)
        print(f"✓ All processing completed!")
        print(f"  Results saved to: {self.args.output_folder}")
        print(f"  Total conversations processed: {completed_conversations}")
        print(f"  Total time: {total_time/60:.1f} minutes")
        print(f"  Average speed: {completed_conversations/total_time:.2f} conversations/second")
        print(f"  Average time per conversation: {total_time/completed_conversations:.2f} seconds")
        print("⚠️  Skipping vLLM cleanup to avoid hanging...")
        print("👋 Exiting...")

        # Exit directly without cleaning up vLLM to avoid hangs
        os._exit(0)

    def run(self):
        """Synchronous entry point: wraps async execution."""
        asyncio.run(self.run_async())


# Backward-compatible alias
class LLMAgent(BatchLLMAgent):
    """Backward-compatible alias for BatchLLMAgent."""
    pass
