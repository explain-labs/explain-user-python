"""HeartChamber — port of src/explain/component_models/HeartChamber.js

A HeartChamber is a TimeVaryingElastance that (a) carries blood composition
(to2, tco2, solutes, drugs, temperature, viscosity) the same way
BloodTimeVaryingElastance does, and (b) has an autonomic-nervous-system
(ANS) modulation of its elastances via `ans_activity` and `ans_sens`.

ANS coupling (β1-adrenergic on the myocardium):
  - systolic (el_max): positive inotropic — ANS activity INCREASES el_max_eff
  - diastolic (el_min): positive lusitropic — ANS activity DECREASES el_min_eff
  - el_k is NOT modulated by ANS

Specifically, calc_elastances applies the three standard factor tiers (as in
TimeVaryingElastance) and then adds the ANS correction:
    el_max_eff += (ans_activity - 1) * el_max * ans_sens
    el_min_eff -= (ans_activity - 1) * el_min * ans_sens

The `el_max >= el_min` clamp and the non-persistent factor reset are preserved.
`ans_activity` and `ans_sens` are persistent — they are read every step but
never reset here (the Ans model, when ported, owns updating them).

Composition mixing is identical to BloodTimeVaryingElastance: one-way,
receiving compartment only, via `dX = (from.X - self.X) * dvol / self.vol`.
"""

from __future__ import annotations

from ..base_models.time_varying_elastance import TimeVaryingElastance


class HeartChamber(TimeVaryingElastance):
    model_type = "HeartChamber"

    model_interface = [
        {"target": "model_type", "type": "string", "readonly": True},
    ]

    def __init__(self, model_ref, name: str = ""):
        super().__init__(model_ref, name)

        # independent composition properties
        self.temp = 37.0           # blood temperature (°C)
        self.viscosity = 6.0       # blood viscosity (cP = Pa·s)
        self.solutes: dict = {}    # name -> concentration
        self.drugs: dict = {}      # name -> concentration

        # ANS modulation — persistent, updated externally by the Ans model.
        # ans_sens=1 is full effect, 0 is no effect.
        self.ans_sens = 1.0
        self.ans_activity = 1.0

        # dependent composition properties (calculated elsewhere; -1 sentinel
        # means "not yet calculated")
        self.to2 = 0.0             # total O2 (mmol/L)
        self.tco2 = 0.0            # total CO2 (mmol/L)
        self.ph = -1.0
        self.pco2 = -1.0           # mmHg
        self.po2 = -1.0            # mmHg
        self.so2 = -1.0
        self.hco3 = -1.0           # mmol/L
        self.be = -1.0             # base excess, mmol/L

        # misc scratch fields present on the JS class. They are not read
        # inside HeartChamber itself but are preserved for parity with any
        # scenario JSON or downstream model that touches them.
        self.el = 0.0
        self.elmin_calc = 0.0
        self.elmax_calc = 0.9

    def calc_elastances(self):
        # Three-tier factor system, then ANS correction. Fully overrides
        # TimeVaryingElastance.calc_elastances — does NOT call super.
        #
        # Sign discipline from the JS: the ANS term is ADDED to el_max (positive
        # inotropy) and SUBTRACTED from el_min (positive lusitropy, lower
        # diastolic stiffness).
        self.el_min_eff = (
            self.el_min
            + (self.el_min_factor - 1) * self.el_min
            + (self.el_min_factor_ps - 1) * self.el_min
            + (self.el_min_factor_scaling_ps - 1) * self.el_min
            - (self.ans_activity - 1) * self.el_min * self.ans_sens
        )

        self.el_max_eff = (
            self.el_max
            + (self.el_max_factor - 1) * self.el_max
            + (self.el_max_factor_ps - 1) * self.el_max
            + (self.el_max_factor_scaling_ps - 1) * self.el_max
            + (self.ans_activity - 1) * self.el_max * self.ans_sens
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

        # reset non-persistent factors (ans_activity / ans_sens are persistent)
        self.el_min_factor = 1.0
        self.el_max_factor = 1.0
        self.el_k_factor = 1.0

    def volume_in(self, dvol: float, comp_from=None):
        # super call first — adds dvol to self.vol (TimeVaryingElastance does
        # not honor fixed_composition, so vol is always updated)
        super().volume_in(dvol, comp_from)

        # Guard against divide-by-zero. Matches the BloodCapacitance /
        # BloodTimeVaryingElastance ports: JS produces NaN when this.vol == 0
        # after super — we skip instead so a research run isn't polluted by
        # NaN state. If you need strict JS parity including NaN propagation,
        # remove this guard.
        if self.vol <= 0.0 or comp_from is None:
            return

        # mix gases
        self.to2 += (comp_from.to2 - self.to2) * dvol / self.vol
        self.tco2 += (comp_from.tco2 - self.tco2) * dvol / self.vol

        # mix solutes (keys defined on self; missing on comp_from → 0)
        for solute in list(self.solutes.keys()):
            cf = 0.0
            cf_val = getattr(comp_from, "solutes", {}).get(solute)
            if cf_val:
                cf = cf_val
            self.solutes[solute] += (cf - self.solutes[solute]) * dvol / self.vol

        # temperature and viscosity are treated like solutes
        cf_temp = getattr(comp_from, "temp", self.temp)
        self.temp += (cf_temp - self.temp) * dvol / self.vol

        cf_visc = getattr(comp_from, "viscosity", self.viscosity)
        self.viscosity += (cf_visc - self.viscosity) * dvol / self.vol

        # mix drugs
        for drug in list(self.drugs.keys()):
            cf = 0.0
            cf_val = getattr(comp_from, "drugs", {}).get(drug)
            if cf_val:
                cf = cf_val
            self.drugs[drug] += (cf - self.drugs[drug]) * dvol / self.vol
