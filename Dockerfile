FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir uv && uv sync --frozen --no-dev

COPY config ./config
COPY gateway ./gateway
COPY approval ./approval
COPY demo/bulletin_A19.pdf ./demo/bulletin_A19.pdf
COPY verify_ledger.py ./

RUN mkdir -p /app/data

EXPOSE 8000

CMD ["uv", "run", "--no-dev", "uvicorn", "gateway.mcp_app:app", "--host", "0.0.0.0", "--port", "8000"]
