"""Heart — port of src/explain/component_models/Heart.js

Top-level cardiac model. Owns the cardiac-cycle state machine, the sinus-node
timing, the PQ/AV/QRS/QT phase timers, the ECG gaussian-pulse generator, and
the contraction/relaxation activation curves. Pushes per-step `act_factor`,
`ans_sens`, `ans_activity` values onto the connected chamber models (by name
lookup in `self._model_engine.models`) each step. Also provides
externally-callable helpers for scaling pericardial stiffness and left/right
contractility/relaxation (`set_pericardium`, `set_contractillity`,
`set_relaxation`).

Faithfulness notes:
  - The JS method name `set_contractillity` (two Ls — a typo in the JS source)
    is preserved verbatim so JSON definitions and any dynamic callers that
    reference the method by name continue to resolve.
  - The ECG accumulator behaviour is JS-exact: `ecg_signal` accumulates
    Gaussian contributions during the PQ phase, holds its last value through
    AV/QRS/QT, and resets to 0 only when no phase is active.
  - All internal model references (`_la`, `_rv`, `_pc`, etc.) are initialised
    to None in `__init__` and bound by name lookup in `init_model`. In JS,
    reading an undefined property returns `undefined`; Python would
    AttributeError, so every reference the JS source uses is defaulted here.

This port produces an importable file with all methods present. Wiring it
into an actual cardiac scenario (with LA / LV / RA / RV / valves / pericardium
defined) is a separate step — untested here.
"""

from __future__ import annotations

import math

from ..base_model import BaseModelClass


