"""BloodDiffusor — port of src/explain/base_models/BloodDiffusor.js

A BloodDiffusor moves O2, CO2, and per-solute quantities between two
blood-containing compartments (referenced by name via `comp_blood1` /
`comp_blood2`). Gas diffusion is driven by the partial-pressure gradient
computed from the solved composition; solute diffusion is driven by the
concentration gradient.

Flow sign convention (JS verbatim):
    do2  = (blood1.po2  - blood2.po2)  * dif_o2_step  * dt
    dco2 = (blood1.pco2 - blood2.pco2) * dif_co2_step * dt
    dsol = (blood1.solutes[s] - blood2.solutes[s]) * dif_s_step * dt
Positive d* means mass moves FROM blood1 TO blood2. Concentrations are
updated mass-conservatively (new_X = (old_X * vol -/+ d) / vol); the
compartment volume is treated as unchanged by the diffusion step itself.

Factor-tier naming note — preserved JS quirk:
The scaling factors here are named `dif_*_factor_scaling` (no `_ps`
suffix), unlike most other ported classes which use `_factor_scaling_ps`.
The JS source uses the `_scaling` form; this port matches JS verbatim.
If scenario JSONs reference one name vs. the other, that is a loader-side
concern, not something this port should try to normalize.

Upstream dependency:
Before computing diffusion, this class calls `calc_blood_composition` on
both compartments. That helper is memoized by engine step stamp, so the
double-call is cheap when many diffusors share the same compartments in
the same step.
"""

from __future__ import annotations

from ..base_model import BaseModelClass
from ..helpers.blood_composition import calc_blood_composition


