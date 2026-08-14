"""
tier.py

Configurable Model Tier Taxonomy and Registry (FLAGSHIP, BALANCED, FAST).
"""

from enum import Enum


class ModelTier(str, Enum):
    FLAGSHIP = "FLAGSHIP"
    BALANCED = "BALANCED"
    FAST = "FAST"


DEFAULT_TIER_CONFIG: dict[str, ModelTier] = {
    "gpt-4.1": ModelTier.FLAGSHIP,
    "openai:gpt-4.1": ModelTier.FLAGSHIP,
    "claude-3-5-sonnet-20241022": ModelTier.FLAGSHIP,
    "anthropic:claude-3-5-sonnet-20241022": ModelTier.FLAGSHIP,
    "gemini-2.5-flash": ModelTier.BALANCED,
    "google:gemini-2.5-flash": ModelTier.BALANCED,
    "llama-3.3-70b-versatile": ModelTier.BALANCED,
    "groq:llama-3.3-70b-versatile": ModelTier.BALANCED,
    "gemma4": ModelTier.FAST,
    "ollama:gemma4": ModelTier.FAST,
}


class TierRegistry:
    """
    Registry managing model tier classifications.
    Configuration can be loaded dynamically or overridden at runtime.
    """

    def __init__(self, mapping: dict[str, ModelTier] | None = None):
        self._mapping = mapping or DEFAULT_TIER_CONFIG.copy()

    def get_tier(self, model_name: str) -> ModelTier:
        # Check direct model_name or fallback to BALANCED
        return self._mapping.get(model_name, ModelTier.BALANCED)

    def set_tier(self, model_name: str, tier: ModelTier) -> None:
        self._mapping[model_name] = tier
