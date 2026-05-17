"""BloodVessel — port of src/explain/component_models/BloodVessel.js

A BloodVessel is a BloodCapacitance that owns one Resistor per entry in its
`inputs` list. The resistors are created during `init_model` with deterministic
names `f"{input_name}_{self.name}"` and are inserted into the engine's
`models` dict alongside any JSON-declared components.

The BloodVessel extends the usual factor-tier system with:
  - Resistance factors (r_factor, r_k_factor) and their _ps / _scaling_ps
    tiers, composed MULTIPLICATIVELY (a product of all multipliers), so that
    simultaneous factors compound correctly: r_factor=2 with r_factor_ps=2
    yields 4x, not the linearised 3x of an additive scheme.
  - `alpha` (resistance-elastance coupling, unitless 0-1) applied ONCE to
    the combined resistance multiplier — `pow(_r_total_factor, alpha)` —
    rather than per-factor. Tissue defaults: veins/venules 0.75,
    arterioles 0.63, large arteries 0.5.
  - ANS modulation via `ans_activity` and `ans_sens`. The per-vessel
    sensitivity-weighted multiplier `1 + (ans_activity - 1) * ans_sens` is
    folded into `_r_total_factor`, so a single ANS signal drives both
    resistance and (via α) elastance in coupled fashion. There is NO
    separate ANS term added to elastance — it's already absorbed by the
    geometric coupling.

`calc_model` is a custom dispatch: calc_resistances → calc_elastances →
propagate effective values (and enabled / gates / external pressures) to
every child resistor → calc_volumes → calc_pressure → get_flows.

`calc_resistances` caches the composed linear-resistance multiplier on
`self._r_total_factor`; `calc_elastances` consumes it as the single source
of truth for the α-coupling. `r_k` carries its own factor stack with the
same ANS coupling but is NOT α-coupled onto elastance (treated as a
structural wall property, not a vasoactive one).

`get_flows` reads each child resistor's `flow` attribute. Because the
engine steps models in insertion order and child resistors are appended
AFTER the vessel itself (in `init_model`), `get_flows` observes resistor
flow from the PREVIOUS step (one-step lag). This matches the JS engine
behavior and is the same ordering pattern as Container / contained
compartments.
"""

from __future__ import annotations

from ..base_models.resistor import Resistor
from .blood_capacitance import BloodCapacitance


