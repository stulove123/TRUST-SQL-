# -*- coding: utf-8 -*-
import argparse
from llm_agent_batch_async import LLMAgent

def main():
    parser = argparse.ArgumentParser()
    
    # Data paths
    parser.add_argument("--input_file", required=True, help="Input jsonl file path")
    parser.add_argument("--output_folder", required=True, help="Output folder path")
    parser.add_argument("--system_prompt_path", required=True, help="System prompt file path")
    parser.add_argument("--databases_path", required=True, help="Databases directory path")
    parser.add_argument("--documents_path", required=True, help="Documents directory path")
    
    # LLM settings
    parser.add_argument("--use_vllm", action="store_true", help="Use vLLM for local inference")
    parser.add_argument("--model", default="gpt-4", help="Model name")
    parser.add_argument("--temperature", type=float, default=0.7, help="Temperature")
    parser.add_argument("--top_p", type=float, default=0.9, help="Top-p")
    parser.add_argument("--max_new_tokens", type=int, default=4096, help="Max new tokens")

    # Jinja template settings
    parser.add_argument('--template_dir', type=str, default=None)
    parser.add_argument('--template_file', type=str, default='chat_template.jinja')
    parser.add_argument('--tool_choice', type=str, default='auto')
    
    # Execution settings
    parser.add_argument("--api_host", default="localhost", help="API host")
    parser.add_argument("--api_port", default="5000", help="API port")
    parser.add_argument("--max_rounds", type=int, default=20, help="Max conversation rounds")
    parser.add_argument("--num_threads", type=int, default=4, help="Number of threads")
    parser.add_argument("--rollout_number", type=int, default=1, help="Number of rollouts per example")
    
    parser.add_argument("--prompt_strategy", default="base", 
                       choices=["spider-agent","base"],
                       help="Prompt building strategy")
    # Batch processing optimization parameters
    parser.add_argument("--batch_size", type=int, default=1024, 
                       help="Batch size for vLLM inference (default: 32). "
                            "Adjust based on GPU memory: "
                            "24GB GPU -> 16-32, "
                            "40GB GPU -> 32-64, "
                            "80GB GPU -> 64-128")
    args = parser.parse_args()
    
    agent = LLMAgent(args)
    agent.run()

if __name__ == "__main__":
    main()