"""Pda — port of src/explain/component_models/Pda.js

Ductus arteriosus. Computes resistance at the aortic and pulmonary halves of a
linearly tapered cone via Hagen-Poiseuille, pushes them onto AAR_DA and DA_PA,
couples elastance to resistance via an alpha exponent, and reports continuity
and modified-Bernoulli velocity outputs (with a jet correction).

See docs/Pda.md and docs/Pda-velocity.md in the JS package for anatomy /
physiology background and the rationale behind the velocity outputs.
"""

from __future__ import annotations

import math

from ..base_model import BaseModelClass


# Hagen-Poiseuille resistance unit conversion: Pa*s/m^3 -> mmHg*s/L.
PA_S_PER_M3_TO_MMHG_S_PER_L = 0.00000750062
# Pre-multiplied prefactors for the resistance formulas (saves one multiply per call).
#   uniform cylinder: R = (8 / pi) * mu * L / r^4 * [Pa->mmHg]
#   conical taper:    R = (8 / 3pi) * mu * L * (r1^2 + r1*r2 + r2^2) / (r1^3 * r2^3) * [Pa->mmHg]
RESISTANCE_PREFACTOR = (8.0 / math.pi) * PA_S_PER_M3_TO_MMHG_S_PER_L
CONICAL_RESISTANCE_PREFACTOR = (8.0 / (3.0 * math.pi)) * PA_S_PER_M3_TO_MMHG_S_PER_L
# Resistance returned when geometry collapses to zero (sentinel "no flow").
RESISTANCE_NO_FLOW = 1e8
# Multiplier on el_base used when the duct is fully closed. The full computation
# yields el ~ el_base * (R_no_flow / R_open)^alpha ~ el_base * few-thousand for
# typical neonatal geometry; the exact value doesn't affect DA pressure when the
# capacitance holds u_vol, so a deterministic constant is sufficient.
CLOSED_EL_SCALE = 5000


