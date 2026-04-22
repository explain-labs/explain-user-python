"""GasExchanger — port of src/explain/base_models/GasExchanger.js

Alveolar gas exchange between one blood compartment and one gas compartment.
Diffusion is partial-pressure driven with concentration updates clamped
non-negative. Calls calc_blood_composition before reading blood po2/pco2.
"""

from __future__ import annotations

from ..base_model import BaseModelClass
from ..helpers.blood_composition import calc_blood_composition


class GasExchanger(BaseModelClass):
    model_type = "GasExchanger"

    model_interface = [
        {"target": "model_type", "type": "string", "readonly": True},
        {"target": "description", "type": "string", "build_prop": True,
         "readonly": True, "caption": "description"},
        {"target": "is_enabled", "type": "boolean", "build_prop": True, "caption": "enabled"},
        {"target": "dif_o2", "type": "number", "build_prop": True,
         "caption": "oxygen diffusion constant"},
        {"target": "dif_co2", "type": "number", "build_prop": True,
         "caption": "carbon dioxide diffusion constant"},
        {"target": "comp_gas", "type": "list", "build_prop": True,
         "caption": "gas component", "options": ["GasCapacitance"]},
        {"target": "comp_blood", "type": "list", "build_prop": True,
         "caption": "blood component",
         "options": ["BloodCapacitance", "BloodTimeVaryingElastance", "BloodPump",
                     "BloodVessel", "MicroVascularUnit", "HeartChamber"]},
        {"target": "dif_o2_factor_ps", "type": "factor"},
        {"target": "dif_co2_factor_ps", "type": "factor"},
    ]

    def __init__(self, model_ref, name: str = ""):
        super().__init__(model_ref, name)

        self.comp_blood = ""
        self.comp_gas = ""
        self.dif_o2 = 0.0
        self.dif_co2 = 0.0

        self.dif_o2_factor = 1.0
        self.dif_co2_factor = 1.0

        self.dif_o2_factor_ps = 1.0
        self.dif_co2_factor_ps = 1.0

        self.dif_o2_factor_scaling = 1.0
        self.dif_co2_factor_scaling = 1.0

        self.flux_o2 = 0.0
        self.flux_co2 = 0.0

        self._blood = None
        self._gas = None
        self.dif_o2_step = 0.0
        self.dif_co2_step = 0.0

    def calc_model(self):
        self._blood = self._model_engine.models[self.comp_blood]
        self._gas = self._model_engine.models[self.comp_gas]

        calc_blood_composition(self._blood)

        po2_blood = self._blood.po2
        pco2_blood = self._blood.pco2
        to2_blood = self._blood.to2
        tco2_blood = self._blood.tco2

        co2_gas = self._gas.co2
        cco2_gas = self._gas.cco2
        po2_gas = self._gas.po2
        pco2_gas = self._gas.pco2

        if self._blood.vol == 0.0:
            return

        self.dif_o2_step = (
            self.dif_o2
            + (self.dif_o2_factor - 1) * self.dif_o2
            + (self.dif_o2_factor_ps - 1) * self.dif_o2
            + (self.dif_o2_factor_scaling - 1) * self.dif_o2
        )
        self.dif_co2_step = (
            self.dif_co2
            + (self.dif_co2_factor - 1) * self.dif_co2
            + (self.dif_co2_factor_ps - 1) * self.dif_co2
            + (self.dif_co2_factor_scaling - 1) * self.dif_co2
        )

        self.flux_o2 = (po2_blood - po2_gas) * self.dif_o2_step * self._t

        new_to2_blood = (to2_blood * self._blood.vol - self.flux_o2) / self._blood.vol
        if new_to2_blood < 0:
            new_to2_blood = 0.0

        new_co2_gas = (co2_gas * self._gas.vol + self.flux_o2) / self._gas.vol
        if new_co2_gas < 0:
            new_co2_gas = 0.0

        self.flux_co2 = (pco2_blood - pco2_gas) * self.dif_co2_step * self._t

        new_tco2_blood = (tco2_blood * self._blood.vol - self.flux_co2) / self._blood.vol
        if new_tco2_blood < 0:
            new_tco2_blood = 0.0

        new_cco2_gas = (cco2_gas * self._gas.vol + self.flux_co2) / self._gas.vol
        if new_cco2_gas < 0:
            new_cco2_gas = 0.0

        self._blood.to2 = new_to2_blood
        self._blood.tco2 = new_tco2_blood
        self._gas.co2 = new_co2_gas
        self._gas.cco2 = new_cco2_gas

        self.dif_o2_factor = 1.0
        self.dif_co2_factor = 1.0
