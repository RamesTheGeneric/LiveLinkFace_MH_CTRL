#!/usr/bin/env python3
"""
Thx claude for fixing my bs
MetaHuman Animator — LiveLink Face UDP Receiver
================================================
Confirmed packet layout (raw UDP payload, byte 0 = first byte after UDP header):

  [0x00–0x01]  version (uint16 LE)
  [0x02–0x03]  uuid_len (uint16 LE)
  [0x04–0x27]  UUID string (36 bytes ASCII)
  [0x28]       sequence number (uint8)
  [0x29–0x2D]  timecode (5 bytes: H M S F SubF)
  [0x2E–0x247] 269 × uint16 LE control curves (538 bytes, 0–65535 → 0.0–1.0)
  [0x248–0x247] (packet ends at byte 584)

Ground truth anchor:
  jawOpen is at absolute byte 0x01B8 = 440
  → curve index = (440 - 46) / 2 = 197  ✓

Curve block structure:
  Index   0– 56: UNKNOWN (57 curves, not yet identified)
  Index  57–224: Known MHA documented curves (browDownL → tongueTipRight)
  Index 225–268: UNKNOWN (44 curves, not yet identified)

Usage:
    python mha_receiver.py [--port 11111] [--verbose] [--log FILE]
    python mha_receiver.py info  FILE.bin
    python mha_receiver.py scan  NEUTRAL.bin ACTIVE.bin [--threshold 0.02]
    python mha_receiver.py diff  A.bin B.bin

MH_Index: https://dev.epicgames.com/documentation/en-us/metahuman/mh-standards-docs/mha_index  # Idk how useful this is anymore but its still here. See ControlMapperConfiguration.json for the actual output
"""

import socket, struct, argparse, os, csv, math, time
from datetime import datetime
from pathlib import Path

import output_osc as sender

# Confirmed layout constants
CURVE_OFFSET  = 46    # immediately after header+timecode, confirmed by jawOpen anchor
NUM_CURVES    = 269   # total uint16 curves in packet
PACKET_SIZE   = 584


RESET="\033[0m"; BOLD="\033[1m"; GREEN="\033[32m"
RED="\033[31m";  YELLOW="\033[33m"; CYAN="\033[36m"; DIM="\033[2m"

## Full 269-curve packet index map 
# Order is the MetaHuman internal rig order, NOT the documented alphabetical order.
# Confirmed anchors marked [C], inferred from adjacent confirmed marked [I], unknown marked [?]
#
# Capture guide for filling unknowns:
#   blink L/R only confirms 16/17, check 14/15 (earUp?)
#   eyeWide L find widen position (18–96)
#   eyeLookLeft find eyeLook* positions
#   smile / cornerPull find in 18–96
#   noseSneer find nose positions
#   tongue out find tongue positions (207+)
#   cheekPuff find in 18–96

