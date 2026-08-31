#!/usr/bin/env python3
"""
Live, READ-ONLY monitor for the force-charge attempt. Does NOT halt the CPU
(halting >500ms trips the BMS-CAN timeouts), just samples memory over the DAP
while the firmware runs. Ctrl-C to stop.

Watch for: cell voltages climbing (= charging is happening) and the alarm-ring
CellUVLock dropping to count 0 (= lock released).

Usage:
  1. Start this script (shows baseline: CellUVLock present, cells ~3.29V).
  2. Plug in the AC cable.
  3. Watch the columns. If cells rise but lock stays -> we then try force-charge injection.
"""
import time, sys
from pyocd.core.helpers import ConnectHelper

RING   = 0x10006810      # CCM: [u16 head][u16 count], records @+4 (60B each)
PTRARR = 0x10006CC4      # CCM: device-struct pointer array; [0] = bms1
FWOFF  = 0x56            # group3/word0 fault word within device struct
CELLS  = 0x20000E02      # SRAM: 16 x u16 cell mV
PACKV  = 0x20000E24      # SRAM: float32 pack voltage (V)  [verified vs 49.69V dump]
PACKI  = 0x20000E34      # SRAM: float32 pack current (A)  [~0 at rest; >0 or <0 = current flowing]

import struct as _st
def u16(d,i): return d[i] | (d[i+1]<<8)
def u32(d,i): return d[i] | (d[i+1]<<8) | (d[i+2]<<16) | (d[i+3]<<24)
def f32(t,a):
    try: return _st.unpack("<f", bytes(t.read_memory_block8(a,4)))[0]
    except: return float("nan")

def main():
    session = ConnectHelper.session_with_chosen_probe(
        options={"target_override":"gd32f470zg","connect_mode":"attach","frequency":1000000})
    session.open()
    t = session.target
    print("time     ring  UVlock  faultword   packV   packI    cell_min cell_max cell_avg spread trend")
    prev_avg=None
    try:
        while True:
            try:
                ring = bytes(t.read_memory_block8(RING, 4))
                count = u16(ring,2)
                # first ring record code
                rec = bytes(t.read_memory_block8(RING+4, 4))
                code0 = u16(rec,0)
                # device fault word
                devp = bytes(t.read_memory_block8(PTRARR,4)); dev=u32(devp,0)
                fw = 0
                if 0x20000000 <= dev < 0x20040000:
                    fw = u32(bytes(t.read_memory_block8(dev+FWOFF,4)),0)
                uv = (fw>>1)&1
                # cells
                cb = bytes(t.read_memory_block8(CELLS, 32))
                cells=[u16(cb,2*i) for i in range(16)]
                mn,mx=min(cells),max(cells); avg=sum(cells)//16
                trend=""
                if prev_avg is not None:
                    d=avg-prev_avg
                    trend = f"{'+' if d>=0 else ''}{d}mV " + ("CHARGING" if d>=2 else ("draining" if d<=-2 else "flat"))
                prev_avg=avg
                pv=f32(t,PACKV); pi=f32(t,PACKI)
                iflag = "  <I!" if abs(pi)>=0.3 else ""
                uvstr = f"YES(0x{code0:04X})" if (count>0 and uv) else ("clr" )
                print(f"{time.strftime('%H:%M:%S')}  {count:>3}  {uvstr:>10}  0x{fw:08X}  {pv:6.2f}  {pi:+6.2f}{iflag:>4}  {mn:>5}   {mx:>5}   {avg:>5}   {mx-mn:>3}  {trend}")
                if count==0 and uv==0:
                    print(">>> CellUVLock CLEARED. Power-cycle and re-check the app to confirm it stays gone.")
            except Exception as e:
                print(f"  (read hiccup: {e})")
            time.sleep(2.0)
    except KeyboardInterrupt:
        print("\nstopped.")
    finally:
        session.close()

if __name__=="__main__":
    main()
