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
    """Monthly budget exceeded."""