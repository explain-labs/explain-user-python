"""GasDiffusor — port of src/explain/base_models/GasDiffusor.js

Moves O2, CO2, N2, other-gas between two gas compartments based on partial
pressure gradients. Uses `_factor_scaling` (no `_ps` suffix) for scaling
factors — same JS quirk as BloodDiffusor.
"""

from __future__ import annotations

from ..base_model import BaseModelClass
from ..helpers.gas_composition import calc_gas_composition


class GasDiffusor(BaseModelClass):
    model_type = "GasDiffusor"

    model_interface = [
        {"target": "model_type", "type": "string", "readonly": True},
        {"target": "description", "type": "string", "build_prop": True,
         "readonly": True, "caption": "description"},
        {"target": "is_enabled", "type": "boolean", "build_prop": True, "caption": "enabled"},
        {"target": "dif_o2", "type": "number", "build_prop": True,
         "caption": "oxygen diffusion constant"},
        {"target": "dif_co2", "type": "number", "build_prop": True,
         "caption": "carbon dioxide diffusion constant"},
        {"target": "dif_n2", "type": "number", "build_prop": True,
         "caption": "nitric oxide diffusion constant"},
        {"target": "dif_other", "type": "number", "build_prop": True,
         "caption": "other gasses diffusion constant"},
        {"target": "comp_gas1", "type": "list", "build_prop": True,
         "caption": "gas component 1", "options": ["GasCapacitance"]},
        {"target": "comp_gas2", "type": "list", "build_prop": True,
         "caption": "gas component 2", "options": ["GasCapacitance"]},
        {"target": "dif_o2_factor_ps", "type": "factor"},
        {"target": "dif_co2_factor_ps", "type": "factor"},
        {"target": "dif_n2_factor_ps", "type": "factor"},
        {"target": "dif_other_factor_ps", "type": "factor"},
    ]

    def __init__(self, model_ref, name: str = ""):
        super().__init__(model_ref, name)

        self.comp_gas1 = ""
        self.comp_gas2 = ""
        self.dif_o2 = 0.01
        self.dif_co2 = 0.01
        self.dif_n2 = 0.01
        self.dif_other = 0.01

        self.dif_o2_factor = 1.0
        self.dif_co2_factor = 1.0
        self.dif_n2_factor = 1.0
        self.dif_other_factor = 1.0

        self.dif_o2_factor_ps = 1.0
        self.dif_co2_factor_ps = 1.0
        self.dif_n2_factor_ps = 1.0
        self.dif_other_factor_ps = 1.0

        # scaling factors — JS quirk: _scaling (no _ps suffix), same as BloodDiffusor
        self.dif_o2_factor_scaling = 1.0
        self.dif_co2_factor_scaling = 1.0
        self.dif_n2_factor_scaling = 1.0
        self.dif_other_factor_scaling = 1.0

        self._comp_gas1 = None
        self._comp_gas2 = None
        self.dif_o2_step = 0.0
        self.dif_co2_step = 0.0
        self.dif_n2_step = 0.0
        self.dif_other_step = 0.0

    def calc_model(self):
        self._comp_gas1 = self._model_engine.models[self.comp_gas1]
        self._comp_gas2 = self._model_engine.models[self.comp_gas2]

        calc_gas_composition(self._comp_gas1)
        calc_gas_composition(self._comp_gas2)

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
        self.dif_n2_step = (
            self.dif_n2
            + (self.dif_n2_factor - 1) * self.dif_n2
            + (self.dif_n2_factor_ps - 1) * self.dif_n2
            + (self.dif_n2_factor_scaling - 1) * self.dif_n2
        )
        self.dif_other_step = (
            self.dif_other
            + (self.dif_other_factor - 1) * self.dif_other
            + (self.dif_other_factor_ps - 1) * self.dif_other
            + (self.dif_other_factor_scaling - 1) * self.dif_other
        )

        do2 = (self._comp_gas1.po2 - self._comp_gas2.po2) * self.dif_o2_step * self._t
        self._comp_gas1.co2 = (self._comp_gas1.co2 * self._comp_gas1.vol - do2) / self._comp_gas1.vol
        self._comp_gas2.co2 = (self._comp_gas2.co2 * self._comp_gas2.vol + do2) / self._comp_gas2.vol

        dco2 = (self._comp_gas1.pco2 - self._comp_gas2.pco2) * self.dif_co2_step * self._t
        self._comp_gas1.cco2 = (self._comp_gas1.cco2 * self._comp_gas1.vol - dco2) / self._comp_gas1.vol
        self._comp_gas2.cco2 = (self._comp_gas2.cco2 * self._comp_gas2.vol + dco2) / self._comp_gas2.vol

        dn2 = (self._comp_gas1.pn2 - self._comp_gas2.pn2) * self.dif_n2_step * self._t
        self._comp_gas1.cn2 = (self._comp_gas1.cn2 * self._comp_gas1.vol - dn2) / self._comp_gas1.vol
        self._comp_gas2.cn2 = (self._comp_gas2.cn2 * self._comp_gas2.vol + dn2) / self._comp_gas2.vol

        dother = (self._comp_gas1.pother - self._comp_gas2.pother) * self.dif_other_step * self._t
        self._comp_gas1.cother = (self._comp_gas1.cother * self._comp_gas1.vol - dother) / self._comp_gas1.vol
        self._comp_gas2.cother = (self._comp_gas2.cother * self._comp_gas2.vol + dother) / self._comp_gas2.vol

        self.dif_o2_factor = 1.0
        self.dif_co2_factor = 1.0
        self.dif_n2_factor = 1.0
        self.dif_other_factor = 1.0
