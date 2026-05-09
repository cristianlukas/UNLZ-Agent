# ADR 0006: Behavior-Level llama.cpp Runtime Overrides

## Status
Accepted

## Context
UNLZ Agent supports global llama.cpp runtime settings from `.env` / Settings (`LLAMACPP_*`), such as context size, GPU layers, flash attention, cache types, and extra args.

Different behaviors (for example: Chat, Dev/Código, Visión) require different runtime tuning. A single global profile forces users to manually reconfigure settings when switching use cases.

## Decision
Introduce behavior-level llama.cpp runtime overrides, sent per request in `POST /chat` as:

```json
{
  "llamacpp_overrides": {
    "context_size": 32768,
    "n_gpu_layers": 999,
    "flash_attn": true,
    "cache_type_k": "q8_0",
    "cache_type_v": "q8_0",
    "extra_args": "--jinja --threads 8"
  }
}
```

Precedence rule:

1. Start with global baseline (`LLAMACPP_*` from `.env` / Settings).
2. Apply only provided behavior override fields.
3. Missing override fields keep global values.

Runtime behavior:

- Backend computes an effective runtime signature (model + merged runtime settings).
- If signature changed, managed llama.cpp is restarted with merged args.
- If no behavior override is present on subsequent requests, runtime reverts to global baseline.
- Model/provider persistence remains in `.env`; behavior overrides are request-scoped (not persisted as global runtime state).

## Consequences

- Users can tune runtime per behavior without touching global defaults.
- Switching behavior can trigger llama.cpp restart when effective runtime differs, increasing startup latency for that transition.
- Configuration remains deterministic and auditable via explicit precedence.
- Feature is backward compatible: behaviors without overrides behave exactly as before.
