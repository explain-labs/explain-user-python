"""Metabolism — port of src/explain/component_models/Metabolism.js

Consumes O2 and produces CO2 across compartments with per-model fractional
VO2 weights. VO2 in ml/kg/min converted to mmol per step via (0.039 * vo2 *
weight / 60) * dt.
"""

from __future__ import annotations

from ..base_model import BaseModelClass


class Metabolism(BaseModelClass):
    model_type = "Metabolism"

    model_interface = [
        {"target": "description", "type": "string", "build_prop": True, "readonly": True},
        {"target": "is_enabled", "type": "boolean", "build_prop": True, "caption": "enabled"},
        {"target": "met_active", "type": "boolean", "build_prop": True},
        {"target": "vo2", "type": "number", "build_prop": True},
        {"target": "resp_q", "type": "number", "build_prop": True},
    ]

    def __init__(self, model_ref, name: str = ""):
        super().__init__(model_ref, name)

        self.met_active = True
        self.vo2 = 8.1
        self.vo2_factor = 1.0
        self.resp_q = 0.8
        self.metabolic_active_models = {}

    def set_metabolic_active_model(self, site, new_fvo2):
        self.metabolic_active_models[site] = new_fvo2

    def calc_model(self):
        if not self.met_active:
            return

        vo2_step = ((0.039 * self.vo2 * self.vo2_factor * self._model_engine.weight) / 60.0) * self._t

        for model, fvo2 in list(self.metabolic_active_models.items()):
            compartment = self._model_engine.models[model]
            if getattr(compartment, "model_type", None) == "MicroVascularUnit":
                compartment = self._model_engine.models[model + "_CAP"]

            vol = compartment.vol
            to2 = compartment.to2
            tco2 = compartment.tco2

            if vol == 0.0:
                return

            dto2 = vo2_step * fvo2

            new_to2 = (to2 * vol - dto2) / vol
            if new_to2 < 0:
                new_to2 = 0

            dtco2 = vo2_step * fvo2 * self.resp_q

            new_tco2 = (tco2 * vol + dtco2) / vol
            if new_tco2 < 0:
                new_tco2 = 0

            compartment.to2 = new_to2
            compartment.tco2 = new_tco2
