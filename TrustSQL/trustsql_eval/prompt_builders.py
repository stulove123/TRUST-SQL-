import os
from transformers import AutoTokenizer


class BasePromptBuilder:

    def __init__(self):
        self.render_count = 0
        self._tokenizer_cache = None

    def _get_tokenizer(self, args):
        """
        Retrieve the tokenizer.
        Priority: args.tokenizer > cached tokenizer > load from template_dir.
        """
        # 1. Prefer tokenizer from args
        if hasattr(args, 'tokenizer') and args.tokenizer is not None:
            return args.tokenizer

        # 2. Use cached tokenizer
        if self._tokenizer_cache is not None:
            return self._tokenizer_cache

        # 3. Load from template_dir
        if not hasattr(args, 'template_dir') or not args.template_dir:
            raise ValueError(
                "Tokenizer not found. Please provide either:\n"
                "  1. args.tokenizer (AutoTokenizer instance)\n"
                "  2. args.template_dir (path to model directory)"
            )

        try:
            print(f"\n{'='*70}")
            print(f"Loading tokenizer from: {args.template_dir}")

            self._tokenizer_cache = AutoTokenizer.from_pretrained(
                args.template_dir,
                trust_remote_code=True,
                use_fast=True
            )

            print(f"✓ Tokenizer loaded successfully")
            print(f"  - Type: {type(self._tokenizer_cache).__name__}")
            print(f"  - Vocab size: {len(self._tokenizer_cache)}")

            # Check for chat template support
            if hasattr(self._tokenizer_cache, 'chat_template'):
                print(f"  - Chat template: Available")
            else:
                print(f"  ⚠️  Chat template: Not available")

            print(f"{'='*70}\n")

            # Cache in args for reuse
            args.tokenizer = self._tokenizer_cache

            return self._tokenizer_cache

        except Exception as e:
            raise ValueError(
                f"Failed to load tokenizer from {args.template_dir}\n"
                f"Error: {e}\n"
                f"Please ensure the path contains tokenizer files"
            )

    def _normalize_messages(self, messages):
        """Normalize the messages format to a list of dicts."""
        if isinstance(messages, str):
            return [{"role": "user", "content": messages}]

        if isinstance(messages, dict):
            if "role" in messages and "content" in messages:
                return [messages]
            return [{"role": "user", "content": str(messages)}]

        if not isinstance(messages, list):
            return [{"role": "user", "content": str(messages)}]

        normalized = []
        for msg in messages:
            if isinstance(msg, dict):
                if "role" not in msg:
                    msg = dict(msg)
                    msg["role"] = "user"
                if "content" not in msg:
                    msg = dict(msg)
                    msg["content"] = ""
                normalized.append(msg)
            elif isinstance(msg, str):
                normalized.append({"role": "user", "content": msg})
            else:
                normalized.append({"role": "user", "content": str(msg)})

        return normalized if normalized else [{"role": "user", "content": ""}]

    def load_system_prompt(self, system_prompt_path):
        """Load a system prompt from a file."""
        try:
            with open(system_prompt_path, 'r', encoding='utf-8') as f:
                return f.read().strip()
        except Exception as e:
            raise FileNotFoundError(f"Could not load system prompt from {system_prompt_path}: {e}")

    def render_prompt(self, messages, args):
        """
        Render a prompt using tokenizer.apply_chat_template.
        """
        # Normalize messages format
        messages = self._normalize_messages(messages)

        # Insert system prompt at the beginning if not already present
        has_system = any(msg.get("role") == "system" for msg in messages)
        if not has_system:
            system_prompt = self.load_system_prompt(args.system_prompt_path)
            messages = [{"role": "system", "content": system_prompt}] + messages

        self.render_count += 1

        if self.render_count % 128 == 0:
            print(f"\n{'='*70}")
            print(f"Prompt Render Debug (Every 128 calls)")
            print(f"{'='*70}")
            print(f"Messages count: {len(messages)}")
            for i, msg in enumerate(messages):
                role = msg.get('role', 'unknown')
                content_len = len(msg.get('content', ''))
                print(f"  [{i}] {role}: {content_len} chars")

        tokenizer = self._get_tokenizer(args)

        try:
            prompt = tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True
            )

            if self.render_count % 128 == 0:
                print(f"\n✓ Prompt rendered successfully")
                print(f"Prompt length: {len(prompt)} characters")
                print(prompt)
                print("-" * 70)
                print(f"{'='*70}\n")

            return prompt

        except Exception as e:
            print(f"❌ Error using apply_chat_template: {e}")
            print(f"Messages: {messages}")
            raise

    def load_external_knowledge(self, external_knowledge_file, documents_path):
        """Load external knowledge from a file."""
        if not external_knowledge_file:
            return None

        knowledge_path = os.path.join(documents_path, external_knowledge_file)
        if os.path.exists(knowledge_path):
            try:
                with open(knowledge_path, 'r', encoding='utf-8') as f:
                    return f.read().strip()
            except Exception as e:
                print(f"Warning: Could not load external knowledge: {e}")
                return None
        return None

    def build_initial_prompt(self, item, args):
        """Build the initial prompt for a given item."""
        # Load external knowledge if available
        external_knowledge = self.load_external_knowledge(
            item.get('external_knowledge'),
            args.documents_path
        )

        user_content_parts = []

        # Task configuration
        user_content_parts.append("**Task Configuration**")
        user_content_parts.append(f"**Database Engine:** SQLite")
        user_content_parts.append(f"**Database:** {item.get('db_id', 'unknown')}")

        if external_knowledge:
            user_content_parts.append(f"**External Knowledge:** {external_knowledge}")

        user_content_parts.append(f"**User Question:** {item.get('instruction', item.get('question', ''))}?")

        # Requirements
        user_content_parts.append("\n**Requirements**")
        user_content_parts.append("1. **Precision:** Make sure you only output the information that is asked in the question.")
        user_content_parts.append("2. **Completeness:** The generated query should return all of the information asked.")
        user_content_parts.append("3. **Correctness:** Think through the steps before generating the query.")

        # Output format
        user_content_parts.append("\n**Output Format:**")
        user_content_parts.append("<think> Your analysis... </think>")
        user_content_parts.append("<tool_call>{\"name\": \"execute_sql_query\", \"arguments\": {...}}</tool_call>")
        user_content_parts.append("OR")
        user_content_parts.append("<answer>\n```sql\nYOUR_SQL_QUERY\n```\n</answer>")

        user_content = "\n".join(user_content_parts)

        return [
            {"role": "user", "content": user_content}
        ]

    def get_stop_token_ids(self, args):
        """
        Read stop token IDs from the tokenizer config.
        Priority: config > hardcoded > empty list.
        """
        tokenizer = self._get_tokenizer(args)
        stop_ids = []

        print(f"\n{'='*70}")
        print("Reading Stop Tokens from Tokenizer Config")
        print(f"{'='*70}")

        # Method 1: read from added_tokens_decoder
        if hasattr(tokenizer, 'added_tokens_decoder'):
            print("\n[Method 1] Reading from added_tokens_decoder...")

            stop_token_contents = {
                '<|endoftext|>',
                '<|im_end|>',
                '<|im_start|>',  # prevent model from generating a new dialogue turn
            }

            for token_id_str, token_info in tokenizer.added_tokens_decoder.items():
                try:
                    token_id = int(token_id_str)

                    if isinstance(token_info, dict):
                        content = token_info.get('content', '')
                        is_special = token_info.get('special', False)
                    else:
                        content = getattr(token_info, 'content', str(token_info))
                        is_special = getattr(token_info, 'special', False)

                    if content in stop_token_contents:
                        stop_ids.append(token_id)
                        print(f"  ✓ Found: {content} -> ID {token_id} (special={is_special})")

                except (ValueError, AttributeError):
                    continue

        # Method 2: read directly from tokenizer attributes
        print("\n[Method 2] Reading from tokenizer attributes...")

        # EOS token
        if hasattr(tokenizer, 'eos_token_id') and tokenizer.eos_token_id is not None:
            if tokenizer.eos_token_id not in stop_ids:
                stop_ids.append(tokenizer.eos_token_id)
                eos_token = tokenizer.eos_token if hasattr(tokenizer, 'eos_token') else 'N/A'
                print(f"  ✓ EOS token: {eos_token} -> ID {tokenizer.eos_token_id}")

        # PAD token (sometimes used as a stop token)
        if hasattr(tokenizer, 'pad_token_id') and tokenizer.pad_token_id is not None:
            if tokenizer.pad_token_id not in stop_ids:
                stop_ids.append(tokenizer.pad_token_id)
                pad_token = tokenizer.pad_token if hasattr(tokenizer, 'pad_token') else 'N/A'
                print(f"  ✓ PAD token: {pad_token} -> ID {tokenizer.pad_token_id}")

        # Method 3: manually encode special strings
        print("\n[Method 3] Encoding special strings...")

        special_strings = [
            "<|im_end|>",
            "<|endoftext|>",
            "<|im_start|>",
        ]

        for special_str in special_strings:
            try:
                # Method 3.1: convert_tokens_to_ids
                if hasattr(tokenizer, 'convert_tokens_to_ids'):
                    token_id = tokenizer.convert_tokens_to_ids(special_str)
                    if token_id is not None and token_id != tokenizer.unk_token_id:
                        if token_id not in stop_ids:
                            stop_ids.append(token_id)
                            print(f"  ✓ Encoded (convert): {special_str} -> ID {token_id}")
                        continue

                # Method 3.2: encode
                ids = tokenizer.encode(special_str, add_special_tokens=False)
                if ids and len(ids) > 0:
                    token_id = ids[0]
                    if token_id not in stop_ids:
                        stop_ids.append(token_id)
                        print(f"  ✓ Encoded (encode): {special_str} -> ID {token_id}")

            except Exception as e:
                print(f"  ✗ Failed to encode '{special_str}': {e}")

        # Method 4: read from tokenizer_config.json
        print("\n[Method 4] Reading from tokenizer_config.json...")

        try:
            import json
            from pathlib import Path

            if hasattr(args, 'template_dir') and args.template_dir:
                tokenizer_dir = Path(args.template_dir)
            elif hasattr(tokenizer, 'name_or_path'):
                tokenizer_dir = Path(tokenizer.name_or_path)
            else:
                tokenizer_dir = None

            if tokenizer_dir and tokenizer_dir.exists():
                config_file = tokenizer_dir / "tokenizer_config.json"

                if config_file.exists():
                    with open(config_file, 'r', encoding='utf-8') as f:
                        config = json.load(f)

                    if 'eos_token' in config:
                        eos_info = config['eos_token']
                        if isinstance(eos_info, dict) and 'content' in eos_info:
                            eos_content = eos_info['content']
                        elif isinstance(eos_info, str):
                            eos_content = eos_info
                        else:
                            eos_content = None

                        if eos_content:
                            print(f"  ✓ Config eos_token: {eos_content}")

                    if 'additional_special_tokens' in config:
                        additional_tokens = config['additional_special_tokens']
                        print(f"  ✓ Additional special tokens: {additional_tokens}")

                    if 'added_tokens_decoder' in config:
                        print(f"  ✓ Found {len(config['added_tokens_decoder'])} tokens in config")

        except Exception as e:
            print(f"  ✗ Could not read tokenizer_config.json: {e}")

        # Deduplicate and sort
        stop_ids = sorted(list(set(stop_ids)))

        print(f"\n{'='*70}")
        print(f"Final Stop Token IDs: {stop_ids}")
        print(f"Total: {len(stop_ids)} unique token(s)")
        print(f"{'='*70}\n")

        if not stop_ids:
            print("⚠️  WARNING: No stop token IDs found!")
            print("   Model may generate indefinitely. Consider:")
            print("   1. Check if tokenizer is loaded correctly")
            print("   2. Manually specify stop_token_ids in args")
            print("   3. Use stop strings as fallback\n")

        return stop_ids

    def get_stop_strings(self):
        """
        Return string-form stop tokens (as a complement to stop token IDs).
        vLLM supports using both stop_token_ids and stop strings simultaneously.
        """
        return [
            "<|im_end|>",
            "<|endoftext|>",
            "<|im_start|>",  # prevent model from generating new dialogue turns
        ]

    def get_comprehensive_stop_config(self, args):
        """
        Return the complete stop configuration (recommended method).
        Returns: {"token_ids": [...], "strings": [...]}
        """
        return {
            "token_ids": self.get_stop_token_ids(args),
            "strings": self.get_stop_strings()
        }


def get_prompt_builder(strategy):
    """Get a prompt builder by strategy name."""
    builders = {
        "base": BasePromptBuilder(),
    }

    return builders.get(strategy, BasePromptBuilder())
