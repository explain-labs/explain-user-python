"""BloodComposition — port of src/explain/component_models/BloodComposition.js

Pure helper; not a BaseModelClass. Exports `calc_blood_composition(bc)`, which
takes a blood-compartment-like object carrying `solutes` (dict), `to2`, `tco2`,
`temp`, optional `prev_ph`, `prev_po2`, `name`, and (optionally) an
`_model_engine` with `model_time_total` for step-stamped memoization.

On each uncached call, the function runs two sequential Brent root-finds:
  1. Acid-base: solve for [H+] via a Stewart-style electroneutrality residual.
     Primary bracket is pH ± 0.1 around `bc.prev_ph`; falls back to
     [5.85e-6, 3.16e-4] mmol/L if the narrow bracket fails.
     Writes: bc.ph, bc.pco2, bc.hco3, bc.be
  2. Oxygenation: solve for pO2 via a Hill-curve saturation + P50-shifted
     affinity (Bohr / Haldane / temp / DPG corrections). Primary bracket is
     prev_po2 ± 10; falls back to [0, 800] mmHg.
     Writes: bc.po2, bc.so2, bc.prev_po2

A memoization gate short-circuits the solvers when all 12 watched inputs
(tco2, to2, temp, prev_ph, prev_po2, plus 10 solute keys) AND the engine's
model_time_total step stamp match the previously cached values on `bc`.

Implementation note on state: the JS module uses ~25 module-level `let`
variables as shared state between the two solvers and the objective
functions `_net_charge_plasma`, `_calc_so2`, `_do2_content`. This Python
port mirrors that shape 1:1 with module-level variables and `global`
declarations, NOT a class or closure. The point is bit-identical
behavior, not re-entrancy — JS doesn't need it and neither does this.
Consequence: do not call `calc_blood_composition` concurrently from
multiple threads.
"""

from __future__ import annotations

import math

# -----------------------------------------------------------------------------
# Constants — copied verbatim from the JS source
# -----------------------------------------------------------------------------
kw              = 2.5119e-11          # water dissociation constant
kc              = 7.94328235e-4       # carbonic acid dissociation constant
kd              = 6.0255959e-8        # bicarbonate dissociation constant
alpha_co2p      = 0.03067             # CO2 solubility coefficient
left_hp_wide    = 5.848931925e-6      # lower bound for H+ concentration
right_hp_wide   = 3.16227766017e-4    # upper bound for H+ concentration
delta_ph_limits = 0.1                 # delta for pH limits
n               = 2.7                 # Hill coefficient
alpha_o2        = 1.38e-5             # O2 solubility coefficient
left_o2_wide    = 0                   # lower bound for pO2
right_o2_wide   = 800.0               # upper bound for pO2
delta_o2_limits = 10.0                # delta for pO2 limits
brent_accuracy  = 1e-6
max_iterations  = 60
gas_constant    = 62.36367

# -----------------------------------------------------------------------------
# Independent variables (solver brackets, P50 family)
# -----------------------------------------------------------------------------
P50_0      = 20.0   # fetal 18.8, neonatal 20.0, adult 26.7
P50        = 0
log10_p50  = 0
P50_n      = 0
left_o2    = 0
right_o2   = 800.0
left_hp    = 5.848931925e-6
right_hp   = 3.16227766017e-4

# -----------------------------------------------------------------------------
# State variables (shared between objective functions and the top-level calc)
# -----------------------------------------------------------------------------
ph             = 0.0
po2            = 0.0
so2            = 0.0
pco2           = 0.0
hco3           = 0.0
be             = 0.0
to2            = 0.0
hemoglobin     = 0.0
dpg            = 5.0
temp           = 0.0
tco2           = 0.0
sid            = 0.0
albumin        = 0.0
phosphates     = 0.0
uma            = 0.0
prev_ph        = 7.37
prev_po2       = 18.7
dpH            = 0  # Bohr effect:   pH down  -> right shift -> P50 up
dpCO2          = 0  # Haldane effect: pCO2 up -> right shift -> P50 up
dT             = 0  # temp up                 -> right shift -> P50 up
dDPG           = 0  # DPG up                  -> right shift -> P50 up
hemoglobin_gdl = 0.0
inv_mmol_to_ml = 0.0


