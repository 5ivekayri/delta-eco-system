FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY requirements.lock ./
RUN --mount=type=cache,target=/root/.cache/pip pip install --require-hashes -r requirements.lock
COPY shared ./shared
COPY apps/delta-core ./apps/delta-core
COPY apps/delta-tasks ./apps/delta-tasks
COPY apps/delta-agent ./apps/delta-agent
RUN --mount=type=cache,target=/root/.cache/pip pip install --no-deps .
RUN useradd --create-home delta
USER delta
EXPOSE 8000
