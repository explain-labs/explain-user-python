"""AnsAfferent — port of src/explain/component_models/AnsAfferent.js

Normalised receptor with min/set/max input range, produces firing_rate 0-1
with gain based on the setpoint side the input falls on. First-order time
constant smoothing. Pushes firing_rate to all connected efferents via
update_effector(firing_rate, effect_weight).
"""

from __future__ import annotations

from ..base_model import BaseModelClass


class AnsAfferent(BaseModelClass):
    model_type = "AnsAfferent"

    model_interface = [
        {"target": "description", "type": "string", "build_prop": True, "readonly": True},
        {"target": "is_enabled", "type": "boolean", "build_prop": True, "caption": "enabled"},
        {"target": "input_prop", "type": "prop-list", "build_prop": True,
         "caption": "input model property"},
        {"target": "min_value", "type": "number", "build_prop": True},
        {"target": "max_value", "type": "number", "build_prop": True},
        {"target": "set_value", "type": "number", "build_prop": True},
        {"target": "tc", "type": "number", "build_prop": True},
        {"target": "efferents", "type": "multiple-list", "build_prop": True},
        {"target": "effect_weight", "type": "number", "build_prop": True},
    ]

    def __init__(self, model_ref, name: str = ""):
        super().__init__(model_ref, name)

        self.input_model = ""
        self.input_prop = ""
        self.efferents = []
        self.effect_weight = 1.0
        self.min_value = 0.0
        self.set_value = 0.0
        self.max_value = 0.0
        self.tc = 1.0
        self.ans_active = True

        self.input_value = 0.0
        self.firing_rate = 0.0

        self._update_interval = 0.015
        self._update_counter = 0.0
        self._max_firing_rate = 1.0
        self._set_firing_rate = 0.5
        self._min_firing_rate = 0.0
        self._gain = 0.0

    def calc_model(self):
        self._update_counter += self._t
        if self._update_counter >= self._update_interval:
            self._update_counter = 0.0

            self.input_value = getattr(self._model_engine.models[self.input_model], self.input_prop)

            if self.input_value > self.max_value:
                _activation = self.max_value - self.set_value
            elif self.input_value < self.min_value:
                _activation = self.min_value - self.set_value
            else:
                _activation = self.input_value - self.set_value

            if _activation > 0:
                _pos_range = self.max_value - self.set_value
                self._gain = (self._max_firing_rate - self._set_firing_rate) / _pos_range if _pos_range != 0 else 0.0
            else:
                _neg_range = self.set_value - self.min_value
                self._gain = (self._set_firing_rate - self._min_firing_rate) / _neg_range if _neg_range != 0 else 0.0

            _new_firing_rate = self._set_firing_rate + self._gain * _activation

            if self.tc > 0:
                self.firing_rate = self._update_interval * ((1.0 / self.tc) * (-self.firing_rate + _new_firing_rate)) + self.firing_rate
            else:
                self.firing_rate = _new_firing_rate

            for effector in self.efferents:
                self._model_engine.models[effector].update_effector(self.firing_rate, self.effect_weight)
