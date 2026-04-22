"""Engine — minimal runner that mirrors the step loop in src/explain/ModelEngine.js.

The Web Worker protocol is deliberately NOT ported. In Python there is no UI
to notify, so the interface is a direct `Engine.load(definition)` +
`Engine.run(duration_s, watch=[...])` returning a list of dicts.

Ordering: models are stepped in insertion order, matching the JS engine
(`for const model_name in model.models` preserves insertion order in modern JS
and in Python 3.7+).
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from .model_index import MODEL_INDEX


class Engine:
    def __init__(self, modeling_stepsize: float = 0.0005):
        self.models: dict = {}
        self.modeling_stepsize = modeling_stepsize
        self.model_time_total = 0.0

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------
    def load(self, definition: dict) -> None:
        """Build the model tree from a `model_definition` dict.

        Accepts either the outer file dict (with a `model_definition` wrapper)
        or the inner `model_definition` dict directly — matches how Model.js
        unwraps incoming scenarios.
        """
        md = definition.get("model_definition", definition)

        # copy every top-level key except `models` onto the engine, matching
        # ModelEngine.js:215-220. Component models read these as
        # `self._model_engine.weight`, `.height`, etc.
        for key, value in md.items():
            if key != "models":
                setattr(self, key, value)

        # first pass: instantiate every top-level model
        for name, body in md["models"].items():
            cls = MODEL_INDEX[body["model_type"]]
            self.models[name] = cls(self, name)

        # second pass: init (applies properties, recurses into components)
        for name, body in md["models"].items():
            args = [{"key": k, "value": v} for k, v in body.items()]
            self.models[name].init_model(args)

    def load_file(self, path: str | Path) -> None:
        with open(path) as f:
            self.load(json.load(f))

    # ------------------------------------------------------------------
    # Stepping
    # ------------------------------------------------------------------
    def step(self) -> None:
        """Advance the simulation by one `modeling_stepsize`."""
        for model in self.models.values():
            model.step_model()
        self.model_time_total += self.modeling_stepsize

    def run(self, duration_s: float, watch: list[tuple[str, str]] | None = None,
            sample_every_s: float = 0.001) -> list[dict]:
        """Step for `duration_s` seconds of simulated time, sampling the
        watched properties at `sample_every_s` intervals.

        `watch` is a list of (instance_name, property_name) tuples.
        Returns a list of dicts (one per sample), always including `t`.
        """
        watch = watch or []
        n_steps = int(round(duration_s / self.modeling_stepsize))
        sample_every_n = max(1, int(round(sample_every_s / self.modeling_stepsize)))

        rows: list[dict] = []
        for i in range(n_steps):
            self.step()
            if i % sample_every_n == 0:
                row = {"t": self.model_time_total}
                for inst, prop in watch:
                    row[f"{inst}.{prop}"] = getattr(self.models[inst], prop)
                rows.append(row)
        return rows

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------
    @staticmethod
    def write_csv(rows: list[dict], path: str | Path) -> None:
        if not rows:
            return
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
