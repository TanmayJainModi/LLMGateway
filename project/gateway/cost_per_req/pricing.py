"""
Approximate pricing per 1M tokens (USD).

Update these values whenever providers change pricing.
"""

MODEL_PRICING = {

    "gemini-2.5-flash": {
        "input": 0.30,
        "output": 2.50,
    },

    "gpt-4.1": {
        "input": 2.00,
        "output": 8.00,
    },

    "claude-3-5-sonnet-20241022": {
        "input": 3.00,
        "output": 15.00,
    },

    "llama-3.3-70b-versatile": {
        "input": 0.59,
        "output": 0.79,
    },

    "gemma4": {
        "input": 0.10,
        "output": 0.30,
    },
}