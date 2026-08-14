"""
fallback.py

Determines the next provider/model to try when automatic routing is enabled.
Enforces Model Tier boundaries (FLAGSHIP, BALANCED, FAST), respects Health Service status,
and caps fallback depth at max_fallback_attempts.
"""

from project.database.model_repository import ModelRepository
from project.gateway.health.service import HealthService, HealthStatus
from project.gateway.routing.tier import TierRegistry, ModelTier


class FallbackManager:
    """
    Tier-aware fallback candidate resolver.
    """

    def __init__(self, tier_registry: TierRegistry | None = None):
        self.model_repository = ModelRepository()
        self.health_service = HealthService()
        self.tier_registry = tier_registry or TierRegistry()

    async def get_next_candidate(
        self,
        team_id: int,
        primary_model_name: str,
        attempted: set[tuple[str, str]],
        fallback_attempts: int = 0,
        allow_cross_tier: bool = False,
        max_fallback_attempts: int = 2,
    ) -> tuple[dict, str] | None:
        """
        Selects the best available candidate in the same model tier.

        Parameters
        ----------
        team_id : int
            Team ID.
        primary_model_name : str
            Requested model name.
        attempted : set[tuple[str, str]]
            Set of (provider_name, model_name) pairs already attempted.
        fallback_attempts : int
            Number of fallback attempts already made (max = 2).
        allow_cross_tier : bool
            If True, permits falling back to lower model tiers when no same-tier models exist.
        max_fallback_attempts : int
            Maximum permitted fallback attempts (default 2).

        Returns
        -------
        tuple[dict, str] | None
            (candidate_dict, fallback_reason) or None if no candidate available.
        """
        # Guard: Stop if max fallback attempts reached
        if fallback_attempts >= max_fallback_attempts:
            return None

        primary_tier = self.tier_registry.get_tier(primary_model_name)
        allowed_models = await self.model_repository.get_allowed_models(team_id)

        healthy_same_tier = []
        degraded_same_tier = []
        other_tier_candidates = []

        for candidate in allowed_models:
            p_name = candidate["provider_name"]
            m_name = candidate["model_name"]
            key = (p_name, m_name)

            if key in attempted:
                continue

            status = await self.health_service.get_current_status(p_name, m_name)
            if status == HealthStatus.DOWN:
                continue

            cand_tier = self.tier_registry.get_tier(m_name)

            if cand_tier == primary_tier:
                if status == HealthStatus.HEALTHY or status == HealthStatus.RECOVERING:
                    healthy_same_tier.append(candidate)
                elif status == HealthStatus.DEGRADED:
                    degraded_same_tier.append(candidate)
            elif allow_cross_tier:
                if status != HealthStatus.DOWN:
                    other_tier_candidates.append(candidate)

        # 1. Same Tier HEALTHY candidate
        if healthy_same_tier:
            cand = healthy_same_tier[0]
            reason = f"Primary model {primary_model_name} unavailable; routed to healthy same-tier model {cand['model_name']} ({primary_tier.value})"
            return cand, reason

        # 2. Same Tier DEGRADED candidate (preferred over cross-tier/failure)
        if degraded_same_tier:
            cand = degraded_same_tier[0]
            reason = f"Primary model {primary_model_name} unavailable; routed to degraded same-tier model {cand['model_name']} ({primary_tier.value})"
            return cand, reason

        # 3. Cross Tier candidate (only if explicitly enabled)
        if allow_cross_tier and other_tier_candidates:
            cand = other_tier_candidates[0]
            cand_tier = self.tier_registry.get_tier(cand['model_name'])
            reason = f"Primary model {primary_model_name} ({primary_tier.value}) unavailable; cross-tier fallback to {cand['model_name']} ({cand_tier.value})"
            return cand, reason

        return None