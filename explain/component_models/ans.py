"""Ans — port of src/explain/component_models/Ans.js

Coordinates ANS afferents/efferents and refreshes blood composition on the
compartments the ANS reads from. 50ms update throttle.
"""

from __future__ import annotations

from ..base_model import BaseModelClass
from ..helpers.blood_composition import calc_blood_composition


class Ans(BaseModelClass):
    model_type = "Ans"

    model_interface = [
        {"target": "description", "type": "string", "build_prop": True, "readonly": True},
        {"target": "is_enabled", "type": "boolean", "build_prop": True, "caption": "enabled"},
        {"target": "ans_active", "type": "boolean", "build_prop": True, "caption": "ANS active"},
    ]

    def __init__(self, model_ref, name: str = ""):
        super().__init__(model_ref, name)

        self.ans_active = True
        self.components = {}
        self.blood_composition_models = []

        self._update_interval = 0.05
        self._update_counter = 0.0

    def calc_model(self):
        self._update_counter += self._t
        if self._update_counter >= self._update_interval:
            self._update_counter = 0.0

            for component in list(self.components.keys()):
                self._model_engine.models[component].ans_active = self.ans_active

            for model_name in self.blood_composition_models:
                m = self._model_engine.models[model_name]
                # JS reads `m.ans_active` as undefined (falsy) on models that
                # never declared it — e.g. BloodVessel. Match with getattr.
                if getattr(m, "ans_active", False):
                    calc_blood_composition(m)
