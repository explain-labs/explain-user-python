"""Pda — port of src/explain/component_models/Pda.js

Ductus arteriosus. Computes resistance at the aortic and pulmonary ends
from diameter via Poiseuille's Law, pushes them onto AAR_DA and DA_PA, and
tracks elastance / velocity / flow across both ends.
"""

from __future__ import annotations

import math

from ..base_model import BaseModelClass


class Pda(BaseModelClass):
    model_type = "Pda"

    model_interface = [
        {"target": "description", "type": "string", "build_prop": True, "readonly": True},
        {"target": "is_enabled", "type": "boolean", "build_prop": True, "caption": "enabled"},
        {"target": "diameter_relative", "type": "number", "build_prop": True},
    ]

    def __init__(self, model_ref, name: str = ""):
        super().__init__(model_ref, name)

        self.diameter_ao = 4.0
        self.diameter_pa = 2.0
        self.diameter_ao_max = 3.0
        self.diameter_pa_max = 2.0
        self.diameter_relative = 0.0
        self.length = 20
        self.type = "conical"
        self.el_min = 30000
        self.el_max = 150000
        self.viscosity = 6

        self.flow = 0
        self.vol = 0
        self.velocity = 0
        self.flow_ao = 0
        self.flow_pa = 0
        self.velocity_ao = 0
        self.velocity_pa = 0
        self.res_ao = 1500
        self.res_pa = 1500
        self.el = 40000

        self._da = None
        self._aar_da = None
        self._da_pa = None

    def calc_model(self):
        self._aar_da = self._model_engine.models["AAR_DA"]
        self._da = self._model_engine.models["DA"]
        self._da_pa = self._model_engine.models["DA_PA"]

        self.diameter_ao = self.diameter_relative * self.diameter_ao_max
        self.diameter_pa = self.diameter_relative * self.diameter_pa_max
        self.diameter_relative = self.diameter_pa / self.diameter_pa_max

        self.flow_ao = self._aar_da.flow
        self.flow_pa = self._da_pa.flow

        self.viscosity = self._da.viscosity

        self._da.el_base = self.el_min

        self.diameter_ao = min(self.diameter_ao, self.diameter_ao_max)
        self.diameter_pa = min(self.diameter_pa, self.diameter_pa_max)

        self._aar_da.no_flow = self.diameter_ao == 0
        self._da_pa.no_flow = self.diameter_pa == 0

        self.res_ao = self.calc_resistance(self.diameter_ao, self.length / 2.0, self.viscosity)
        self.res_pa = self.calc_resistance(self.diameter_pa, self.length / 2.0, self.viscosity)

        self._aar_da.r_for = self.res_ao
        self._aar_da.r_back = self.res_ao

        self._da_pa.r_for = self.res_pa
        self._da_pa.r_back = self.res_pa

        self.el = self.el_min + (self.el_max - self.el_min) * (self.diameter_pa / self.diameter_pa_max)

        area_ao = ((self.diameter_ao * 0.001) / 2.0) ** 2.0 * math.pi
        area_pa = ((self.diameter_pa * 0.001) / 2.0) ** 2.0 * math.pi

        self.velocity_ao = (self.flow_ao * 0.001) / area_ao if area_ao > 0 else 0.0
        self.velocity_pa = (self.flow_pa * 0.001) / area_pa if area_pa > 0 else 0.0

        self.vol = self._da.vol

    def set_diameter(self, new_diameter):
        self.diameter_ao = new_diameter
        self.diameter_pa = new_diameter

    def calc_resistance(self, diameter, length=20.0, viscosity=6.0):
        if diameter > 0.0 and length > 0.0:
            n_pas = viscosity / 1000.0
            length_meters = length / 1000.0
            radius_meters = diameter / 2 / 1000.0
            res = (8.0 * n_pas * length_meters) / (math.pi * (radius_meters ** 4))
            res = res * 0.00000750062
            return res
        return 100000000