class Heart(BaseModelClass):
    model_type = "Heart"

    # Metadata pruned to the essentials used by the engine (full UI interface
    # list from the JS source is omitted — it's informational only for the
    # editor layer, which this port does not serve).
    model_interface = [
        {"target": "description", "type": "string", "build_prop": True,
         "readonly": True, "caption": "description"},
        {"target": "is_enabled", "type": "boolean", "build_prop": True,
         "caption": "enabled"},
        {"target": "heart_rate_ref", "type": "number", "build_prop": True,
         "caption": "reference heart rate (bpm)"},
        {"target": "pq_time", "type": "number", "build_prop": True,
         "caption": "pq time (s)"},
        {"target": "qrs_time", "type": "number", "build_prop": True,
         "caption": "qrs time (s)"},
        {"target": "qt_time", "type": "number", "build_prop": True,
         "caption": "qt time (s)"},
        {"target": "av_delay", "type": "number", "build_prop": True,
         "caption": "av delay time (s)"},
        {"target": "ans_sens", "type": "number", "build_prop": True,
         "caption": "ans sensitivity"},
        {"target": "cont_factor_left", "type": "factor",
         "caption": "systolic function factor left"},
        {"target": "cont_factor_right", "type": "factor",
         "caption": "systolic function factor right"},
        {"target": "relax_factor_left", "type": "factor",
         "caption": "diastolic function factor left"},
        {"target": "relax_factor_right", "type": "factor",
         "caption": "diastolic function factor right"},
        {"target": "pc_el_factor", "type": "factor",
         "caption": "pericardial stiffness factor"},
        {"target": "pc_extra_volume", "type": "number", "build_prop": True,
         "caption": "pericardial fluid volume (L)"},
    ]

    def __init__(self, model_ref, name: str = ""):
        super().__init__(model_ref, name)

        # -----------------------------------------------
        # independent properties
        # -----------------------------------------------
        self.heart_rate_ref = 110.0
        self.pq_time = 0.1
        self.qrs_time = 0.075
        self.qt_time = 0.25
        self.av_delay = 0.0005
        self.ans_sens = 1.0
        self.ans_activity = 1.0
        self.ans_activity_hr = 1.0
        self.hr_factor = 1.0
        self.hr_override = False
        self.hr_mob_factor = 1.0
        self.hr_temp_factor = 1.0
        self.hr_drug_factor = 1.0

        self.cont_factor = 1.0
        self.cont_factor_left = 1.0
        self.cont_factor_right = 1.0
        self.cont_mob_factor = 1.0
        self.cont_drug_factor = 1.0

        self.relax_factor = 1.0
        self.relax_factor_left = 1.0
        self.relax_factor_right = 1.0
        self.relax_mob_factor = 1.0
        self.relax_drug_factor = 1.0

        self.pc_el_factor = 1.0
        self.pc_extra_volume = 0.0

        # -----------------------------------------------
        # dependent properties
        # -----------------------------------------------
        self.heart_rate = 120.0
        self.heart_rate_measured = 120
        self.cardiac_cycle_state = 0

        self.ecg_signal = 0.0
        self.ncc_ventricular = 0
        self.ncc_atrial = 0
        self.cardiac_cycle_running = 0
        self.cardiac_cycle_time = 0.353

        # chamber metrics
        self.lv_edv = 0.0
        self.lv_esv = 0.0
        self.lv_edp = 0.0
        self.lv_esp = 0.0
        self.lv_sp = 0.0
        self.lv_sv = 0.0
        self.lv_ef = 0.0

        self.rv_edv = 0.0
        self.rv_esv = 0.0
        self.rv_edp = 0.0
        self.rv_esp = 0.0
        self.rv_sp = 0.0
        self.rv_sv = 0.0
        self.rv_ef = 0.0

        self.ra_edv = 0.0
        self.ra_esv = 0.0
        self.ra_edp = 0.0
        self.ra_esp = 0.0
        self.ra_sp = 0.0

        self.la_edv = 0.0
        self.la_esv = 0.0
        self.la_edp = 0.0
        self.la_esp = 0.0
        self.la_sp = 0.0

        # -----------------------------------------------
        # local properties
        # -----------------------------------------------
        self._kn = 0.579
        self.prev_cardiac_cycle_running = 0
        self.prev_cardiac_cycle_state = 0
        self._temp_cardiac_cycle_time = 0.0
        self._sa_node_interval = 1.0
        self._sa_node_timer = 0.0
        self._av_delay_timer = 0.0
        self._pq_timer = 0.0
        self._pq_running = False
        self._av_delay_running = False
        self._qrs_timer = 0.0
        self._qrs_running = False
        self._ventricle_is_refractory = False
        self._qt_timer = 0.0
        self._qt_running = False

        # Internal chamber / valve / coronary / pericardium references.
        # All default to None and are re-bound in init_model. Python requires
        # them to exist as attributes before any method reads them.
        self._la = None
        self._lv = None
        self._ra = None
        self._ra_rv = None
        self._raivci = None
        self._raivci_rv = None
        self._rasvc = None
        self._rasvc_rv = None
        self._raivci_rasvc = None
        self._rv = None
        self._rv_pa = None
        self._rv_aa = None
        self._la_lv = None
        self._lv_aa = None
        self._lv_pa = None
        self._coronaries = None
        self._aa_cor = None
        self._cor_raivci = None
        self._cor_rasvc = None
        self._pc = None

        self._systole_running = False
        self._diastole_running = False

        self.prev_la_lv_flow = 0.0
        self.prev_lv_aa_flow = 0.0
        self.prev_cont_factor = 1.0
        self.prev_cont_factor_left = 1.0
        self.prev_cont_factor_right = 1.0

        self.prev_relax_factor = 1.0
        self.prev_relax_factor_left = 1.0
        self.prev_relax_factor_right = 1.0

        self.prev_pc_el_factor = 1.0
        self._hr_counter = 1
        self._hr_factor = 1

        self._update_counter_factors = 0.0
        self._update_interval_factors = 0.015

        # Activation factors / QTC are set in calc_* methods at first run;
        # initialised here so analyze() / external callers don't AttributeError
        # if they peek before the first calc_model tick.
        self.aaf = 0.0
        self.vaf = 0.0
        self.cqt_time = 0.0

    # -------------------------------------------------------------------------
    # init_model — resolve all model references by name (fallback to None)
    # -------------------------------------------------------------------------
    def init_model(self, args):
        super().init_model(args)

        models = self._model_engine.models

        # left atrial components (atrium and mitral valve)
        self._la = models.get("LA")
        self._la_lv = models.get("LA_LV")

        # right atrial components (atrium and tricuspid valve)
        self._ra = models.get("RA")
        self._ra_rv = models.get("RA_RV")

        # preferential flow models (not always present)
        self._raivci = models.get("RAIVCI")
        self._raivci_rv = models.get("RAIVCI_RV")
        self._rasvc = models.get("RASVC")
        self._rasvc_rv = models.get("RASVC_RV")
        self._raivci_rasvc = models.get("RAIVCI_RASVC")

        # right ventricular components (ventricle and pulmonary valve)
        self._rv = models.get("RV")
        self._rv_pa = models.get("RV_PA")

        # TGA or other congenital heart diseases may not have a normal connection
        self._rv_aa = models.get("RV_AA")

        # left ventricular components (ventricle and aortic valve)
        self._lv = models.get("LV")
        self._lv_aa = models.get("LV_AA")

        # TGA / congenital: LV_PA may not exist
        self._lv_pa = models.get("LV_PA")

        # coronary circulation (tried under two names — first "COR", then "CORONARIES")
        self._coronaries = models.get("COR") or models.get("CORONARIES")
        self._aa_cor = models.get("AA_COR")

        # preferential flow models (coronary-side)
        self._cor_raivci = models.get("COR_RAIVCI")
        self._cor_rasvc = models.get("COR_RASVC")

        # pericardium
        self._pc = models.get("PERICARDIUM")

    # -------------------------------------------------------------------------
    # analyze — captures hemodynamic metrics at cardiac-cycle state transitions
    # -------------------------------------------------------------------------
    def analyze(self):
        # systole -> diastole transition (end systolic capture)
        if self.prev_cardiac_cycle_state == 1 and self.cardiac_cycle_state == 0:
            self.lv_esv = self._lv.vol if self._lv else 0
            self.lv_esp = self._lv.pres_in if self._lv else 0

            self.la_esv = self._la.vol if self._la else 0
            self.la_esp = self._la.pres_in if self._la else 0

            self.rv_esv = self._rv.vol if self._rv else 0
            self.rv_esp = self._rv.pres_in if self._rv else 0

            self.ra_esv = (self._raivci.vol if self._raivci else 0) + (self._rasvc.vol if self._rasvc else 0)
            self.ra_esp = 0.5 * (
                (self._raivci.pres_in if self._raivci else 0)
                + (self._rasvc.pres_in if self._rasvc else 0)
            )

            if self._ra:
                self.ra_esv = self._ra.vol
                self.ra_esp = self._ra.pres_in

        # diastole -> systole transition (end diastolic capture + derived metrics)
        if self.prev_cardiac_cycle_state == 0 and self.cardiac_cycle_state == 1:
            self.lv_edv = self._lv.vol if self._lv else 0
            self.lv_esp = self._lv.pres_in if self._lv else 0

            self.la_edv = self._la.vol if self._la else 0
            self.la_esp = self._la.pres_in if self._la else 0

            self.rv_edv = self._rv.vol if self._rv else 0
            self.rv_esp = self._rv.pres_in if self._rv else 0

            self.ra_edv = (self._raivci.vol if self._raivci else 0) + (self._rasvc.vol if self._rasvc else 0)
            self.ra_esp = 0.5 * (
                (self._raivci.pres_in if self._raivci else 0)
                + (self._rasvc.pres_in if self._rasvc else 0)
            )

            if self._ra:
                self.ra_edv = self._ra.vol
                self.ra_esp = self._ra.pres_in

            # store derived parameters. JS semantics of `0/0 = NaN` are
            # preserved explicitly here: Python raises ZeroDivisionError where
            # JS silently produces NaN, so we check the divisor before dividing.
            # Happens naturally when a scenario has no right-heart chambers
            # (rv_edv stays at 0), or before the first full cardiac cycle
            # (lv_edv stays at 0 until the first end-diastolic capture).
            self.lv_sv = self.lv_edv - self.lv_esv
            self.rv_sv = self.rv_edv - self.rv_esv
            self.lv_ef = self.lv_sv / self.lv_edv if self.lv_edv != 0 else float("nan")
            self.rv_ef = self.rv_sv / self.rv_edv if self.rv_edv != 0 else float("nan")

    # -------------------------------------------------------------------------
    # calc_model — main per-step dispatch
    # -------------------------------------------------------------------------
    def calc_model(self):
        # Throttle factor propagation to every _update_interval_factors (15 ms).
        self._update_counter_factors += self._t
        if self._update_counter_factors > self._update_interval_factors:
            self._update_counter_factors = 0.0

            cont_left = self.cont_factor_left
            cont_right = self.cont_factor_right
            if cont_left != self.prev_cont_factor_left or cont_right != self.prev_cont_factor_right:
                self.set_contractillity(cont_left, cont_right)
            self.prev_cont_factor_left = cont_left
            self.prev_cont_factor_right = cont_right

            relax_left = self.relax_factor_left
            relax_right = self.relax_factor_right
            if relax_left != self.prev_relax_factor_left or relax_right != self.prev_relax_factor_right:
                self.set_relaxation(relax_left, relax_right)
            self.prev_relax_factor_left = relax_left
            self.prev_relax_factor_right = relax_right

            pc_el = self.pc_el_factor
            if pc_el != self.prev_pc_el_factor:
                self.set_pericardium(pc_el, self.pc_extra_volume)
            self.prev_pc_el_factor = pc_el

            # push pericardial fluid volume every throttle tick
            if self._pc:
                self._pc.vol_extra = self.pc_extra_volume

        # cache previous cycle state
        self.prev_cardiac_cycle_running = self.cardiac_cycle_running
        self.prev_cardiac_cycle_state = self.cardiac_cycle_state

        # mitral valve closes -> systole starts
        if self.prev_la_lv_flow > 0.0 and self._la_lv.flow <= 0.0:
            self._systole_running = True
        self.prev_la_lv_flow = self._la_lv.flow

        # aortic valve closes during systole -> systole ends
        if self._systole_running:
            if self.prev_lv_aa_flow > 0.0 and self._lv_aa.flow <= 0.0:
                self._systole_running = False
        self.prev_lv_aa_flow = self._lv_aa.flow

        # update cardiac-cycle state
        if self._systole_running:
            self.cardiac_cycle_state = 1
            self._diastole_running = False
        else:
            self.cardiac_cycle_state = 0
            self._diastole_running = True

        # heart rate from reference + additive factor contributions
        self.heart_rate = (
            self.heart_rate_ref
            + (self.ans_activity_hr - 1.0) * self.heart_rate_ref * self.ans_sens
            + (self.hr_factor - 1.0) * self.heart_rate_ref
            + (self.hr_mob_factor - 1.0) * self.heart_rate_ref
            + (self.hr_temp_factor - 1.0) * self.heart_rate_ref
            + (self.hr_drug_factor - 1.0) * self.heart_rate_ref
        )

        if self.hr_override:
            self.heart_rate = self.heart_rate_ref

        # heart-rate-dependent QTc
        self.cqt_time = self.calc_qtc(self.heart_rate)

        # sinus node interval
        self._sa_node_interval = 60.0 / self.heart_rate

        # sinus node fires: start PQ, reset atrial activation counter, start cycle
        if self._sa_node_timer > self._sa_node_interval:
            self._sa_node_timer = 0.0
            self._pq_running = True
            self.ncc_atrial = -1
            self.cardiac_cycle_running = 1
            self._temp_cardiac_cycle_time = 0.0

        # PQ timer elapsed: start AV-delay
        if self._pq_timer > self.pq_time:
            self._pq_timer = 0.0
            self._pq_running = False
            self._av_delay_running = True

        # AV-delay elapsed: fire QRS unless refractory
        if self._av_delay_timer > self.av_delay:
            self._av_delay_timer = 0.0
            self._av_delay_running = False

            if not self._ventricle_is_refractory:
                self._qrs_running = True
                self.ncc_ventricular = -1

        # QRS timer elapsed: start QT, mark refractory
        if self._qrs_timer > self.qrs_time:
            self._qrs_timer = 0.0
            self._qrs_running = False
            self._qt_running = True
            self._ventricle_is_refractory = True

        # QT timer elapsed: refractory ends, cycle ends
        if self._qt_timer > self.cqt_time:
            self._qt_timer = 0.0
            self._qt_running = False
            self._ventricle_is_refractory = False
            self.cardiac_cycle_running = 0
            self.cardiac_cycle_time = self._temp_cardiac_cycle_time

        # advance timers
        self._sa_node_timer += self._t

        if self.cardiac_cycle_running == 1:
            self._temp_cardiac_cycle_time += self._t

        if self._pq_running:
            self._pq_timer += self._t
            # ECG P-wave: Gaussian contribution during PQ phase.
            # Wave parameters from JS source: amp=0.05, center=pq_time/2, width=pq_time
            self.ecg_signal += self.gaussian(
                self._pq_timer, 0.05, self.pq_time / 2.0, self.pq_time
            )

        if self._av_delay_running:
            self._av_delay_timer += self._t

        if self._qrs_running:
            self._qrs_timer += self._t

        if self._qt_running:
            self._qt_timer += self._t

        # ECG signal only active during a phase; reset to 0 when idle
        if not self._pq_running and not self._av_delay_running and not self._qrs_running and not self._qt_running:
            self.ecg_signal = 0.0

        # measured heart rate: update when ventricle fires, or periodically
        # even when no contraction occurred for a while
        if self.ncc_ventricular == -1:
            self.heart_rate_measured = 60 / self._hr_counter
            self._hr_counter = 0.0
            self._hr_factor = 1.0

        if self._hr_counter > 1 * self._hr_factor:
            self.heart_rate_measured = 60 / self._hr_counter
            self._hr_factor += 1

        self._hr_counter += self._t

        # advance activation counters
        self.ncc_atrial += 1
        self.ncc_ventricular += 1

        # varying elastance / activation factors propagated to chambers
        self.calc_varying_elastance()

    # -------------------------------------------------------------------------
    # calc_varying_elastance — compute aaf / vaf and push onto chambers
    # -------------------------------------------------------------------------
    def calc_varying_elastance(self):
        # atrial activation factor (half-sine over PQ duration)
        _atrial_duration = self.pq_time / self._t
        if self.ncc_atrial >= 0 and self.ncc_atrial < _atrial_duration:
            self.aaf = math.sin(math.pi * (self.ncc_atrial / _atrial_duration))
        else:
            self.aaf = 0.0

        # ventricular activation factor (JS's skewed-sine with _kn=0.579)
        _ventricular_duration = (self.qrs_time + self.cqt_time) / self._t
        if self.ncc_ventricular >= 0 and self.ncc_ventricular < _ventricular_duration:
            self.vaf = (
                (self.ncc_ventricular / (self._kn * _ventricular_duration))
                * math.sin(math.pi * (self.ncc_ventricular / _ventricular_duration))
            )
        else:
            self.vaf = 0.0

        # Push ANS + activation factors onto connected chambers. Order and
        # conditional gates copied from JS verbatim.
        if self._raivci:
            self._raivci.ans_sens = self.ans_sens
            self._raivci.ans_activity = self.ans_activity
            self._raivci.act_factor = self.aaf
        if self._rasvc:
            self._rasvc.ans_sens = self.ans_sens
            self._rasvc.ans_activity = self.ans_activity
            self._rasvc.act_factor = self.aaf

        if self._rv:
            self._rv.ans_sens = self.ans_sens
            self._rv.ans_activity = self.ans_activity
            self._rv.act_factor = self.vaf

        if self._la:
            self._la.ans_sens = self.ans_sens
            self._la.ans_activity = self.ans_activity
            self._la.act_factor = self.aaf

        if self._ra:
            self._ra.ans_sens = self.ans_sens
            self._ra.ans_activity = self.ans_activity
            self._ra.act_factor = self.aaf

        if self._lv:
            self._lv.ans_sens = self.ans_sens
            self._lv.ans_activity = self.ans_activity
            self._lv.act_factor = self.vaf

        if self._coronaries:
            self._coronaries.act_factor = self.vaf

        # capture hemodynamic transitions
        self.analyze()

    # -------------------------------------------------------------------------
    # calc_qtc — Bazett's formula with a low-HR guard
    # -------------------------------------------------------------------------
    def calc_qtc(self, hr):
        if hr > 10.0:
            return self.qt_time * math.sqrt(60.0 / hr)
        return self.qt_time * 2.449

    # -------------------------------------------------------------------------
    # set_pericardium — incremental adjustment of pericardial elastance factor
    # -------------------------------------------------------------------------
    def set_pericardium(self, new_el_factor, new_volume):
        # skip entirely if no pericardium configured
        if not self._pc:
            return

        f_pc_el = self._pc.el_base_factor_ps
        delta = new_el_factor - self.prev_pc_el_factor

        # clamp to non-negative
        f_pc_el = max(f_pc_el + delta, 0)

        self._pc.el_base_factor_ps = f_pc_el

    # -------------------------------------------------------------------------
    # set_contractillity — incremental adjustment of chamber el_max_factor_ps.
    #
    # The method name preserves the JS typo (two Ls) so external callers that
    # reference it by name continue to resolve.
    # -------------------------------------------------------------------------
    def set_contractillity(self, new_cont_factor_left, new_cont_factor_right):
        # pull current persistent systolic factors; use 0 for chambers that
        # are not configured (matches the JS `? : 0` guards).
        f_ps_la = self._la.el_max_factor_ps
        f_ps_lv = self._lv.el_max_factor_ps
        f_ps_raivc = self._raivci.el_max_factor_ps if self._raivci else 0
        f_ps_rasvc = self._rasvc.el_max_factor_ps if self._rasvc else 0
        f_ps_ra = self._ra.el_max_factor_ps if self._ra else 0
        f_ps_rv = self._rv.el_max_factor_ps

        delta_left = new_cont_factor_left - self.prev_cont_factor_left
        delta_right = new_cont_factor_right - self.prev_cont_factor_right

        f_ps_la = max(f_ps_la + delta_left, 0)
        f_ps_lv = max(f_ps_lv + delta_left, 0)
        f_ps_raivc = max(f_ps_raivc + delta_right, 0)
        f_ps_rasvc = max(f_ps_rasvc + delta_right, 0)
        f_ps_ra = max(f_ps_ra + delta_right, 0)
        f_ps_rv = max(f_ps_rv + delta_right, 0)

        self._la.el_max_factor_ps = f_ps_la
        self._lv.el_max_factor_ps = f_ps_lv
        if self._raivci:
            self._raivci.el_max_factor_ps = f_ps_raivc
        if self._rasvc:
            self._rasvc.el_max_factor_ps = f_ps_rasvc
        if self._ra:
            self._ra.el_max_factor_ps = f_ps_ra
        self._rv.el_max_factor_ps = f_ps_rv

        self.cont_factor_left = new_cont_factor_left
        self.cont_factor_right = new_cont_factor_right

    # -------------------------------------------------------------------------
    # set_relaxation — incremental adjustment of chamber el_min_factor_ps
    # -------------------------------------------------------------------------
    def set_relaxation(self, new_relax_factor_left, new_relax_factor_right):
        f_ps_la = self._la.el_min_factor_ps
        f_ps_lv = self._lv.el_min_factor_ps
        f_ps_raivc = self._raivci.el_min_factor_ps if self._raivci else 0
        f_ps_rasvc = self._rasvc.el_min_factor_ps if self._rasvc else 0
        f_ps_ra = self._ra.el_min_factor_ps if self._ra else 0
        f_ps_rv = self._rv.el_min_factor_ps

        delta_left = new_relax_factor_left - self.prev_relax_factor_left
        delta_right = new_relax_factor_right - self.prev_relax_factor_right

        f_ps_la = max(f_ps_la + delta_left, 0)
        f_ps_lv = max(f_ps_lv + delta_left, 0)
        f_ps_raivc = max(f_ps_raivc + delta_right, 0)
        f_ps_rasvc = max(f_ps_rasvc + delta_right, 0)
        f_ps_ra = max(f_ps_ra + delta_right, 0)
        f_ps_rv = max(f_ps_rv + delta_right, 0)

        self._la.el_min_factor_ps = f_ps_la
        self._lv.el_min_factor_ps = f_ps_lv
        if self._raivci:
            self._raivci.el_min_factor_ps = f_ps_raivc
        if self._rasvc:
            self._rasvc.el_min_factor_ps = f_ps_rasvc
        if self._ra:
            self._ra.el_min_factor_ps = f_ps_ra
        self._rv.el_min_factor_ps = f_ps_rv

        self.relax_factor_left = new_relax_factor_left
        self.relax_factor_right = new_relax_factor_right

    # -------------------------------------------------------------------------
    # gaussian — utility used by the ECG generator
    # -------------------------------------------------------------------------
    def gaussian(self, t, amp, center, width):
        return amp * math.exp(-((t - center) ** 2) / (2 * width * width))
