class ValidationError(Exception):
    """Base validation exception."""


class InvalidAPIKeyError(ValidationError):
    """Invalid team API key."""


class UnknownProviderError(ValidationError):
    """Unknown provider."""


class UnknownModelError(ValidationError):
    """Unknown model."""


class ProviderDisabledError(ValidationError):
    """Provider is disabled."""


class ModelDisabledError(ValidationError):
    """Model is disabled."""


class ModelNotAllowedError(ValidationError):
    """Team is not allowed to use this model."""


class BudgetExceededError(ValidationError):
    """Budget cap exceeded (monthly or daily)."""

    def __init__(
        self,
        message: str,
        budget_type: str = "monthly",
        limit: float = 0.0,
        current_spend: float = 0.0,
        estimated_cost: float = 0.0,
    ):
        super().__init__(message)
        self.message = message
        self.budget_type = budget_type
        self.limit = limit
        self.current_spend = current_spend
        self.estimated_cost = estimated_cost


class RequestTypeNotAllowedError(ValidationError):
    """Request type is not allowed for team."""
