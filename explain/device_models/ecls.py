"""Ecls — port of src/explain/device_models/Ecls.js

Extracorporeal circulation circuit: drainage cannula -> tubing_in -> pump
-> oxygenator -> tubing_out -> return cannula. Uses RealTimeMovingAverage
for filtered venous / internal / arterial pressures and flow.
"""

from __future__ import annotations

from ..base_model import BaseModelClass
from ..helpers.gas_composition import calc_gas_composition
from ..helpers.blood_composition import calc_blood_composition
from ..helpers.real_time_moving_average import RealTimeMovingAverage


class Ecls(BaseModelClass):
    model_type = "Ecls"

    model_interface = [
        {"target": "ecls_clamped", "type": "boolean", "build_prop": True, "caption": "ECLS clamped"},
    ]

    def __init__(self, model_ref, name: str = ""):
        super().__init__(model_ref, name)

        self.ecls_running = False
        self.ecls_clamped = True

        self.drainage_res_factor = 1.0
        self.return_res_factor = 1.0
        self.tubing_res_factor = 1.0
        self.pump_res_factor = 1.0
        self.oxy_res_for = 1500
        self.oxy_res_back = 1500
        self.oxy_res_factor = 1.0
        self.oxy_vol = 0.09
        self.gas_flow = 0.5
        self.gas_fio2 = 0.205
        self.gas_fico2 = 0.000392
        self.gas_humidity = 0.5
        self.gas_temp = 20.0
        self.dif_o2 = 0.0005
        self.dif_co2 = 0.001
        self.pump_rpm = 1500.0
        self.pump_mode = 0
        self.pump_pressure = 0.0
        self.cannula_sizes_single = [6, 8, 10, 12]
        self.cannula_size_double = [13, 14, 15]

        self.drainage_site = "RA"
        self.drainage_cannula_diameter = 0.0027
        self.drainage_cannula_length = 0.105

        self.return_site = "AAR"
        self.return_cannula_diameter = 0.0027
        self.return_cannula_length = 0.105

        self.tubing_in_diameter = 0.00375
        self.tubing_in_length = 1.0

        self.tubing_out_diameter = 0.00375
        self.tubing_out_length = 1.0

        self.pump_res_for = 50
        self.pump_res_back = 50
        self.pump_vol = 0.031

        self.return_cannulas = {
            "Bio-Medicus arterial 8 Fr":  {"inner_diameter": 0.002,  "length": 0.1,   "resistance": 5500},
            "Bio-Medicus arterial 10 Fr": {"inner_diameter": 0.00267,"length": 0.105, "resistance": 1700},
            "Bio-Medicus arterial 12 Fr": {"inner_diameter": 0.0032, "length": 0.11,  "resistance": 650},
            "Medtronic Crescent 13 Fr":   {"inner_diameter": 0.0029, "length": 0.089, "resistance": 7000},
            "Medtronic Crescent 15 Fr":   {"inner_diameter": 0.0029, "length": 0.097, "resistance": 2700},
        }

        self.drainage_cannulas = {
            "Bio-Medicus venous 8 Fr":    {"inner_diameter": 0.0021, "length": 0.1,   "resistance": 4600},
            "Bio-Medicus venous 10 Fr":   {"inner_diameter": 0.0027, "length": 0.105, "resistance": 1500},
            "Bio-Medicus venous 12 Fr":   {"inner_diameter": 0.0033, "length": 0.11,  "resistance": 600},
            "Bio-Medicus venous 14 Fr":   {"inner_diameter": 0.0039, "length": 0.115, "resistance": 260},
            "Medtronic Crescent 13 Fr":   {"inner_diameter": 0.0028, "length": 0.089, "resistance": 2500},
            "Medtronic Crescent 15 Fr":   {"inner_diameter": 0.0028, "length": 0.097, "resistance": 1100},
        }

        self.drainage_cannula_type = "Bio-Medicus venous 12 Fr"
        self.return_cannula_type = "Bio-Medicus arterial 10 Fr"

        sel_drainage = self.drainage_cannulas.get(self.drainage_cannula_type)
        if sel_drainage:
            self.drainage_cannula_diameter = sel_drainage["inner_diameter"]
            self.drainage_cannula_length = sel_drainage["length"]

        sel_return = self.return_cannulas.get(self.return_cannula_type)
        if sel_return:
            self.return_cannula_diameter = sel_return["inner_diameter"]
            self.return_cannula_length = sel_return["length"]

        self.p_ven = 0.0
        self.p_int = 0.0
        self.p_art = 0.0
        self.flow = 0.0
        self.flow_avg = 0.0
        self.sat_ven_o2 = 0.0
        self.sat_postoxy_o2 = 0.0
        self.pco2_postoxy = 0.0
        self.tubing_in_res = 1000
        self.tubing_in_vol = 0.1
        self.tubing_out_res = 1000
        self.tubing_out_vol = 0.1
        self.drainage_res = (self.drainage_cannulas.get(self.drainage_cannula_type) or {}).get("resistance", 1000)
        self.return_res = (self.return_cannulas.get(self.return_cannula_type) or {}).get("resistance", 1000)

        self.prev_fio2 = 0.0
        self.prev_fico2 = 0.0
        self.prev_gas_flow = 0.0
        self.pressure_avg_window = 400
        self.flow_avg_window = 400
        self._update_interval = 0.015
        self._update_counter = 0.0
        self._blood_comp_interval = 1.0
        self._blood_comp_counter = 0.0
        self._flow_avg_calculator = RealTimeMovingAverage(self.flow_avg_window)
        self._p_ven_avg_calculator = RealTimeMovingAverage(self.pressure_avg_window)
        self._p_int_avg_calculator = RealTimeMovingAverage(self.pressure_avg_window)
        self._p_art_avg_calculator = RealTimeMovingAverage(self.pressure_avg_window)

        self._ecls_drainage = None
        self._ecls_tubing_in = None
        self._ecls_pump = None
        self._ecls_oxy = None
        self._ecls_tubing_out = None
        self._ecls_return = None
        self._ecls_gas_source = None
        self._ecls_gas_oxy = None
        self._ecls_gas_out = None
        self._ecls_gas_insp_valve = None
        self._ecls_gasex = None

    def calc_model(self):
        if not self.ecls_running:
            self.flow = 0.0
            self.flow_avg = 0.0
            self.p_ven = 0.0
            self.p_int = 0.0
            self.p_art = 0.0
            self._flow_avg_calculator.reset()
            self._p_ven_avg_calculator.reset()
            self._p_int_avg_calculator.reset()
            self._p_art_avg_calculator.reset()
            self._blood_comp_counter = 0.0
            return

        self._blood_comp_counter += self._t
        self._update_counter += self._t
        if self._update_counter > self._update_interval:
            self._update_counter = 0.0

            newWindow = max(1, int(self.flow_avg_window))
            if newWindow != self._flow_avg_calculator.windowSize:
                self._flow_avg_calculator = RealTimeMovingAverage(newWindow)

            newPressureWindow = max(1, int(self.pressure_avg_window))
            if newPressureWindow != self._p_ven_avg_calculator.windowSize:
                self._p_ven_avg_calculator = RealTimeMovingAverage(newPressureWindow)
                self._p_int_avg_calculator = RealTimeMovingAverage(newPressureWindow)
                self._p_art_avg_calculator = RealTimeMovingAverage(newPressureWindow)

            models = self._model_engine.models
            self._ecls_drainage = models["ECLS_DRAINAGE"]
            self._ecls_tubing_in = models["ECLS_TUBING_IN"]
            self._ecls_pump = models["ECLS_PUMP"]
            self._ecls_oxy = models["ECLS_OXY"]
            self._ecls_tubing_out = models["ECLS_TUBING_OUT"]
            self._ecls_return = models["ECLS_RETURN"]
            self._ecls_gas_source = models["ECLS_GAS_SOURCE"]
            self._ecls_gas_oxy = models["ECLS_GAS_OXY"]
            self._ecls_gas_out = models["ECLS_GAS_OUT"]
            self._ecls_gas_insp_valve = models["ECLS_GAS_INSP_VALVE"]
            self._ecls_gasex = models["ECLS_GASEX"]

            self._ecls_drainage.comp_from = self.drainage_site
            self._ecls_return.comp_to = self.return_site

            sel_drainage = self.drainage_cannulas.get(self.drainage_cannula_type)
            if sel_drainage:
                self.drainage_res = sel_drainage["resistance"]
                self.drainage_cannula_diameter = sel_drainage["inner_diameter"]
                self.drainage_cannula_length = sel_drainage["length"]

            sel_return = self.return_cannulas.get(self.return_cannula_type)
            if sel_return:
                self.return_res = sel_return["resistance"]
                self.return_cannula_diameter = sel_return["inner_diameter"]
                self.return_cannula_length = sel_return["length"]

            self._ecls_drainage.is_enabled = self.ecls_running
            self._ecls_tubing_in.is_enabled = self.ecls_running
            self._ecls_pump.is_enabled = self.ecls_running
            self._ecls_oxy.is_enabled = self.ecls_running
            self._ecls_tubing_out.is_enabled = self.ecls_running
            self._ecls_return.is_enabled = self.ecls_running
            self._ecls_gas_source.is_enabled = self.ecls_running
            self._ecls_gas_oxy.is_enabled = self.ecls_running
            self._ecls_gas_out.is_enabled = self.ecls_running
            self._ecls_gas_insp_valve.is_enabled = self.ecls_running
            self._ecls_gasex.is_enabled = self.ecls_running

            self._ecls_drainage.no_flow = self.ecls_clamped
            self._ecls_tubing_in.no_flow = self.ecls_clamped
            self._ecls_pump.no_flow = self.ecls_clamped
            self._ecls_oxy.no_flow = self.ecls_clamped
            self._ecls_tubing_out.no_flow = self.ecls_clamped
            self._ecls_return.no_flow = self.ecls_clamped
            self._ecls_gasex.is_enabled = not self.ecls_clamped

            self._ecls_drainage.r_for = self.drainage_res * self.drainage_res_factor
            self._ecls_drainage.r_back = self.drainage_res * self.drainage_res_factor
            self._ecls_tubing_in.r_for = self.tubing_in_res * self.tubing_res_factor
            self._ecls_tubing_in.r_back = self.tubing_in_res * self.tubing_res_factor
            self._ecls_pump.r_for = self.pump_res_for * self.pump_res_factor
            self._ecls_pump.r_back = self.pump_res_back * self.pump_res_factor
            self._ecls_oxy.r_for = self.oxy_res_for * self.oxy_res_factor
            self._ecls_oxy.r_back = self.oxy_res_back * self.oxy_res_factor
            self._ecls_tubing_out.r_for = self.tubing_out_res * self.tubing_res_factor
            self._ecls_tubing_out.r_back = self.tubing_out_res * self.tubing_res_factor
            self._ecls_return.r_for = self.return_res * self.return_res_factor
            self._ecls_return.r_back = self.return_res * self.return_res_factor

            if self.prev_fio2 != self.gas_fio2 or self.prev_fico2 != self.gas_fico2:
                calc_gas_composition(self._ecls_gas_source, self.gas_fio2, self.gas_temp, self.gas_humidity, self.gas_fico2)
                self.prev_fio2 = self.gas_fio2
                self.prev_fico2 = self.gas_fico2

            if self.prev_gas_flow != self.gas_flow:
                res = (self._ecls_gas_source.pres - self._ecls_gas_out.pres) / (self.gas_flow / 60.0)
                if res > 60:
                    self._ecls_gas_insp_valve.r_for = res - 50
                self.prev_gas_flow = self.gas_flow

            self._ecls_gasex.dif_o2 = self.dif_o2
            self._ecls_gasex.dif_co2 = self.dif_co2

            self.pump_pressure = -self.pump_rpm / 25.0
            self._ecls_pump.pump_rpm = self.pump_rpm
            if self.pump_mode == 0:
                self._ecls_pump.p1_ext = 0.0
                self._ecls_pump.p2_ext = self.pump_pressure
            else:
                self._ecls_oxy.p1_ext = self.pump_pressure
                self._ecls_oxy.p2_ext = 0.0

            p_ven_raw = self._ecls_tubing_in.pres
            p_int_raw = self._ecls_pump.pres
            p_art_raw = self._ecls_tubing_out.pres
            self.p_ven = self._p_ven_avg_calculator.addValue(p_ven_raw)
            self.p_int = self._p_int_avg_calculator.addValue(p_int_raw)
            self.p_art = self._p_art_avg_calculator.addValue(p_art_raw)
            self.flow = self._ecls_return.flow * 60.0
            self.flow_avg = self._flow_avg_calculator.addValue(self.flow)

            if self._blood_comp_counter >= self._blood_comp_interval:
                self._blood_comp_counter -= self._blood_comp_interval
                calc_blood_composition(self._ecls_tubing_in)
                calc_blood_composition(self._ecls_tubing_out)
                self.sat_ven_o2 = self._ecls_tubing_in.so2
                self.sat_postoxy_o2 = self._ecls_tubing_out.so2
                self.pco2_postoxy = self._ecls_tubing_out.pco2
