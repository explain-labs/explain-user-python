"""Blood — port of src/explain/component_models/Blood.js

Top-level blood system. Seeds composition into every blood-containing model
at init, and every 1s runs calc_blood_composition on AA, AD, IVCI, SVC to
populate preductal/arterial/venous bloodgas dicts.
"""

from __future__ import annotations

from ..base_model import BaseModelClass
from ..helpers.blood_composition import calc_blood_composition


class Blood(BaseModelClass):
    model_type = "Blood"

    model_interface = [
        {"target": "description", "type": "string", "build_prop": True, "readonly": True},
        {"target": "is_enabled", "type": "boolean", "build_prop": True, "caption": "enabled"},
    ]

    def __init__(self, model_ref, name: str = ""):
        super().__init__(model_ref, name)

        self.viscosity = 6.0
        self.temp = 37.0
        self.to2 = 0.0
        self.tco2 = 0.0
        self.solutes = {}
        self.P50_0 = 20.0
        self.blood_containing_modeltypes = [
            "BloodVessel", "HeartChamber", "BloodCapacitance",
            "BloodTimeVaryingElastance", "BloodPump", "MicroVascularUnit",
        ]

        self.preductal_art_bloodgas = {}
        self.art_bloodgas = {}
        self.ven_bloodgas = {}
        self.art_solutes = {}

        self._update_interval = 1.0
        self._update_counter = 0.0
        self._ascending_aorta = None
        self._descending_aorta = None
        self._blood_components = []

    def init_model(self, args):
        # JS apply setattrs directly (doesn't call super.init_model)
        for arg in args:
            setattr(self, arg["key"], arg["value"])

        self._blood_components = []
        for model_name in list(self._model_engine.models.keys()):
            model = self._model_engine.models[model_name]
            if getattr(model, "model_type", None) in self.blood_containing_modeltypes:
                self._blood_components.append(model)
                if getattr(model, "to2", 0.0) == 0.0 and getattr(model, "tco2", 0.0) == 0.0:
                    model.to2 = self.to2
                    model.tco2 = self.tco2
                    model.solutes = dict(self.solutes)
                    model.temp = self.temp
                    model.viscosity = self.viscosity

        self._ascending_aorta = self._model_engine.models.get("AA")
        self._descending_aorta = self._model_engine.models.get("AD")

        self.art_solutes = dict(self.solutes)

        self._is_initialized = True

    def calc_model(self):
        self._update_counter += self._t
        if self._update_counter >= self._update_interval:
            self._update_counter = 0.0

            if self._ascending_aorta is not None:
                calc_blood_composition(self._ascending_aorta)
                self.preductal_art_bloodgas = {
                    "ph": self._ascending_aorta.ph,
                    "pco2": self._ascending_aorta.pco2,
                    "po2": self._ascending_aorta.po2,
                    "hco3": self._ascending_aorta.hco3,
                    "be": self._ascending_aorta.be,
                    "so2": self._ascending_aorta.so2,
                }

            if self._descending_aorta is not None:
                calc_blood_composition(self._descending_aorta)
                self.art_bloodgas = {
                    "ph": self._descending_aorta.ph,
                    "pco2": self._descending_aorta.pco2,
                    "po2": self._descending_aorta.po2,
                    "hco3": self._descending_aorta.hco3,
                    "be": self._descending_aorta.be,
                    "so2": self._descending_aorta.so2,
                }

            ivci = self._model_engine.models.get("IVCI")
            if ivci is not None:
                calc_blood_composition(ivci)
            svc = self._model_engine.models.get("SVC")
            if svc is not None:
                calc_blood_composition(svc)

            if self._descending_aorta is not None:
                self.art_solutes = dict(self._descending_aorta.solutes)

    def set_temperature(self, new_temp, bc_site=""):
        self.temp = new_temp
        if bc_site:
            self._model_engine.models[bc_site].temp = new_temp
        else:
            for model in self._blood_components:
                model.temp = new_temp

    def set_viscosity(self, new_viscosity):
        self.viscosity = new_viscosity
        for model in self._blood_components:
            model.viscosity = new_viscosity

    def set_to2(self, new_to2, bc_site=""):
        if bc_site:
            self._model_engine.models[bc_site].to2 = new_to2
        else:
            for model in self._blood_components:
                model.to2 = new_to2

    def set_tco2(self, new_tco2, bc_site=""):
        if bc_site:
            self._model_engine.models[bc_site].tco2 = new_tco2
        else:
            for model in self._blood_components:
                model.tco2 = new_tco2

    def set_solute(self, solute, solute_value, bc_site=""):
        if bc_site:
            self._model_engine.models[bc_site].solutes[solute] = solute_value
        else:
            for model in self._blood_components:
                model.solutes = dict(self.solutes)
