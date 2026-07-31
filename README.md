# Explain (Python) — archived

> **Superseded.** This is a Python port of the Explain physiological simulation
> engine. Development continues in two repositories:
>
> - [**explain-engine**](https://github.com/explain-labs/explain-engine) — the
>   simulation engine (JavaScript, framework-agnostic and dependency-free)
> - [**explain-ui**](https://github.com/explain-labs/explain-ui) — the Vue 3 +
>   Vite web app built on it
>
> Start at the [Explain Labs organization page](https://github.com/explain-labs)
> for setup instructions. This repository is kept read-only for reference.

A 1:1 Python port of the Explain engine: the same JSON scenario definitions
under `model_definitions/` load unchanged, and the per-step physics matches the
JavaScript implementation. The engine package itself (`explain/`) has no
external dependencies.

```python
from explain import Engine
```

See `test.py` for a minimal run.
