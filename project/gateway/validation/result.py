from dataclasses import dataclass

from asyncpg import Record


@dataclass
class ValidationResult:
    """
    Result returned by the validation layer.

    If validation succeeds, allowed=True and the corresponding
    database records are populated.

    If validation fails, allowed=False and reason contains
    the failure message.
    """

    allowed: bool

    reason: str | None = None

    team: Record | None = None

    provider: Record | None = None

    model: Record | None = None

    team_model_access: Record | None = None