ALL_CURVES = [
    # ── 0–5: unknown ──────────────────────────────────────────────────────────
    "unknown_000", "unknown_001", "unknown_002",                    # [?]
    "unknown_003", "unknown_004", "unknown_005",                    # [?]

    # ── 6–13: brows ───────────────────────────────────────────────────────────
    "browDownL",       "browDownR",                                 # 6–7   [I]
    "browLateralL",    "browLateralR",                              # 8–9   [I]
    "browRaiseInL",    "browRaiseInR",                              # 10–11 [C]
    "browRaiseOuterL", "browRaiseOuterR",                           # 12–13 [C]

    # ── 14–15: earUpL/R ─────────────────────────
    "earUpL",     "earUpR",                               # [?]

    # ── 16–17: eye blink ──────────────────────────────────────────────────────
    "eyeBlinkL",       "eyeBlinkR",                                 # 16–17 [C]

    # ── 18–96: unknown (79 curves — eye look/widen/squint, nose, mouth open shapes)
    "eyeLidPressL", "eyeLidPressR", # eyeLidPress
    
    "eyeWidenL", "eyeWidenR", # eyeWide

    # --- 22-23: eyeSquintInnerL/R
    "eyeSquintInnerL", "eyeSquintInnerR", 

    "eyeCheekRaiseL", "eyeCheekRaiseR", # cheekPuff?
    "eyeFaceScrunchL", "eyeFaceScrunchR", # cheekPuff?
    
    "eyeUpperLidUpL", "eyeUpperLidUpR",
    "eyeRelaxL", "eyeRelaxR", 
    "eyeLowerLidUpL", "eyeLowerLidUpR",
    "eyeLowerLidDownL", "eyeLowerLidDownR", 
    
    # --- 36-39: eyeLookUpDownL/R
    "eyeLookUpL", "eyeLookUpR", "eyeLookDownL", "eyeLookDownR",

    # --- 40-43: eyeLookLeftRightL/R
    "eyeLookLeftL", "eyeLookLeftR", "eyeLookRightL", "eyeLookRightR", 

    "eyePupilWideL", "eyePupilWideR", # eyePupilDilation?
    "eyePupilNarrowL", "eyePupilNarrowR", 
    "eyeParallelLookDirection", # ???
    "eyelashesUpINL", "eyelashesUpINR", 
    "eyelashesUpOUTL", "eyelashesUpOUTR", 
    "eyelashesDownINL", "eyelashesDownINR", 
    "eyelashesDownOUTL", "eyelashesDownOUTR", 

    # --- 57-58: noseSneerL/R
    "noseWrinkleL", "noseWrinkleR", 

    "noseWrinkleUpperL", "noseWrinkleUpperR", 
    "noseNostrilDepressL","noseNostrilDepressR", 
    "noseNostrilDilateL", "noseNostrilDilateR", 
    "noseNostrilCompressL", "noseNostrilCompressR", 
    "noseNasolabialDeepenL", "noseNasolabialDeepenR", 
    "mouthCheekSuckL", "mouthCheekSuckR", 
    "mouthCheekBlowL", "mouthCheekBlowR", 
    "mouthLipsBlowL", "mouthLipsBlowR", 

    # --- 75-76: mouuthLeft/Right
    "mouthLeft", "mouthRight", 

    "mouthUp", # mouthUp???
    "mouthDown", # mouthDown???
    
    # --- 79-80: mouthUpperLipRaiseL/R
    "mouthUpperLipRaiseL", "mouthUpperLipRaiseR", 

    # --- 81-82: mouthLowerLipDepressL/R
    "mouthLowerLipDepressL", "mouthLowerLipDepressR", 

    # --- 83-84: mouthCornerPullL/R         smile
    "mouthCornerPullL", "mouthCornerPullR", 

    # --- 85-86: mouthStretchL/R
    "mouthStretchL", "mouthStretchR", 

    # --- 87-88: mouthStretchLipsClosedL/R
    "mouthStretchLipsCloseL", "mouthStretchLipsCloseR", 
    
    # --- 89-90: mouthDimpleL/R
    "mouthDimpleL", "mouthDimpleR", 

    # --- 91-92: mouthCornerDepressL/R      Frown
    "mouthCornerDepressL", "mouthCornerDepressR", 
    
    "mouthPressUL","mouthPressUR", "mouthPressDL", "mouthPressDR", # mouthPress

    # ── 97–104: mouth purse / towards ─────────────────────────────────────────    Pucker
    "mouthLipsPurseUL",  "mouthLipsPurseUR",                       # 97–98  [C]
    "mouthLipsPurseDL",  "mouthLipsPurseDR",                       # 99–100 [C]
    "mouthLipsTowardsUL","mouthLipsTowardsUR",                     # 101–102 [C]
    "mouthLipsTowardsDL","mouthLipsTowardsDR",                     # 103–104 [C]

    # ── 105–196: unknown (92 curves — rest of mouth shapes) ───────────────────
    # --- 105-108: mouthFunnelUL/RR/DL/DR
    "mouthFunnelUL", "mouthFunnelUR", "mouthFunnelDL", "mouthFunnelDR", # Funnel

    "mouthLipsTogetherUL", "mouthLipsTogetherUR", "mouthLipsTogetherDL", "mouthLipsTogetherDR", # mouthClose also??????
    "mouthUpperLipBiteL", "mouthUpperLipBiteR", "mouthLowerLipBiteL", "mouthLowerLipBiteR",
    "mouthLipsTightenUL", "mouthLipsTightenUR", "mouthLipsTightenDL", "mouthLipsTightenDR",
    "mouthLipsPressL", "mouthLipsPressR", "mouthSharpCornerPullL", "mouthSharpCornerPullR",
    "mouthStickyUC", "mouthStickyUINL", "mouthStickyUINR", "mouthStickyUOUTL",
    "mouthStickyUOUTR", "mouthStickyDC", "mouthStickyDINL", "mouthStickyDINR",
    "mouthStickyDOUTL", "mouthStickyDOUTR", "mouthLipsStickyLPh1", "mouthLipsStickyLPh2",
    "mouthLipsStickyLPh3", "mouthLipsStickyRPh1", "mouthLipsStickyRPh2", "mouthLipsStickyRPh3", 

    # --- 141-144: mouthLipsTogether/RR/DL/DR   # mouthClose
    "mouthLipsPushUL", "mouthLipsPushUR", "mouthLipsPushDL", "mouthLipsPushDR",

    "mouthLipsPullUL", "mouthLipsPullUR", "mouthLipsPullDL", "mouthLipsPullDR",
    "mouthLipsThinUL", "mouthLipsThinUR", "mouthLipsThinDL", "mouthLipsThinDR",
    "mouthLipsThickUL", "mouthLipsThickUR", "mouthLipsThickDL", "mouthLipsThickDR",
    "mouthLipsThinInwardUL", "mouthLipsThinInwardUR", "mouthLipsThinInwardDL", "mouthLipsThinInwardDR",
    "mouthLipsThickInwardUL", "mouthLipsThickInwardUR", "mouthLipsThickInwardDL", "mouthLipsThickInwardDR",
    "mouthCornerSharpenUL", "mouthCornerSharpenUR", "mouthCornerSharpenDL", "mouthCornerSharpenDR",
    "mouthCornerRounderUL", "mouthCornerRounderUR", "mouthCornerRounderDL", "mouthCornerRounderDR",
    "mouthUpperLipTowardsTeethL", "mouthUpperLipTowardsTeethR", "mouthLowerLipTowardsTeethL", "mouthLowerLipTowardsTeethR",
    "mouthUpperLipShiftLeft", "mouthUpperLipShiftRight", "mouthLowerLipShiftLeft", "mouthLowerLipShiftRight",


    "mouthUpperLipRollInL", "mouthUpperLipRollInR", # mouthLipsTogetherUL/UR???
    
    "mouthUpperLipRollOutL", "mouthUpperLipRollOutR",
    
    "mouthLowerLipRollInL", "mouthLowerLipRollInR", # mouthLipsTogetherDL/DR???

    "mouthLowerLipRollOutL", "mouthLowerLipRollOutR",
    "mouthCornerUpL", "mouthCornerUpR", "mouthCornerDownL", "mouthCornerDownR",
    "mouthCornerWideL", "mouthCornerWideR", "mouthCornerNarrowL", "mouthCornerNarrowR",

    # ── 197–206: jaw ──────────────────────────────────────────────────────────
    "jawOpen",         "jawLeft",         "jawRight",               # 197–199 [C]
    "jawFwd",          "jawBack",                                   # 200–201 [C]
    "jawChinRaiseDL",  "jawChinRaiseDR",                            # 202–203 [C]
    "jawChinRaiseUL",  "jawChinRaiseUR",                            # 204–205 [C]
    "jawOpenExtreme",                                               # 206     [C]

    # ── 207–268: unknown (tongue + unknown suffix, 62 curves) ─────────────────
    "neckStretchL", "neckStretchR", "neckSwallowPh1", "neckSwallowPh2",
    "neckSwallowPh3", "unknown_212", "neckSwallowPh4", 
    "neckMastoidContractL", "neckMastoidContractR", 
    "neckThroatDown", "neckThroatUp", "neckDigastricDown", "neckDigastricUp", 
    "neckThroatExhale", "neckThroatInhale", "teethUpU",
    "teethUpD", "teethDownU", "teethDownD", "teethLeftU",
    "teethLeftD", "teethRightU", "teethRightD", "teethFwdU",
    "teethFwdD", "teethBackU", "unknown_233", "unknown_234",
    "unknown_235", "unknown_236", "unknown_237", "unknown_238",
    "unknown_239", "unknown_240", "unknown_241", "unknown_242",
    "unknown_243", "unknown_244", "unknown_245", "unknown_246",
    "unknown_247", "unknown_248", "unknown_249", "unknown_250",
    "unknown_251", "unknown_252", "unknown_253", "unknown_254",
    "unknown_255", "unknown_256", 

    "unknown_257", "unknown_258", #Head LR?

    "unknown_259", "unknown_260", "unknown_261", "unknown_262",
    "unknown_263", "unknown_264", "unknown_265", "unknown_266",
    "unknown_267", "unknown_268",
]


