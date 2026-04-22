"""Resuscitation — port of src/explain/device_models/Resuscitation.js

CPR controller. Applies sinusoidal chest-compression pressure to target
compartments (pres_cc) at chest_comp_freq, with optional compression pause
during ventilations (synchronized with ventilator via trigger_breath()).
"""

from __future__ import annotations

import math

from ..base_model import BaseModelClass


class Resuscitation(BaseModelClass):
    model_type = "Resuscitation"

    model_interface = [
        {"target": "description", "type": "string", "build_prop": True, "readonly": True},
        {"target": "is_enabled", "type": "boolean", "build_prop": True, "caption": "enabled"},
    ]

    def __init__(self, model_ref, name: str = ""):
        super().__init__(model_ref, name)

        self.cpr_enabled = False
        self.chest_comp_freq = 100.0
        self.chest_comp_max_pres = 10.0
        self.chest_comp_targets = {"THORAX": 0.1}
        self.chest_comp_no = 15
        self.chest_comp_cont = False

        self.vent_freq = 30.0
        self.vent_no = 2
        self.vent_pres_pip = 16.0
        self.vent_pres_peep = 5.0
        self.vent_insp_time = 1.0
        self.vent_fio2 = 0.21

        self.chest_comp_pres = 0.0

        self._ventilator = None
        self._breathing = None
        self._comp_timer = 0.0
        self._comp_counter = 0
        self._comp_pause = False
        self._comp_pause_interval = 2.0
        self._comp_pause_counter = 0.0
        self._vent_interval = 0.0
        self._vent_counter = 0.0

    def init_model(self, args):
        for arg in args:
            setattr(self, arg["key"], arg["value"])

        self._ventilator = self._model_engine.models.get("Ventilator")
        self._breathing = self._model_engine.models.get("Breathing")

        self.set_fio2(self.vent_fio2)

        self._is_initialized = True

    def calc_model(self):
        if not self.cpr_enabled:
            return

        self._comp_pause_interval = (60.0 / self.vent_freq) * self.vent_no
        self._vent_interval = self._comp_pause_interval / self.vent_no + self._t

        if self.chest_comp_cont:
            self._ventilator.vent_rate = self.vent_freq
        else:
            self._ventilator.vent_rate = 1.0

        if self._comp_pause:
            self._comp_pause_counter += self._t

            if self._comp_pause_counter > self._comp_pause_interval:
                self._comp_pause = False
                self._comp_pause_counter = 0.0
                self._comp_counter = 0
                self._vent_counter = 0.0

            self._vent_counter += self._t

            if self._vent_counter > self._vent_interval:
                self._vent_counter = 0.0
                self._ventilator.trigger_breath()
        else:
            a = self.chest_comp_max_pres / 2.0
            f = self.chest_comp_freq / 60.0
            self.chest_comp_pres = a * math.sin(2 * math.pi * f * self._comp_timer - 0.5 * math.pi) + a

            self._comp_timer += self._t

            if self._comp_timer > 60.0 / self.chest_comp_freq:
                self._comp_timer = 0.0
                self._comp_counter += 1

        if self._comp_counter >= self.chest_comp_no and not self.chest_comp_cont:
            self._comp_pause = True
            self._comp_pause_counter = 0.0
            self._comp_counter = 0
            self._ventilator.trigger_breath()

        for key, value in self.chest_comp_targets.items():
            self._model_engine.models[key].pres_cc = self.chest_comp_pres * value

    def switch_cpr(self, state):
        if state:
            self._ventilator.switch_ventilator(True)
            self._ventilator.set_pc(
                self.vent_pres_pip, self.vent_pres_peep, 1.0, self.vent_insp_time, 5.0
            )
            self._breathing.switch_breathing(False)
            self.cpr_enabled = True
        else:
            self.cpr_enabled = False

    def set_fio2(self, new_fio2):
        if self._ventilator is not None:
            self._ventilator.set_fio2(new_fio2)
