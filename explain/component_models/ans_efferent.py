"""AnsEfferent — port of src/explain/component_models/AnsEfferent.js

Receives firing rates from afferents via update_effector(), averages them,
translates the average to an effect factor bracketed between
effect_at_min_firing_rate and effect_at_max_firing_rate, and writes it onto
the target model's target_prop with first-order TC smoothing.
"""

from __future__ import annotations

from ..base_model import BaseModelClass


class AnsEfferent(BaseModelClass):
    model_type = "AnsEfferent"

    model_interface = [
        {"target": "description", "type": "string", "build_prop": True, "readonly": True},
        {"target": "is_enabled", "type": "boolean", "build_prop": True, "caption": "enabled"},
        {"target": "target_prop", "type": "prop-list", "build_prop": True},
        {"target": "effect_at_max_firing_rate", "type": "number", "build_prop": True},
        {"target": "effect_at_min_firing_rate", "type": "number", "build_prop": True},
        {"target": "tc", "type": "number", "build_prop": True},
    ]

    def __init__(self, model_ref, name: str = ""):
        super().__init__(model_ref, name)

        self.target_model = ""
        self.target_prop = ""
        self.effect_at_max_firing_rate = 0.0
        self.effect_at_min_firing_rate = 0.0
        self.tc = 1.0
        self.ans_active = True

        self.firing_rate = 0.0
        self.effector = 1.0

        self._update_interval = 0.015
        self._update_counter = 0.0
        self._cum_firing_rate = 0.0
        self._cum_firing_rate_counter = 1.0

    def calc_model(self):
        self._update_counter += self._t
        if self._update_counter >= self._update_interval:
            self._update_counter = 0.0

            self.firing_rate = 0.5
            if self._cum_firing_rate_counter > 0.0:
                self.firing_rate = self._cum_firing_rate / self._cum_firing_rate_counter

            if self.firing_rate >= 0.5:
                effector = 1.0 + ((self.effect_at_max_firing_rate - 1.0) / 0.5) * (self.firing_rate - 0.5)
            else:
                effector = self.effect_at_min_firing_rate + ((1.0 - self.effect_at_min_firing_rate) / 0.5) * self.firing_rate

            if not self.ans_active:
                effector = 1.0
                self.effector = 1.0

            if self.tc > 0:
                self.effector = self._update_interval * ((1.0 / self.tc) * (-self.effector + effector)) + self.effector
            else:
                self.effector = effector

            setattr(self._model_engine.models[self.target_model], self.target_prop, self.effector)

            self._cum_firing_rate = 0.5
            self._cum_firing_rate_counter = 0.0

    def update_effector(self, new_firing_rate, weight):
        self._cum_firing_rate += (new_firing_rate - 0.5) * weight
        self._cum_firing_rate_counter += 1.0