assert len(ALL_CURVES) == NUM_CURVES, f"Expected {NUM_CURVES}, got {len(ALL_CURVES)}"
# Hard-verify our ground truth anchors
assert ALL_CURVES[16]  == "eyeBlinkL"
assert ALL_CURVES[17]  == "eyeBlinkR"
assert ALL_CURVES[10]  == "browRaiseInL"
assert ALL_CURVES[97]  == "mouthLipsPurseUL"
assert ALL_CURVES[104] == "mouthLipsTowardsDR"
assert ALL_CURVES[197] == "jawOpen"
assert CURVE_OFFSET + 197 * 2 == 440  # abs byte 0x01B8


# Parser

def parse_packet(data: bytes) -> dict | None:
    if len(data) != PACKET_SIZE:
        return None
    try:
        version  = struct.unpack_from('<H', data, 0)[0]
        uuid_len = struct.unpack_from('<H', data, 2)[0]
        if uuid_len == 0 or uuid_len > 64:
            return None
        uuid_str = data[4:4+uuid_len].decode('ascii', errors='replace')
        seq = data[4+uuid_len]
        tc = struct.unpack_from('5B', data, 4+uuid_len+1)

        curves = {}
        for i, name in enumerate(ALL_CURVES):
            curves[name] = struct.unpack_from('<H', data, CURVE_OFFSET + i*2)[0] / 65535.0

        return {
            "version": version, "uuid": uuid_str, "seq": seq,
            "tc": f"{tc[0]:02d}:{tc[1]:02d}:{tc[2]:02d}:{tc[3]:02d}.{tc[4]:02d}",
            "curves": curves,
        }
    except (struct.error, IndexError):
        return None


