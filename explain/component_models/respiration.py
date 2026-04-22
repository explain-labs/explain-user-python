"""Respiration — port of src/explain/component_models/Respiration.js

Orchestrator for lungs / thorax / airway resistance / gas exchangers.
Delta-based factor writes, same pattern as Circulation.
"""

from __future__ import annotations

from ..base_model import BaseModelClass


class Respiration(BaseModelClass):
    model_type = "Respiration"

    model_interface = [
        {"target": "description", "type": "string", "build_prop": True, "readonly": True},
        {"target": "is_enabled", "type": "boolean", "build_prop": True, "caption": "enabled"},
    ]

    def __init__(self, model_ref, name: str = ""):
        super().__init__(model_ref, name)

        self.upper_airways = ["MOUTH_DS"]
        self.lower_airways = ["DS_ALL", "DS_ALR"]
        self.lower_airways_left = ["DS_ALL"]
        self.lower_airways_right = ["DS_ALR"]
        self.dead_space = ["DS"]
        self.thorax = ["THORAX"]
        self.pleural_space_left = []
        self.pleural_space_right = []
        self.lungs = ["ALL", "ALR"]
        self.left_lung = ["ALL"]
        self.right_lung = ["ALR"]
        self.gas_echangers = ["GASEX_LL", "GASEX_RL"]
        self.gas_exchanger_left_lung = ["GASEX_LL"]
        self.gas_exchanger_right_lung = ["GASEX_RL"]
        self.intrapulmonary_shunt = ["IPS"]

        self.el_lungs_factor = 1.0
        self.el_thorax_factor = 1.0

        self.res_upper_airways_factor = 1.0
        self.res_lower_airways_factor = 1.0

        self.gex_factor = 1.0

        self._update_interval = 0.015
        self._update_counter = 0.0
        self._prev_el_lungs_factor = 1.0
        self._prev_el_thorax_factor = 1.0
        self._prev_gex_factor = 1.0
        self._prev_res_upper_airways_factor = 1.0
        self._prev_res_lower_airways_factor = 1.0

    def calc_model(self):
        self._update_counter += self._t
        if self._update_counter > self._update_interval:
            self._update_counter = 0.0

            if self._prev_el_lungs_factor != self.el_lungs_factor:
                self.set_el_lung_factor(self.el_lungs_factor)
                self._prev_el_lungs_factor = self.el_lungs_factor

            if self._prev_el_thorax_factor != self.el_thorax_factor:
                self.set_el_thorax_factor(self.el_thorax_factor)
                self._prev_el_thorax_factor = self.el_thorax_factor

            if self._prev_res_upper_airways_factor != self.res_upper_airways_factor:
                self.set_upper_airway_resistance(self.res_upper_airways_factor)
                self._prev_res_upper_airways_factor = self.res_upper_airways_factor

            if self._prev_res_lower_airways_factor != self.res_lower_airways_factor:
                self.set_lower_airway_resistance(self.res_lower_airways_factor)
                self._prev_res_lower_airways_factor = self.res_lower_airways_factor

            if self._prev_gex_factor != self.gex_factor:
                self.set_gasexchange(self.gex_factor)
                self._prev_gex_factor = self.gex_factor

    def set_el_lung_factor(self, new_factor):
        for lung_name in self.lungs:
            m = self._model_engine.models[lung_name]
            f_ps = m.el_base_factor_ps
            delta = new_factor - self._prev_el_lungs_factor
            f_ps += delta
            if f_ps < 0:
                new_factor = -f_ps
                f_ps = 0
            m.el_base_factor_ps = f_ps
            self.el_lungs_factor = new_factor

    def set_el_thorax_factor(self, new_factor):
        for thorax_name in self.thorax:
            m = self._model_engine.models[thorax_name]
            f_ps = m.el_base_factor_ps
            delta = new_factor - self._prev_el_thorax_factor
            f_ps += delta
            if f_ps < 0:
                new_factor = -f_ps
                f_ps = 0
            m.el_base_factor_ps = f_ps
            self.el_thorax_factor = new_factor

    def set_upper_airway_resistance(self, new_factor):
        for uaw_name in self.upper_airways:
            m = self._model_engine.models[uaw_name]
            f_ps = m.r_factor_ps
            delta = new_factor - self._prev_res_upper_airways_factor
            f_ps += delta
            if f_ps < 0:
                new_factor = -f_ps
                f_ps = 0
            m.r_factor_ps = f_ps
            self.res_upper_airways_factor = new_factor

    def set_lower_airway_resistance(self, new_factor):
        for law_name in self.lower_airways:
            m = self._model_engine.models[law_name]
            f_ps = m.r_factor_ps
            delta = new_factor - self._prev_res_lower_airways_factor
            f_ps += delta
            if f_ps < 0:
                new_factor = -f_ps
                f_ps = 0
            m.r_factor_ps = f_ps
            self.res_lower_airways_factor = new_factor

    def set_gasexchange(self, new_factor):
        for gex_name in self.gas_echangers:
            m = self._model_engine.models[gex_name]
            f_ps_o2 = m.dif_o2_factor_ps
            f_ps_co2 = m.dif_co2_factor_ps
            delta = new_factor - self._prev_gex_factor
            f_ps_o2 += delta
            f_ps_co2 += delta
            if f_ps_o2 < 0:
                new_factor = -f_ps_o2
                f_ps_o2 = 0
                f_ps_co2 = 0
            m.dif_o2_factor_ps = f_ps_o2
            m.dif_co2_factor_ps = f_ps_co2
            self.gex_factor = new_factor
