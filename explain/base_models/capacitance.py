"""Capacitance — Python port of src/explain/base_models/Capacitance.js

A capacitance holds a volume of fluid at a pressure determined by its elastance
and unstressed volume. Pressure = el_eff * (vol - u_vol_eff) + el_k_eff * (vol - u_vol_eff)^2.
All factor tiers (non-persistent, persistent `_ps`, scaling `_scaling_ps`) are preserved.
"""

from __future__ import annotations

from ..base_model import BaseModelClass


class Capacitance(BaseModelClass):
    model_type = "Capacitance"

    # Class-level metadata (trimmed to essentials for the spike; full interface
    # list from the JS file can be restored when needed for UI/editor support).
    model_interface = [
        {"target": "model_type", "type": "string", "readonly": True,
         "caption": "model type"},
        {"target": "description", "type": "string", "build_prop": True,
         "edit_mode": "basic", "readonly": True, "caption": "description"},
        {"target": "is_enabled", "type": "boolean", "build_prop": True,
         "edit_mode": "basic", "caption": "enabled"},
        {"target": "u_vol", "type": "number", "build_prop": True,
         "caption": "unstressed volume (L)"},
        {"target": "el_base", "type": "number", "build_prop": True,
         "caption": "elastance baseline (mmHg/L)"},
        {"target": "el_k", "type": "number", "build_prop": True,
         "caption": "elastance non-linear k"},
    ]

    def __init__(self, model_ref, name: str = ""):
        super().__init__(model_ref, name)

        # independent persistent properties
        self.u_vol = 0.0       # unstressed volume UV (L)
        self.el_base = 0.0     # baseline elastance E (mmHg/L)
        self.el_k = 0.0        # non-linear elastance factor K2 (unitless)
        self.pres_ext = 0.0    # non-persistent external pressure (mmHg)
        self.fixed_composition = False

        # non-persistent factors — reset to 1.0 every step
        self.u_vol_factor = 1.0
        self.el_base_factor = 1.0
        self.el_k_factor = 1.0

        # persistent factors (_ps)
        self.u_vol_factor_ps = 1.0
        self.el_base_factor_ps = 1.0
        self.el_k_factor_ps = 1.0

        # scaling factors (_scaling_ps)
        self.u_vol_factor_scaling_ps = 1.0
        self.el_base_factor_scaling_ps = 1.0
        self.el_k_factor_scaling_ps = 1.0

        # dependent properties
        self.vol = 0.0        # current volume (L)
        self.pres = 0.0       # total pressure (mmHg)
        self.pres_in = 0.0    # recoil pressure of the elastance (mmHg)
        self.pres_tm = 0.0    # transmural pressure (mmHg)

        # calculated intermediates
        self.el_eff = 0.0
        self.u_vol_eff = 0.0
        self.el_k_eff = 0.0

    def calc_model(self):
        self.calc_elastances()
        self.calc_volumes()
        self.calc_pressure()

    def calc_elastances(self):
        self.el_eff = (
            self.el_base
            + (self.el_base_factor - 1) * self.el_base
            + (self.el_base_factor_ps - 1) * self.el_base
            + (self.el_base_factor_scaling_ps - 1) * self.el_base
        )
        self.el_k_eff = (
            self.el_k
            + (self.el_k_factor - 1) * self.el_k
            + (self.el_k_factor_ps - 1) * self.el_k
            + (self.el_k_factor_scaling_ps - 1) * self.el_k
        )
        # reset non-persistent factors
        self.el_base_factor = 1.0
        self.el_k_factor = 1.0

    def calc_volumes(self):
        self.u_vol_eff = (
            self.u_vol
            + (self.u_vol_factor - 1) * self.u_vol
            + (self.u_vol_factor_ps - 1) * self.u_vol
            + (self.u_vol_factor_scaling_ps - 1) * self.u_vol
        )
        # reset non-persistent factor
        self.u_vol_factor = 1.0

    def calc_pressure(self):
        # recoil pressure (with optional non-linear term)
        self.pres_in = (
            self.el_k_eff * ((self.vol - self.u_vol_eff) ** 2)
            + self.el_eff * (self.vol - self.u_vol_eff)
        )
        self.pres_tm = self.pres_in - self.pres_ext
        self.pres = self.pres_in + self.pres_ext
        # external pressure is non-persistent
        self.pres_ext = 0.0

    def volume_in(self, dvol: float, source=None):
        """Add volume. Source is accepted for interface compatibility but ignored
        in the base Capacitance (subclasses like BloodCapacitance handle mixing)."""
        if not self.fixed_composition:
            self.vol += dvol
        # no return value in JS; Python mirrors that (implicit None)

    def volume_out(self, dvol: float) -> float:
        """Remove volume. Returns the amount that could NOT be removed
        (positive when the compartment was empty)."""
        if not self.fixed_composition:
            self.vol -= dvol

        if self.vol < 0.0:
            vol_not_removed = -self.vol
            self.vol = 0.0
            return vol_not_removed

        return 0.0