# Display 

def bar(v, w=24):
    return f"[{'█'*int(min(max(v,0),1)*w)}{'░'*(w-int(min(max(v,0),1)*w))}]"

def print_frame(frame: dict, raw: bytes, verbose: bool):
    c = frame["curves"]
    os.system('cls' if os.name == 'nt' else 'clear')
    print(f"{BOLD}{CYAN}MetaHuman Animator LiveLink{RESET}  "
          f"seq={YELLOW}{frame['seq']:3d}{RESET}  tc={frame['tc']}  "
          f"uuid={DIM}{frame['uuid'][:8]}…{RESET}")
    print()

    if verbose:
        # Group by known vs unknown regions
        regions = [
            ("Unknown [0–5]",           ALL_CURVES[0:6]),
            ("Brows [6–13]",            ALL_CURVES[6:14]),
            ("Unknown [14–15]",         ALL_CURVES[14:16]),
            ("Eyes — blink [16–17]",    ALL_CURVES[16:18]),
            ("Unknown [18–96]",         ALL_CURVES[18:97]),
            ("Mouth — purse/towards [97–104]", ALL_CURVES[97:105]),
            ("Unknown [105–196]",       ALL_CURVES[105:197]),
            ("Jaw [197–206]",           ALL_CURVES[197:207]),
            ("Unknown [207–268]",       ALL_CURVES[207:269]),
        ]
        for gname, names in regions:
            active = [(n, c[n]) for n in names if c[n] > 0.005]
            if not active:
                continue
            print(f"{BOLD}{gname}{RESET}")
            for name, v in active:
                idx = ALL_CURVES.index(name)
                print(f"  [{idx:>3}] {name:<34} {GREEN}{bar(v)} {v:.4f}{RESET}")
            print()
    else:
        active = [(n, c[n]) for n in ALL_CURVES if c[n] > 0.02]
        active.sort(key=lambda x: -x[1])
        print(f"{BOLD}Active curves:{RESET}")
        if active:
            for name, v in active[:20]:
                idx = ALL_CURVES.index(name)
                print(f"  [{idx:>3}] {name:<34} {GREEN}{bar(v)} {v:.4f}{RESET}")
        else:
            print(f"  {DIM}(neutral){RESET}")
        print()


# Live mode

def live_mode(port: int, verbose: bool, log_path: str | None):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(('0.0.0.0', port))
    sock.settimeout(0.5)
    print(f"Listening on UDP :{port}  Ctrl+C to stop")

    osc = sender.OSCClient('127.0.0.1', 8888)

    csv_f, csv_w = None, None
    if log_path:
        csv_f = open(log_path, 'w', newline='')
        csv_w = csv.writer(csv_f)
        csv_w.writerow(["ts", "seq", "tc"] + ALL_CURVES)
        print(f"Logging to {log_path}")

    n, dropped, last_seq, t0 = 0, 0, None, time.time()
    try:
        while True:
            try:
                data, addr = sock.recvfrom(65535)
            except socket.timeout:
                continue
            if len(data) != PACKET_SIZE:
                print(f"  {YELLOW}Unexpected size: {len(data)}b (expected {PACKET_SIZE}){RESET}")
                continue
            frame = parse_packet(data)
            if not frame:
                continue
            n += 1
            if last_seq is not None:
                dropped += (frame['seq'] - (last_seq+1)) & 0xFF
            last_seq = frame['seq']
            if csv_w:
                csv_w.writerow([
                    datetime.now().isoformat(timespec='milliseconds'),
                    frame['seq'], frame['tc'],
                ] + [frame['curves'][k] for k in ALL_CURVES])
            #print_frame(frame, data, verbose)
            curves = frame["curves"]
            osc.send_msgs(curves)
            fps = n / (time.time()-t0) if time.time()-t0 > 0 else 0
            print(f"{DIM}  frames={n}  dropped={dropped}  fps={fps:.1f}  src={addr[0]}{RESET}")
    except KeyboardInterrupt:
        print(f"\nStopped. {n} frames, {dropped} dropped.")
    finally:
        sock.close()
        if csv_f: csv_f.close()


