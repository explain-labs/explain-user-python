"""GasComposition — port of src/explain/component_models/GasComposition.js

Pure helper that (re)initialises the gas composition on a GasCapacitance-like
object from an fio2 / temp / humidity / fico2 specification. Triggers the
target's `calc_model()` first to refresh pressure, then derives every
concentration, partial pressure, and volume fraction (O2, CO2, N2, other, H2O)
using the ideal gas law and an Antoine-style water-vapour pressure curve.

Mutates on `gc`:
  ctotal, ph2o, fh2o, ch2o, po2, fo2, co2, pco2, fco2, cco2,
  pn2, fn2, cn2, pother, fother, cother.

Signature matches the JS source exactly, including default arguments:
  calc_gas_composition(gc, fio2=0.205, temp=37, humidity=1.0, fico2=0.000392)

No module-level state (unlike blood_composition.py) — this function is pure:
all constants are local to the function body, matching the JS.
"""

from __future__ import annotations

import math


def calc_gas_composition(gc, fio2=0.205, temp=37, humidity=1.0, fico2=0.000392):
    _fo2_dry = 0.205
    _fco2_dry = 0.000392
    _fn2_dry = 0.794608
    _fother_dry = 0.0
    _gas_constant = 62.36367

    # dry-gas composition adjusted for the supplied fio2/fico2
    new_fo2_dry = fio2
    new_fco2_dry = fico2
    new_fn2_dry = (_fn2_dry * (1.0 - (fio2 + fico2))) / (1.0 - (_fo2_dry + _fco2_dry))
    new_fother_dry = (_fother_dry * (1.0 - (fio2 + fico2))) / (1.0 - (_fo2_dry + _fco2_dry))

    # refresh pressure on the target compartment
    gc.calc_model()

    pressure = gc.pres

    # total gas concentration via ideal gas law (mmol/L)
    gc.ctotal = (pressure / (_gas_constant * (273.15 + temp))) * 1000.0

    # water vapour: Antoine-style saturation pressure scaled by humidity (0-1)
    gc.ph2o = math.exp(20.386 - 5132 / (temp + 273)) * humidity
    gc.fh2o = gc.ph2o / pressure
    gc.ch2o = gc.fh2o * gc.ctotal

    # O2
    gc.po2 = new_fo2_dry * (pressure - gc.ph2o)
    gc.fo2 = gc.po2 / pressure
    gc.co2 = gc.fo2 * gc.ctotal

    # CO2
    gc.pco2 = new_fco2_dry * (pressure - gc.ph2o)
    gc.fco2 = gc.pco2 / pressure
    gc.cco2 = gc.fco2 * gc.ctotal

    # N2
    gc.pn2 = new_fn2_dry * (pressure - gc.ph2o)
    gc.fn2 = gc.pn2 / pressure
    gc.cn2 = gc.fn2 * gc.ctotal

    # other
    gc.pother = new_fother_dry * (pressure - gc.ph2o)
    gc.fother = gc.pother / pressure
    gc.cother = gc.fother * gc.ctotal
