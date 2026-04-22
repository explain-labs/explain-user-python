"""Ventilator — port of src/explain/device_models/Ventilator.js

Mechanical ventilator supporting PC, PRVC, and PS modes. Controls inspiratory
and expiratory valves and the ET-tube resistor. Pressures in JSON/UI are in
cmH2O and converted to mmHg internally via /1.35951.
"""

from __future__ import annotations

from ..base_model import BaseModelClass
from ..helpers.gas_composition import calc_gas_composition


class Ventilator(BaseModelClass):
    model_type = "Ventilator"

    model_interface = [
        {"target": "description", "type": "string", "build_prop": True, "readonly": True},
        {"target": "is_enabled", "type": "boolean", "build_prop": True, "caption": "enabled"},
    ]

    def __init__(self, model_ref, name: str = ""):
        super().__init__(model_ref, name)

        self.pres_atm = 760
        self.fio2 = 0.205
        self.humidity = 1.0
        self.temp = 37
        self.ettube_diameter = 4
        self.ettube_length = 110
        self.vent_mode = "PRVC"
        self.vent_rate = 40
        self.tidal_volume = 0.015
        self.insp_time = 0.4
        self.insp_flow = 12
        self.exp_flow = 3
        self.pip_cmh2o = 14
        self.pip_cmh2o_max = 14
        self.peep_cmh2o = 3
        self.trigger_volume_perc = 6
        self.synchronized = False
        self.components = {}

        self.pres = 0.0
        self.flow = 0.0
        self.vol = 0.0
        self.exp_time = 1.0
        self.trigger_volume = 0.0
        self.minute_volume = 0.0
        self.compliance = 0.0
        self.resistance = 0.0
        self.exp_tidal_volume = 0.0
        self.insp_tidal_volume = 0.0
        self.ncc_insp = 0.0
        self.ncc_exp = 0.0
        self.etco2 = 0.0
        self.co2 = 0.0
        self.triggered_breath = False
        self.tv_kg = 0.0

        self._vent_gasin = None
        self._vent_gascircuit = None
        self._vent_gasout = None
        self._vent_insp_valve = None
        self._vent_exp_valve = None
        self._vent_ettube = None
        self._ventilator_parts = []
        self._ettube_length_ref = 110
        self._pip = 0.0
        self._pip_max = 0.0
        self._peep = 0.0
        self._a = 0.0
        self._b = 0.0
        self._insp_time_counter = 0.0
        self._exp_time_counter = 0.0
        self._insp_tidal_volume_counter = 0.0
        self._exp_tidal_volume_counter = 0.0
        self._trigger_volume_counter = 0.0
        self._inspiration = False
        self._expiration = True
        self._tv_tolerance = 0.0005
        self._trigger_blocked = False
        self._trigger_start = False
        self._breathing_model = None
        self._peak_flow = 0.0
        self._prev_et_tube_flow = 0.0
        self._et_tube_resistance = 40.0

    def init_model(self, args):
        super().init_model(args)

        self._breathing_model = self._model_engine.models.get("Breathing")
        self._vent_gasin = self._model_engine.models.get("VENT_GASIN")
        self._vent_gascircuit = self._model_engine.models.get("VENT_GASCIRCUIT")
        self._vent_gasout = self._model_engine.models.get("VENT_GASOUT")
        self._vent_insp_valve = self._model_engine.models.get("VENT_INSP_VALVE")
        self._vent_ettube = self._model_engine.models.get("VENT_ETTUBE")
        self._vent_exp_valve = self._model_engine.models.get("VENT_EXP_VALVE")

        self._ventilator_parts = [
            self._vent_gasin, self._vent_gascircuit, self._vent_gasout,
            self._vent_insp_valve, self._vent_ettube, self._vent_exp_valve,
        ]

        if self._vent_gasin is not None:
            calc_gas_composition(self._vent_gasin, self.fio2, self.temp, self.humidity)
        if self._vent_gascircuit is not None:
            calc_gas_composition(self._vent_gascircuit, self.fio2, self.temp, self.humidity)
        if self._vent_gasout is not None:
            calc_gas_composition(self._vent_gasout, 0.205, 20.0, 0.5)

        self.set_ettube_diameter(self.ettube_diameter)
        self._et_tube_resistance = self.calc_ettube_resistance(self.flow)

    def calc_model(self):
        self._pip = self.pip_cmh2o / 1.35951
        self._pip_max = self.pip_cmh2o_max / 1.35951
        self._peep = self.peep_cmh2o / 1.35951

        if self.synchronized:
            self.triggering()

        if self.vent_mode == "PC" or self.vent_mode == "PRVC":
            self.time_cycling()
            self.pressure_control()

        if self.vent_mode == "PS":
            self.flow_cycling()
            self.pressure_control()

        self.pres = (self._vent_gascircuit.pres - self.pres_atm) * 1.35951
        self.flow = self._vent_ettube.flow * 60.0
        self.vol += self._vent_ettube.flow * 1000 * self._t
        self.co2 = self._model_engine.models["DS"].pco2
        self.minute_volume = self.exp_tidal_volume * self.vent_rate
        self.compliance = 1 / ((self._pip - self._peep) / self.exp_tidal_volume) if self.exp_tidal_volume != 0 else 0
        self.resistance = None
        self._et_tube_resistance = self.calc_ettube_resistance(self.flow)

    def triggering(self):
        self.trigger_volume = (self.tidal_volume / 100.0) * self.trigger_volume_perc

        if self._breathing_model.ncc_insp == 1 and not self._trigger_blocked:
            self._trigger_start = True

        if self._trigger_start:
            self._trigger_volume_counter += self._vent_ettube.flow * self._t

        if self._trigger_volume_counter > self.trigger_volume:
            self._trigger_volume_counter = 0.0
            self._exp_time_counter = self.exp_time
            self._trigger_start = False
            self.triggered_breath = True

    def flow_cycling(self):
        if self._vent_ettube.flow > 0.0 and self.triggered_breath:
            if self._vent_ettube.flow > self._prev_et_tube_flow:
                self._inspiration = True
                self._expiration = False
                self.ncc_insp = -1

                if self._vent_ettube.flow > self._peak_flow:
                    self._peak_flow = self._vent_ettube.flow

                self.exp_tidal_volume = -self._exp_tidal_volume_counter
            elif self._vent_ettube.flow < 0.3 * self._peak_flow:
                self._inspiration = False
                self._expiration = True
                self.ncc_exp = -1
                self._exp_tidal_volume_counter = 0.0
                self.triggered_breath = False

            self._prev_et_tube_flow = self._vent_ettube.flow

        if self._vent_ettube.flow < 0.0 and not self.triggered_breath:
            self._peak_flow = 0.0
            self._prev_et_tube_flow = 0.0
            self._inspiration = False
            self._expiration = True
            self.ncc_exp = -1
            self._exp_tidal_volume_counter += self._vent_ettube.flow * self._t

        if self._inspiration:
            self.ncc_insp += 1
            self._trigger_blocked = True

        if self._expiration:
            self.ncc_exp += 1
            self._trigger_blocked = False

    def time_cycling(self):
        self.exp_time = 60.0 / self.vent_rate - self.insp_time
        if self._insp_time_counter > self.insp_time:
            self._insp_time_counter = 0.0
            self.insp_tidal_volume = self._insp_tidal_volume_counter
            self._insp_tidal_volume_counter = 0.0
            self._inspiration = False
            self._expiration = True
            self.triggered_breath = False
            self.ncc_exp = -1

        if self._exp_time_counter > self.exp_time:
            self._exp_time_counter = 0.0
            self._inspiration = True
            self._expiration = False
            self.ncc_insp = -1
            self.vol = 0.0
            self.exp_tidal_volume = -self._exp_tidal_volume_counter
            self.etco2 = self._model_engine.models["DS"].pco2
            self.tv_kg = (self.exp_tidal_volume * 1000.0) / self._model_engine.weight

            if self.exp_tidal_volume > 0:
                self.compliance = 1 / (((self._pip - self._peep) * 1.35951) / (self.exp_tidal_volume * 1000.0))

            self._exp_tidal_volume_counter = 0.0

            if self.vent_mode == "PRVC":
                self.pressure_regulated_volume_control()

        if self._inspiration:
            self._insp_time_counter += self._t
            self.ncc_insp += 1
            self._trigger_blocked = True
            self._trigger_volume_counter = 0.0

        if self._expiration:
            self._exp_time_counter += self._t
            self.ncc_exp += 1
            self._trigger_blocked = False

    def pressure_control(self):
        if self._inspiration:
            self._vent_exp_valve.no_flow = True
            self._vent_insp_valve.no_flow = False
            self._vent_insp_valve.no_back_flow = True
            self._vent_insp_valve.r_for = (self._vent_gasin.pres + self._pip - self.pres_atm - self._peep) / (self.insp_flow / 60.0)

            if self._vent_gascircuit.pres > self._pip + self.pres_atm:
                self._vent_insp_valve.no_flow = True

            if self._vent_ettube.flow > 0:
                self._insp_tidal_volume_counter += self._vent_ettube.flow * self._t

        if self._expiration:
            self._vent_insp_valve.no_flow = True
            self._vent_exp_valve.no_flow = False
            self._vent_exp_valve.no_back_flow = True
            self._vent_exp_valve.r_for = 10
            self._vent_gasout.vol = self._peep / self._vent_gasout.el_base + self._vent_gasout.u_vol

            if self._vent_ettube.flow < 0:
                self._exp_tidal_volume_counter += self._vent_ettube.flow * self._t

    def pressure_regulated_volume_control(self):
        if self.exp_tidal_volume < self.tidal_volume - self._tv_tolerance:
            self.pip_cmh2o += 1.0

            if self.pip_cmh2o > self.pip_cmh2o_max:
                self.pip_cmh2o = self.pip_cmh2o_max

        if self.exp_tidal_volume > self.tidal_volume + self._tv_tolerance:
            self.pip_cmh2o -= 1.0

            if self.pip_cmh2o < self.peep_cmh2o + 2.0:
                self.pip_cmh2o = self.peep_cmh2o + 2.0

    def reset_dependent_properties(self):
        self.pres = 0.0
        self.flow = 0.0
        self.vol = 0.0
        self.exp_time = 1.0
        self.trigger_volume = 0.0
        self.minute_volume = 0.0
        self.compliance = 0.0
        self.resistance = 0.0
        self.exp_tidal_volume = 0.0
        self.insp_tidal_volume = 0.0
        self.ncc_insp = 0.0
        self.ncc_exp = 0.0
        self.etco2 = 0.0
        self.co2 = 0.0
        self.triggered_breath = False

    def switch_ventilator(self, state):
        self.is_enabled = state
        if not state:
            self.reset_dependent_properties()

        for vp in self._ventilator_parts:
            if vp is None:
                continue
            vp.is_enabled = state
            if hasattr(vp, "no_flow"):
                vp.no_flow = not state

        mouth_ds = self._model_engine.models.get("MOUTH_DS")
        if mouth_ds is not None:
            mouth_ds.no_flow = state

    def calc_ettube_resistance(self, flow):
        _ettube_length_ref = 110
        res = (self._a * flow + self._b) * (self.ettube_length / _ettube_length_ref)
        if res < 15.0:
            res = 15

        if self._vent_ettube is not None:
            self._vent_ettube.r_for = res
            self._vent_ettube.r_back = res

        return res

    def set_ettube_length(self, new_length):
        if new_length >= 50:
            self.ettube_length = new_length

    def set_ettube_diameter(self, new_diameter):
        if new_diameter > 1.5:
            self.ettube_diameter = new_diameter
            self._a = -2.375 * new_diameter + 11.9375
            self._b = -14.375 * new_diameter + 65.9374

    def set_fio2(self, new_fio2):
        if new_fio2 > 20:
            self.fio2 = new_fio2 / 100.0
        else:
            self.fio2 = new_fio2

        if self._vent_gasin is not None:
            calc_gas_composition(self._vent_gasin, self.fio2, self._vent_gasin.temp, self._vent_gasin.humidity)

    def set_humidity(self, new_humidity):
        if 0 <= new_humidity <= 1.0:
            self.humidity = new_humidity
            if self._vent_gasin is not None:
                calc_gas_composition(self._vent_gasin, self.fio2, self._vent_gasin.temp, self.humidity)

    def set_temp(self, new_temp):
        self.temp = new_temp
        if self._vent_gasin is not None:
            calc_gas_composition(self._vent_gasin, self.fio2, self.temp, self._vent_gasin.humidity)

    def set_pc(self, pip=14.0, peep=4.0, rate=40.0, t_in=0.4, insp_flow=10.0):
        self.pip_cmh2o = pip
        self.pip_cmh2o_max = pip
        self.peep_cmh2o = peep
        self.vent_rate = rate
        self.insp_time = t_in
        self.insp_flow = insp_flow
        self.vent_mode = "PC"

    def set_prvc(self, pip_max=18.0, peep=4.0, rate=40.0, tv=15.0, t_in=0.4, insp_flow=10.0):
        self.pip_cmh2o_max = pip_max
        self.peep_cmh2o = peep
        self.vent_rate = rate
        self.insp_time = t_in
        self.tidal_volume = tv / 1000.0
        self.insp_flow = insp_flow
        self.vent_mode = "PRVC"

    def set_psv(self, pip=14.0, peep=4.0, rate=40.0, t_in=0.4, insp_flow=10.0):
        self.pip_cmh2o = pip
        self.pip_cmh2o_max = pip
        self.peep_cmh2o = peep
        self.vent_rate = rate
        self.insp_time = t_in
        self.insp_flow = insp_flow
        self.vent_mode = "PS"

    def trigger_breath(self, pip=14.0, peep=4.0, rate=40.0, t_in=0.4, insp_flow=10.0):
        self._exp_time_counter = self.exp_time + 0.1
