"""Fluids — port of src/explain/component_models/Fluids.js

Manages IV fluid administration by queuing fluid objects and pushing
incremental doses into target blood compartments via their volume_in method.
"""

from __future__ import annotations

from ..base_model import BaseModelClass


class Fluids(BaseModelClass):
    model_type = "Fluids"

    model_interface = [
        {"target": "description", "type": "string", "build_prop": True, "readonly": True},
        {"target": "is_enabled", "type": "boolean", "build_prop": True, "caption": "enabled"},
    ]

    def __init__(self, model_ref, name: str = ""):
        super().__init__(model_ref, name)

        self.fluids_temp = 37.0
        self.fluids = {}
        self.default_volume = 10

        self._default_time = 10
        self._default_type = "normal_saline"
        self._running_fluid_list = []
        self._update_interval = 0.015
        self._update_counter = 0.0

    def init_model(self, args):
        super().init_model(args)

    def calc_model(self):
        self._update_counter += self._t
        if self._update_counter > self._update_interval:
            self._update_counter = 0
            self.process_fluid_list()

    def add_volume(self, volume, in_time=10, fluid_in="normal_saline", site="VLB"):
        fluid = {
            "vol": volume / 1000.0,
            "time_left": in_time,
            "delta": (volume / 1000.0) / (in_time / self._update_interval),
            "site": site,
            "to2": 0.0,
            "tco2": 0.0,
            "temp": self.fluids_temp,
            "viscosity": 1,
            "solutes": dict(self.fluids.get(fluid_in, {})),
            "drugs": {},
        }
        self._running_fluid_list.append(fluid)

    def process_fluid_list(self):
        if len(self._running_fluid_list) > 0:
            filtered_list = self.removeByProperty(self._running_fluid_list, "time_left", 0.0)
            self._running_fluid_list = list(filtered_list)

            for f in self._running_fluid_list:
                f["vol"] -= f["delta"]
                f["time_left"] -= self._update_interval
                if f["time_left"] <= 0:
                    f["delta"] = 0.0
                    f["time_left"] = 0.0

                self._model_engine.models[f["site"]].volume_in(f["delta"], _FluidProxy(f))

    def removeByProperty(self, arr, propName, valueToRemove):
        return [item for item in arr if item[propName] > valueToRemove]


class _FluidProxy:
    """Lightweight wrapper so volume_in(f, comp_from) can read attrs off the fluid dict."""

    def __init__(self, f):
        self._f = f

    def __getattr__(self, name):
        if name == "solutes":
            return self._f.get("solutes", {})
        if name == "drugs":
            return self._f.get("drugs", {})
        if name in self._f:
            return self._f[name]
        raise AttributeError(name)
