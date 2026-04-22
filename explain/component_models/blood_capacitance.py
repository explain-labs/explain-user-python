"""BloodCapacitance — port of src/explain/component_models/BloodCapacitance.js

Extends Capacitance with blood-composition tracking (to2, tco2, solutes,
drugs, temperature, viscosity). Overrides `volume_in` to mix the inflowing
composition into the current compartment using the classical mixing formula:

    this.X += (comp_from.X - this.X) * dvol / this.vol

This is equivalent to a mass-conservation mix where `this.vol` is the
post-inflow volume: new_X = (old_X * (vol - dvol) + comp_from.X * dvol) / vol.
"""

from __future__ import annotations

from ..base_models.capacitance import Capacitance


class BloodCapacitance(Capacitance):
    model_type = "BloodCapacitance"

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

    def volume_in(self, dvol: float, comp_from=None):
        # super call first — adds dvol to self.vol (unless fixed_composition)
        super().volume_in(dvol, comp_from)

        # Guard against divide-by-zero. Matches JS behavior when this.vol == 0
        # after super — JS produces NaN, which propagates; we skip instead so
        # a research run isn't polluted by NaN state. If you need strict JS
        # parity including NaN propagation, remove this guard.
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

        # mix drugs
        for drug in list(self.drugs.keys()):
            cf = 0.0
            cf_val = getattr(comp_from, "drugs", {}).get(drug)
            if cf_val:
                cf = cf_val
            self.drugs[drug] += (cf - self.drugs[drug]) * dvol / self.vol

        # temperature and viscosity are treated like solutes
        cf_temp = getattr(comp_from, "temp", self.temp)
        self.temp += (cf_temp - self.temp) * dvol / self.vol

        cf_visc = getattr(comp_from, "viscosity", self.viscosity)
        self.viscosity += (cf_visc - self.viscosity) * dvol / self.vol
