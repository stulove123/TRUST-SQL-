"""
Quick smoke test for vLLM AsyncLLMEngine.

Usage:
    CUDA_VISIBLE_DEVICES=0 python test_vllm.py

Set MODEL_PATH to the local path of your model before running.
"""

import os
import asyncio

os.environ["CUDA_VISIBLE_DEVICES"] = "0"
os.environ["VLLM_USE_V1"] = "0"

from vllm import AsyncLLMEngine, SamplingParams
from vllm.engine.arg_utils import AsyncEngineArgs

# Replace with the actual path to your model
MODEL_PATH = "/path/to/your/model"


async def test():
    try:
        engine_args = AsyncEngineArgs(
            model=MODEL_PATH,
            trust_remote_code=True,
            disable_log_requests=False,
        )

        engine = AsyncLLMEngine.from_engine_args(engine_args)

        sampling_params = SamplingParams(temperature=0.7, max_tokens=50)

        print("Testing generation...")
        results = engine.generate("Hello, who are you?", sampling_params, "test-001")

        async for output in results:
            print(f"Output: {output.outputs[0].text}")

        print("✓ Test passed!")

    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test())
