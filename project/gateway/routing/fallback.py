"""
fallback.py

Determines the next provider/model to try when automatic routing
is enabled.

This class never calls an LLM provider.
It only selects the next candidate.
"""

from project.database.model_repository import ModelRepository


class FallbackManager:

    def __init__(self):

        self.model_repository = ModelRepository()

    async def get_next_candidate(
        self,
        team_id: int,
        attempted: set[tuple[str, str]],
    ):
        """
        Returns the next provider/model pair that has not
        already been attempted.

        Parameters
        ----------
        team_id
            Team requesting inference.

        attempted
            Set containing
            (provider_name, model_name)
            pairs already attempted.

        Returns
        -------
        dict | None
        """

        allowed_models = await self.model_repository.get_allowed_models(
            team_id,
        )

        for candidate in allowed_models:

            key = (
                candidate["provider_name"],
                candidate["model_name"],
            )

            if key in attempted:
                continue

            return candidate

        return None