"""Gas — port of src/explain/component_models/Gas.js

Top-level gas system. Seeds pres_atm / temp / target_temp onto every
GasCapacitance at init, then calls calc_gas_composition on each with the
system fio2.
"""

from __future__ import annotations

from ..base_model import BaseModelClass
from ..helpers.gas_composition import calc_gas_composition


class Gas(BaseModelClass):
    model_type = "Gas"

    model_interface = [
        {"target": "description", "type": "string", "build_prop": True, "readonly": True},
        {"target": "is_enabled", "type": "boolean", "build_prop": True, "caption": "enabled"},
    ]

    def __init__(self, model_ref, name: str = ""):
        super().__init__(model_ref, name)

        self.pres_atm = 760.0
        self.fio2 = 0.21
        self.temp = 20.0
        self.humidity = 0.5
        self.humidity_settings = {}
        self.temp_settings = {}

        self.gas_containing_modeltypes = ["GasCapacitance"]
        self._gas_components = []

    def init_model(self, args):
        # match JS: setattrs directly, don't call super
        for arg in args:
            setattr(self, arg["key"], arg["value"])

        self._gas_components = []
        for model_name in list(self._model_engine.models.keys()):
            model = self._model_engine.models[model_name]
            if getattr(model, "model_type", None) in self.gas_containing_modeltypes:
                self._gas_components.append(model)
                model.pres_atm = self.pres_atm
                model.temp = self.temp
                model.target_temp = self.temp

        for model_name in list(self.temp_settings.keys()):
            temp = self.temp_settings[model_name]
            self._model_engine.models[model_name].temp = temp
            self._model_engine.models[model_name].target_temp = temp

        for model_name in list(self.humidity_settings.keys()):
            humidity = self.humidity_settings[model_name]
            self._model_engine.models[model_name].humidity = humidity

        for model in self._gas_components:
            calc_gas_composition(model, self.fio2, model.temp, model.humidity)

        self._is_initialized = True

    def calc_model(self):
        pass

    def set_atmospheric_pressure(self, new_pres_atm):
        self.pres_atm = new_pres_atm
        for model in self._gas_components:
            model.pres_atm = self.pres_atm

    def set_temperature(self, new_temp, sites=None):
        if sites is None:
            sites = ["OUT", "MOUTH"]
        if not isinstance(sites, list):
            sites = [sites]

        for site in sites:
            self.temp_settings[site] = float(new_temp)

        for model_name in list(self.temp_settings.keys()):
            temp = self.temp_settings[model_name]
            self._model_engine.models[model_name].temp = temp
            self._model_engine.models[model_name].target_temp = temp

    def set_humidity(self, new_humidity, sites=None):
        if sites is None:
            sites = ["OUT", "MOUTH"]
        if not isinstance(sites, list):
            sites = [sites]

        for site in sites:
            self.humidity_settings[site] = float(new_humidity)

        for model_name in list(self.humidity_settings.keys()):
            humidity = self.humidity_settings[model_name]
            self._model_engine.models[model_name].humidity = humidity

    def set_fio2(self, new_fio2, sites=None):
        self.fio2 = new_fio2
        if sites is None:
            sites = ["OUT", "MOUTH"]
        if not isinstance(sites, list):
            sites = [sites]

        for site in sites:
            m = self._model_engine.models[site]
            calc_gas_composition(m, self.fio2, m.temp, m.humidity)