class Pda(BaseModelClass):
    model_type = "Pda"

    model_interface = [
        {"target": "description", "type": "string", "build_prop": True,
         "edit_mode": "caption", "readonly": True, "caption": "description"},
        {"target": "is_enabled", "type": "boolean", "build_prop": True,
         "edit_mode": "all", "readonly": False, "caption": "enabled"},
        {"caption": "ductus diameter (%)", "target": "diameter_relative",
         "type": "number", "delta": 1, "factor": 100, "rounding": 0,
         "ul": 100, "ll": 0, "build_prop": True, "edit_mode": "basic",
         "readonly": False, "slider": True},
        {"caption": "max diameter aortic ampulla (mm)", "target": "diameter_ao_max",
         "type": "number", "delta": 0.1, "factor": 1.0, "rounding": 1,
         "build_prop": True, "edit_mode": "extra", "readonly": False},
        {"caption": "max diameter pulmonary end (mm)", "target": "diameter_pa_max",
         "type": "number", "delta": 0.1, "factor": 1.0, "rounding": 1,
         "build_prop": True, "edit_mode": "extra", "readonly": False},
        {"caption": "ductus arteriosus length (mm)", "target": "length",
         "type": "number", "delta": 0.1, "factor": 1.0, "rounding": 1,
         "build_prop": True, "edit_mode": "extra", "readonly": False},
        {"caption": "baseline elastance (open duct, mmHg/L)", "target": "el_base",
         "type": "number", "delta": 0.1, "factor": 1.0, "rounding": 1,
         "build_prop": True, "edit_mode": "extra", "readonly": False},
        {"caption": "elastance-resistance coupling alpha", "target": "alpha",
         "type": "number", "delta": 0.05, "factor": 1.0, "rounding": 2,
         "ul": 1.5, "ll": 0.0, "build_prop": True, "edit_mode": "extra",
         "readonly": False},
        {"caption": "jet velocity exponent", "target": "jet_exponent",
         "type": "number", "delta": 0.1, "factor": 1.0, "rounding": 2,
         "ul": 3.0, "ll": 0.0, "build_prop": True, "edit_mode": "extra",
         "readonly": False},
    ]

    def __init__(self, model_ref, name: str = ""):
        super().__init__(model_ref, name)

        # -----------------------------------------------
        # independent properties
        # -----------------------------------------------
        self.diameter_ao_max = 3.0    # max diameter at aortic origin (mm)
        self.diameter_pa_max = 2.0    # max diameter at pulmonary end (mm)
        self.diameter_relative = 0.0  # relative diameter [0..1], scales both ends together
        self.length = 20              # length (mm)
        self.el_base = 30000          # baseline (open-duct) elastance (mmHg/L); scaled by (R/R_open)^alpha as the duct constricts
        # alpha: resistance-elastance coupling exponent (BloodVessel-style). Between the large-artery
        # thin-wall value (0.5, gives the literature "order of magnitude" elastance rise for ~100x R
        # rise during functional closure) and the arteriole value (0.63), with a small bump for the
        # PDA's high SM content.
        self.alpha = 0.55
        # jet_exponent: exponent n on (R_total / R_open_total)^(n/4) used to amplify the continuity
        # velocity into a jet-corrected end velocity. Same driver as the elastance alpha-coupling; the /4
        # normalization makes n = 1 behave like a linear diameter correction (matches the original
        # empirical (d_max/d_pa)^1 formula).
        self.jet_exponent = 0.6

        # -----------------------------------------------
        # dependent properties (recomputed each step)
        # -----------------------------------------------
        self.diameter_ao = 0.0       # current diameter at aortic origin (mm)
        self.diameter_pa = 0.0       # current diameter at pulmonary end (mm)
        self.viscosity = 6           # blood viscosity (cP), pulled from the DA capacitance
        self.vol = 0                 # duct volume (L), pulled from the DA capacitance
        self.flow_ao = 0             # flow at the aortic resistor (L/s)
        self.flow_pa = 0             # flow at the pulmonary resistor (L/s)
        self.res_ao = 1500           # resistance of the AO-half of the cone (mmHg*s/L)
        self.res_pa = 1500           # resistance of the PA-half of the cone (mmHg*s/L)
        self.el = 30000              # current elastance, el_base * (R/R_open)^alpha (mmHg/L)
        self.velocity_ao = 0         # bulk mean velocity at aortic end, Q/A (m/s)
        self.velocity_pa = 0         # bulk mean velocity at pulmonary end, Q/A (m/s)
        self.velocity_doppler = 0    # peak velocity from modified Bernoulli, sign(dP)*sqrt(|dP|/4) (m/s)
        self.velocity_ao_jet = 0     # velocity_ao amplified by stenosis factor (m/s)
        self.velocity_pa_jet = 0     # velocity_pa amplified by stenosis factor (m/s)

        # -----------------------------------------------
        # local references (preceded with _)
        # -----------------------------------------------
        self._da = None      # BloodCapacitance (DA)
        self._aar_da = None  # Resistor (AA -> DA)
        self._da_pa = None   # Resistor (DA -> PA)

    def init_model(self, args):
        super().init_model(args)

        # cache sub-model references so we don't hash-lookup every step
        self._aar_da = self._model_engine.models.get("AAR_DA")
        self._da = self._model_engine.models.get("DA")
        self._da_pa = self._model_engine.models.get("DA_PA")

    def calc_model(self):
        aar_da = self._aar_da
        da_pa = self._da_pa
        da = self._da

        # ----- closed-duct fast path -----
        # diameter_relative == 0 is the postnatal steady state. The cone math, the
        # Bernoulli sqrt, and the continuity divisions all degenerate; set sentinel
        # values and skip the rest.
        if self.diameter_relative == 0:
            self.diameter_ao = 0
            self.diameter_pa = 0
            self.viscosity = da.viscosity
            self.flow_ao = aar_da.flow
            self.flow_pa = da_pa.flow
            aar_da.no_flow = True
            da_pa.no_flow = True
            self.res_ao = RESISTANCE_NO_FLOW
            self.res_pa = RESISTANCE_NO_FLOW
            aar_da.r_for = RESISTANCE_NO_FLOW
            aar_da.r_back = RESISTANCE_NO_FLOW
            da_pa.r_for = RESISTANCE_NO_FLOW
            da_pa.r_back = RESISTANCE_NO_FLOW
            self.el = self.el_base * CLOSED_EL_SCALE
            da.el_base = self.el
            self.velocity_doppler = 0
            self.velocity_ao = 0
            self.velocity_pa = 0
            self.velocity_ao_jet = 0
            self.velocity_pa_jet = 0
            self.vol = da.vol
            return

        # ----- geometry: diameters scale together along diameter_relative -----
        d_ao = min(self.diameter_relative * self.diameter_ao_max, self.diameter_ao_max)
        d_pa = min(self.diameter_relative * self.diameter_pa_max, self.diameter_pa_max)
        self.diameter_ao = d_ao
        self.diameter_pa = d_pa

        # pull current flows and viscosity from the underlying models
        self.flow_ao = aar_da.flow
        self.flow_pa = da_pa.flow
        self.viscosity = da.viscosity

        # when fully constricted, force no flow on both resistors
        aar_da.no_flow = d_ao == 0
        da_pa.no_flow = d_pa == 0

        # ----- resistance: linearly tapered cone, split at the midpoint -----
        half_length = self.length * 0.5
        d_mid = (d_ao + d_pa) * 0.5
        res_ao = self.calc_conical_resistance(d_ao, d_mid, half_length, self.viscosity)
        res_pa = self.calc_conical_resistance(d_mid, d_pa, half_length, self.viscosity)
        self.res_ao = res_ao
        self.res_pa = res_pa
        aar_da.r_for = res_ao
        aar_da.r_back = res_ao
        da_pa.r_for = res_pa
        da_pa.r_back = res_pa

        # ----- resistance-elastance coupling (BloodVessel alpha-pattern) -----
        # As the duct constricts, R rises as ~1/d^4 and the wall stiffness rises as (R / R_open)^alpha,
        # reproducing the literature-described order-of-magnitude jump in total elastance during
        # functional closure. The result is unbounded — the closed-duct case naturally drives the
        # elastance toward effective infinity.
        d_mid_max = (self.diameter_ao_max + self.diameter_pa_max) * 0.5
        res_open_ao = self.calc_conical_resistance(self.diameter_ao_max, d_mid_max, half_length, self.viscosity)
        res_open_pa = self.calc_conical_resistance(d_mid_max, self.diameter_pa_max, half_length, self.viscosity)
        res_open_total = res_open_ao + res_open_pa
        res_total = res_ao + res_pa
        r_factor = res_total / res_open_total if res_open_total > 0 else 1.0
        self.el = self.el_base * (r_factor ** self.alpha)
        da.el_base = self.el

        # ----- velocity outputs -----
        # Modified Bernoulli at the trans-ductal gradient:
        #   dP (mmHg) = 4 * v^2   ->   v_jet (m/s) = sign(dP) * sqrt(|dP|/4)
        # The signed gradient (p_aa - p_pa) keeps the sign of all outputs consistent during flow
        # reversal (PHT / bidirectional shunting); using a local p_da would let the DA capacitance's
        # transient pressure swings flip the sign of one half independently of the other.
        closed = aar_da.no_flow or da_pa.no_flow
        v_doppler = 0.0
        if not closed:
            p_aa = getattr(getattr(aar_da, "_comp_from", None), "pres", 0.0)
            p_pa = getattr(getattr(da_pa, "_comp_to", None), "pres", 0.0)
            dp = p_aa - p_pa
            sign = (dp > 0) - (dp < 0)
            v_doppler = sign * math.sqrt(abs(dp) / 4.0)
        self.velocity_doppler = v_doppler

        # Continuity (Q/A) bulk mean velocities at each end.
        # diameter is in mm; convert to m by *1e-3, then radius = d/2, area = pi*r^2.
        r_ao_m = d_ao * 0.0005
        r_pa_m = d_pa * 0.0005
        area_ao = math.pi * r_ao_m * r_ao_m
        area_pa = math.pi * r_pa_m * r_pa_m
        # flow is L/s; multiply by 1e-3 to get m^3/s so Q/A is in m/s.
        self.velocity_ao = (aar_da.flow * 0.001) / area_ao if area_ao > 0 else 0.0
        self.velocity_pa = (da_pa.flow * 0.001) / area_pa if area_pa > 0 else 0.0

        # Jet correction: amplify the smooth continuity waveform as the duct constricts.
        jet_scale = r_factor ** (self.jet_exponent * 0.25)
        self.velocity_ao_jet = self.velocity_ao * jet_scale
        self.velocity_pa_jet = self.velocity_pa * jet_scale

        self.vol = da.vol

    def calc_resistance(self, diameter, length=20.0, viscosity=6.0):
        # Poiseuille's law for a uniform cylinder: R = (8 * mu * L) / (pi * r^4)
        # diameter (mm), length (mm), viscosity (cP).
        if diameter <= 0.0 or length <= 0.0:
            return RESISTANCE_NO_FLOW

        n_pas = viscosity * 0.001       # cP -> Pa*s
        length_m = length * 0.001        # mm -> m
        r_m = diameter * 0.0005          # mm/2 -> m
        r2 = r_m * r_m
        r4 = r2 * r2
        return (RESISTANCE_PREFACTOR * n_pas * length_m) / r4

    def calc_conical_resistance(self, d1, d2, length=20.0, viscosity=6.0):
        # Hagen-Poiseuille integrated over a linearly tapered cone:
        #   R = (8 * mu * L) / (3 * pi) * (r1^2 + r1*r2 + r2^2) / (r1^3 * r2^3)
        # diameters (mm), length (mm), viscosity (cP).
        if d1 <= 0.0 or d2 <= 0.0 or length <= 0.0:
            return RESISTANCE_NO_FLOW

        n_pas = viscosity * 0.001       # cP -> Pa*s
        length_m = length * 0.001       # mm -> m
        r1 = d1 * 0.0005                # mm/2 -> m
        r2 = d2 * 0.0005                # mm/2 -> m
        numerator = r1 * r1 + r1 * r2 + r2 * r2
        denominator = r1 * r1 * r1 * r2 * r2 * r2
        return (CONICAL_RESISTANCE_PREFACTOR * n_pas * length_m * numerator) / denominator
