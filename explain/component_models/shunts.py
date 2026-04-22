"""Shunts — port of src/explain/component_models/Shunts.js

Foramen ovale (LA_RAIVCI, LA_RASVC) + ventricular septal defect (VSD)
resistance and flow. Uses Poiseuille's Law from diameter; L-R factor biases
forward resistance over back resistance across the FO.
"""

from __future__ import annotations

import math

from ..base_model import BaseModelClass


class Shunts(BaseModelClass):
    model_type = "Shunts"

    model_interface = [
        {"target": "description", "type": "string", "build_prop": True, "readonly": True},
        {"target": "is_enabled", "type": "boolean", "build_prop": True, "caption": "enabled"},
        {"target": "diameter_fo", "type": "number", "build_prop": True},
        {"target": "diameter_vsd", "type": "number", "build_prop": True},
    ]

    def __init__(self, model_ref, name: str = ""):
        super().__init__(model_ref, name)

        self.diameter_fo = 2.0
        self.diameter_fo_max = 10.0
        self.diameter_vsd = 2.0
        self.diameter_vsd_max = 10.0

        self.atrial_septal_width = 3.0
        self.ventricular_septal_width = 5.0
        self.fo_lr_factor = 10.0
        self.viscosity = 6.0

        self.flow_fo = 0.0
        self.flow_vsd = 0.0

        self.velocity_fo = 0.0
        self.velocity_vsd = 0.0

        self.res_fo = 500
        self.res_vsd = 500

        self._fo_ivci = None
        self._fo_svc = None
        self._vsd = None

    def calc_model(self):
        self._fo_ivci = self._model_engine.models["LA_RAIVCI"]
        self._fo_svc = self._model_engine.models["LA_RASVC"]
        self._vsd = self._model_engine.models["VSD"]

        self.viscosity = self._model_engine.models["LV"].viscosity

        self.diameter_fo = min(self.diameter_fo, self.diameter_fo_max)
        self.diameter_vsd = min(self.diameter_vsd, self.diameter_vsd_max)

        self._fo_ivci.no_flow = self.diameter_fo == 0
        self._fo_svc.no_flow = self.diameter_fo == 0
        self._vsd.no_flow = self.diameter_vsd == 0

        self.res_fo = self.calc_resistance(self.diameter_fo, self.atrial_septal_width, self.viscosity)
        self.res_vsd = self.calc_resistance(self.diameter_vsd, self.ventricular_septal_width, self.viscosity)

        self._fo_ivci.r_for = self.res_fo * self.fo_lr_factor
        self._fo_ivci.r_back = self.res_fo

        self._fo_svc.r_for = self.res_fo * self.fo_lr_factor
        self._fo_svc.r_back = self.res_fo

        self._vsd.r_for = self.res_vsd
        self._vsd.r_back = self.res_vsd

        self.flow_fo = self._fo_ivci.flow + self._fo_svc.flow
        self.flow_vsd = self._vsd.flow

        area_fo = ((self.diameter_fo * 0.001) / 2.0) ** 2.0 * math.pi
        area_vsd = ((self.diameter_vsd * 0.001) / 2.0) ** 2.0 * math.pi

        self.velocity_fo = (self.flow_fo * 0.001) / area_fo if area_fo > 0 else 0.0
        self.velocity_vsd = (self.flow_vsd * 0.001) / area_vsd if area_vsd > 0 else 0.0

    def calc_resistance(self, diameter, length=2.0, viscosity=6.0):
        if diameter > 0.0 and length > 0.0:
            n_pas = viscosity / 1000.0
            length_meters = length / 1000.0
            radius_meters = diameter / 2 / 1000.0
            res = (8.0 * n_pas * length_meters) / (math.pi * (radius_meters ** 4))
            res = res * 0.00000750062
            return res
        return 100000000