# Info 

def cmd_info(data: bytes, filename: str = ""):
    print(f"\n{BOLD}{filename}  —  {len(data)} bytes{RESET}")
    if len(data) != PACKET_SIZE:
        print(f"  {YELLOW}Expected {PACKET_SIZE} bytes{RESET}")
    frame = parse_packet(data)
    if not frame:
        print(f"  {RED}Parse failed{RESET}"); return

    print(f"  UUID: {frame['uuid']}  seq={frame['seq']}  tc={frame['tc']}")
    print(f"\n{BOLD}All {NUM_CURVES} curves  (abs byte = {CURVE_OFFSET} + index×2):{RESET}")
    print(f"  {'idx':>4}  {'abs':>5}  {'name':<34}  {'norm':>8}  bar")
    print("  " + "─"*72)
    for i, name in enumerate(ALL_CURVES):
        v   = frame['curves'][name]
        abs_byte = CURVE_OFFSET + i*2
        if v < 0.005 and 'unknown' in name:
            continue   # skip zero unknowns for readability
        col = GREEN if v > 0.02 else DIM
        b   = '█'*int(v*20) if v > 0.005 else ''
        print(f"  {i:>4}  0x{abs_byte:04x}  {name:<34}  {col}{v:>8.4f}  {b}{RESET}")


# Scan

def cmd_scan(neutral: bytes, active: bytes, threshold: float = 0.02):
    fn = parse_packet(neutral)
    fa = parse_packet(active)
    if not fn or not fa:
        print(f"{RED}Parse failed{RESET}"); return

    print(f"\n{BOLD}Activation scan  (threshold={threshold:.0%}){RESET}")
    print(f"  {'idx':>4}  {'abs':>5}  {'name':<34}  {'neutral':>8}  {'active':>8}  {'Δ':>8}")
    print("  " + "─"*72)
    for i, name in enumerate(ALL_CURVES):
        vn = fn['curves'][name]
        va = fa['curves'][name]
        d  = va - vn
        if abs(d) >= threshold:
            abs_byte = CURVE_OFFSET + i*2
            col = GREEN if d > 0 else RED
            print(f"  {i:>4}  0x{abs_byte:04x}  {name:<34}  "
                  f"{vn:>8.4f}  {va:>8.4f}  {col}{d:>+8.4f}{RESET}")


# Diff 

def cmd_diff(a: bytes, b: bytes, la: str = "A", lb: str = "B"):
    print(f"\n{BOLD}DIFF  {la}  vs  {lb}{RESET}")
    cmd_scan(a, b, threshold=0.02)



def main():
    ap = argparse.ArgumentParser(description="MetaHuman Animator LiveLink receiver")
    ap.add_argument('--port',    type=int, default=11111)
    ap.add_argument('--verbose', action='store_true')
    ap.add_argument('--log',     type=str, default=None)
    sub = ap.add_subparsers(dest='cmd')
    sub.add_parser('live')
    ia = sub.add_parser('info');  ia.add_argument('file')
    sa = sub.add_parser('scan');  sa.add_argument('neutral'); sa.add_argument('active')
    sa.add_argument('--threshold', type=float, default=0.02)
    da = sub.add_parser('diff');  da.add_argument('a'); da.add_argument('b')
    args = ap.parse_args()

    if args.cmd == 'info':
        cmd_info(Path(args.file).read_bytes(), args.file)
    elif args.cmd == 'scan':
        cmd_scan(Path(args.neutral).read_bytes(), Path(args.active).read_bytes(),
                 args.threshold)
    elif args.cmd == 'diff':
        cmd_diff(Path(args.a).read_bytes(), Path(args.b).read_bytes(), args.a, args.b)
    else:
        live_mode(args.port, args.verbose, args.log)

if __name__ == '__main__':
    main()