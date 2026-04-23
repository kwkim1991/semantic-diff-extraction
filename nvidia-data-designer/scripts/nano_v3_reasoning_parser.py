"""
(optional)
bash scripts/launch_nemotron_nano.sh bf16    # Option A: BF16 (1x H100/A100 80GB)
bash scripts/launch_nemotron_nano.sh fp8     # Option B: FP8 (1x H100 80GB)
bash scripts/launch_nemotron_nano.sh nvfp4   # Option C: NVFP4 (1x B200)

"""


from vllm.reasoning.abs_reasoning_parsers import ReasoningParserManager
from vllm.reasoning.deepseek_r1_reasoning_parser import DeepSeekR1ReasoningParser


@ReasoningParserManager.register_module("nano_v3")
class NanoV3ReasoningParser(DeepSeekR1ReasoningParser):
    def extract_reasoning(self, model_output, request):
        reasoning_content, final_content = super().extract_reasoning(
            model_output, request
        )
        if (
            hasattr(request, "chat_template_kwargs")
            and request.chat_template_kwargs
            and request.chat_template_kwargs.get("enable_thinking") is False
            and final_content is None
        ):
            reasoning_content, final_content = final_content, reasoning_content

        return reasoning_content, final_content