# Delta inference bridge

Loopback-only OpenRouter/local/auto routing, bounded cloud timeout, lazy local
model, idle unload, systemd lifecycle and Linux parent-death cleanup. Image requests
use the configured vision model; local text-only mode rejects them.

Linux setup (Python 3.12+): create `.venv`, install `requirements-lock.txt`, copy
`config.example.json` to `config.json`. Read the existing server key from `../../.env`
or OPENROUTER_API_KEY. Never commit config, keys, runtime/model binaries or logs.

Install the official llama.cpp b12189 Vulkan release into runtime/llama-b12189;
place ggml-org/Qwen3-1.7B-GGUF Qwen3-1.7B-Q4_K_M.gguf (revision
daeb8e2d528a760970442092f6bf1e55c3b659eb) in models. Verify MODEL-SHA256SUMS.
Set device to the Vulkan GPU reported by your runtime. Defaults were verified on
GTX 1650 (Vulkan1), not a portable hardware autodetection setting.

`./activate.sh` restarts the existing delta-local.service with this repository's
Core and contracts, then starts bridge. `./control.sh auto|local|openrouter|status`
changes routing. `./deactivate.sh` removes the runtime override and restarts Delta.
Units live in XDG_RUNTIME_DIR and must be activated again after logout/reboot.
DELTA_BRIDGE_PYTHON optionally overrides .venv/bin/python.

OpenRouter 8 s -> local fallback up to 60 s; local idle unload 120 s. Vision uses
OpenRouter only, deadline 45 s. A failed inference never executes tools by itself.
`python -m pytest test_bridge.py` covers routing, schema validation and cleanup.
