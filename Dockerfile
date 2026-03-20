FROM python:3.11-slim

WORKDIR /app

RUN pip install uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY src/ ./src/

EXPOSE 8000

CMD ["uv", "run", "hypercorn", "src.slicehash.app:app", "--bind", "0.0.0.0:8000", "-w", "1"]
