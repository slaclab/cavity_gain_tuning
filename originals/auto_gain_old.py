from numpy import pi, arctan
from sys import argv
try:
    from cothread.catools import caget, caput
    catools = True
except Exception:
    print("catools not available")
    catools = False
if hasattr(__builtins__, 'raw_input'):  # stupid python2
    input = raw_input

# system measurements / configuration
adc_clk = 1320e6/14  # Hz
sys_latency = 1.2e-6  # s  a.k.a. group delay, not counting filter in DSP
prefix = None
if catools and len(argv) > 1:
    prefix = argv[1]

if prefix is None:
    # Demo only
    cav_hbw = 14.9  # Hz
    plant_gain = 0.73
    volt_set = 14.6  # MV
    volt_fs = 40.6  # MV
    lowpass_bw = 150e3  # Hz  controller baseband bandwidth
else:
    # Live
    freq = caget(prefix+"FREQ")
    qloaded = caget(prefix+"QLOADED")
    cav_hbw = freq / (2*qloaded)
    plant_gain = caget(prefix+"PLANT_GAIN")
    volt_set = caget(prefix+"ADES")
    volt_fs = caget(prefix+"CAV:SCALE")
    lowpass_bw = caget(prefix+"LOWPASS_BW")

# configure choices
sys_hbw =int(argv[2])  # Hz # this as high as possible so beam does not disturb stability as much.
ctlr_zero_place = 0.25
vfrac = volt_set / volt_fs

print("Cavity HBW:     %6.3f Hz" % cav_hbw)
print("Plant gain:     %6.3f" % plant_gain)
print("Amplitude set:  %6.3f FS" % vfrac)
print("Target sys HBW: %6.3f kHz" % (sys_hbw*0.001))
if vfrac < 0.01:
    print("Aborting for too-low cavity setpoint")
    exit(1)
print("")

# computation
zero_omega = sys_hbw * 2 * pi * ctlr_zero_place  # /s
sys_pgain = sys_hbw / cav_hbw
sys_igain = sys_pgain * zero_omega
theory_phase_margin = 90 - \
    360 * (sys_latency + 1.0/(2*pi*lowpass_bw)) * sys_hbw - \
    arctan(ctlr_zero_place)*180/pi
print("phase margin %.1f degrees" % theory_phase_margin)
#
ctl_pgain = sys_pgain / plant_gain
ctl_igain = sys_igain / plant_gain
#
print("Sys K_P  %9.1f" % sys_pgain)
print("Sys K_I  %.3e /s" % sys_igain)
print("")
print("Ctl K_P  %9.1f" % ctl_pgain)
print("Ctl K_I  %.3e /s" % ctl_igain)
print("")
#
# inverse gains of the CORDIC-related DSP surrounding the actual PI module
# XXX Still need to confirm and document these factors of two
# based on simulations of fdbk_core.v
cgain = 1.64676  # unitless CORDIC gain
amp_quirk = 2.0 / cgain**2
phs_quirk = vfrac * pi / cgain
#
amp_pgain = ctl_pgain * amp_quirk
amp_igain = ctl_igain * amp_quirk
phs_pgain = ctl_pgain * phs_quirk
phs_igain = ctl_igain * phs_quirk


def plist(fmt, val, scale):
    rv = round(val*scale)
    bad = abs(rv) > 2**17-1
    suffix = "BAD!" if bad else "."
    print(fmt % (val, rv, suffix))
    return bad


# scaling values confirmed with simulations of xy_pi_clip.v
pscale = -64.0
iscale = -32768.0/adc_clk * (8.0) # factor of 8 introduced by Jorge 2022/07/12
bad = False
bad |= plist("Amp K_P  %9.1f     %7d  %s", amp_pgain, pscale)
bad |= plist("Amp K_I  %9.3e /s  %7d  %s", amp_igain, iscale)
bad |= plist("Phs K_P  %9.1f     %7d  %s", phs_pgain, pscale)
bad |= plist("Phs K_I  %9.3e /s  %7d  %s", phs_igain, iscale)

if bad:
    print("Invalid configuration, not pushing")
    exit(1)
if prefix is None:
    exit(0)

x = input("Push? [n] ")
if len(x) > 0 and (x[0] == "y" or x[0] == "Y"):
    print("proceeding")
    caput(prefix+"REG_AMPFB_GAIN_P", round(amp_pgain*pscale))
    caput(prefix+"REG_AMPFB_GAIN_I", round(amp_igain*iscale))
    caput(prefix+"REG_PHAFB_GAIN_P", round(phs_pgain*pscale))
    caput(prefix+"REG_PHAFB_GAIN_I", round(phs_igain*iscale))
    print("done")