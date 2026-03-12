FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:0.6.6 /uv /uvx /bin/
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY .env.example ./.env.example

RUN uv sync --frozen --no-dev

EXPOSE 3000

CMD ["uv", "run", "python", "-m", "real_time_translation_ai_agent.main"]
