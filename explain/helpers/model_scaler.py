"""ModelScaler — port of src/explain/helpers/ModelScaler.js

Config-driven scaling of model subsystems by name (blood, heart, lung,
airway, containers, etc). Tracks previous values to compute deltas for
volume scaling; `incorporate()` bakes all persistent scaling factors into
base properties and resets factors to 1.0.
"""

from __future__ import annotations


class ModelScaler:
    def __init__(self, model, config=None):
        self._model = model
        self._config = config

        self._prev = {
            "blood_vol": 1.0, "heart_vol": 1.0, "lung_vol": 1.0,
            "thorax_vol": 1.0, "pericardium_vol": 1.0,
            "blood_el": 1.0, "blood_res": 1.0,
            "pulm_el": 1.0, "pulm_res": 1.0, "pulm_uvol": 1.0,
            "sys_el": 1.0, "sys_res": 1.0, "sys_uvol": 1.0,
            "airway_el": 1.0, "airway_uvol": 1.0,
            "airway_upper_res": 1.0, "airway_lower_res": 1.0,
            "left_lung_el": 1.0, "left_lung_res": 1.0, "left_lung_uvol": 1.0,
            "right_lung_el": 1.0, "right_lung_res": 1.0, "right_lung_uvol": 1.0,
            "heart_el_min": 1.0, "heart_el_max": 1.0,
            "left_heart_el_min": 1.0, "left_heart_el_max": 1.0, "left_heart_uvol": 1.0,
            "right_heart_el_min": 1.0, "right_heart_el_max": 1.0, "right_heart_uvol": 1.0,
            "heart_res": 1.0,
            "thorax_el": 1.0, "pericardium_el": 1.0,
        }

    def _apply(self, names, prop, factor):
        for name in names:
            comp = self._model.models.get(name)
            if comp is not None and hasattr(comp, prop):
                setattr(comp, prop, factor)

    def _scale_vol(self, names, factor, delta):
        for name in names:
            comp = self._model.models.get(name)
            if comp is None:
                continue
            if hasattr(comp, "vol"):
                comp.vol *= delta
            if hasattr(comp, "u_vol_factor_scaling_ps"):
                comp.u_vol_factor_scaling_ps = factor

    def scale_blood_volume(self, factor):
        delta = factor / self._prev["blood_vol"]
        self._prev["blood_vol"] = factor
        self._scale_vol(self._config["blood"]["volume"], factor, delta)

    def scale_heart_volume(self, factor):
        delta = factor / self._prev["heart_vol"]
        self._scale_vol(self._config["heart"]["volume"], factor, delta)
        self._prev["heart_vol"] = factor

    def scale_lung_volume(self, factor):
        delta = factor / self._prev["lung_vol"]
        self._scale_vol(self._config["lung"]["volume"], factor, delta)
        self._prev["lung_vol"] = factor

    def scale_thorax_volume(self, factor):
        delta = factor / self._prev["thorax_vol"]
        self._scale_vol(self._config["thorax"], factor, delta)
        self._prev["thorax_vol"] = factor

    def scale_pericardium_volume(self, factor):
        delta = factor / self._prev["pericardium_vol"]
        self._scale_vol(self._config["pericardium"], factor, delta)
        self._prev["pericardium_vol"] = factor

    def scale_blood_elastances(self, factor):
        self._apply(self._config["blood"]["el_base"], "el_base_factor_scaling_ps", factor)
        self._prev["blood_el"] = factor

    def scale_blood_resistances(self, factor):
        self._apply(self._config["blood"]["resistance"], "r_factor_scaling_ps", factor)
        self._prev["blood_res"] = factor

    def scale_pulmonary_elastances(self, factor):
        self._apply(self._config["blood_pulmonary"]["el_base"], "el_base_factor_scaling_ps", factor)
        self._prev["pulm_el"] = factor

    def scale_pulmonary_resistances(self, factor):
        self._apply(self._config["blood_pulmonary"]["resistance"], "r_factor_scaling_ps", factor)
        self._prev["pulm_res"] = factor

    def scale_pulmonary_u_vol(self, factor):
        self._apply(self._config["blood_pulmonary"]["el_base"], "u_vol_factor_scaling_ps", factor)
        self._prev["pulm_uvol"] = factor

    def scale_systemic_elastances(self, factor):
        self._apply(self._config["blood_systemic"]["el_base"], "el_base_factor_scaling_ps", factor)
        self._prev["sys_el"] = factor

    def scale_systemic_resistances(self, factor):
        self._apply(self._config["blood_systemic"]["resistance"], "r_factor_scaling_ps", factor)
        self._prev["sys_res"] = factor

    def scale_systemic_u_vol(self, factor):
        self._apply(self._config["blood_systemic"]["el_base"], "u_vol_factor_scaling_ps", factor)
        self._prev["sys_uvol"] = factor

    def scale_airway_elastances(self, factor):
        self._apply(self._config["airway"]["el_base"], "el_base_factor_scaling_ps", factor)
        self._prev["airway_el"] = factor

    def scale_airway_u_vol(self, factor):
        self._apply(self._config["airway"]["u_vol"], "u_vol_factor_scaling_ps", factor)
        self._prev["airway_uvol"] = factor

    def scale_airway_upper_resistances(self, factor):
        self._apply(self._config["airway"]["resistance_upper"], "r_factor_scaling_ps", factor)
        self._prev["airway_upper_res"] = factor

    def scale_airway_lower_resistances(self, factor):
        self._apply(self._config["airway"]["resistance_lower"], "r_factor_scaling_ps", factor)
        self._prev["airway_lower_res"] = factor

    def scale_left_lung_elastances(self, factor):
        self._apply(self._config["left_lung"]["el_base"], "el_base_factor_scaling_ps", factor)
        self._prev["left_lung_el"] = factor

    def scale_left_lung_resistances(self, factor):
        self._apply(self._config["left_lung"]["resistance"], "r_factor_scaling_ps", factor)
        self._prev["left_lung_res"] = factor

    def scale_left_lung_u_vol(self, factor):
        self._apply(self._config["left_lung"]["u_vol"], "u_vol_factor_scaling_ps", factor)
        self._prev["left_lung_uvol"] = factor

    def scale_right_lung_elastances(self, factor):
        self._apply(self._config["right_lung"]["el_base"], "el_base_factor_scaling_ps", factor)
        self._prev["right_lung_el"] = factor

    def scale_right_lung_resistances(self, factor):
        self._apply(self._config["right_lung"]["resistance"], "r_factor_scaling_ps", factor)
        self._prev["right_lung_res"] = factor

    def scale_right_lung_u_vol(self, factor):
        self._apply(self._config["right_lung"]["u_vol"], "u_vol_factor_scaling_ps", factor)
        self._prev["right_lung_uvol"] = factor

    def scale_heart_el_min(self, factor):
        self._apply(self._config["heart"]["el_min"], "el_min_factor_scaling_ps", factor)
        self._prev["heart_el_min"] = factor

    def scale_heart_el_max(self, factor):
        self._apply(self._config["heart"]["el_max"], "el_max_factor_scaling_ps", factor)
        self._prev["heart_el_max"] = factor

    def scale_left_heart_el_min(self, factor):
        self._apply(self._config["heart_left"]["el_min"], "el_min_factor_scaling_ps", factor)
        self._prev["left_heart_el_min"] = factor

    def scale_left_heart_el_max(self, factor):
        self._apply(self._config["heart_left"]["el_max"], "el_max_factor_scaling_ps", factor)
        self._prev["left_heart_el_max"] = factor

    def scale_left_heart_u_vol(self, factor):
        self._apply(self._config["heart_left"]["el_min"], "u_vol_factor_scaling_ps", factor)
        self._prev["left_heart_uvol"] = factor

    def scale_right_heart_el_min(self, factor):
        self._apply(self._config["heart_right"]["el_min"], "el_min_factor_scaling_ps", factor)
        self._prev["right_heart_el_min"] = factor

    def scale_right_heart_el_max(self, factor):
        self._apply(self._config["heart_right"]["el_max"], "el_max_factor_scaling_ps", factor)
        self._prev["right_heart_el_max"] = factor

    def scale_right_heart_u_vol(self, factor):
        self._apply(self._config["heart_right"]["el_min"], "u_vol_factor_scaling_ps", factor)
        self._prev["right_heart_uvol"] = factor

    def scale_heart_resistances(self, factor):
        self._apply(self._config["heart"]["resistance"], "r_factor_scaling_ps", factor)
        self._prev["heart_res"] = factor

    def scale_thorax_elastances(self, factor):
        self._apply(self._config["thorax"], "el_base_factor_scaling_ps", factor)
        self._prev["thorax_el"] = factor

    def scale_pericardium_elastances(self, factor):
        self._apply(self._config["pericardium"], "el_base_factor_scaling_ps", factor)
        self._prev["pericardium_el"] = factor

    def incorporate(self):
        u_vol_groups = (
            list(self._config["blood"]["volume"])
            + list(self._config["blood_pulmonary"]["el_base"])
            + list(self._config["blood_systemic"]["el_base"])
            + list(self._config["heart"]["volume"])
            + list(self._config["heart_left"]["el_min"])
            + list(self._config["heart_right"]["el_min"])
            + list(self._config["lung"]["volume"])
            + list(self._config["thorax"])
            + list(self._config["pericardium"])
        )
        self._bake(u_vol_groups, "u_vol", "u_vol_factor_scaling_ps")

        el_base_groups = (
            list(self._config["blood"]["el_base"])
            + list(self._config["blood_pulmonary"]["el_base"])
            + list(self._config["blood_systemic"]["el_base"])
            + list(self._config["lung"]["el_base"])
            + list(self._config["thorax"])
            + list(self._config["pericardium"])
        )
        self._bake(el_base_groups, "el_base", "el_base_factor_scaling_ps")

        self._bake(self._config["heart"]["el_min"], "el_min", "el_min_factor_scaling_ps")
        self._bake(self._config["heart"]["el_max"], "el_max", "el_max_factor_scaling_ps")

        res_groups = (
            list(self._config["blood"]["resistance"])
            + list(self._config["blood_pulmonary"]["resistance"])
            + list(self._config["blood_systemic"]["resistance"])
            + list(self._config["lung"]["resistance"])
            + list(self._config["heart"]["resistance"])
        )
        self._bake_resistance(res_groups)

        for key in self._prev:
            self._prev[key] = 1.0

    def _bake(self, names, base_prop, factor_prop):
        for name in names:
            comp = self._model.models.get(name)
            if comp is None:
                continue
            f = getattr(comp, factor_prop, None)
            if f is not None and f != 1.0:
                setattr(comp, base_prop, getattr(comp, base_prop) * f)
                setattr(comp, factor_prop, 1.0)

    def _bake_resistance(self, names):
        for name in names:
            comp = self._model.models.get(name)
            if comp is None:
                continue
            f = getattr(comp, "r_factor_scaling_ps", None)
            if f is not None and f != 1.0:
                if hasattr(comp, "r_for"):
                    comp.r_for *= f
                if hasattr(comp, "r_back"):
                    comp.r_back *= f
                comp.r_factor_scaling_ps = 1.0

    def add_volume(self, vol_liters):
        ivci = self._model.models.get("IVCI")
        if ivci is not None and hasattr(ivci, "vol"):
            ivci.vol += vol_liters

    def reset(self):
        self.scale_blood_volume(1.0)
        self.scale_heart_volume(1.0)
        self.scale_lung_volume(1.0)
        self.scale_thorax_volume(1.0)
        self.scale_pericardium_volume(1.0)

        self.scale_blood_elastances(1.0)
        self.scale_blood_resistances(1.0)

        self.scale_pulmonary_elastances(1.0)
        self.scale_pulmonary_resistances(1.0)
        self.scale_pulmonary_u_vol(1.0)

        self.scale_systemic_elastances(1.0)
        self.scale_systemic_resistances(1.0)
        self.scale_systemic_u_vol(1.0)

        self.scale_airway_elastances(1.0)
        self.scale_airway_u_vol(1.0)
        self.scale_airway_upper_resistances(1.0)
        self.scale_airway_lower_resistances(1.0)

        self.scale_left_lung_elastances(1.0)
        self.scale_left_lung_resistances(1.0)
        self.scale_left_lung_u_vol(1.0)

        self.scale_right_lung_elastances(1.0)
        self.scale_right_lung_resistances(1.0)
        self.scale_right_lung_u_vol(1.0)

        self.scale_heart_el_min(1.0)
        self.scale_heart_el_max(1.0)
        self.scale_left_heart_el_min(1.0)
        self.scale_left_heart_el_max(1.0)
        self.scale_left_heart_u_vol(1.0)
        self.scale_right_heart_el_min(1.0)
        self.scale_right_heart_el_max(1.0)
        self.scale_right_heart_u_vol(1.0)
        self.scale_heart_resistances(1.0)

        self.scale_thorax_elastances(1.0)
        self.scale_pericardium_elastances(1.0)
