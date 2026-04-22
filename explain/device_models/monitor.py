"""Monitor — port of src/explain/device_models/Monitor.js

Per-beat hemodynamic monitor. Collects min/max pressures and accumulated
flows over the heartbeat. At the rising edge of ncc_ventricular=1 it
computes ABP/PAP systolic/diastolic/mean, EDV/ESV/SV, and cardiac outputs
(LVO/RVO, regional flows). Uses rolling lists for heartrate, EDV, ESV,
saturations.
"""

from __future__ import annotations

from ..base_model import BaseModelClass


class Monitor(BaseModelClass):
    model_type = "Monitor"

    model_interface = [
        {"target": "description", "type": "string", "build_prop": True, "readonly": True},
        {"target": "is_enabled", "type": "boolean", "build_prop": True, "caption": "enabled"},
    ]

    def __init__(self, model_ref, name: str = ""):
        super().__init__(model_ref, name)

        self.hr_avg_beats = 5.0
        self.flow_avg_beats = 1.0
        self.rr_avg_time = 20.0
        self.sat_avg_time = 5.0
        self.sat_sampling_interval = 1.0
        self.heart = "Heart"
        self.lv = "LV"
        self.rv = "RV"
        self.ascending_aorta = "AA"
        self.descending_aorta = "AD"
        self.pulm_artery = "PA"
        self.right_atrium_ivci = "RAIVCI"
        self.right_atrium_svc = "RASVC"
        self.right_atrium = ""  # JS leaves undefined but reads via init
        self.breathing = "Breathing"
        self.ventilator = "Ventilator"
        self.aortic_valve = "LV_AA"
        self.pulm_valve = "RV_PA"
        self.aa_cor = "AA_COR"
        self.aa_brain = "AA_BR"
        self.ad_kid = "AD_KID_ART"
        self.ad_ls = "AD_LS"
        self.ad_int = "AD_INT"
        self.ad_rlb = "AD_RLB"
        self.ivc_ra = "IVCI_RAIVCI"
        self.svc_ra = "SVC_RASVC"
        self.thorax = "THORAX"
        self.deadspace = "DS"
        self.fo_ivci = "LA_RAIVCI"
        self.fo_svc = "LA_RASVC"
        self.da = "AAR_DA"
        self.vsd = "VSD"
        self.ips = "IPS"
        self.ua = "AD_UMB_ART"
        self.uv = "UMB_VEN_IVCI"

        self.heart_rate = 0.0
        self.heart_rate_btb = 0.0
        self.resp_rate = 0.0
        self.resp_rate_btb = 0.0
        self.abp_pre_syst = 0.0
        self.abp_pre_diast = 0.0
        self.abp_pre_mean = 0.0
        self.abp_post_syst = 0.0
        self.abp_post_diast = 0.0
        self.abp_post_mean = 0.0
        self.pap_syst = 0.0
        self.pap_diast = 0.0
        self.pap_mean = 0.0
        self.edv_lv = 0.0
        self.esv_lv = 0.0
        self.edp_lv = 0.0
        self.esp_lv = 0.0
        self.edv_rv = 0.0
        self.esv_rv = 0.0
        self.edp_rv = 0.0
        self.esp_rv = 0.0
        self.cvp_ivci = 0.0
        self.cvp_svc = 0.0
        self.sao2_pre = 0.0
        self.sao2_post = 0.0
        self.svo2_ivci = 0.0
        self.svo2_svc = 0.0
        self.etco2 = 0.0
        self.temp = 0.0
        self.co = 0.0
        self.ci = 0.0
        self.lvo = 0.0
        self.rvo = 0.0
        self.lv_sv = 0.0
        self.rv_sv = 0.0
        self.ivc_flow = 0.0
        self.svc_flow = 0.0
        self.cor_flow = 0.0
        self.brain_flow = 0.0
        self.kid_flow = 0.0
        self.ls_flow = 0.0
        self.int_flow = 0.0
        self.rlb_flow = 0.0
        self.da_flow = 0.0
        self.fo = 0.0
        self.fo_ivci_flow = 0.0
        self.fo_svc_flow = 0.0
        self.fo_flow = 0.0
        self.vsd_flow = 0.0
        self.ips_flow = 0.0
        self.ua_flow = 0.0
        self.uv_flow = 0.0
        self.fio2 = 0.0
        self.pip = 0.0
        self.p_plat = 0.0
        self.peep = 0.0
        self.tidal_volume = 0.0
        self.ph = 0.0
        self.po2 = 0.0
        self.pco2 = 0.0
        self.hco3 = 0.0
        self.be = 0.0
        self.dps = 0.0
        self.do2_br = 0.0
        self.do2_lb = 0.0

        self.ecg_signal = 0.0
        self.abp_signal = 0.0
        self.pap_signal = 0.0
        self.cvp_signal = 0.0
        self.sao2_pre_signal = 0.0
        self.sao2_post_signal = 0.0
        self.sao2_signal = 0.0
        self.resp_signal = 0.0
        self.co2_signal = 0.0

        self._heart = None
        self._lv = None
        self._rv = None
        self._ra = None
        self._breathing = None
        self._ventilator = None
        self._aa = None
        self._ad = None
        self._ra_ivci = None
        self._ra_svc = None
        self._pa = None
        self._ds = None
        self._thorax = None
        self._lv_aa = None
        self._rv_pa = None
        self._ivc_ra = None
        self._svc_ra = None
        self._aa_cor = None
        self._aa_br = None
        self._ad_kid = None
        self._ad_ls = None
        self._ad_int = None
        self._ad_rlb = None
        self._ad_umb_art = None
        self._umb_ven_ivci = None
        self._fo_ivci = None
        self._fo_svc = None
        self._da = None
        self._vsd = None
        self._ips = None

        self._temp_aa_pres_max = -1000.0
        self._temp_aa_pres_min = 1000.0
        self._temp_ad_pres_max = -1000.0
        self._temp_ad_pres_min = 1000.0
        self._temp_ra_ivci_pres_max = -1000.0
        self._temp_ra_ivci_pres_min = 1000.0
        self._temp_ra_svc_pres_max = -1000.0
        self._temp_ra_svc_pres_min = 1000.0
        self._temp_pa_pres_max = -1000.0
        self._temp_pa_pres_min = 1000.0
        self._temp_lv_pres_max = -1000.0
        self._temp_lv_pres_min = 1000.0
        self._temp_rv_pres_max = -1000.0
        self._temp_rv_pres_min = 1000.0
        self._temp_lv_vol_max = -1000.0
        self._temp_lv_vol_min = 1000.0
        self._temp_rv_vol_max = -1000.0
        self._temp_rv_vol_min = 1000.0
        self._lvo_counter = 0.0
        self._rvo_counter = 0.0
        self._cor_flow_counter = 0.0
        self._ivc_flow_counter = 0.0
        self._svc_flow_counter = 0.0
        self._brain_flow_counter = 0.0
        self._kid_flow_counter = 0.0
        self._ls_flow_counter = 0.0
        self._int_flow_counter = 0.0
        self._rlb_flow_counter = 0.0
        self._da_flow_counter = 0.0
        self._fo_ivci_flow_counter = 0.0
        self._fo_svc_flow_counter = 0.0
        self._vsd_flow_counter = 0.0
        self._ips_flow_counter = 0.0
        self._ua_flow_counter = 0.0
        self._uv_flow_counter = 0.0
        self._hr_list = []
        self._hr_sum = 0.0
        self._edv_lv_list = []
        self._edv_lv_sum = 0.0
        self._edv_rv_list = []
        self._edv_rv_sum = 0.0
        self._esv_lv_list = []
        self._esv_lv_sum = 0.0
        self._esv_rv_list = []
        self._esv_rv_sum = 0.0
        self._edp_lv_list = []
        self._edp_rv_list = []
        self._rr_list = []
        self._sao2_list = []
        self._sao2_pre_list = []
        self._sao2_ven_list = []
        self._rr_avg_counter = 0.0
        self._sat_avg_counter = 0.0
        self._sat_sampling_counter = 0.0
        self._beats_counter = 0
        self._beats_time = 0.0
        self._qrs_interval_counter = 0.0
        self._qrs_interval_counter_factor = 1.0
        self._rr_update_counter = 0.0

    def init_model(self, args):
        for arg in args:
            setattr(self, arg["key"], arg["value"])

        m = self._model_engine.models
        self._heart = m.get(self.heart)
        self._lv = m.get(self.lv)
        self._rv = m.get(self.rv)
        self._ra = m.get(self.right_atrium)
        self._ra_ivci = m.get(self.right_atrium_ivci)
        self._ra_svc = m.get(self.right_atrium_svc)
        self._breathing = m.get(self.breathing)
        self._ventilator = m.get(self.ventilator)
        self._ds = m.get(self.deadspace)
        self._thorax = m.get(self.thorax)
        self._aa = m.get(self.ascending_aorta)
        self._ad = m.get(self.descending_aorta)
        self._pa = m.get(self.pulm_artery)
        self._lv_aa = m.get(self.aortic_valve)
        self._rv_pa = m.get(self.pulm_valve)
        self._ivc_ra = m.get(self.ivc_ra)
        self._svc_ra = m.get(self.svc_ra)
        self._aa_cor = m.get(self.aa_cor)
        self._aa_br = m.get(self.aa_brain)
        self._ad_kid = m.get(self.ad_kid)
        self._ad_ls = m.get(self.ad_ls)
        self._ad_int = m.get(self.ad_int)
        self._ad_rlb = m.get(self.ad_rlb)
        self._da = m.get(self.da)
        self._fo_ivci = m.get(self.fo_ivci)
        self._fo_svc = m.get(self.fo_svc)
        self._vsd = m.get(self.vsd)
        self._ips = m.get(self.ips)
        self._ad_umb_art = m.get(self.ua)
        self._umb_ven_ivci = m.get(self.uv)
        self._rr_update_counter = 0.0

        self._is_initialized = True

    def calc_avg_heartrate(self, hr):
        self._hr_list.append(hr)
        self._hr_sum += hr

        if hr < 80:
            self.hr_avg_beats = 4.0
        else:
            self.hr_avg_beats = 12.0
        if len(self._hr_list) > self.hr_avg_beats:
            removed_hr = self._hr_list.pop(0)
            self._hr_sum -= removed_hr

        self.heart_rate = self._hr_sum / len(self._hr_list)

    def calc_model(self):
        self.collect_pressures()
        self.collect_blood_flows()
        self.collect_signals()

        self.temp = self._aa.temp
        self.etco2 = self._ventilator.etco2

        if self._heart.ncc_ventricular == 1:
            self.heart_rate_btb = 60.0 / self._qrs_interval_counter if self._qrs_interval_counter > 0 else 0
            self._qrs_interval_counter = 0.0
            self._qrs_interval_counter_factor = 1.0
            self.calc_avg_heartrate(self.heart_rate_btb)

        if self._qrs_interval_counter > 1 * self._qrs_interval_counter_factor:
            self.heart_rate_btb = 60 / self._qrs_interval_counter
            self._qrs_interval_counter_factor += 1
            self.calc_avg_heartrate(self.heart_rate_btb)
        self.heart_rate = self.heart_rate_btb

        if self._rr_update_counter > 0.015:
            self._rr_update_counter = 0.0
            self.resp_rate = self._breathing.resp_rate_measured
        self._rr_update_counter += self._t

        if self._heart.ncc_ventricular == 1:
            self._beats_counter += 1
            if self._aa:
                self.abp_pre_syst = self._temp_aa_pres_max
                self.abp_pre_diast = self._temp_aa_pres_min
                self.abp_pre_mean = (2 * self._temp_aa_pres_min + self._temp_aa_pres_max) / 3.0
                self._temp_aa_pres_max = -1000.0
                self._temp_aa_pres_min = 1000.0
            if self._ad:
                self.abp_post_syst = self._temp_ad_pres_max
                self.abp_post_diast = self._temp_ad_pres_min
                self.abp_post_mean = (2 * self._temp_ad_pres_min + self._temp_ad_pres_max) / 3.0
                self._temp_ad_pres_max = -1000.0
                self._temp_ad_pres_min = 1000.0
            if self._ra_ivci:
                self.cvp_ivci = (2 * self._temp_ra_ivci_pres_min + self._temp_ra_ivci_pres_max) / 3.0
                self._temp_ra_ivci_pres_max = -1000.0
                self._temp_ra_ivci_pres_min = 1000.0
            if self._ra_svc:
                self.cvp_svc = (2 * self._temp_ra_svc_pres_min + self._temp_ra_svc_pres_max) / 3.0
                self._temp_ra_svc_pres_max = -1000.0
                self._temp_ra_svc_pres_min = 1000.0

            if self._pa:
                self.pap_syst = self._temp_pa_pres_max
                self.pap_diast = self._temp_pa_pres_min
                self.pap_mean = (2 * self._temp_pa_pres_min + self._temp_pa_pres_max) / 3.0
                self._temp_pa_pres_max = -1000.0
                self._temp_pa_pres_min = 1000.0
            if self._lv:
                edv_lv_value = self._temp_lv_vol_max * 1000.0
                edv_rv_value = self._temp_rv_vol_max * 1000.0
                esv_lv_value = self._temp_lv_vol_min * 1000.0
                esv_rv_value = self._temp_rv_vol_min * 1000.0

                self._edv_lv_list.append(edv_lv_value)
                self._edv_rv_list.append(edv_rv_value)
                self._esv_lv_list.append(esv_lv_value)
                self._esv_rv_list.append(esv_rv_value)

                self._edv_lv_sum += edv_lv_value
                self._edv_rv_sum += edv_rv_value
                self._esv_lv_sum += esv_lv_value
                self._esv_rv_sum += esv_rv_value

                self.edv_lv = self._edv_lv_sum / len(self._edv_lv_list)
                self.edv_rv = self._edv_rv_sum / len(self._edv_rv_list)
                self.esv_lv = self._esv_lv_sum / len(self._esv_lv_list)
                self.esv_rv = self._esv_rv_sum / len(self._esv_rv_list)

                self.lv_sv = self.edv_lv - self.esv_lv
                self.rv_sv = self.edv_rv - self.esv_rv

                if len(self._edv_lv_list) > self.hr_avg_beats:
                    self._edv_lv_sum -= self._edv_lv_list.pop(0)
                    self._edv_rv_sum -= self._edv_rv_list.pop(0)
                    self._esv_lv_sum -= self._esv_lv_list.pop(0)
                    self._esv_rv_sum -= self._esv_rv_list.pop(0)

                self.edp_lv = self._temp_lv_pres_min
                self.esp_lv = self._temp_lv_pres_max
                self.edp_rv = self._temp_rv_pres_min
                self.esp_rv = self._temp_rv_pres_max

                self._temp_lv_pres_max = -1000
                self._temp_lv_pres_min = 1000
                self._temp_rv_pres_max = -1000
                self._temp_rv_pres_min = 1000
                self._temp_lv_vol_max = -1000
                self._temp_lv_vol_min = 1000
                self._temp_rv_vol_max = -1000
                self._temp_rv_vol_min = 1000

        if self._beats_counter > self.flow_avg_beats:
            if self._lv_aa:
                self.lvo = (self._lvo_counter / self._beats_time) * 60.0
                self._lvo_counter = 0.0
            if self._rv_pa:
                self.rvo = (self._rvo_counter / self._beats_time) * 60.0
                self._rvo_counter = 0.0
            if self._ivc_ra:
                self.ivc_flow = (self._ivc_flow_counter / self._beats_time) * 60.0
                self._ivc_flow_counter = 0.0
            if self._svc_ra:
                self.svc_flow = (self._svc_flow_counter / self._beats_time) * 60.0
                self._svc_flow_counter = 0.0
            if self._aa_cor:
                self.cor_flow = (self._cor_flow_counter / self._beats_time) * 60.0
                self._cor_flow_counter = 0.0
            if self._aa_br:
                self.brain_flow = (self._brain_flow_counter / self._beats_time) * 60.0
                self._brain_flow_counter = 0.0
                self.do2_br = self.brain_flow * self._aa.to2 * 22.4
            if self._ad_kid:
                self.kid_flow = (self._kid_flow_counter / self._beats_time) * 60.0
                self._kid_flow_counter = 0.0
                self.do2_lb = self.kid_flow * 4 * self._ad.to2 * 22.4
            if self._ad_ls:
                self.ls_flow = (self._ls_flow_counter / self._beats_time) * 60.0
                self._ls_flow_counter = 0.0
            if self._ad_int:
                self.int_flow = (self._int_flow_counter / self._beats_time) * 60.0
                self._int_flow_counter = 0.0
            if self._ad_rlb:
                self.rlb_flow = (self._rlb_flow_counter / self._beats_time) * 60.0
                self._rlb_flow_counter = 0.0
            if self._da:
                self.da_flow = (self._da_flow_counter / self._beats_time) * 60.0
                self._da_flow_counter = 0.0
            if self._fo_ivci and self._fo_svc:
                self.fo_ivci_flow = (self._fo_ivci_flow_counter / self._beats_time) * 60.0
                self._fo_ivci_flow_counter = 0.0
                self.fo_svc_flow = (self._fo_svc_flow_counter / self._beats_time) * 60.0
                self._fo_svc_flow_counter = 0.0
                self.fo_flow = self.fo_ivci_flow + self.fo_svc_flow
            if self._vsd:
                self.vsd_flow = (self._vsd_flow_counter / self._beats_time) * 60.0
                self._vsd_flow_counter = 0.0
            if self._ips:
                self.ips_flow = (self._ips_flow_counter / self._beats_time) * 60.0
                self._ips_flow_counter = 0.0
            if self._ad_umb_art:
                self.ua_flow = (self._ua_flow_counter / self._beats_time) * 60.0
                self._ua_flow_counter = 0.0
            if self._umb_ven_ivci:
                self.uv_flow = (self._uv_flow_counter / self._beats_time) * 60.0
                self._uv_flow_counter = 0.0

            self._beats_counter = 0
            self._beats_time = 0.0

        self._qrs_interval_counter += self._t
        self._beats_time += self._t

        self.sao2_pre = self._aa.so2
        self.sao2_post = self._ad.so2

        self.svo2_ivci = self._ra_ivci.so2 if self._ra_ivci else 0.0
        self.svo2_svc = self._ra_svc.so2 if self._ra_svc else 0.0

    def collect_signals(self):
        self.ecg_signal = self._heart.ecg_signal if self._heart else 0.0
        self.resp_signal = self._thorax.vol if self._thorax else 0.0
        self.sao2_pre_signal = self._aa.pres_in if self._aa else 0.0
        self.sao2_post_signal = self._ad.pres_in if self._ad else 0.0
        self.abp_signal = self._ad.pres_in if self._ad else 0.0
        self.pap_signal = self._pa.pres_in if self._pa else 0.0
        self.cvp_signal = self._ra_ivci.pres_in if self._ra_ivci else 0.0
        self.co2_signal = self._ventilator.co2 if self._ventilator else 0.0

    def collect_pressures(self):
        if self._aa:
            self._temp_aa_pres_max = max(self._temp_aa_pres_max, self._aa.pres_in)
            self._temp_aa_pres_min = min(self._temp_aa_pres_min, self._aa.pres_in)
        if self._lv:
            self._temp_lv_pres_max = max(self._temp_lv_pres_max, self._lv.pres_in)
            self._temp_lv_pres_min = min(self._temp_lv_pres_min, self._lv.pres_in)
        if self._rv:
            self._temp_rv_pres_max = max(self._temp_rv_pres_max, self._rv.pres_in)
            self._temp_rv_pres_min = min(self._temp_rv_pres_min, self._rv.pres_in)
        if self._lv:
            self._temp_lv_vol_max = max(self._temp_lv_vol_max, self._lv.vol)
            self._temp_lv_vol_min = min(self._temp_lv_vol_min, self._lv.vol)
        if self._rv:
            self._temp_rv_vol_max = max(self._temp_rv_vol_max, self._rv.vol)
            self._temp_rv_vol_min = min(self._temp_rv_vol_min, self._rv.vol)
        if self._ad:
            self._temp_ad_pres_max = max(self._temp_ad_pres_max, self._ad.pres_in)
            self._temp_ad_pres_min = min(self._temp_ad_pres_min, self._ad.pres_in)
        if self._ra_ivci:
            self._temp_ra_ivci_pres_max = max(self._temp_ra_ivci_pres_max, self._ra_ivci.pres_in)
            self._temp_ra_ivci_pres_min = min(self._temp_ra_ivci_pres_min, self._ra_ivci.pres_in)
        if self._ra_svc:
            self._temp_ra_svc_pres_max = max(self._temp_ra_svc_pres_max, self._ra_svc.pres_in)
            self._temp_ra_svc_pres_min = min(self._temp_ra_svc_pres_min, self._ra_svc.pres_in)
        if self._pa:
            self._temp_pa_pres_max = max(self._temp_pa_pres_max, self._pa.pres_in)
            self._temp_pa_pres_min = min(self._temp_pa_pres_min, self._pa.pres_in)

    def collect_blood_flows(self):
        self._lvo_counter += self._lv_aa.flow * self._t if self._lv_aa else 0.0
        self._rvo_counter += self._rv_pa.flow * self._t if self._rv_pa else 0.0
        self._cor_flow_counter += self._aa_cor.flow * self._t if self._aa_cor else 0.0
        self._ivc_flow_counter += self._ivc_ra.flow * self._t if self._ivc_ra else 0.0
        self._svc_flow_counter += self._svc_ra.flow * self._t if self._svc_ra else 0.0
        self._brain_flow_counter += self._aa_br.flow * self._t if self._aa_br else 0.0
        self._kid_flow_counter += self._ad_kid.flow * self._t if self._ad_kid else 0.0
        self._ls_flow_counter += self._ad_ls.flow * self._t if self._ad_ls else 0.0
        self._int_flow_counter += self._ad_int.flow * self._t if self._ad_int else 0.0
        self._rlb_flow_counter += self._ad_rlb.flow * self._t if self._ad_rlb else 0.0
        self._da_flow_counter += self._da.flow * self._t if self._da else 0.0
        self._fo_ivci_flow_counter += self._fo_ivci.flow * self._t if self._fo_ivci else 0.0
        self._fo_svc_flow_counter += self._fo_svc.flow * self._t if self._fo_svc else 0.0
        self._vsd_flow_counter += self._vsd.flow * self._t if self._vsd else 0.0
        self._ips_flow_counter += self._ips.flow * self._t if self._ips else 0.0
        self._ua_flow_counter += self._ad_umb_art.flow * self._t if self._ad_umb_art else 0.0
        self._uv_flow_counter += self._umb_ven_ivci.flow * self._t if self._umb_ven_ivci else 0.0
