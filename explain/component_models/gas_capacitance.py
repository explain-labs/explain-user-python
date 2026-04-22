"""GasCapacitance — port of src/explain/component_models/GasCapacitance.js

Extends Capacitance with gas-specific state: temperature, humidity,
per-species concentrations (o2, co2, n2, h2o, other), partial pressures,
and volume fractions. The calc_model pipeline is entirely custom — it does
NOT call the parent calc_model; it runs add_heat → add_watervapour →
calc_elastances → calc_volumes → calc_pressure → calc_gas_composition in
that order.

calc_pressure override adds three non-persistent external pressures
(pres_ext absorbed by super, then pres_cc + pres_mus) plus the persistent
pres_atm. pres_cc and pres_mus are reset after absorption; pres_atm is NOT
reset (it's a persistent scenario property, not a per-step push).

volume_in override uses the classical mass-conservation mixing formula
`(X*vol + (X_from - X)*dvol) / vol` — note this is written in the pre-
divide form in the JS source, which differs in operation order from the
BloodCapacitance port's `X += (X_from - X) * dvol / vol`. Algebraically
identical; floating-point order differs, so the JS form is preserved
verbatim to keep bit-identical agreement with the JS engine.

add_heat uses a hardcoded temperature-relaxation coefficient (0.0005) that
is NOT self._t — it's a simulation tuning constant. The subsequent
ideal-gas-law volume adjustment is gated on `pres != 0` and honours
fixed_composition.

add_watervapour's dH2O coefficient IS multiplied by self._t, so that term
is step-size dependent.
"""

from __future__ import annotations

import math

from ..base_models.capacitance import Capacitance