class BloodDiffusor(BaseModelClass):
    model_type = "BloodDiffusor"

    model_interface = [
        {"target": "model_type", "type": "string", "readonly": True},
        {"target": "description", "type": "string", "build_prop": True,
         "readonly": True, "caption": "description"},
        {"target": "is_enabled", "type": "boolean", "build_prop": True,
         "caption": "enabled"},
        {"target": "dif_o2", "type": "number", "build_prop": True,
         "caption": "oxygen diffusion constant"},
        {"target": "dif_co2", "type": "number", "build_prop": True,
         "caption": "carbon dioxide diffusion constant"},
        {"target": "dif_solutes", "type": "number", "build_prop": True,
         "caption": "solute diffusion constant"},
        {"target": "comp_blood1", "type": "list", "build_prop": True,
         "caption": "blood component 1",
         "options": ["BloodCapacitance", "BloodTimeVaryingElastance",
                     "BloodPump", "BloodVessel", "MicroVascularUnit",
                     "HeartChamber"]},
        {"target": "comp_blood2", "type": "list", "build_prop": True,
         "caption": "blood component 2",
         "options": ["BloodCapacitance", "BloodTimeVaryingElastance",
                     "BloodPump", "BloodVessel", "MicroVascularUnit",
                     "HeartChamber"]},
        {"target": "dif_o2_factor_ps", "type": "factor",
         "caption": "oxygen diffusion factor"},
        {"target": "dif_co2_factor_ps", "type": "factor",
         "caption": "carbon dioxide diffusion factor"},
        {"target": "dif_solutes_factor_ps", "type": "factor",
         "caption": "solute diffusion factor"},
    ]

    def __init__(self, model_ref, name: str = ""):
        super().__init__(model_ref, name)

        # independent properties (connected compartment names and per-species
        # diffusion constants). `dif_solutes` is a dict {solute_name -> constant}
        # populated from JSON at init time.
        self.comp_blood1 = "PLF"
        self.comp_blood2 = "PLM"
        self.dif_o2 = 0.01         # mmol / (mmHg * s)
        self.dif_co2 = 0.01        # mmol / (mmHg * s)
        self.dif_solutes: dict = {}  # {name: constant mmol / (mmol * s)}

        # non-persistent factors — reset to 1.0 each step
        self.dif_o2_factor = 1.0
        self.dif_co2_factor = 1.0
        self.dif_solutes_factor = 1.0

        # persistent factors (_ps)
        self.dif_o2_factor_ps = 1.0
        self.dif_co2_factor_ps = 1.0
        self.dif_solutes_factor_ps = 1.0

        # scaling factors — NOTE: JS names these `_scaling` (no `_ps` suffix),
        # diverging from the convention used by Capacitance / Resistor. Port
        # matches JS verbatim.
        self.dif_o2_factor_scaling = 1.0
        self.dif_co2_factor_scaling = 1.0
        self.dif_solutes_factor_scaling = 1.0

        # dependent (per-step diffusion strength after factor tiers)
        self.dif_o2_step = 0.0
        self.dif_co2_step = 0.0

        # internal references, resolved each step
        self._comp_blood1 = None
        self._comp_blood2 = None

    def calc_model(self):
        # resolve connected compartments by name (same pattern as Resistor)
        self._comp_blood1 = self._model_engine.models[self.comp_blood1]
        self._comp_blood2 = self._model_engine.models[self.comp_blood2]

        # ensure po2/pco2 are fresh on both compartments before reading them.
        # calc_blood_composition is memoized by engine step stamp, so repeat
        # calls in the same step are cheap.
        calc_blood_composition(self._comp_blood1)
        calc_blood_composition(self._comp_blood2)

        # effective diffusion constants for this step
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

        # JS quirk: `solutes_step` is a SCALAR multiplier applied to every
        # per-solute diffusion constant, not a per-solute effective value.
        # It folds the three factor tiers into one unitless multiplier.
        solutes_step = (
            1.0
            + (self.dif_solutes_factor - 1)
            + (self.dif_solutes_factor_ps - 1)
            + (self.dif_solutes_factor_scaling - 1)
        )

        # O2 diffusion (partial-pressure driven)
        do2 = (self._comp_blood1.po2 - self._comp_blood2.po2) * self.dif_o2_step * self._t

        if not self._comp_blood1.fixed_composition:
            self._comp_blood1.to2 = (
                self._comp_blood1.to2 * self._comp_blood1.vol - do2
            ) / self._comp_blood1.vol
        if not self._comp_blood2.fixed_composition:
            self._comp_blood2.to2 = (
                self._comp_blood2.to2 * self._comp_blood2.vol + do2
            ) / self._comp_blood2.vol

        # CO2 diffusion (partial-pressure driven)
        dco2 = (self._comp_blood1.pco2 - self._comp_blood2.pco2) * self.dif_co2_step * self._t

        if not self._comp_blood1.fixed_composition:
            self._comp_blood1.tco2 = (
                self._comp_blood1.tco2 * self._comp_blood1.vol - dco2
            ) / self._comp_blood1.vol
        if not self._comp_blood2.fixed_composition:
            self._comp_blood2.tco2 = (
                self._comp_blood2.tco2 * self._comp_blood2.vol + dco2
            ) / self._comp_blood2.vol

        # Solute diffusion (concentration-gradient driven). Iteration is over
        # the keys in self.dif_solutes; both compartments must carry the same
        # solute keys (JS would NaN-propagate if missing — Python will
        # KeyError, which is louder and easier to debug).
        for sol in list(self.dif_solutes.keys()):
            dif = self.dif_solutes[sol] * solutes_step
            dsol = (
                self._comp_blood1.solutes[sol] - self._comp_blood2.solutes[sol]
            ) * dif * self._t

            if not self._comp_blood1.fixed_composition:
                self._comp_blood1.solutes[sol] = (
                    self._comp_blood1.solutes[sol] * self._comp_blood1.vol - dsol
                ) / self._comp_blood1.vol
            if not self._comp_blood2.fixed_composition:
                self._comp_blood2.solutes[sol] = (
                    self._comp_blood2.solutes[sol] * self._comp_blood2.vol + dsol
                ) / self._comp_blood2.vol

        # reset non-persistent factors
        self.dif_o2_factor = 1.0
        self.dif_co2_factor = 1.0
        self.dif_solutes_factor = 1.0
