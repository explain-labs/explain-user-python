"""Smoke test for the updated Pda port — exercises both branches.

1. Loads the term_neonate scenario.
2. With diameter_relative == 0, runs a few steps and verifies the
   closed-duct fast path sentinels.
3. Opens the duct (diameter_relative = 0.5), runs again, and verifies
   the new physics: conical resistance halves, alpha-coupled elastance,
   Doppler velocity from the AA/PA pressure gradient, and jet velocities.
4. Spot-checks calc_conical_resistance(d,d,L) == calc_resistance(d,L)
   (cone with equal end-diameters must collapse to the cylinder formula).
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from explain import Engine  # noqa: E402
from explain.component_models.pda import (  # noqa: E402
    CLOSED_EL_SCALE,
    RESISTANCE_NO_FLOW,
)

SCENARIO = HERE / "model_definitions" / "term_neonate.json"


def almost(a, b, tol=1e-6):
    return abs(a - b) <= tol * max(1.0, abs(a), abs(b))


def main() -> int:
    eng = Engine()
    eng.load_file(SCENARIO)
    pda = eng.models["Pda"]
    aar_da = eng.models["AAR_DA"]
    da_pa = eng.models["DA_PA"]
    da = eng.models["DA"]

    print("=== Pda configuration after load ===")
    print(f"  diameter_ao_max={pda.diameter_ao_max}  diameter_pa_max={pda.diameter_pa_max}")
    print(f"  length={pda.length}  el_base={pda.el_base}  alpha={pda.alpha}  jet_exponent={pda.jet_exponent}")
    print(f"  diameter_relative={pda.diameter_relative}")
    print()

    # Verify new attrs survived a JSON load that still carries legacy fields
    # (type, el_min, el_max, velocity, diameter_max). They become inert
    # attrs and must not clobber the new defaults.
    assert hasattr(pda, "el_base") and pda.el_base == 30000, "el_base default lost"
    assert hasattr(pda, "alpha") and pda.alpha == 0.55, "alpha default lost"
    assert hasattr(pda, "jet_exponent") and pda.jet_exponent == 0.6, "jet_exponent default lost"
    assert pda._aar_da is aar_da and pda._da is da and pda._da_pa is da_pa, "cached refs missing"

    # --- helper identity: cone(d,d,L) == cylinder(d,L) ---
    cyl = pda.calc_resistance(2.0, length=10.0, viscosity=6.0)
    cone = pda.calc_conical_resistance(2.0, 2.0, length=10.0, viscosity=6.0)
    assert almost(cyl, cone), f"cone(d,d) {cone} != cylinder(d) {cyl}"
    print(f"calc_conical_resistance(d,d,L) == calc_resistance(d,L)  ->  {cone:.6g}  OK")

    # Cone with smaller pulmonary end must be MORE resistive than the same-length cylinder at d_ao
    cone_taper = pda.calc_conical_resistance(3.0, 2.0, length=10.0, viscosity=6.0)
    cyl_wide = pda.calc_resistance(3.0, length=10.0, viscosity=6.0)
    assert cone_taper > cyl_wide, "tapered cone should be more resistive than the wide cylinder"
    print(f"cone(3,2,10) > cyl(3,10)  ->  {cone_taper:.4g} > {cyl_wide:.4g}  OK")
    print()

    # --- closed-duct fast path ---
    eng.run(0.05, watch=[], sample_every_s=0.05)  # a few real steps
    print("=== After steady state with diameter_relative=0 (closed) ===")
    print(f"  diameter_ao={pda.diameter_ao}  diameter_pa={pda.diameter_pa}")
    print(f"  res_ao={pda.res_ao:.3e}  res_pa={pda.res_pa:.3e}")
    print(f"  el={pda.el:.3e}  da.el_base={da.el_base:.3e}")
    print(f"  velocity_ao={pda.velocity_ao}  velocity_pa={pda.velocity_pa}  velocity_doppler={pda.velocity_doppler}")
    print(f"  aar_da.no_flow={aar_da.no_flow}  da_pa.no_flow={da_pa.no_flow}")

    assert pda.res_ao == RESISTANCE_NO_FLOW and pda.res_pa == RESISTANCE_NO_FLOW, "closed: res should be sentinel"
    assert aar_da.r_for == RESISTANCE_NO_FLOW and aar_da.r_back == RESISTANCE_NO_FLOW
    assert da_pa.r_for == RESISTANCE_NO_FLOW and da_pa.r_back == RESISTANCE_NO_FLOW
    assert aar_da.no_flow is True and da_pa.no_flow is True
    assert almost(pda.el, pda.el_base * CLOSED_EL_SCALE), "closed: el == el_base * CLOSED_EL_SCALE"
    assert pda.velocity_doppler == 0 and pda.velocity_ao_jet == 0 and pda.velocity_pa_jet == 0
    print("  closed-duct sentinels  OK")
    print()

    # --- open-duct branch ---
    pda.diameter_relative = 0.5
    # Let the circulation settle into the new geometry
    eng.run(2.0, watch=[], sample_every_s=2.0)
    print("=== After opening to diameter_relative=0.5 ===")
    print(f"  diameter_ao={pda.diameter_ao:.3f}  diameter_pa={pda.diameter_pa:.3f}")
    print(f"  res_ao={pda.res_ao:.3f}  res_pa={pda.res_pa:.3f}  (mmHg*s/L)")
    print(f"  el={pda.el:.3f}  (mmHg/L)  alpha={pda.alpha}")
    print(f"  flow_ao={pda.flow_ao:.4g}  flow_pa={pda.flow_pa:.4g}")
    print(f"  velocity_ao={pda.velocity_ao:.3f}  velocity_pa={pda.velocity_pa:.3f}  (m/s)")
    print(f"  velocity_ao_jet={pda.velocity_ao_jet:.3f}  velocity_pa_jet={pda.velocity_pa_jet:.3f}  (m/s)")
    print(f"  velocity_doppler={pda.velocity_doppler:.3f}  (m/s)")

    assert almost(pda.diameter_ao, 0.5 * pda.diameter_ao_max), "diameter_ao geometry"
    assert almost(pda.diameter_pa, 0.5 * pda.diameter_pa_max), "diameter_pa geometry"
    assert 0 < pda.res_ao < RESISTANCE_NO_FLOW, "res_ao should be finite and non-zero"
    assert 0 < pda.res_pa < RESISTANCE_NO_FLOW, "res_pa should be finite and non-zero"
    # PA half tapers to a smaller diameter -> more resistive than AO half
    assert pda.res_pa > pda.res_ao, f"res_pa ({pda.res_pa}) should exceed res_ao ({pda.res_ao})"
    # alpha-coupled elastance must be >= el_base (R_total >= R_open_total at any closure)
    assert pda.el >= pda.el_base, f"el ({pda.el}) should be >= el_base ({pda.el_base})"
    assert da.el_base == pda.el, "da.el_base must mirror pda.el"
    # Doppler velocity sign follows AA - PA gradient
    expected_sign = 1 if aar_da._comp_from.pres > da_pa._comp_to.pres else -1
    if pda.velocity_doppler != 0:
        assert (pda.velocity_doppler > 0) == (expected_sign > 0), "doppler sign vs AA-PA gradient"
    # Jet correction must amplify in the direction of stenosis (r_factor >= 1)
    if pda.velocity_ao != 0:
        assert abs(pda.velocity_ao_jet) >= abs(pda.velocity_ao) - 1e-12, "jet should amplify (or equal) ao"
    if pda.velocity_pa != 0:
        assert abs(pda.velocity_pa_jet) >= abs(pda.velocity_pa) - 1e-12, "jet should amplify (or equal) pa"
    # Continuity check: flow / area. aar_da.flow updates between the Pda
    # calc and the sample, so allow a loose tolerance — we're verifying the
    # formula is right, not bit-identical synchronization.
    if pda.diameter_ao > 0:
        r_ao_m = pda.diameter_ao * 0.0005
        area_ao = math.pi * r_ao_m * r_ao_m
        expected_v_ao = (aar_da.flow * 0.001) / area_ao
        rel_err = abs(pda.velocity_ao - expected_v_ao) / max(1e-9, abs(expected_v_ao))
        assert rel_err < 0.01, \
            f"velocity_ao continuity off by {rel_err:.2%}: {pda.velocity_ao} vs {expected_v_ao}"
    print("  open-duct physics  OK")
    print()

    # --- fully open ---
    pda.diameter_relative = 1.0
    eng.run(2.0, watch=[], sample_every_s=2.0)
    print("=== After opening to diameter_relative=1.0 ===")
    print(f"  res_ao={pda.res_ao:.3f}  res_pa={pda.res_pa:.3f}")
    print(f"  el={pda.el:.3f}")
    print(f"  velocity_doppler={pda.velocity_doppler:.3f}  velocity_pa_jet={pda.velocity_pa_jet:.3f}")
    # At full open, R_total == R_open_total exactly, so r_factor == 1 and el == el_base
    assert almost(pda.el, pda.el_base, tol=1e-9), f"fully open: el ({pda.el}) should equal el_base ({pda.el_base})"
    # And jet_scale = 1**(jet_exponent*0.25) = 1, so jet == continuity
    assert almost(pda.velocity_ao_jet, pda.velocity_ao, tol=1e-9)
    assert almost(pda.velocity_pa_jet, pda.velocity_pa, tol=1e-9)
    print("  fully-open invariants  OK")
    print()

    # --- monotonicity: more closure => more resistance, more elastance ---
    pda.diameter_relative = 0.2
    eng.run(0.5, watch=[], sample_every_s=0.5)
    el_at_02 = pda.el
    res_at_02 = pda.res_ao + pda.res_pa
    pda.diameter_relative = 0.8
    eng.run(0.5, watch=[], sample_every_s=0.5)
    el_at_08 = pda.el
    res_at_08 = pda.res_ao + pda.res_pa
    print("=== Monotonicity (less closure => less R, less el) ===")
    print(f"  diameter_relative=0.2  R_total={res_at_02:.3f}  el={el_at_02:.3f}")
    print(f"  diameter_relative=0.8  R_total={res_at_08:.3f}  el={el_at_08:.3f}")
    assert res_at_02 > res_at_08, "more closure should increase total resistance"
    assert el_at_02 > el_at_08, "more closure should increase elastance"
    print("  monotonicity  OK")

    print()
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
