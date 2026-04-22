"""Resistor — Python port of src/explain/base_models/Resistor.js

A Resistor moves volume between two Capacitance-like components based on the
pressure difference. It respects `no_flow` / `no_back_flow` gates, applies the
three-tier factor system, and honors the `volume_out` contract (propagates
volume that could not be removed, so volume is conserved).
"""

from __future__ import annotations

from ..base_model import BaseModelClass


class Resistor(BaseModelClass):
    model_type = "Resistor"

    model_interface = [
        {"target": "model_type", "type": "string", "readonly": True},
        {"target": "description", "type": "string", "build_prop": True,
         "readonly": True, "caption": "description"},
        {"target": "is_enabled", "type": "boolean", "build_prop": True,
         "caption": "enabled"},
        {"target": "no_flow", "type": "boolean", "build_prop": True,
         "caption": "no flow allowed"},
        {"target": "no_back_flow", "type": "boolean", "build_prop": True,
         "caption": "no back flow allowed"},
        {"target": "r_for", "type": "number", "build_prop": True,
         "caption": "forward resistance"},
        {"target": "r_back", "type": "number", "build_prop": True,
         "caption": "backward resistance"},
        {"target": "r_k", "type": "number", "build_prop": True,
         "caption": "non linear resistance coefficient"},
        {"target": "comp_from", "type": "string", "build_prop": True,
         "caption": "comp from"},
        {"target": "comp_to", "type": "string", "build_prop": True,
         "caption": "comp to"},
    ]

    def __init__(self, model_ref, name: str = ""):
        super().__init__(model_ref, name)

        # independent properties
        self.r_for = 1.0       # forward flow resistance (mmHg*s/L)
        self.r_back = 1.0      # backward flow resistance (mmHg*s/L)
        self.r_k = 0.0         # non-linear resistance coefficient
        self.comp_from = ""    # upstream component name
        self.comp_to = ""      # downstream component name
        self.no_flow = False
        self.no_back_flow = False
        self.p1_ext = 0.0      # external pressure on inlet (mmHg, non-persistent)
        self.p2_ext = 0.0      # external pressure on outlet (mmHg, non-persistent)
        self.fixed_composition = False

        # non-persistent factors
        self.r_factor = 1.0
        self.r_k_factor = 1.0

        # persistent factors
        self.r_factor_ps = 1.0
        self.r_k_factor_ps = 1.0

        # scaling factors
        self.r_factor_scaling_ps = 1.0
        self.r_k_factor_scaling_ps = 1.0

        # dependent properties
        self.flow = 0.0

        # calculated intermediates
        self.r_for_eff = 1000.0
        self.r_back_eff = 1000.0
        self.r_k_eff = 0.0

        # internal references / state
        self._comp_from = None
        self._comp_to = None
        self._prev_flow = 0.0

    def calc_model(self):
        # look up connected components (by name)
        self._comp_from = self._model_engine.models[self.comp_from]
        self._comp_to = self._model_engine.models[self.comp_to]

        self.calc_resistance()
        self.calc_flow()

    def calc_resistance(self):
        self.r_for_eff = (
            self.r_for
            + (self.r_factor - 1) * self.r_for
            + (self.r_factor_ps - 1) * self.r_for
            + (self.r_factor_scaling_ps - 1) * self.r_for
        )
        self.r_back_eff = (
            self.r_back
            + (self.r_factor - 1) * self.r_back
            + (self.r_factor_ps - 1) * self.r_back
            + (self.r_factor_scaling_ps - 1) * self.r_back
        )
        self.r_k_eff = (
            self.r_k
            + (self.r_k_factor - 1) * self.r_k
            + (self.r_k_factor_ps - 1) * self.r_k
            + (self.r_k_factor_scaling_ps - 1) * self.r_k
        )
        # reset non-persistent factors
        self.r_factor = 1.0
        self.r_k_factor = 1.0

    def calc_flow(self):
        # read pressures and incorporate transient external pressures
        p1_t = self._comp_from.pres + self.p1_ext
        p2_t = self._comp_to.pres + self.p2_ext

        # reset external pressures
        self.p1_ext = 0.0
        self.p2_ext = 0.0

        # reset flow
        self.flow = 0.0

        if self.no_flow:
            self._prev_flow = 0.0
            return

        # forward flow
        if p1_t >= p2_t:
            self.flow = (p1_t - p2_t - self.r_k_eff * (self.flow ** 2)) / self.r_for_eff

            vol_not_removed = self._comp_from.volume_out(self.flow * self._t)
            self._comp_to.volume_in(self.flow * self._t - vol_not_removed, self._comp_from)

            self._prev_flow = self.flow
            return

        # backward flow
        if p1_t < p2_t and not self.no_back_flow:
            self.flow = (p1_t - p2_t + self.r_k_eff * (self.flow ** 2)) / self.r_back_eff

            vol_not_removed = self._comp_to.volume_out(-self.flow * self._t)
            self._comp_from.volume_in(-self.flow * self._t - vol_not_removed, self._comp_to)

            self._prev_flow = self.flow
            return
