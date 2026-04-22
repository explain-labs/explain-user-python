"""BloodPump — port of src/explain/component_models/BloodPump.js

A BloodPump is a BloodCapacitance that, in addition to its own recoil pressure,
generates a pump pressure (as a function of RPM) and applies it to one of its
two connected resistors. Two modes are supported:

  - pump_mode = 0 (centrifugal): the pressure difference is applied across the
    INLET resistor — the compartment on the far side of the inlet gets the
    suction. Implemented by setting inlet.p2_ext = pump_pressure.
  - pump_mode = 1 (roller pump): the pressure is applied across the OUTLET
    resistor. Implemented by setting outlet.p1_ext = pump_pressure.

The pump pressure formula is `pump_pressure = -pump_rpm / 25.0` (JS verbatim).
The negative sign means: positive RPM creates a suction on the inlet (mode 0)
or a push on the outlet (mode 1), producing forward flow through the pump.

Also differs from plain BloodCapacitance by summing THREE non-persistent
external pressures into `pres`: `pres_ext + pres_cc + pres_mus`. The latter
two are pushed by external models (Breathing, Resuscitation) and come from
JSON state; they are declared here with 0.0 defaults so the class works in
scenarios that don't touch them. All three are reset after absorption,
matching the non-persistent contract of `pres_ext`.

`pres_tm` is NOT computed in `calc_pressure` — the JS source omits it, so this
port does too. It retains whatever value it had from parent initialization.
"""

from __future__ import annotations

from .blood_capacitance import BloodCapacitance


class BloodPump(BloodCapacitance):
    model_type = "BloodPump"

    model_interface = [
        {"target": "model_type", "type": "string", "readonly": True},
        {"target": "description", "type": "string", "build_prop": True,
         "readonly": True, "caption": "description"},
        {"target": "is_enabled", "type": "boolean", "build_prop": True,
         "caption": "enabled"},
        {"target": "u_vol", "type": "number", "caption": "unstressed volume (L)"},
        {"target": "el_base", "type": "number", "caption": "elastance pump (mmHg/L)"},
        {"target": "el_k", "type": "number", "caption": "non linear elastance factor"},
        {"target": "pump_rpm", "type": "number", "caption": "pump rpm"},
        {"target": "inlet", "type": "list", "caption": "inlet blood resistor",
         "options": ["BloodResistor", "BloodVesselResistor", "HeartValve"]},
        {"target": "outlet", "type": "list", "caption": "outlet blood resistor",
         "options": ["BloodResistor", "BloodVesselResistor", "HeartValve"]},
    ]

    def __init__(self, model_ref, name: str = ""):
        super().__init__(model_ref, name)

        # pump state
        self.pump_rpm = 0.0        # rotations per minute
        self.pump_mode = 0         # 0 = centrifugal, 1 = roller pump
        self.pump_pressure = 0.0   # mmHg, generated from pump_rpm

        # connected resistor names (strings, populated from JSON)
        self.inlet = ""
        self.outlet = ""

        # extra non-persistent external pressures. Not declared by parent
        # Capacitance / BloodCapacitance in either JS or Python — JS relies on
        # JSON init_model to create them. We declare with 0.0 defaults here to
        # match Python's attribute-presence requirements; real scenarios (e.g.
        # term_neonate_state.json) always set them explicitly.
        self.pres_cc = 0.0         # e.g. chest-compression pressure
        self.pres_mus = 0.0        # e.g. muscle / effort pressure

        # internal references (resolved every step from names above)
        self._inlet = None
        self._outlet = None

    def calc_pressure(self):
        # resolve connected resistors by name (same pattern as Resistor.calc_model)
        self._inlet = self._model_engine.models[self.inlet]
        self._outlet = self._model_engine.models[self.outlet]

        # recoil pressure (with optional non-linear term) — same formula as
        # parent Capacitance, repeated here because the JS override does not
        # call super.
        self.pres_in = (
            self.el_k_eff * ((self.vol - self.u_vol_eff) ** 2)
            + self.el_eff * (self.vol - self.u_vol_eff)
        )

        # total pressure: recoil + three non-persistent external pushes
        self.pres = self.pres_in + self.pres_ext + self.pres_cc + self.pres_mus

        # reset all three non-persistent external pressures
        self.pres_ext = 0.0
        self.pres_cc = 0.0
        self.pres_mus = 0.0

        # pump pressure is a linear function of RPM. Negative sign: positive
        # RPM produces a negative pressure at the downstream side of the pump,
        # which drives forward flow through the connected resistor.
        self.pump_pressure = -self.pump_rpm / 25.0

        if self.pump_mode == 0:
            # centrifugal: apply across the INLET resistor
            self._inlet.p1_ext = 0.0
            self._inlet.p2_ext = self.pump_pressure
        else:
            # roller pump: apply across the OUTLET resistor
            self._outlet.p1_ext = self.pump_pressure
            self._outlet.p2_ext = 0.0