# =============================================================================
# Exported entry point
# =============================================================================
def calc_blood_composition(bc):
    """Compute pH / pCO2 / HCO3 / BE / pO2 / sO2 on `bc`.

    Memoized: returns immediately if every watched input and the engine step
    stamp match previously cached values on `bc`.
    """
    sol = getattr(bc, "solutes", None) or {}
    engine = getattr(bc, "_model_engine", None)
    step_stamp = getattr(engine, "model_time_total", None) if engine is not None else None

    if (
        getattr(bc, "_bc_cache_initialized", False)
        and getattr(bc, "_bc_prev_tco2", None) == bc.tco2
        and getattr(bc, "_bc_prev_to2", None) == bc.to2
        and getattr(bc, "_bc_prev_temp", None) == bc.temp
        and getattr(bc, "_bc_prev_prev_ph", None) == (getattr(bc, "prev_ph", None) or 7.37)
        and getattr(bc, "_bc_prev_prev_po2", None) == (getattr(bc, "prev_po2", None) or 18.7)
        and getattr(bc, "_bc_prev_na", None) == sol.get("na")
        and getattr(bc, "_bc_prev_k", None) == sol.get("k")
        and getattr(bc, "_bc_prev_ca", None) == sol.get("ca")
        and getattr(bc, "_bc_prev_mg", None) == sol.get("mg")
        and getattr(bc, "_bc_prev_cl", None) == sol.get("cl")
        and getattr(bc, "_bc_prev_lact", None) == sol.get("lact")
        and getattr(bc, "_bc_prev_albumin", None) == sol.get("albumin")
        and getattr(bc, "_bc_prev_phosphates", None) == sol.get("phosphates")
        and getattr(bc, "_bc_prev_uma", None) == sol.get("uma")
        and getattr(bc, "_bc_prev_hemoglobin", None) == sol.get("hemoglobin")
        and (step_stamp is None or getattr(bc, "_bc_prev_step_stamp", None) == step_stamp)
    ):
        return

    _calc_blood_composition_js(bc)

    bc._bc_prev_step_stamp = step_stamp
    bc._bc_prev_tco2 = bc.tco2
    bc._bc_prev_to2 = bc.to2
    bc._bc_prev_temp = bc.temp
    bc._bc_prev_prev_ph = getattr(bc, "prev_ph", None) or 7.37
    bc._bc_prev_prev_po2 = getattr(bc, "prev_po2", None) or 18.7
    bc._bc_prev_na = sol.get("na")
    bc._bc_prev_k = sol.get("k")
    bc._bc_prev_ca = sol.get("ca")
    bc._bc_prev_mg = sol.get("mg")
    bc._bc_prev_cl = sol.get("cl")
    bc._bc_prev_lact = sol.get("lact")
    bc._bc_prev_albumin = sol.get("albumin")
    bc._bc_prev_phosphates = sol.get("phosphates")
    bc._bc_prev_uma = sol.get("uma")
    bc._bc_prev_hemoglobin = sol.get("hemoglobin")
    bc._bc_cache_initialized = True


