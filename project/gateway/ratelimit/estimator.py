"""
estimator.py

Estimates input token count before the LLM call
so the TPM bucket can reserve the correct amount.

Strategy:
    - OpenAI / Groq: Use tiktoken (cl100k_base encoding).
    - Anthropic / Gemini / Ollama: Character-based approximation (len / 4).
"""

import tiktoken

from project.gateway.schemas.request import ChatRequest

# Pre-load the tiktoken encoding once at module level.
_cl100k_encoding = None


def _get_tiktoken_encoding():
    global _cl100k_encoding
    if _cl100k_encoding is None:
        _cl100k_encoding = tiktoken.get_encoding("cl100k_base")
    return _cl100k_encoding


# Providers that use tiktoken-compatible tokenizers.
TIKTOKEN_PROVIDERS = {"openai", "groq"}


class TokenEstimator:
    """
    Estimates the total token cost of a request
    before the provider call.

    estimated_cost = estimated_input_tokens + max_output_tokens
    """

    def estimate(
        self,
        request: ChatRequest,
        provider_name: str,
    ) -> int:
        """
        Estimate total token cost for rate limiting reservation.

        Parameters
        ----------
        request : ChatRequest
            The incoming chat request.
        provider_name : str
            The name of the provider (openai, groq, anthropic, etc.).

        Returns
        -------
        int
            Estimated total tokens (input + max output).
        """

        input_tokens = self._estimate_input_tokens(request, provider_name)

        max_output = request.max_tokens if request.max_tokens else 4096

        return input_tokens + max_output

    def _estimate_input_tokens(
        self,
        request: ChatRequest,
        provider_name: str,
    ) -> int:
        """
        Estimate input token count from system prompt + messages.
        """

        # Collect all text content.
        text_parts = []

        if request.system_prompt:
            text_parts.append(request.system_prompt)

        for message in request.messages:
            if message.content:
                text_parts.append(message.content)

        full_text = "\n".join(text_parts)

        if provider_name.lower() in TIKTOKEN_PROVIDERS:
            return self._tiktoken_count(full_text)

        return self._char_approximation(full_text)

    @staticmethod
    def _tiktoken_count(text: str) -> int:
        """
        Accurate token count using tiktoken (cl100k_base).
        Used for OpenAI and Groq models.
        """

        encoding = _get_tiktoken_encoding()
        return len(encoding.encode(text))

    @staticmethod
    def _char_approximation(text: str) -> int:
        """
        Conservative character-based approximation.

        ~4 characters per token is a safe estimate
        that slightly over-reserves. The refund after
        the response corrects the bucket.
        """

        return max(1, len(text) // 4)
