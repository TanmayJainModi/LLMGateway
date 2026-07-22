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


class Validator:
    """
    Performs all gateway validation checks.

    Validation order:

        1. Team API key
        2. Provider exists
        3. Provider enabled
        4. Model exists
        5. Model enabled
        6. Team has access
        7. Budget check
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
    ) -> ValidationResult:
        """
        Validate an incoming gateway request.

        Returns
        -------
        ValidationResult
        """

        team = await self._validate_team(team_api_key)

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

        await self._validate_budget(team)

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
    ):
        """
        Validate the team's monthly budget.
        """

        if team["monthly_spend"] >= team["monthly_budget"]:
            raise BudgetExceededError(
                "Monthly budget exceeded."
            )