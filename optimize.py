from lcls_tools.superconducting.scLinac import ALL_CRYOMODULES

from gain_linac import GAIN_CRYOMODULES

for cm_name in ALL_CRYOMODULES:
    cm = GAIN_CRYOMODULES[cm_name]
    for cav in cm.cavities.values():
        cav.search()
