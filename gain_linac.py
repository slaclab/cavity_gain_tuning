from time import sleep

import numpy as np
from cothread.catools import caget, caput
from epics import caget_many, camonitor, camonitor_clear
from lcls_tools.superconducting.scLinac import Cavity, CryoDict, Piezo, SSA, StepperTuner
from numpy import arctan, pi
from scipy.stats import siegelslopes

CHEETO_MULTIPLIER = -51.0471

# system measurements / configuration
adc_clk = 1320e6 / 14  # Hz
sys_latency = 1.2e-6  # s  a.k.a. group delay, not counting filter in DSP


class GainCavity(Cavity):
    def __init__(self, cavityNum, rackObject, ssaClass=SSA,
                 stepperClass=StepperTuner, piezoClass=Piezo):
        super().__init__(cavityNum, rackObject)
        self.feedback_clip_pvs = [self.pvPrefix + "PHAFB_HSUM",
                                  self.pvPrefix + "PHAFB_LSUM",
                                  self.pvPrefix + "AMPFB_HSUM",
                                  self.pvPrefix + "AMPFB_LSUM"]
        self.clip_counter = 0
        self.stop_at_no_clips = False
    
    @property
    def freq(self):
        return caget(self.pvPrefix + "FREQ")
    
    @property
    def qloaded(self):
        return caget(self.pvPrefix + "QLOADED")
    
    @property
    def cav_hbw(self):
        return self.freq / (2 * self.qloaded)
    
    @property
    def plant_gain(self):
        return caget(self.pvPrefix + "PLANT_GAIN")
    
    @property
    def volt_set(self):
        return caget(self.pvPrefix + "ADES")
    
    @property
    def volt_fs(self):
        return caget(self.pvPrefix + "CAV:SCALE")
    
    @property
    def lowpass_bw(self):
        return caget(self.pvPrefix + "LOWPASS_BW")
    
    @staticmethod
    def plist(fmt, val, scale):
        rv = round(val * scale)
        bad = abs(rv) > 2 ** 17 - 1
        suffix = "BAD!" if bad else "."
        print(fmt % (val, rv, suffix))
        return bad
    
    def counter_callback(self, value, **kwargs):
        if value != 0:
            self.clip_counter += 1
    
    def clip_count(self, secs_to_wait=10):
        for pv in self.feedback_clip_pvs:
            camonitor(pv, self.counter_callback)
        
        print(f"Waiting {secs_to_wait} seconds to see clips")
        for i in range(secs_to_wait):
            if self.clip_counter > 1:
                break
            sleep(1)
        
        for pv in self.feedback_clip_pvs:
            camonitor_clear(pv)
        
        found_clips = self.clip_counter
        self.clip_counter = 0
        print(f"Found {found_clips} for {self}")
        return found_clips
    
    def search(self, sys_hbw=1000, time_to_wait=10):
        self.optimize(sys_hbw)
        sleep(1)
        self.straighten_cheeto()
        sleep(2)
        if self.clip_count(time_to_wait) > 1 and sys_hbw > 1000:
            print(f"Clips detected for {self}, backing off")
            self.stop_at_no_clips = True
            self.search(sys_hbw - 500, time_to_wait=60)
        else:
            if self.stop_at_no_clips:
                print(f"{self} gains optimized or crossing below 1000")
                self.stop_at_no_clips = False
                return
            else:
                print(f"No clips found for {self} or crossing <= 1000,"
                      f" increasing and retrying")
                self.search(sys_hbw + 1000, time_to_wait=10)
    
    def optimize(self, sys_hbw):
        print(f"Optimizing {self} at {sys_hbw} crossing")
        ctlr_zero_place = 0.25
        vfrac = self.volt_set / self.volt_fs
        
        print("Cavity HBW:     %6.3f Hz" % self.cav_hbw)
        print("Plant gain:     %6.3f" % self.plant_gain)
        print("Amplitude set:  %6.3f FS" % vfrac)
        print("Target sys HBW: %6.3f kHz" % (sys_hbw * 0.001))
        if vfrac < 0.01:
            print("Aborting for too-low cavity setpoint")
            return
        
        zero_omega = sys_hbw * 2 * pi * ctlr_zero_place  # /s
        sys_pgain = sys_hbw / self.cav_hbw
        sys_igain = sys_pgain * zero_omega
        theory_phase_margin = 90 - \
                              360 * (sys_latency + 1.0 / (2 * pi * self.lowpass_bw)) * sys_hbw - \
                              arctan(ctlr_zero_place) * 180 / pi
        print("phase margin %.1f degrees" % theory_phase_margin)
        #
        ctl_pgain = sys_pgain / self.plant_gain
        ctl_igain = sys_igain / self.plant_gain
        #
        print("Sys K_P  %9.1f" % sys_pgain)
        print("Sys K_I  %.3e /s" % sys_igain)
        print("")
        print("Ctl K_P  %9.1f" % ctl_pgain)
        print("Ctl K_I  %.3e /s" % ctl_igain)
        print("")
        
        # inverse gains of the CORDIC-related DSP surrounding the actual PI module
        # XXX Still need to confirm and document these factors of two
        # based on simulations of fdbk_core.v
        cgain = 1.64676  # unitless CORDIC gain
        amp_quirk = 2.0 / cgain ** 2
        phs_quirk = vfrac * pi / cgain
        #
        amp_pgain = ctl_pgain * amp_quirk
        amp_igain = ctl_igain * amp_quirk
        phs_pgain = ctl_pgain * phs_quirk
        phs_igain = ctl_igain * phs_quirk
        
        # scaling values confirmed with simulations of xy_pi_clip.v
        pscale = -64.0
        iscale = -32768.0 / adc_clk * (8.0)  # factor of 8 introduced by Jorge 2022/07/12
        bad = False
        bad |= self.plist("Amp K_P  %9.1f     %7d  %s", amp_pgain, pscale)
        bad |= self.plist("Amp K_I  %9.3e /s  %7d  %s", amp_igain, iscale)
        bad |= self.plist("Phs K_P  %9.1f     %7d  %s", phs_pgain, pscale)
        bad |= self.plist("Phs K_I  %9.3e /s  %7d  %s", phs_igain, iscale)
        
        if bad:
            print("Invalid configuration, not pushing")
            return
        
        caput(self.pvPrefix + "REG_AMPFB_GAIN_P", round(amp_pgain * pscale))
        caput(self.pvPrefix + "REG_AMPFB_GAIN_I", round(amp_igain * iscale))
        caput(self.pvPrefix + "REG_PHAFB_GAIN_P", round(phs_pgain * pscale))
        caput(self.pvPrefix + "REG_PHAFB_GAIN_I", round(phs_igain * iscale))
    
    def straighten_cheeto(self):
        print(f"Straightening cheeto for {self}")
        aact = caget(self.pvPrefix + "AACTMEAN")
        if aact > 1:
            startVal = caget(self.pvPrefix + "SEL_POFF")
            nord = caget(self.pvPrefix + "DAC:NORD")
            pvL = [self.pvPrefix + "CTRL:QWF", self.pvPrefix + "CTRL:IWF"]
            [qwf, iwf] = caget_many(pvL, False, nord)
            [slope, inter] = siegelslopes(iwf, qwf)
            
            if not np.isnan(slope):
                step = slope * CHEETO_MULTIPLIER
                if step > 5:
                    step = 5
                elif step < -5:
                    step = -5
                if startVal + step < -180:
                    step = step + 360
                elif startVal + step > 180:
                    step = step - 360
                
                caput(self.pvPrefix + "SEL_POFF", startVal + step)


GAIN_CRYOMODULES = CryoDict(cavityClass=GainCavity)
