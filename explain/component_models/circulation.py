"""Circulation — port of src/explain/component_models/Circulation.js

Orchestrates groups of vessels (systemic / pulmonary arteries, arterioles,
capillaries, venules, veins) and heart chambers. Applies ANS influence and
SVR/PVR arteriolar/venular factors via delta-based persistent-factor writes.
Reports total/systemic/pulmonary/heart blood volumes.
"""

from __future__ import annotations

from ..base_model import BaseModelClass


class Circulation(BaseModelClass):
    model_type = "Circulation"

    model_interface = [
        {"target": "description", "type": "string", "build_prop": True, "readonly": True},
        {"target": "is_enabled", "type": "boolean", "build_prop": True, "caption": "enabled"},
    ]

    def __init__(self, model_ref, name: str = ""):
        super().__init__(model_ref, name)

        self.heart_chambers = []
        self.coronaries = []

        self.systemic_arteries = []
        self.systemic_arterioles = []
        self.systemic_capillaries = []
        self.systemic_venules = []
        self.systemic_veins = []

        self.pulmonary_arteries = []
        self.pulmonary_arterioles = []
        self.pulmonary_capillaries = []
        self.pulmonary_venules = []
        self.pulmonary_veins = []

        self.ans_activity = 1.0
        self.svr_factor_art = 1.0
        self.svr_factor_ven = 1.0
        self.pvr_factor_art = 1.0
        self.pvr_factor_ven = 1.0

        self.total_blood_volume = 0.0
        self.syst_blood_volume = 0.0
        self.pulm_blood_volume = 0.0
        self.heart_blood_volume = 0.0
        self.syst_blood_volume_perc = 0.0
        self.pulm_blood_volume_perc = 0.0
        self.heart_blood_volume_perc = 0.0

        self._bloodvessel_list = []
        self._systemic_bloodvessel_list = []
        self._pulmonary_bloodvessel_list = []

        self.prev_ans_activity = 0.0
        self.prev_svr_factor_art = 1.0
        self.prev_svr_factor_ven = 1.0
        self.prev_pvr_factor_art = 1.0
        self.prev_pvr_factor_ven = 1.0
        self._update_interval = 0.015
        self._update_counter = 0.0
        self._update_interval_slow = 1.0
        self._update_counter_slow = 0.0

    def init_model(self, args):
        super().init_model(args)

        self._bloodvessel_list = (
            list(self.systemic_arteries)
            + list(self.systemic_arterioles)
            + list(self.systemic_capillaries)
            + list(self.systemic_venules)
            + list(self.systemic_veins)
            + list(self.pulmonary_arteries)
            + list(self.pulmonary_arterioles)
            + list(self.pulmonary_capillaries)
            + list(self.pulmonary_venules)
            + list(self.pulmonary_veins)
        )

        self._systemic_bloodvessel_list = (
            list(self.systemic_arteries)
            + list(self.systemic_arterioles)
            + list(self.systemic_capillaries)
            + list(self.systemic_venules)
            + list(self.systemic_veins)
        )

        self._pulmonary_bloodvessel_list = (
            list(self.pulmonary_arteries)
            + list(self.pulmonary_arterioles)
            + list(self.pulmonary_capillaries)
            + list(self.pulmonary_venules)
            + list(self.pulmonary_veins)
        )

    def calc_model(self):
        self._update_counter += self._t
        if self._update_counter > self._update_interval:
            self._update_counter = 0.0

            if self.prev_ans_activity != self.ans_activity:
                for name in self._bloodvessel_list:
                    m = self._model_engine.models.get(name)
                    if m is not None and hasattr(m, "ans_activity"):
                        m.ans_activity = self.ans_activity
                self.prev_ans_activity = self.ans_activity

            if self.prev_svr_factor_art != self.svr_factor_art:
                self.set_svr_factor_art(self.svr_factor_art)
                self.prev_svr_factor_art = self.svr_factor_art

            if self.prev_svr_factor_ven != self.svr_factor_ven:
                self.set_svr_factor_ven(self.svr_factor_ven)
                self.prev_svr_factor_ven = self.svr_factor_ven

            if self.prev_pvr_factor_art != self.pvr_factor_art:
                self.set_pvr_factor_art(self.pvr_factor_art)
                self.prev_pvr_factor_art = self.pvr_factor_art

            if self.prev_pvr_factor_ven != self.pvr_factor_ven:
                self.set_pvr_factor_ven(self.pvr_factor_ven)
                self.prev_pvr_factor_ven = self.pvr_factor_ven

        self._update_counter_slow += self._t
        if self._update_counter_slow > self._update_interval_slow:
            self._update_counter_slow = 0.0
            self.calc_blood_volumes()

    def set_svr_factor_art(self, new_svr_factor):
        for syst_model_name in self.systemic_arterioles:
            m = self._model_engine.models[syst_model_name]
            f_ps = m.r_factor_ps
            delta_svr = new_svr_factor - self.prev_svr_factor_art
            f_ps += delta_svr
            if f_ps < 0:
                new_svr_factor = -f_ps
                f_ps = 0
            m.r_factor_ps = f_ps
            self.svr_factor_art = new_svr_factor

    def set_svr_factor_ven(self, new_svr_factor):
        for syst_model_name in self.systemic_venules:
            m = self._model_engine.models[syst_model_name]
            f_ps = m.r_factor_ps
            delta_svr = new_svr_factor - self.prev_svr_factor_ven
            f_ps += delta_svr
            if f_ps < 0:
                new_svr_factor = -f_ps
                f_ps = 0
            m.r_factor_ps = f_ps
            self.svr_factor_ven = new_svr_factor

    def set_pvr_factor_art(self, new_pvr_factor):
        for pulm_model_name in self.pulmonary_arterioles:
            m = self._model_engine.models[pulm_model_name]
            f_ps = m.r_factor_ps
            delta_pvr = new_pvr_factor - self.prev_pvr_factor_art
            f_ps += delta_pvr
            if f_ps < 0:
                new_pvr_factor = -f_ps
                f_ps = 0
            m.r_factor_ps = f_ps
            self.pvr_factor_art = new_pvr_factor

    def set_pvr_factor_ven(self, new_pvr_factor):
        for pulm_model_name in self.pulmonary_venules:
            m = self._model_engine.models[pulm_model_name]
            f_ps = m.r_factor_ps
            delta_pvr = new_pvr_factor - self.prev_pvr_factor_ven
            f_ps += delta_pvr
            if f_ps < 0:
                new_pvr_factor = -f_ps
                f_ps = 0
            m.r_factor_ps = f_ps
            self.pvr_factor_ven = new_pvr_factor

    def calc_blood_volumes(self):
        self.total_blood_volume = 0.0
        self.syst_blood_volume = 0.0
        self.pulm_blood_volume = 0.0
        self.heart_blood_volume = 0.0

        for name in self._systemic_bloodvessel_list:
            m = self._model_engine.models[name]
            if getattr(m, "vol", 0) and m.is_enabled:
                self.syst_blood_volume += m.vol

        for name in self.heart_chambers:
            m = self._model_engine.models[name]
            if getattr(m, "vol", 0) and m.is_enabled:
                self.heart_blood_volume += m.vol

        for name in self.coronaries:
            m = self._model_engine.models[name]
            if getattr(m, "vol", 0) and m.is_enabled:
                self.syst_blood_volume += m.vol

        for name in self._pulmonary_bloodvessel_list:
            m = self._model_engine.models[name]
            if getattr(m, "vol", 0) and m.is_enabled:
                self.pulm_blood_volume += m.vol

        self.total_blood_volume = self.syst_blood_volume + self.pulm_blood_volume + self.heart_blood_volume
        if self.total_blood_volume > 0:
            self.syst_blood_volume_perc = self.syst_blood_volume / self.total_blood_volume * 100.0
            self.pulm_blood_volume_perc = self.pulm_blood_volume / self.total_blood_volume * 100.0
            self.heart_blood_volume_perc = self.heart_blood_volume / self.total_blood_volume * 100.0
