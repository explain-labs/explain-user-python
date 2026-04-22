"""Container — Python port of src/explain/base_models/Container.js

A Container is an elastic enclosure that holds other compartments. Its volume is
the sum of `vol_extra` plus the `vol` of every contained component, and its
recoil pressure is computed exactly like a Capacitance (el_eff, u_vol_eff,
el_k_eff across the three factor tiers). After computing its own pressure, it
adds that pressure to each contained component's `pres_ext`, so the contained
compartments feel the container's squeeze on their next step.

Container has no `volume_in` / `volume_out`; it does not itself gain or lose
fluid — its volume is derived from what it contains.
"""

from __future__ import annotations

from ..base_model import BaseModelClass


class Container(BaseModelClass):
    model_type = "Container"

    model_interface = [
        {"target": "model_type", "type": "string", "build_prop": False,
         "edit_mode": "basic", "readonly": True, "caption": "model type"},
        {"target": "description", "type": "string", "build_prop": True,
         "edit_mode": "basic", "readonly": True, "caption": "description"},
        {"target": "is_enabled", "type": "boolean", "build_prop": True,
         "edit_mode": "basic", "readonly": False, "caption": "enabled"},
        {"target": "u_vol", "type": "number", "build_prop": True,
         "edit_mode": "basic", "readonly": False, "caption": "unstressed volume (L)"},
        {"target": "el_base", "type": "number", "build_prop": True,
         "edit_mode": "basic", "readonly": False, "caption": "elastance baseline (mmHg/L)"},
        {"target": "el_k", "type": "number", "build_prop": True,
         "edit_mode": "basic", "readonly": False, "caption": "elastance non linear k"},
        {"target": "u_vol_factor_ps", "type": "factor",
         "caption": "unstressed volume factor"},
        {"target": "el_base_factor_ps", "type": "factor",
         "caption": "elastance baseline factor"},
        {"target": "el_k_factor_ps", "type": "factor",
         "caption": "elastance non linear  factor"},
        {"target": "contained_components", "type": "multiple-list",
         "build_prop": True, "edit_mode": "basic",
         "caption": "contained compartments",
         "options": [
             "BloodCapacitance",
             "BloodTimeVaryingElastance",
             "BloodPump",
             "BloodVessel",
             "HeartChamber",
             "GasCapacitance",
         ]},
    ]

    def __init__(self, model_ref, name: str = ""):
        super().__init__(model_ref, name)

        # independent persistent properties
        self.u_vol = 0.0          # unstressed volume UV (L)
        self.el_base = 0.0        # baseline elastance E (mmHg/L)
        self.el_k = 0.0           # non-linear elastance factor K2 (unitless)
        self.pres_ext = 0.0       # non-persistent external pressure p2(t) (mmHg)
        self.vol_extra = 0.0      # additional volume of the container (L)
        self.contained_components: list = []  # names of models contained in this Container

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
        # start from the container's own additional volume
        self.vol = self.vol_extra

        # accumulate the volume of every contained component (looked up by name)
        for c in self.contained_components:
            self.vol += self._model_engine.models[c].vol

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

        # push the container pressure onto every contained component's pres_ext
        for c in self.contained_components:
            self._model_engine.models[c].pres_ext += self.pres

        # external pressure is non-persistent
        self.pres_ext = 0.0