# =============================================================================
# Pure-JS numerical path (the _js suffix is kept to match the JS function name)
# =============================================================================
def _calc_blood_composition_js(bc):
    global tco2, to2, sid, albumin, phosphates, uma, hemoglobin, temp
    global prev_ph, prev_po2, hemoglobin_gdl, inv_mmol_to_ml
    global left_hp, right_hp, left_o2, right_o2
    global dpH, dpCO2, dT, dDPG
    global log10_p50, P50, P50_n
    global be

    sol = bc.solutes
    tco2 = bc.tco2
    to2 = bc.to2
    sid = sol["na"] + sol["k"] + 2 * sol["ca"] + 2 * sol["mg"] - sol["cl"] - sol["lact"]
    albumin = sol["albumin"]
    phosphates = sol["phosphates"]
    uma = sol["uma"]
    hemoglobin = sol["hemoglobin"]
    temp = bc.temp
    prev_ph = getattr(bc, "prev_ph", None) or 7.37
    prev_po2 = getattr(bc, "prev_po2", None) or 18.7
    hemoglobin_gdl = hemoglobin / 0.6206
    inv_mmol_to_ml = 760.0 / (gas_constant * (273.15 + temp))

    # set the wide limits
    left_hp = left_hp_wide
    right_hp = right_hp_wide

    # set the limits based on the previous calculation if available
    if prev_ph > 0:
        left_hp = (10.0 ** (-(prev_ph + delta_ph_limits))) * 1000.0
        right_hp = (10.0 ** (-(prev_ph - delta_ph_limits))) * 1000.0

    hp = _brent_root_finding(_net_charge_plasma, left_hp, right_hp, max_iterations, brent_accuracy)
    if hp > 0:
        be = (hco3 - 25.1 + (2.3 * hemoglobin + 7.7) * (ph - 7.4)) * (1.0 - 0.023 * hemoglobin)
        bc.ph = ph
        bc.pco2 = pco2
        bc.hco3 = hco3
        bc.be = be
    else:
        # fall back to wide limits if the narrow pH bracket failed
        left_hp = left_hp_wide
        if left_hp < 0:
            left_hp = 0
        right_hp = right_hp_wide
        hp = _brent_root_finding(_net_charge_plasma, left_hp, right_hp, max_iterations, brent_accuracy)
        if hp > 0:
            be = (hco3 - 25.1 + (2.3 * hemoglobin + 7.7) * (ph - 7.4)) * (1.0 - 0.023 * hemoglobin)
            bc.ph = ph
            bc.pco2 = pco2
            bc.hco3 = hco3
            bc.be = be
        else:
            print(f"definitive ab root finding failed in: {getattr(bc, 'name', '?')}")

    # Bohr / Haldane / temp / DPG shifts of the oxygen dissociation curve
    dpH = ph - 7.40
    dpCO2 = pco2 - 40.0
    dT = temp - 37.0
    dDPG = dpg - 5.0

    log10_p50 = math.log10(P50_0) - 0.48 * dpH + 0.014 * dpCO2 + 0.024 * dT + 0.051 * dDPG
    P50 = 10.0 ** log10_p50
    P50_n = P50 ** n

    # dynamic pO2 bracketing off the previous step's result
    dyn_limits_used_oxy = False
    left_o2 = left_o2_wide
    right_o2 = right_o2_wide
    if prev_po2 > 0:
        left_o2 = prev_po2 - delta_o2_limits
        if left_o2 < 0:
            left_o2 = 0
        right_o2 = prev_po2 + delta_o2_limits
        dyn_limits_used_oxy = True

    # Note: the JS binds the brent result to a LOCAL `po2` that shadows the
    # module-level `po2`. We use `po2_local` here to make the scope explicit;
    # the module-level `po2` is never read before being overwritten next call,
    # so the shadowing is behaviorally inert.
    po2_local = _brent_root_finding(_do2_content, left_o2, right_o2, max_iterations, brent_accuracy)
    if po2_local > -1:
        bc.po2 = po2_local
        bc.so2 = so2 * 100.0
        bc.prev_po2 = po2_local
    else:
        if dyn_limits_used_oxy:
            # fall back to the wide pO2 bracket
            left_o2 = left_o2_wide
            right_o2 = right_o2_wide
            po2_local = _brent_root_finding(_do2_content, left_o2, right_o2, max_iterations, brent_accuracy)
            if po2_local > -1:
                bc.po2 = po2_local
                bc.so2 = so2 * 100.0
                bc.prev_po2 = po2_local
            else:
                print(f"definitive oxy root finding failed in: {getattr(bc, 'name', '?')}")


