"""
router.py

Routes validated requests to the appropriate provider.

The router assumes that validation has already
been performed.
"""

from project.gateway.routing.provider_factory import (
    ProviderFactory,
)
from project.gateway.cost_per_req.cost import estimate_cost
from project.database.team_repository import TeamRepository
from project.gateway.schemas.request import ChatRequest
from project.gateway.schemas.response import ChatResponse
from project.gateway.routing.fallback import FallbackManager

from project.gateway.validation.result import (
    ValidationResult,
)


class Router:
    """
    Routes requests to providers.
    """
    def __init__(self):

        self.fallback = FallbackManager()
        self.team_repository = TeamRepository()

    async def route(
        self,
        validation: ValidationResult,
        request: ChatRequest,
        automatic_routing: bool = True,
    ) -> ChatResponse:
        """
        Route a request to the requested provider.

        If automatic routing is enabled, failed providers/models
        are skipped until a working candidate is found.
        """

        attempted = set()

        provider_name = validation.provider["provider_name"]
        model_name = validation.model["model_name"]

        while True:

            attempted.add(
                (
                    provider_name,
                    model_name,
                )
            )

            provider = ProviderFactory.create(
                provider_name,
            )

            request.model = model_name

            try:

                response = await provider.chat(request)

                # Record usage only after a successful provider response.

                if (
                    response.message is not None
                    and response.message.content
                    and response.usage is not None
                ):

                    cost = estimate_cost(
                        model=response.model,
                        input_tokens=response.usage.input_tokens,
                        output_tokens=response.usage.output_tokens,
                    )

                    await self.team_repository.add_usage(
                        team_id=validation.team["id"],
                        model_id=validation.model["id"],
                        input_tokens=response.usage.input_tokens,
                        output_tokens=response.usage.output_tokens,
                        estimated_cost=cost,
                    )

                await provider.close()
                return response

            except Exception:

                await provider.close()

                if not automatic_routing:
                    raise

                candidate = await self.fallback.get_next_candidate(
                    team_id=validation.team["id"],
                    attempted=attempted,
                )

                if candidate is None:

                    raise RuntimeError(
                        "No provider/model available for fallback."
                    )

                provider_name = candidate["provider_name"]
                model_name = candidate["model_name"]