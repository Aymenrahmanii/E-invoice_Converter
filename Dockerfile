# App image: Python 3.12 + a JRE so the CLI can run KoSIT and Mustang itself.
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
      openjdk-21-jre-headless curl unzip make \
 && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.13.6 /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY scripts ./scripts
RUN bash scripts/fetch_validators.sh
COPY src ./src
RUN uv sync --frozen --no-dev
COPY tests ./tests
ENV PATH="/app/.venv/bin:$PATH"
CMD ["sh", "-c", "einvoice sample --out out && einvoice validate out/xrechnung.xml out/zugferd.pdf"]
