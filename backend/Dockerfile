FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.12.10 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Capa de dependencias: se reconstruye solo si cambian pyproject.toml o uv.lock
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

# Capa de código: cambia en cada commit
COPY src/ ./src/
RUN uv sync --frozen

CMD ["python", "-m", "vocab.cli.main"]
