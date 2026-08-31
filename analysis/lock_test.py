#!/usr/bin/env python3
"""
Cable-disconnect lock-source test helper.  Two modes:

  python lock_test.py check     # READ-ONLY snapshot (no halt). Is CellUVLock present?
  python lock_test.py clear     # clear the GD32's CellUVLock copy (halt + RAM write, like clear_word.py)

DECISIVE SEQUENCE (with the BMS<->inverter cable DISCONNECTED):
  1. Disconnect the cable.
  2. POWER-CYCLE the unit (cold boot) with the cable still out.
  3. python lock_test.py check
        => CLEAN  : CellUVLock is pushed over the cable -> the inverter board owns the NV latch (XDS110 target).
        => PRESENT: the GD32 re-derives/holds it locally -> we were wrong about the source.
  (optional) python lock_test.py clear  then re-check, to confirm it doesn't get re-pushed while running.

Read-only 'check' uses background memory reads (no CPU halt) so it won't disturb timing.
"""
import sys, time, struct
from pyocd.core.helpers import ConnectHelper
from pyocd.core.target import Target

PTRARR=0x10006CC4   # CCM: device-struct ptr array; [0]=bms1
RING  =0x10006810   # CCM: [u16 head][u16 count], 60B records @+4
FWOFF =0x56         # group3/word0 fault word in device struct
CELLS =0x20000E02
PACKV =0x20000E24
PACKI =0x20000E34

def u16(d,i): return d[i]|(d[i+1]<<8)
def u32(d,i): return d[i]|(d[i+1]<<8)|(d[i+2]<<16)|(d[i+3]<<24)

def connect():
    s=ConnectHelper.session_with_chosen_probe(
        options={"target_override":"gd32f470zg","connect_mode":"attach","frequency":1000000})
    s.open(); return s

def read_state(t):
    rd=lambda a,n: bytes(t.read_memory_block8(a,n))
    st={}
    try:
        ring=rd(RING,4); st['cnt']=u16(ring,2); st['code0']=u16(rd(RING+4,4),0)
    except Exception: st['cnt']=-1; st['code0']=0
    st['dev']=0; st['fw']=-1; st['ser']=""
    try:
        dev=u32(rd(PTRARR,4),0); st['dev']=dev
        if 0x20000000<=dev<0x20040000:
            st['ser']=rd(dev+6,20).split(b"\x00")[0].decode("ascii","replace")
            st['fw']=u32(rd(dev+FWOFF,4),0)
    except Exception: pass
    try:
        cb=rd(CELLS,32); st['cells']=[u16(cb,2*i) for i in range(16)]
        st['pv']=struct.unpack("<f",rd(PACKV,4))[0]; st['pi']=struct.unpack("<f",rd(PACKI,4))[0]
    except Exception:
        st['cells']=[0]*16; st['pv']=0.0; st['pi']=0.0
    return st

def uvbit(st): return ((st['fw']>>1)&1) if st['fw']>=0 else None

def show(st,label):
    uv=uvbit(st)
    devok = 0x20000000<=st['dev']<0x20040000 and st['ser'][:4]=="bms1"
    print(f"[{label}] ring={st['cnt']} code0=0x{st['code0']:04X}  "
          f"dev={'0x%08X'%st['dev']} ser={st['ser']!r}  faultword=0x{st['fw']:08X} CellUVLock={uv}")
    print(f"        cells {min(st['cells'])}-{max(st['cells'])} mV  packV={st['pv']:.2f}V packI={st['pi']:+.2f}A")
    return devok, uv

def verdict(st):
    uv=uvbit(st)
    present = (st['cnt']>0) or (uv==1)
    if not present:
        print("  => CLEAN: no CellUVLock present.")
    else:
        print("  => CellUVLock PRESENT.")
    return present

def check():
    s=connect(); t=s.target
    try:
        st=read_state(t); show(st,"CHECK"); verdict(st)
    finally:
        s.close()

def clear():
    s=connect(); t=s.target
    try:
        t.halt()
        st=read_state(t); devok,uv=show(st,"BEFORE")
        if not devok:
            print("  !! no valid bms1 device struct -> nothing to clear. Aborting."); t.resume(); return
        fwaddr=st['dev']+FWOFF
        # write BOTH the device fault word and the alarm-ring header (head+count = 0)
        t.write_memory_block8(fwaddr, bytes(4))
        t.write_memory_block8(RING, bytes(4))
        # immediate read-back WHILE STILL HALTED: did the RAM writes actually take?
        imm=read_state(t)
        print(f"  immediate (halted) read-back: faultword=0x{imm['fw']:08X}  ring count={imm['cnt']}")
        if imm['fw']!=0 or imm['cnt']!=0:
            print("  !! WRITE DID NOT STICK even while halted -> wrong address/struct, or memory-protected.")
            print("     (faultword should be 0x00000000 and ring 0 right after the write.) Tell me this line.")
            t.resume(); return
        print("  RAM writes took. Resuming and sampling how fast it re-fills...")
        t.resume()
        t0=time.time()
        for mark in (0.5,1.0,2.0,4.0):
            while time.time()-t0 < mark: time.sleep(0.02)
            t.halt(); s2=read_state(t); t.resume()
            print(f"   +{mark:>3.1f}s: faultword=0x{s2['fw']:08X}  ring={s2['cnt']}  code0=0x{s2['code0']:04X}")
        print("\n  INTERPRETATION:")
        print("   - stays 0 the whole time            => cleared; do the cold-boot check next.")
        print("   - faultword/ring re-fill in <~1s    => a LIVE source re-pushes it every cycle (cache or cable).")
        print("   - only ring re-fills (word stays 0) => firmware re-adds the alarm record from a cached fault.")
    finally:
        s.close()

if __name__=="__main__":
    mode=sys.argv[1].lower() if len(sys.argv)>1 else "check"
    (clear if mode=="clear" else check)()
