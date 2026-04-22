"""Placenta — port of src/explain/component_models/Placenta.js"""

from __future__ import annotations

from ..base_model import BaseModelClass


class Placenta(BaseModelClass):
    model_type = "Placenta"

    model_interface = [
        {"target": "description", "type": "string", "build_prop": True, "readonly": True},
        {"target": "is_enabled", "type": "boolean", "build_prop": True, "caption": "enabled"},
        {"target": "placenta_running", "type": "boolean", "build_prop": True},
        {"target": "umb_clamped", "type": "boolean", "build_prop": True},
    ]

    def __init__(self, model_ref, name: str = ""):
        super().__init__(model_ref, name)

        self.placenta_running = False
        self.umb_clamped = True
        self.umb_art_res = 800
        self.umb_art_res_factor = 1.0
        self.umb_ven_res = 100
        self.umb_ven_res_factor = 1.0
        self.plf_res = 2000
        self.plf_res_factor = 1.0
        self.mat_to2 = 6.85
        self.mat_tco2 = 23
        self.dif_o2 = 0.0005
        self.dif_co2 = 0.001

        self.umb_art_flow = 0.0
        self.umb_art_velocity = 0.0
        self.umb_ven_flow = 0.0
        self.umb_ven_velocity = 0.0

        self._update_interval = 0.015
        self._update_counter = 0.0
        self._umb_art = None
        self._umb_ven = None
        self._plf = None
        self._plm = None
        self._gas_exchanger = None

    def calc_model(self):
        self._update_counter += self._t
        if self._update_counter > self._update_interval and self.placenta_running:
            self._update_counter = 0.0

            self._umb_art = self._model_engine.models["PL_UMB_ART"]
            self._umb_ven = self._model_engine.models["PL_UMB_VEN"]
            self._plf = self._model_engine.models["PL_FETAL"]
            self._plm = self._model_engine.models["PL_MAT"]
            self._gas_exchanger = self._model_engine.models["PL_GASEX"]

            self._umb_art.is_enabled = self.placenta_running
            self._umb_ven.is_enabled = self.placenta_running
            self._plf.is_enabled = self.placenta_running
            self._plm.is_enabled = self.placenta_running
            self._gas_exchanger.is_enabled = self.placenta_running

            self._umb_art.no_flow = self.umb_clamped
            self._umb_ven.no_flow = self.umb_clamped
            self._plf.no_flow = self.umb_clamped

            self._umb_art.r_for = self.umb_art_res * self.umb_art_res_factor
            self._umb_art.r_back = self.umb_art_res * self.umb_art_res_factor
            self._umb_ven.r_for = self.umb_ven_res * self.umb_ven_res_factor
            self._umb_ven.r_back = self.umb_ven_res * self.umb_ven_res_factor
            self._plf.r_for = self.plf_res * self.plf_res_factor
            self._plf.r_back = self.plf_res * self.plf_res_factor

            self._plm.to2 = self.mat_to2
            self._plm.tco2 = self.mat_tco2

            self._gas_exchanger.dif_o2 = self.dif_o2
            self._gas_exchanger.dif_co2 = self.dif_co2
