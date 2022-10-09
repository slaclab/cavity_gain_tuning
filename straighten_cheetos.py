from scipy import stats
import matplotlib.pyplot as plt
import numpy as np
import time
from epics import caget, caput,caget_many
import sys

MULT = -51.0471

# input: CM prefix
narg=len(sys.argv)
if narg<2 :
  print('Too few arguments. Usage: ./testslops.py ACCL:LxB:##')
  raise SystemExit
#
CM=sys.argv[1].upper()

for cc in range(8) :
  pvPrefix=f"{CM}{cc+1}0:"
  aact=caget(pvPrefix+"AACTMEAN")
  if aact>1:
    startVal=caget(pvPrefix+"SEL_POFF")
    # nord tells you how many points are meaningful
    nord=caget(pvPrefix+"DAC:NORD")
    pvL=[pvPrefix+"CTRL:QWF", pvPrefix+"CTRL:IWF"]
    [qwf,iwf]=caget_many(pvL,False,nord)

    [slop,inter] = stats.siegelslopes(iwf,qwf)

    if not np.isnan(slop) :
      step=slop*MULT
      if step>5 :
        step=5
      elif step<-5 :
        step=-5
      if startVal+step < -180 :
        step=step+360
      elif startVal+step>180 :
        step=step-360
      try :
        caput(pvPrefix+"SEL_POFF",startVal+step)
      except :
        print(f"Tried to caput {pvPrefix}SEL_POFF {startVal+step}")