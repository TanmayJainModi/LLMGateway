"""
validator.py

Validates an incoming gateway request before it reaches the router.

Responsibilities
----------------
- Validate the team API key
- Validate the requested provider
- Validate the requested model
- Validate the team's access to the model
- Validate the team's monthly budget

The validator does NOT perform routing or call any LLM provider.
"""

from project.database.team_repository import TeamRepository
from project.database.provider_repository import ProviderRepository
from project.database.model_repository import ModelRepository

from project.gateway.validation.result import ValidationResult
from project.gateway.validation.exceptions import (
    InvalidAPIKeyError,
    UnknownProviderError,
    UnknownModelError,
    ProviderDisabledError,
    ModelDisabledError,
    ModelNotAllowedError,
    BudgetExceededError,
)


from project.gateway.telemetry.tracer import gateway_tracer
import project.gateway.telemetry.attributes as attrs


class Validator:
    """
    Performs all gateway validation checks.
    """

    def __init__(self):
        self.team_repository = TeamRepository()
        self.provider_repository = ProviderRepository()
        self.model_repository = ModelRepository()

    async def validate(
        self,
        team_api_key: str,
        provider_name: str,
        model_name: str,
        estimated_cost: float = 0.0,
    ) -> ValidationResult:
        """
        Validate an incoming gateway request.
        """
        with gateway_tracer.start_span("authentication") as span:
            team = await self._validate_team(team_api_key)

            gateway_tracer.set_attributes(
                span,
                {
                    attrs.TEAM_ID: team["id"],
                    attrs.TEAM_NAME: team["name"],
                    attrs.PROVIDER_REQUESTED: provider_name,
                    attrs.MODEL_REQUESTED: model_name,
                    "gateway.auth_success": True,
                },
            )

            provider = await self._validate_provider(
                provider_name,
            )

            model = await self._validate_model(
                provider_name=provider_name,
                model_name=model_name,
            )

            team_access = await self._validate_team_access(
                team_id=team["id"],
                model_id=model["id"],
            )

            await self._validate_budget(team, estimated_cost)

            return ValidationResult(
                allowed=True,
                team=team,
                provider=provider,
                model=model,
                team_model_access=team_access,
            )


    async def _validate_team(
        self,
        api_key: str,
    ):
        """
        Validate the team API key.
        """

        team = await self.team_repository.get_team_by_api_key(
            api_key,
        )

        if team is None:
            raise InvalidAPIKeyError(
                "Invalid team API key."
            )

        return team

    async def _validate_provider(
        self,
        provider_name: str,
    ):
        """
        Validate the provider.
        """

        provider = await self.provider_repository.get_provider(
            provider_name,
        )

        if provider is None:
            raise UnknownProviderError(
                f"Unknown provider '{provider_name}'."
            )

        return provider

    async def _validate_model(
        self,
        provider_name: str,
        model_name: str,
    ):
        """
        Validate the model.
        """

        model = await self.model_repository.get_model(
            provider_name,
            model_name,
        )

        if model is None:
            raise UnknownModelError(
                f"Unknown model '{model_name}'."
            )

        return model

    async def _validate_team_access(
        self,
        team_id: int,
        model_id: int,
    ):
        """
        Validate that the team is allowed
        to use the requested model.
        """

        access = await self.model_repository.get_team_access(
            team_id,
            model_id,
        )

        if access is None:
            raise ModelNotAllowedError(
                "Your team is not allowed to use this model."
            )

        if not access["enabled"]:
            raise ModelNotAllowedError(
                "Access to this model has been disabled for your team."
            )

        return access

    async def _validate_budget(
        self,
        team,
        estimated_cost: float = 0.0,
    ):
        """
        Validate the team's monthly and daily budget caps (pre-flight check).
        """
        from datetime import date

        monthly_spend = float(team["monthly_spend"] or 0)
        monthly_budget = float(team["monthly_budget"])

        if (monthly_spend + estimated_cost) > monthly_budget:
            raise BudgetExceededError(
                message=f"Monthly budget cap exceeded (${monthly_spend + estimated_cost:.4f} / ${monthly_budget:.2f}).",
                budget_type="monthly",
                limit=monthly_budget,
                current_spend=monthly_spend,
                estimated_cost=estimated_cost,
            )

        if team.get("daily_budget") is not None:
            daily_budget = float(team["daily_budget"])
            today = date.today()

            if team.get("daily_spend_date") != today:
                effective_daily_spend = 0.0
            else:
                effective_daily_spend = float(team.get("daily_spend") or 0)

            if (effective_daily_spend + estimated_cost) > daily_budget:
                raise BudgetExceededError(
                    message=f"Daily budget cap exceeded (${effective_daily_spend + estimated_cost:.4f} / ${daily_budget:.2f}).",
                    budget_type="daily",
                    limit=daily_budget,
                    current_spend=effective_daily_spend,
                    estimated_cost=estimated_cost,
                )