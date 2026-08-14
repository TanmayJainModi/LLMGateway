import asyncio
import os
import asyncpg
from dotenv import load_dotenv

load_dotenv()

TEAM_POLICIES = [
    {
        "api_key": "founders-api-key",
        "default_system_prompt": "You are the Founders AI Assistant representing AcmeAI. Provide concise executive summaries.",
        "compliance_disclaimer": "CONFIDENTIAL: Internal executive communications only.",
        "blocked_keywords": ["secret_key", "sudo", "eval("],
        "enable_request_filter": True,
    },
    {
        "api_key": "tech-api-key",
        "default_system_prompt": "You are the Engineering Assistant. Prioritize code correctness, performance, and clear technical assumptions.",
        "compliance_disclaimer": "SECURITY NOTICE: Do not expose production secrets, environment variables, or private API keys.",
        "blocked_keywords": ["secret_key", "prod_password", "aws_secret", "sudo"],
        "enable_request_filter": True,
    },
    {
        "api_key": "sales-api-key",
        "default_system_prompt": "You are the Sales AI Assistant. Maintain a persuasive yet professional tone and highlight product benefits using bullet points.",
        "compliance_disclaimer": "COMPLIANCE NOTICE: Do not make binding commitments or promises regarding unreleased features.",
        "blocked_keywords": ["guarantee", "refund_all", "secret_key"],
        "enable_request_filter": True,
    },
    {
        "api_key": "marketing-api-key",
        "default_system_prompt": "You are the Marketing AI Assistant. Write engaging, creative content optimized for brand voice and audience readability.",
        "compliance_disclaimer": "BRAND POLICY: Adhere strictly to AcmeAI brand voice guidelines.",
        "blocked_keywords": ["competitor_leak", "secret_key"],
        "enable_request_filter": True,
    },
    {
        "api_key": "creative-api-key",
        "default_system_prompt": "You are the Creative AI Assistant. Encourage original brainstorming and offer multiple imaginative ideas.",
        "compliance_disclaimer": "COPYRIGHT NOTICE: Ensure all concepts conform to original content standards.",
        "blocked_keywords": ["plagiarize", "secret_key"],
        "enable_request_filter": True,
    },
]


async def seed():
    conn = await asyncpg.connect(
        host=os.getenv("POSTGRES_HOST"),
        port=int(os.getenv("POSTGRES_PORT")),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
        database=os.getenv("POSTGRES_DB"),
    )

    for team in TEAM_POLICIES:
        await conn.execute(
            """
            UPDATE teams
            SET default_system_prompt = $1,
                compliance_disclaimer = $2,
                blocked_keywords = $3,
                enable_request_filter = $4
            WHERE api_key = $5
            """,
            team["default_system_prompt"],
            team["compliance_disclaimer"],
            team["blocked_keywords"],
            team["enable_request_filter"],
            team["api_key"],
        )

    print("PostgreSQL team policies seeded successfully!")
    await conn.close()


if __name__ == "__main__":
    asyncio.run(seed())
