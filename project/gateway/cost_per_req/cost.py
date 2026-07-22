from project.gateway.cost_per_req.pricing import MODEL_PRICING


def estimate_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
) -> float:

    pricing = MODEL_PRICING[model]

    input_cost = (
        input_tokens / 1_000_000
    ) * pricing["input"]

    output_cost = (
        output_tokens / 1_000_000
    ) * pricing["output"]

    return round(
        input_cost + output_cost,
        6,
    )