class GasCapacitance(Capacitance):
    model_type = "GasCapacitance"

    model_interface = [
        {"target": "model_type", "type": "string", "readonly": True},
        {"target": "description", "type": "string", "build_prop": True,
         "readonly": True, "caption": "description"},
        {"target": "is_enabled", "type": "boolean", "build_prop": True,
         "caption": "enabled"},
        {"target": "fixed_composition", "type": "boolean",
         "caption": "fixed gas composition"},
        {"target": "u_vol", "type": "number", "caption": "unstressed volume (L)"},
        {"target": "el_base", "type": "number", "caption": "elastance baseline (mmHg/L)"},
        {"target": "el_k", "type": "number", "caption": "elastance non linear k"},
        {"target": "target_temp", "type": "number", "caption": "target temperature (dgs C)"},
        {"target": "pres_atm", "type": "number", "caption": "atmospheric pressure (mmHg)"},
        {"target": "u_vol_factor_ps", "type": "factor",
         "caption": "unstressed volume factor"},
        {"target": "el_base_factor_ps", "type": "factor",
         "caption": "elastance baseline factor"},
        {"target": "el_k_factor_ps", "type": "factor",
         "caption": "elastance non linear factor"},
    ]

    def __init__(self, model_ref, name: str = ""):
        super().__init__(model_ref, name)

        # independent gas-specific properties
        self.pres_atm = 760              # atmospheric pressure (mmHg), persistent
        self.pres_cc = 0.0               # non-persistent chest-compression pressure (mmHg)
        self.pres_mus = 0.0              # non-persistent muscle pressure (mmHg)
        self.fixed_composition = False
        self.target_temp = 0.0           # target temperature (°C)

        # dependent gas-specific properties
        self.ctotal = 0.0                # total gas concentration (mmol/L)
        self.co2 = 0.0                   # O2 concentration (mmol/L)
        self.cco2 = 0.0                  # CO2 concentration (mmol/L)
        self.cn2 = 0.0                   # N2 concentration (mmol/L)
        self.cother = 0.0                # other-gas concentration (mmol/L)
        self.ch2o = 0.0                  # water-vapour concentration (mmol/L)
        self.po2 = 0.0                   # partial pressure O2 (mmHg)
        self.pco2 = 0.0                  # partial pressure CO2 (mmHg)
        self.pn2 = 0.0                   # partial pressure N2 (mmHg)
        self.pother = 0.0                # partial pressure other (mmHg)
        self.ph2o = 0.0                  # partial pressure H2O vapour (mmHg)
        self.fo2 = 0.0                   # fraction O2
        self.fco2 = 0.0                  # fraction CO2
        self.fn2 = 0.0                   # fraction N2
        self.fother = 0.0                # fraction other
        self.fh2o = 0.0                  # fraction H2O
        self.temp = 0.0                  # gas temperature (°C)
        self.humidity = 0.0              # humidity (fraction)

        # derived (written by calc_pressure, read by consumers); initialised
        # here for Python attribute-presence, matching how JS creates it on
        # first calc_pressure call.
        self.pres_rel = 0.0

        # local constants
        self._gas_constant = 62.36367    # ideal-gas constant (L·mmHg/(mol·K))

    # -------------------------------------------------------------------------
    # calc_model — custom dispatch (does NOT call super().calc_model())
    # -------------------------------------------------------------------------
    def calc_model(self):
        self.add_heat()
        self.add_watervapour()
        self.calc_elastances()
        self.calc_volumes()
        self.calc_pressure()
        self.calc_gas_composition()

    # -------------------------------------------------------------------------
    # calc_pressure — extends parent with pres_cc + pres_mus + pres_atm
    # -------------------------------------------------------------------------
    def calc_pressure(self):
        # parent computes pres_in, pres_tm, pres = pres_in + pres_ext, and
        # resets pres_ext to 0 at the end.
        super().calc_pressure()

        # layer in the other external pressures and atmospheric pressure
        self.pres = self.pres + self.pres_cc + self.pres_mus + self.pres_atm
        self.pres_rel = self.pres - self.pres_atm

        # reset non-persistent external pressures (pres_atm stays)
        self.pres_cc = 0.0
        self.pres_mus = 0.0

    # -------------------------------------------------------------------------
    # volume_in — adds volume and mixes gas composition via mass conservation
    # -------------------------------------------------------------------------
    def volume_in(self, dvol, comp_from=None):
        # super handles the volume update (respects fixed_composition)
        super().volume_in(dvol, comp_from)

        # Mixing formula in the JS source's pre-divide form. Algebraically
        # equivalent to `self.X += (comp_from.X - self.X) * dvol / self.vol`
        # but floating-point ordering differs — preserved exactly to keep
        # JS bit-parity.
        self.co2 = (self.co2 * self.vol + (comp_from.co2 - self.co2) * dvol) / self.vol
        self.cco2 = (self.cco2 * self.vol + (comp_from.cco2 - self.cco2) * dvol) / self.vol
        self.cn2 = (self.cn2 * self.vol + (comp_from.cn2 - self.cn2) * dvol) / self.vol
        self.ch2o = (self.ch2o * self.vol + (comp_from.ch2o - self.ch2o) * dvol) / self.vol
        self.cother = (self.cother * self.vol + (comp_from.cother - self.cother) * dvol) / self.vol

        # temperature mix
        self.temp = (self.temp * self.vol + (comp_from.temp - self.temp) * dvol) / self.vol

    # -------------------------------------------------------------------------
    # add_heat — relaxes temp toward target_temp; adjusts volume via ideal gas law
    # -------------------------------------------------------------------------
    def add_heat(self):
        # Temperature relaxation. Note the coefficient is a hardcoded 0.0005
        # in the JS source; it is NOT self._t, so this is a simulation-tuned
        # constant that survives step-size changes. Port verbatim.
        dT = (self.target_temp - self.temp) * 0.0005
        self.temp += dT

        # ideal gas law volume change. Honours fixed_composition.
        if self.pres != 0.0 and not self.fixed_composition:
            dV = (self.ctotal * self.vol * self._gas_constant * dT) / self.pres
            self.vol += dV / 1000.0

        # clamp non-negative (safety against drift)
        if self.vol < 0:
            self.vol = 0

    # -------------------------------------------------------------------------
    # add_watervapour — water-vapour transport and associated volume change
    # -------------------------------------------------------------------------
    def add_watervapour(self):
        pH2Ot = self.calc_watervapour_pressure()

        # Water-vapour concentration drift. The 0.00001 coefficient IS
        # multiplied by self._t, so this term is step-size dependent.
        dH2O = 0.00001 * (pH2Ot - self.ph2o) * self._t

        if self.vol > 0.0:
            self.ch2o = (self.ch2o * self.vol + dH2O) / self.vol

        # Volume change from water vapour addition (ideal-gas law).
        if self.pres != 0.0 and not self.fixed_composition:
            self.vol += ((self._gas_constant * (273.15 + self.temp)) / self.pres) * (dH2O / 1000.0)

    # -------------------------------------------------------------------------
    # calc_watervapour_pressure — Antoine-style fit for saturation vapour pressure
    # -------------------------------------------------------------------------
    def calc_watervapour_pressure(self):
        return math.exp(20.386 - 5132 / (self.temp + 273))

    # -------------------------------------------------------------------------
    # calc_gas_composition — derive fractions and partial pressures from
    # concentrations. Early-returns if ctotal == 0 (partial pressures and
    # fractions retain their previous values).
    # -------------------------------------------------------------------------
    def calc_gas_composition(self):
        self.ctotal = self.ch2o + self.co2 + self.cco2 + self.cn2 + self.cother

        # JS divides only if ctotal != 0; else returns early leaving the
        # previous partial pressures / fractions in place.
        if self.ctotal == 0.0:
            return

        self.ph2o = (self.ch2o / self.ctotal) * self.pres
        self.po2 = (self.co2 / self.ctotal) * self.pres
        self.pco2 = (self.cco2 / self.ctotal) * self.pres
        self.pn2 = (self.cn2 / self.ctotal) * self.pres
        self.pother = (self.cother / self.ctotal) * self.pres

        self.fh2o = self.ch2o / self.ctotal
        self.fo2 = self.co2 / self.ctotal
        self.fco2 = self.cco2 / self.ctotal
        self.fn2 = self.cn2 / self.ctotal
        self.fother = self.cother / self.ctotal
