FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY requirements.lock requirements-stt.lock requirements-voice.lock requirements-neural.lock requirements-neural-cuda.lock ./
ARG INSTALL_STT=false
ARG INSTALL_VOICE=false
ARG INSTALL_NEURAL=false
ARG NEURAL_FLAVOR=cpu
RUN --mount=type=cache,target=/root/.cache/pip pip install --require-hashes -r requirements.lock
RUN --mount=type=cache,target=/root/.cache/pip if [ "$INSTALL_NEURAL" = "true" ]; then if [ "$NEURAL_FLAVOR" = "cuda" ]; then pip install --require-hashes -r requirements-neural-cuda.lock; else pip install --require-hashes --extra-index-url https://download.pytorch.org/whl/cpu -r requirements-neural.lock; fi; elif [ "$INSTALL_VOICE" = "true" ]; then pip install --require-hashes -r requirements-voice.lock; elif [ "$INSTALL_STT" = "true" ]; then pip install --require-hashes -r requirements-stt.lock; fi
RUN if [ "$INSTALL_NEURAL" = "true" ]; then apt-get update && apt-get install -y --no-install-recommends sox && rm -rf /var/lib/apt/lists/*; fi
COPY shared ./shared
COPY apps/delta-core ./apps/delta-core
COPY apps/delta-tasks ./apps/delta-tasks
COPY apps/delta-agent ./apps/delta-agent
RUN --mount=type=cache,target=/root/.cache/pip pip install --no-deps .
RUN useradd --create-home delta && mkdir -p /models/whisper /models/piper /models/qwen && chown -R delta:delta /models
USER delta
EXPOSE 8000
