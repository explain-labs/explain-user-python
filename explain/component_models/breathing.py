"""Breathing — port of src/explain/component_models/Breathing.js

Spontaneous breathing driver. Computes respiratory rate and tidal volume
from target minute volume, cycles through inspiration/expiration, and
modulates THORAX.el_base_factor via the respiratory-muscle-pressure curve
(ramp on inspiration, decay on expiration using Mecklenburgh function).
"""

from __future__ import annotations

import math

from ..base_model import BaseModelClass


class Breathing(BaseModelClass):
    model_type = "Breathing"

    model_interface = [
        {"target": "description", "type": "string", "build_prop": True, "readonly": True},
        {"target": "is_enabled", "type": "boolean", "build_prop": True, "caption": "enabled"},
        {"target": "breathing_enabled", "type": "boolean", "build_prop": True},
        {"target": "minute_volume_ref", "type": "number", "build_prop": True},
        {"target": "vt_rr_ratio", "type": "number", "build_prop": True},
        {"target": "ie_ratio", "type": "number", "build_prop": True},
        {"target": "rmp_gain_max", "type": "number", "build_prop": True},
    ]

    def __init__(self, model_ref, name: str = ""):
        super().__init__(model_ref, name)

        self.breathing_enabled = True
        self.minute_volume_ref = 0.2
        self.minute_volume_ref_factor = 1.0
        self.minute_volume_ref_scaling_factor = 1.0
        self.vt_rr_ratio = 0.0001212
        self.vt_rr_ratio_factor = 1.0
        self.vt_rr_ratio_scaling_factor = 1.0
        self.rmp_gain_max = 100.0
        self.ie_ratio = 0.3
        self.mv_ans_factor = 1.0
        self.ans_activity_factor = 1.0

        self.target_minute_volume = 0.0
        self.resp_rate = 36.0
        self.resp_rate_measured = 36.0
        self.target_tidal_volume = 0.0
        self.minute_volume = 0.0
        self.exp_tidal_volume = 0.0
        self.insp_tidal_volume = 0.0
        self.resp_muscle_pressure = 0.0
        self.ncc_insp = 0
        self.ncc_exp = 0
        self.rmp_gain = 9.5

        self._eMin4 = math.e ** -4
        self._ti = 0.4
        self._te = 1.0
        self._breath_timer = 0.0
        self._breath_interval = 60.0
        self._insp_running = False
        self._insp_timer = 0.0
        self._temp_insp_volume = 0.0
        self._exp_running = False
        self._exp_timer = 0.0
        self._temp_exp_volume = 0.0
        self._rr_counter = 0.0
        self._rr_factor = 0.0

        self.debug_factor1 = 0.0

    def calc_model(self):
        _weight = self._model_engine.weight

        _minute_volume_ref = (
            self.minute_volume_ref * self.minute_volume_ref_factor
            * self.minute_volume_ref_scaling_factor * _weight
        )
        self.target_minute_volume = (
            (_minute_volume_ref + (self.mv_ans_factor - 1.0) * _minute_volume_ref)
            * self.ans_activity_factor
        )

        self.vt_rr_controller(_weight)

        self._breath_interval = 60.0
        if self.resp_rate > 0:
            self._breath_interval = 60.0 / self.resp_rate
            self._ti = self.ie_ratio * self._breath_interval
            self._te = self._breath_interval - self._ti

        if self._breath_timer > self._breath_interval:
            self._breath_timer = 0.0
            self._insp_running = True
            self._insp_timer = 0.0
            self.ncc_insp = 0

        if self._insp_timer > self._ti:
            self._insp_timer = 0.0
            self._insp_running = False
            self._exp_running = True
            self.ncc_exp = 0
            self._temp_exp_volume = 0.0
            self.insp_tidal_volume = self._temp_insp_volume

        if self._exp_timer > self._te:
            self._exp_timer = 0.0
            self._exp_running = False
            self._temp_insp_volume = 0.0
            self.exp_tidal_volume = -self._temp_exp_volume

            if self.breathing_enabled:
                if abs(self.exp_tidal_volume) < self.target_tidal_volume:
                    self.rmp_gain += 0.1
                if abs(self.exp_tidal_volume) > self.target_tidal_volume:
                    self.rmp_gain -= 0.1
                self.rmp_gain = max(0.0, min(self.rmp_gain, self.rmp_gain_max))
            self.minute_volume = self.exp_tidal_volume * self.resp_rate

        self._breath_timer += self._t

        mouth_ds = self._model_engine.models["MOUTH_DS"]

        if self._insp_running:
            self._insp_timer += self._t
            self.ncc_insp += 1
            if mouth_ds.flow > 0:
                self._temp_insp_volume += mouth_ds.flow * self._t

        if self._exp_running:
            self._exp_timer += self._t
            self.ncc_exp += 1
            if mouth_ds.flow < 0:
                self._temp_exp_volume += mouth_ds.flow * self._t

        self.resp_muscle_pressure = 0.0
        if self.breathing_enabled:
            self.resp_muscle_pressure = self.calc_resp_muscle_pressure()
        else:
            self.resp_rate = 0.0
            self.ncc_insp = 0.0
            self.ncc_exp = 0.0
            self.target_tidal_volume = 0.0
            self.resp_muscle_pressure = 0.0

        if self.ncc_insp == 1:
            self.resp_rate_measured = 60 / self._rr_counter
            self._rr_counter = 0.0
            self._rr_factor = 1.0

        if self._rr_counter > 4 * self._rr_factor:
            self.resp_rate_measured = 60 / self._rr_counter
            self._rr_factor += 1
        self._rr_counter += self._t

        self._model_engine.models["THORAX"].el_base_factor += self.resp_muscle_pressure

    def vt_rr_controller(self, _weight):
        if not self.breathing_enabled:
            self.resp_rate = 0.0
            return
        self.resp_rate = math.sqrt(
            self.target_minute_volume
            / (self.vt_rr_ratio * self.vt_rr_ratio_factor * self.vt_rr_ratio_scaling_factor * _weight)
        )

        if self.resp_rate > 0:
            self.target_tidal_volume = self.target_minute_volume / self.resp_rate

    def calc_resp_muscle_pressure(self):
        mp = 0.0

        if self._insp_running:
            mp = (self.ncc_insp / (self._ti / self._t)) * self.rmp_gain

        if self._exp_running:
            mp = ((math.e ** (-4.0 * (self.ncc_exp / (self._te / self._t))) - self._eMin4) / (1.0 - self._eMin4)) * self.rmp_gain

        return mp

    def switch_breathing(self, state):
        self.breathing_enabled = state
