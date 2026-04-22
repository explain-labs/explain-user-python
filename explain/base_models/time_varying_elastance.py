"""TimeVaryingElastance — port of src/explain/base_models/TimeVaryingElastance.js

A pressure-volume relationship whose elastance varies over the cardiac cycle.
An external `act_factor` (normally supplied by the Heart model) interpolates
between `el_min` (diastole) and `el_max` (systole) to produce the recoil
pressure.

    p_ed  = el_k_eff * (vol - u_vol_eff)^2 + el_min_eff * (vol - u_vol_eff)
    p_ms  = (vol - u_vol_eff) * el_max_eff
    pres_in = (p_ms - p_ed) * act_factor + p_ed

`volume_out` has a subtle extra guard inherited from the JS source — it only
treats the compartment as "empty" when `vol < 0 AND vol < u_vol`. Ported verbatim.
"""

from __future__ import annotations

from ..base_model import BaseModelClass


class TimeVaryingElastance(BaseModelClass):
    model_type = "TimeVaryingElastance"

    model_interface = [
        {"target": "model_type", "type": "string", "readonly": True},
        {"target": "description", "type": "string", "build_prop": True,
         "readonly": True, "caption": "description"},
        {"target": "is_enabled", "type": "boolean", "build_prop": True,
         "caption": "enabled"},
        {"target": "vol", "type": "number", "build_prop": True,
         "caption": "volume (L)"},
        {"target": "u_vol", "type": "number", "build_prop": True,
         "caption": "unstressed volume (L)"},
        {"target": "el_min", "type": "number", "build_prop": True,
         "caption": "elastance minimum (mmHg/L)"},
        {"target": "el_max", "type": "number", "build_prop": True,
         "caption": "elastance maximum (mmHg/L)"},
        {"target": "el_k", "type": "number", "build_prop": True,
         "caption": "elastance non-linear k"},
    ]

    def __init__(self, model_ref, name: str = ""):
        super().__init__(model_ref, name)

        # independent persistent properties
        self.u_vol = 0.0
        self.el_min = 0.0
        self.el_max = 0.0
        self.el_k = 0.0
        self.pres_ext = 0.0
        self.act_factor = 0.0   # supplied externally (e.g. by Heart model)

        # non-persistent factors
        self.u_vol_factor = 1.0
        self.el_min_factor = 1.0
        self.el_max_factor = 1.0
        self.el_k_factor = 1.0

        # persistent factors (_ps)
        self.u_vol_factor_ps = 1.0
        self.el_min_factor_ps = 1.0
        self.el_max_factor_ps = 1.0
        self.el_k_factor_ps = 1.0

        # scaling factors (_scaling_ps)
        self.u_vol_factor_scaling_ps = 1.0
        self.el_min_factor_scaling_ps = 1.0
        self.el_max_factor_scaling_ps = 1.0
        self.el_k_factor_scaling_ps = 1.0

        # dependent
        self.vol = 0.0
        self.pres = 0.0
        self.pres_in = 0.0
        self.pres_tm = 0.0

        # calculated intermediates
        self.el_min_eff = 0.0
        self.el_max_eff = 0.0
        self.u_vol_eff = 0.0
        self.el_k_eff = 0.0

    def calc_model(self):
        self.calc_elastances()
        self.calc_volumes()
        self.calc_pressure()

    def calc_elastances(self):
        self.el_min_eff = (
            self.el_min
            + (self.el_min_factor - 1) * self.el_min
            + (self.el_min_factor_ps - 1) * self.el_min
            + (self.el_min_factor_scaling_ps - 1) * self.el_min
        )
        self.el_max_eff = (
            self.el_max
            + (self.el_max_factor - 1) * self.el_max
            + (self.el_max_factor_ps - 1) * self.el_max
            + (self.el_max_factor_scaling_ps - 1) * self.el_max
        )
        self.el_k_eff = (
            self.el_k
            + (self.el_k_factor - 1) * self.el_k
            + (self.el_k_factor_ps - 1) * self.el_k
            + (self.el_k_factor_scaling_ps - 1) * self.el_k
        )

        # el_max must not drop below el_min
        if self.el_max_eff < self.el_min_eff:
            self.el_max_eff = self.el_min_eff

        # reset non-persistent factors
        self.el_min_factor = 1.0
        self.el_max_factor = 1.0
        self.el_k_factor = 1.0

    def calc_volumes(self):
        self.u_vol_eff = (
            self.u_vol
            + (self.u_vol_factor - 1) * self.u_vol
            + (self.u_vol_factor_ps - 1) * self.u_vol
            + (self.u_vol_factor_scaling_ps - 1) * self.u_vol
        )
        self.u_vol_factor = 1.0

    def calc_pressure(self):
        p_ms = (self.vol - self.u_vol_eff) * self.el_max_eff
        p_ed = (
            self.el_k_eff * ((self.vol - self.u_vol_eff) ** 2)
            + self.el_min_eff * (self.vol - self.u_vol_eff)
        )
        self.pres_in = (p_ms - p_ed) * self.act_factor + p_ed
        self.pres = self.pres_in + self.pres_ext
        self.pres_tm = self.pres_in - self.pres_ext
        self.pres_ext = 0.0

    def volume_in(self, dvol: float, comp_from=None):
        self.vol += dvol

    def volume_out(self, dvol: float) -> float:
        self.vol -= dvol
        # NOTE: this guard comes straight from TimeVaryingElastance.js. The
        # `vol < u_vol` second condition is a subtle difference from
        # Capacitance — e.g. if u_vol is negative, the compartment can go
        # below zero without triggering the "empty" handling.
        if self.vol < 0.0 and self.vol < self.u_vol:
            vol_not_removed = -self.vol
            self.vol = 0.0
            return vol_not_removed
        return 0.0
