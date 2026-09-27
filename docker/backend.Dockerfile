FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY requirements.lock requirements-stt.lock requirements-voice.lock ./
ARG INSTALL_STT=false
ARG INSTALL_VOICE=false
RUN --mount=type=cache,target=/root/.cache/pip pip install --require-hashes -r requirements.lock
RUN --mount=type=cache,target=/root/.cache/pip if [ "$INSTALL_VOICE" = "true" ]; then pip install --require-hashes -r requirements-voice.lock; elif [ "$INSTALL_STT" = "true" ]; then pip install --require-hashes -r requirements-stt.lock; fi
COPY shared ./shared
COPY apps/delta-core ./apps/delta-core
COPY apps/delta-tasks ./apps/delta-tasks
COPY apps/delta-agent ./apps/delta-agent
RUN --mount=type=cache,target=/root/.cache/pip pip install --no-deps .
RUN useradd --create-home delta && mkdir -p /models/whisper /models/piper && chown -R delta:delta /models
USER delta
EXPOSE 8000