# =============================================================================
# Objective functions (mutate module state, matching the JS exactly)
# =============================================================================
def _net_charge_plasma(hp_estimate):
    """Stewart electroneutrality residual. Mutates module-level ph, hco3, pco2.

    JS: `_net_charge_plasma(hp_estimate)`.
    """
    global ph, hco3, pco2

    ph = -math.log10(hp_estimate / 1000.0)
    cco2p = tco2 / (1.0 + kc / hp_estimate + (kc * kd) / (hp_estimate * hp_estimate))
    hco3 = (kc * cco2p) / hp_estimate
    co3p = (kd * hco3) / hp_estimate
    ohp = kw / hp_estimate

    pco2 = cco2p / alpha_co2p

    a_base = albumin * (0.123 * ph - 0.631) + phosphates * (0.309 * ph - 0.469)

    return hp_estimate + sid - hco3 - 2.0 * co3p - ohp - a_base - uma


def _calc_so2(po2_estimate):
    """Hill-equation saturation at the current P50. Pure; reads module state."""
    po2_n = po2_estimate ** n
    denom = po2_n + P50_n
    return po2_n / denom


def _do2_content(po2_estimate):
    """TO2 residual for pO2 root-finding. Mutates module-level so2.

    Inputs: po2 in mmHg, so2 in fraction, hemoglobin in mmol/L.
    Converts hemoglobin (mmol/L -> g/dL via /0.6206) and the result
    (ml O2/dL blood -> ml O2/L blood via *10.0, then to mmol/L via
    inv_mmol_to_ml which embeds the ideal-gas conversion at body temperature).
    """
    global so2

    so2 = _calc_so2(po2_estimate)

    to2_new_estimate = (0.0031 * po2_estimate + 1.36 * hemoglobin_gdl * so2) * 10.0
    to2_new_estimate = to2_new_estimate * inv_mmol_to_ml

    dto2 = to2 - to2_new_estimate
    return dto2


# =============================================================================
# Brent root-finder (inverse-quadratic interpolation with bisection fallback)
# =============================================================================
def _brent_root_finding(f, x0, x1, max_iter, tolerance):
    """Port of the JS `_brent_root_finding`. Returns the root, or -1 if the
    interval does not bracket a sign change or iterations are exhausted."""
    fx0 = f(x0)
    fx1 = f(x1)

    if fx0 * fx1 > 0:
        return -1

    if abs(fx0) < abs(fx1):
        x0, x1 = x1, x0
        fx0, fx1 = fx1, fx0

    x2 = x0
    fx2 = fx0
    d = 0
    mflag = True
    steps_taken = 0

    while steps_taken < max_iter:
        if abs(fx0) < abs(fx1):
            x0, x1 = x1, x0
            fx0, fx1 = fx1, fx0

        if fx0 != fx2 and fx1 != fx2:
            # inverse quadratic interpolation
            L0 = (x0 * fx1 * fx2) / ((fx0 - fx1) * (fx0 - fx2))
            L1 = (x1 * fx0 * fx2) / ((fx1 - fx0) * (fx1 - fx2))
            L2 = (x2 * fx1 * fx0) / ((fx2 - fx0) * (fx2 - fx1))
            new_point = L0 + L1 + L2
        else:
            # secant
            new_point = x1 - (fx1 * (x1 - x0)) / (fx1 - fx0)

        if (
            new_point < (3 * x0 + x1) / 4
            or new_point > x1
            or (mflag and abs(new_point - x1) >= abs(x1 - x2) / 2)
            or (not mflag and abs(new_point - x1) >= abs(x2 - d) / 2)
            or (mflag and abs(x1 - x2) < tolerance)
            or (not mflag and abs(x2 - d) < tolerance)
        ):
            new_point = (x0 + x1) / 2
            mflag = True
        else:
            mflag = False

        fnew = f(new_point)
        d = x2
        x2 = x1

        if fx0 * fnew < 0:
            x1 = new_point
            fx1 = fnew
        else:
            x0 = new_point
            fx0 = fnew

        steps_taken += 1

        if abs(fnew) < tolerance:
            return new_point

    return -1
