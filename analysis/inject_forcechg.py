#!/usr/bin/env python3
"""
Force the PCS into charge mode despite the stale CellUVLock, by injecting the
firmware's own 'Set Inv Force Chg' command handler.

Handler 0x0804088C(r0=cmd_id, r1=payload_ptr, r2=len):
  validates cmd_id==0x0365C001, len==4, payload(LE) in {5,10};
  builds {reg=0xA0AB, data=payload} and enqueues it (0x0804003C, non-blocking ring insert);
  returns 1 on success. Early-reject path if state byte [0x200002FC+4]==1.

This is the SAME proven non-blocking injection pattern as the working ClrOneDeviceAllAlarmBySn
call (validate -> queue -> return 1). It does NOT wait on a semaphore, so it won't hang.

Run with unit ON, AC plugged, SWD attached. After it returns r0=1, the PCS task should pick
up the queued command and start charging -> watch cells climb (this script polls for ~20s,
or run monitor_charge.py). Power-cycle recovers if anything misbehaves.
"""
import time
from pyocd.core.helpers import ConnectHelper
from pyocd.core.target import Target

HANDLER = 0x0804088C
CMD_ID  = 0x0365C001
PAYVAL  = 5                 # 5 or 10 (handler accepts both); start with 5
TRAP    = 0x08000000
STATE   = 0x200002FC        # +4 = reject gate; +0 = ring write idx; +2 = pending flag
CELLS   = 0x20000E02

def u16(d,i): return d[i]|(d[i+1]<<8)
def u32(d,i): return d[i]|(d[i+1]<<8)|(d[i+2]<<16)|(d[i+3]<<24)
def cells_avg(t):
    cb=bytes(t.read_memory_block8(CELLS,32)); c=[u16(cb,2*i) for i in range(16)]
    return min(c),max(c),sum(c)//16

session = ConnectHelper.session_with_chosen_probe(
    options={"target_override":"gd32f470zg","connect_mode":"attach","frequency":1000000})
session.open(); t=session.target
try:
    t.halt()
    gate = t.read_memory_block8(STATE+4,1)[0]
    widx = t.read_memory_block8(STATE,1)[0]
    print(f"state byte [0x{STATE+4:08X}]={gate} (1 => handler early-rejects)   ring write idx={widx}")
    mn,mx,av=cells_avg(t); print(f"cells before: min={mn} max={mx} avg={av}")

    saved={r:t.read_core_register(r) for r in ('r0','r1','r2','r3','r12','sp','lr','pc','xpsr')}
    sp=saved['sp']
    payload=(sp-0x40)&~7
    new_sp =(sp-0x80)&~7
    t.write_memory_block8(payload, bytes([PAYVAL,0,0,0]))   # LE payload

    t.set_breakpoint(TRAP)
    t.write_core_register('sp', new_sp)
    t.write_core_register('r0', CMD_ID)
    t.write_core_register('r1', payload)
    t.write_core_register('r2', 4)
    t.write_core_register('lr', TRAP|1)
    t.write_core_register('pc', HANDLER)
    t.write_core_register('xpsr', 0x01000000)
    print(f"injecting Set Inv Force Chg (cmd=0x{CMD_ID:08X}, data={PAYVAL}) ...")
    t.resume()
    t0=time.time(); ok=False
    while time.time()-t0 < 3.0:
        if t.get_state()==Target.State.HALTED: ok=True; break
        time.sleep(0.01)
    if not ok:
        t.halt(); pc=t.read_core_register('pc')
        print(f"  !! did not return in 3s (stopped pc=0x{pc:08X}). Restoring + aborting.")
    else:
        r0=t.read_core_register('r0'); pc=t.read_core_register('pc')
        print(f"  returned r0=0x{r0:08X} (1=queued OK)   trap pc=0x{pc:08X}")
        widx2=t.read_memory_block8(STATE,1)[0]; pend=t.read_memory_block8(STATE+2,1)[0]
        print(f"  ring write idx now={widx2} (was {widx})   pending flag [+2]={pend}")

    t.remove_breakpoint(TRAP)
    for r,v in saved.items(): t.write_core_register(r,v)
    t.resume()
    print("firmware resumed. Polling cells for ~20s (watch for a rising avg = charging started):")
    for _ in range(10):
        time.sleep(2.0)
        mn,mx,av=cells_avg(t)
        print(f"    cells min={mn} max={mx} avg={av}")
finally:
    session.close()
print("== done ==  (now run monitor_charge.py to keep watching; power-cycle if needed)")
