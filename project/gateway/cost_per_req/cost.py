def estimate_cost(
    input_tokens: int,
    output_tokens: int,
    input_price_per_1m: float = 0.0,
    output_price_per_1m: float = 0.0,
) -> float:
    """
    Calculate the total estimated cost (USD) for a request
    based on token counts and model pricing per 1M tokens.
    """
    input_cost = (input_tokens / 1_000_000) * float(input_price_per_1m)
    output_cost = (output_tokens / 1_000_000) * float(output_price_per_1m)

    return round(input_cost + output_cost, 6)