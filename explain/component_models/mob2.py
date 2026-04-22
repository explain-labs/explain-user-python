"""Mob2 — port of src/explain/component_models/Mob2.js

Myocardial oxygen balance. Two VO2 terms (basal + stroke-work), per-gram of
heart tissue. Computes PV-loop area via trapezoidal integration on LV and
RV per beat, captures at the rising edge of cardiac_cycle_running. Hypoxia
feedback via _d_hr, _d_cont, _d_ans written onto Heart/ventricle/atrial
*_mob_factor fields.
"""

from __future__ import annotations

from ..base_model import BaseModelClass


class Mob2(BaseModelClass):
    model_type = "Mob2"

    model_interface = [
        {"target": "description", "type": "string", "build_prop": True, "readonly": True},
        {"target": "is_enabled", "type": "boolean", "build_prop": True, "caption": "enabled"},
        {"target": "mob_active", "type": "boolean"},
    ]

    def __init__(self, model_ref, name: str = ""):
        super().__init__(model_ref, name)

        self.mob_active = True
        self.to2_min = 0.0002
        self.to2_ref = 0.2
        self.resp_q = 0.1

        self.bm_vo2_per_g = 3.7e-5
        self.sw_vo2_per_g = 2.0e-7

        self.hw_intercept = 7.799
        self.hw_slope = 0.004296

        self.hr_factor = 1
        self.hr_factor_max = 1
        self.hr_factor_min = 0.01
        self.hr_tc = 5
        self.cont_factor = 1
        self.cont_factor_max = 1
        self.cont_factor_min = 0.01
        self.cont_tc = 5
        self.ans_factor = 1
        self.ans_factor_max = 1
        self.ans_factor_min = 0.01
        self.ans_tc = 5
        self.ans_activity_factor = 1

        self.hw = 0.0
        self.bm_vo2 = 0.0
        self.sw_vo2 = 0.0
        self.mob_vo2 = 0.0
        self.mvo2_step = 0.0
        self.stroke_work_lv = 0.0
        self.stroke_work_rv = 0.0
        self.stroke_work_total = 0.0
        self.mob = 0.0

        # computed per-step gains
        self.hr_g = 0.0
        self.cont_g = 0.0
        self.ans_g = 0.0

        self._aa = None
        self._aa_cor = None
        self._cor = None
        self._heart = None
        self._lv = None
        self._rv = None
        self._a_to2 = 0.0
        self._d_hr = 0.0
        self._d_cont = 0.0
        self._d_ans = 0.0
        self._sw_vo2_per_beat = 0.0
        self._prev_lv_vol = 0.0
        self._prev_lv_pres = 0.0
        self._prev_rv_vol = 0.0
        self._prev_rv_pres = 0.0
        self._pv_area_lv_inc = 0.0
        self._pv_area_lv_dec = 0.0
        self._pv_area_rv_inc = 0.0
        self._pv_area_rv_dec = 0.0

    def calc_model(self):
        if not self.mob_active:
            return

        self.hw = self.hw_intercept + self.hw_slope * self._model_engine.weight * 1000.0

        self.hr_g = (self.hr_factor_max - self.hr_factor_min) / (self.to2_ref - self.to2_min)
        self.cont_g = (self.cont_factor_max - self.cont_factor_min) / (self.to2_ref - self.to2_min)
        self.ans_g = (self.ans_factor_max - self.ans_factor_min) / (self.to2_ref - self.to2_min)

        self._aa = self._model_engine.models["AA"]
        self._aa_cor = self._model_engine.models["AA_COR"]
        self._cor = self._model_engine.models["COR"]
        self._heart = self._model_engine.models["Heart"]
        self._lv = self._model_engine.models["LV"]
        self._rv = self._model_engine.models["RV"]

        to2_cor = self._cor.to2
        tco2_cor = self._cor.tco2
        vol_cor = self._cor.vol

        self._a_to2 = self.activation_function(to2_cor, self.to2_ref, self.to2_ref, self.to2_min)
        self._d_hr = self._t * ((1 / self.hr_tc) * (-self._d_hr + self._a_to2)) + self._d_hr
        self._d_cont = self._t * ((1 / self.cont_tc) * (-self._d_cont + self._a_to2)) + self._d_cont
        self._d_ans = self._t * ((1 / self.ans_tc) * (-self._d_ans + self._a_to2)) + self._d_ans

        self.bm_vo2 = self.bm_vo2_per_g * self.hw
        self.sw_vo2 = self.calc_sw_vo2()

        self.mob_vo2 = self.bm_vo2 + self.sw_vo2

        self.mvo2_step = self.mob_vo2 * self._t
        co2_production = self.mvo2_step * self.resp_q

        self.calc_hypoxia_effects()

        o2_inflow = self._aa_cor.flow * self._aa.to2
        o2_use = self.mvo2_step / self._t
        self.mob = o2_inflow - o2_use + to2_cor

        if vol_cor > 0:
            new_to2_cor = (to2_cor * vol_cor - self.mvo2_step) / vol_cor
            new_tco2_cor = (tco2_cor * vol_cor + co2_production) / vol_cor
            if new_to2_cor >= 0:
                self._cor.to2 = new_to2_cor
                self._cor.tco2 = new_tco2_cor

    def calc_sw_vo2(self):
        # Rising-edge cardiac_cycle_running capture.
        #
        # JS source deviation: Mob2.js line 317 reads
        # `this._heart._prev_cardiac_cycle_running` (underscore-prefixed), but
        # Heart.js only declares/updates `this.prev_cardiac_cycle_running`
        # (no underscore). In JS, the read returns `undefined` every step,
        # making the rising-edge check fire on EVERY step the cycle is
        # running — not just at the transition — so stroke work is captured
        # many times per beat and reset, giving a wildly wrong per-beat
        # sw_vo2. This is a latent JS bug.
        #
        # This Python port intentionally reads the correct attribute name
        # (`prev_cardiac_cycle_running`, no underscore) so the rising-edge
        # semantics are what the code clearly intended. Consequence: Mob2
        # output will NOT be bit-identical to the JS engine until the JS
        # source is also fixed. All other Mob2 paths (hypoxia filters,
        # PV-loop integration, coronary update, cross-writes) remain
        # bit-identical.
        heart_prev_running = getattr(self._heart, "prev_cardiac_cycle_running", 0)
        if self._heart.cardiac_cycle_running and not heart_prev_running:
            self.stroke_work_lv = self._pv_area_lv_dec - self._pv_area_lv_inc
            self.stroke_work_rv = self._pv_area_rv_dec - self._pv_area_rv_inc
            self.stroke_work_total = self.stroke_work_lv + self.stroke_work_rv

            self._sw_vo2_per_beat = self.sw_vo2_per_g * self.hw * self.stroke_work_total

            self._pv_area_lv_inc = 0.0
            self._pv_area_lv_dec = 0.0
            self._pv_area_rv_inc = 0.0
            self._pv_area_rv_dec = 0.0

        _dV_lv = self._lv.vol - self._prev_lv_vol
        if _dV_lv > 0:
            self._pv_area_lv_inc += _dV_lv * self._prev_lv_pres + (_dV_lv * (self._lv.pres - self._prev_lv_pres)) / 2.0
        else:
            self._pv_area_lv_dec += -_dV_lv * self._prev_lv_pres + (-_dV_lv * (self._lv.pres - self._prev_lv_pres)) / 2.0

        _dV_rv = self._rv.vol - self._prev_rv_vol
        if _dV_rv > 0:
            self._pv_area_rv_inc += _dV_rv * self._prev_rv_pres + (_dV_rv * (self._rv.pres - self._prev_rv_pres)) / 2.0
        else:
            self._pv_area_rv_dec += -_dV_rv * self._prev_rv_pres + (-_dV_rv * (self._rv.pres - self._prev_rv_pres)) / 2.0

        self._prev_lv_vol = self._lv.vol
        self._prev_lv_pres = self._lv.pres
        self._prev_rv_vol = self._rv.vol
        self._prev_rv_pres = self._rv.pres

        cc_time = self._heart.cardiac_cycle_time
        return self._sw_vo2_per_beat / cc_time if cc_time > 0 else 0.0

    def calc_hypoxia_effects(self):
        self.ans_activity_factor = 1.0 + self.ans_g * self._d_ans
        self._heart.ans_activity_factor = self.ans_activity_factor

        self.hr_factor = 1.0 + self.hr_g * self._d_hr
        self._heart.hr_mob_factor = self.hr_factor

        self.cont_factor = 1.0 + self.cont_g * self._d_cont
        self._heart._lv.el_max_mob_factor = self.cont_factor
        self._heart._rv.el_max_mob_factor = self.cont_factor
        self._heart._la.el_max_mob_factor = self.cont_factor
        if self._heart._raivci:
            self._heart._raivci.el_max_mob_factor = self.cont_factor
        if self._heart._rasvc:
            self._heart._rasvc.el_max_mob_factor = self.cont_factor

    def activation_function(self, value, max_, setpoint, min_):
        if value >= max_:
            return max_ - setpoint
        if value <= min_:
            return min_ - setpoint
        return value - setpoint