class BloodVessel(BloodCapacitance):
    model_type = "BloodVessel"

    model_interface = [
        {"target": "model_type", "type": "string", "readonly": True},
        {"target": "description", "type": "string", "build_prop": True,
         "readonly": True, "caption": "description"},
        {"target": "is_enabled", "type": "boolean", "build_prop": True,
         "caption": "enabled"},
        {"target": "no_flow", "type": "boolean", "build_prop": True,
         "caption": "no flow allowed"},
        {"target": "no_back_flow", "type": "boolean", "build_prop": True,
         "caption": "no back flow allowed"},
        {"target": "vol", "type": "number", "build_prop": True, "caption": "volume (L)"},
        {"target": "u_vol", "type": "number", "build_prop": True,
         "caption": "unstressed volume (L)"},
        {"target": "el_base", "type": "number", "build_prop": True,
         "caption": "elastance baseline (mmHg/L)"},
        {"target": "el_k", "type": "number", "build_prop": True,
         "caption": "elastance non linear k"},
        {"target": "r_for", "type": "number", "build_prop": True, "caption": "r_for (mmHg/L/s)"},
        {"target": "r_back", "type": "number", "build_prop": True, "caption": "r_back (mmHg/L/s)"},
        {"target": "alpha", "type": "number", "build_prop": True,
         "caption": "resistance-elastance coupling (0-1)"},
        {"target": "ans_sens", "type": "number", "build_prop": True,
         "caption": "ans sensitivity (0-1)"},
        {"target": "inputs", "type": "multiple-list", "build_prop": True,
         "caption": "inputs",
         "options": ["BloodVessel", "BloodTimeVaryingElastance",
                     "BloodCapacitance", "BloodPump"]},
    ]

    def __init__(self, model_ref, name: str = ""):
        super().__init__(model_ref, name)

        # independent properties unique to a BloodVessel
        self.inputs: list = []       # names of upstream compartments
        self.r_for = 1.0             # forward resistance (mmHg*s/L)
        self.r_back = 1.0            # backward resistance (mmHg*s/L)
        self.r_k = 0.0               # non-linear resistance coefficient
        self.no_flow = False
        self.no_back_flow = False
        self.p1_ext = 0.0            # external pressure on inlet (mmHg), non-persistent
        self.p2_ext = 0.0            # external pressure on outlet (mmHg), non-persistent
        self.alpha = 0.0             # resistance-elastance coupling (0-1)
        self.ans_sens = 0.0          # ANS sensitivity (0-1)
        self.ans_activity = 1.0      # ANS activity (persistent; updated externally)

        # non-persistent resistance factors (reset each step)
        self.r_factor = 1.0
        self.r_k_factor = 1.0

        # persistent resistance factors
        self.r_factor_ps = 1.0
        self.r_k_factor_ps = 1.0

        # scaling resistance factors
        self.r_factor_scaling_ps = 1.0
        self.r_k_factor_scaling_ps = 1.0

        # dependent flow properties
        self.flow = 0.0              # net flow (L/s)
        self.flow_forward = 0.0      # sum of positive resistor flows (L/s)
        self.flow_backward = 0.0     # sum of absolute-value negative resistor flows (L/s)

        # calculated effective resistances
        self.r_for_eff = 1000.0
        self.r_back_eff = 1000.0
        self.r_k_eff = 0.0

        # internal dict of child resistors, keyed by f"{input_name}_{self.name}"
        self._resistors: dict = {}

        # composed multiplicative R multiplier, cached by calc_resistances and
        # reused by calc_elastances for the α-coupling
        self._r_total_factor = 1.0

    def init_model(self, args):
        # apply JSON args and instantiate `components` sub-models (Capacitance path)
        super().init_model(args)

        # for each upstream input name, create a dedicated Resistor carrying
        # this vessel's r_for / r_back / r_k / gates. The resistor is inserted
        # into the engine's models dict under a deterministic composite name so
        # that re-loading a saved state finds the existing resistor instead of
        # creating a duplicate.
        for input_name in self.inputs:
            resistor_name = f"{input_name}_{self.name}"

            # if a resistor with this composite name was already registered
            # (e.g. from a re-loaded saved state), just reference it
            if resistor_name in self._model_engine.models:
                self._resistors[resistor_name] = self._model_engine.models[resistor_name]
                continue

            res = Resistor(self._model_engine, resistor_name)

            # args for the child resistor. Note this shadows the outer `args`
            # in the JS source; we rename to `res_args` to be explicit.
            res_args = [
                {"key": "name", "value": resistor_name},
                {"key": "description", "value": f"input connector for {self.name}"},
                {"key": "is_enabled", "value": self.is_enabled},
                {"key": "model_type", "value": "Resistor"},
                {"key": "r_for", "value": self.r_for},
                {"key": "r_back", "value": self.r_back},
                {"key": "r_k", "value": self.r_k},
                {"key": "no_flow", "value": self.no_flow},
                {"key": "no_back_flow", "value": self.no_back_flow},
                {"key": "comp_from", "value": input_name},
                {"key": "comp_to", "value": self.name},
            ]
            res.init_model(res_args)

            self._model_engine.models[resistor_name] = res
            self._resistors[resistor_name] = res

    def calc_model(self):
        # custom dispatch (NOT inherited; overrides the parent chain)
        self.calc_resistances()
        self.calc_elastances()

        # propagate effective values onto every child resistor every step
        for resistor in self._resistors.values():
            resistor.is_enabled = self.is_enabled
            resistor.r_for = self.r_for_eff
            resistor.r_back = self.r_back_eff
            resistor.r_k = self.r_k_eff
            resistor.no_back_flow = self.no_back_flow
            resistor.no_flow = self.no_flow
            resistor.p1_ext = self.p1_ext
            resistor.p2_ext = self.p2_ext

        # parent volume + pressure pipeline (Capacitance methods)
        self.calc_volumes()
        self.calc_pressure()

        # read back resistor flows (one-step lag — see class docstring)
        self.get_flows()

    def get_flows(self):
        self.flow = 0.0
        self.flow_forward = 0.0
        self.flow_backward = 0.0

        for resistor in self._resistors.values():
            if resistor.is_enabled:
                if resistor.flow > 0:
                    self.flow_forward += resistor.flow
                else:
                    self.flow_backward += -resistor.flow

        self.flow = self.flow_forward - self.flow_backward

    def calc_resistances(self):
        # Multiplicative composition of all resistance multipliers. Composing
        # factors as a product (rather than summing their deltas) lets
        # simultaneous factors compound correctly: r_factor=2 with
        # r_factor_ps=2 gives a true 4x rise, not the linearised 3x. The ANS
        # contribution is the per-vessel sensitivity-weighted multiplier
        # (1 + (a-1)*ans_sens).
        ans_mult = 1 + (self.ans_activity - 1) * self.ans_sens

        r_total_factor = (
            self.r_factor
            * self.r_factor_ps
            * self.r_factor_scaling_ps
            * ans_mult
        )

        self.r_for_eff = self.r_for * r_total_factor
        self.r_back_eff = self.r_back * r_total_factor

        # r_k carries its own factor stack but the same ANS coupling.
        r_k_total_factor = (
            self.r_k_factor
            * self.r_k_factor_ps
            * self.r_k_factor_scaling_ps
            * ans_mult
        )
        self.r_k_eff = self.r_k * r_k_total_factor

        # Cache the composed linear-resistance multiplier for the elastance
        # step (single source of truth for the α-coupling).
        self._r_total_factor = r_total_factor

        # reset non-persistent factors
        self.r_factor = 1.0
        self.r_k_factor = 1.0

    def calc_elastances(self):
        # Multiplicative composition of the passive elastance multipliers
        # (aging, scaling, scenario edits — direct E modifiers, not R-coupled).
        el_passive_mult = (
            self.el_base_factor
            * self.el_base_factor_ps
            * self.el_base_factor_scaling_ps
        )

        # Geometric R→E coupling: apply α once to the *combined* resistance
        # multiplier, not per-factor. The ANS signal is already folded into
        # _r_total_factor, so there is no separate ANS term here.
        el_geom_mult = self._r_total_factor ** self.alpha

        self.el_eff = self.el_base * el_passive_mult * el_geom_mult

        # el_k carries its own multipliers and is NOT α-coupled to R — the
        # non-linear stiffening term is treated as a structural property of
        # the wall, not driven by vasoactivity.
        el_k_passive_mult = (
            self.el_k_factor
            * self.el_k_factor_ps
            * self.el_k_factor_scaling_ps
        )
        self.el_k_eff = self.el_k * el_k_passive_mult

        # reset non-persistent factors
        self.el_base_factor = 1.0
        self.el_k_factor = 1.0
