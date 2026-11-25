#!/usr/bin/env python3
"""xt20_focus: save and restore X-T20 focus positions over USB (gphoto2 'manualfocusdrive').

Needs: gphoto2 on PATH, the X-T20 tethered over USB (X-T20 fw 2.11 USB tether SD-boot card, PC CONNECTION MODE =
USB RAW CONV./BACKUP RESTORE), focus selector on M. Close Ekos/INDI (or anything else holding the camera)
first, because only one program can talk to the camera at a time.

  xt20-focus get                 print the current focus position
  xt20-focus save stars          remember the current position as 'stars'
  xt20-focus goto stars          drive the lens back to 'stars' and verify by reading it back
  xt20-focus set 117             drive to a raw position
  xt20-focus nudge -3            move relative to the current position
  xt20-focus list                show saved positions
  xt20-focus rm stars            forget a saved position (local file only)
  xt20-focus info                dump the raw gphoto2 config for manualfocusdrive (debug)

Positions are stored in ~/.config/xt20-focus/positions.json (override with XT20_FOCUS_DB).
The value is written with --set-config-value, NOT --set-config: the camera publishes this property as a
5-entry enumeration, and gphoto2's --set-config treats an unknown small number (0..4) as a list INDEX.

Busy and lost replies: the camera answers PTP 0x2019 Device Busy (gphoto2: "PTP Device Busy",
error -110) while a menu or the Q menu is open and briefly after autofocus. Each gphoto2 call is
retried with a growing delay (XT20_FOCUS_BUSY_RETRIES, default 5; first delay XT20_FOCUS_BACKOFF
seconds, default 0.3, doubling). If a reply goes missing (I/O error, timeout, device gone), the
call is repeated once in a fresh gphoto2 process, which opens a new PTP session, instead of
sending more requests on the old one. Every move is read back and a mismatch is reported.
"""
import argparse, json, os, re, subprocess, sys, time
from datetime import datetime

KEY = os.environ.get('XT20_FOCUS_KEY', 'manualfocusdrive')
DB = os.path.expanduser(os.environ.get('XT20_FOCUS_DB', '~/.config/xt20-focus/positions.json'))
GPHOTO = os.environ.get('GPHOTO2', 'gphoto2')

BUSY_RETRIES = int(os.environ.get('XT20_FOCUS_BUSY_RETRIES', '5'))
BACKOFF = float(os.environ.get('XT20_FOCUS_BACKOFF', '0.3'))

# gphoto2 / libgphoto2 wording: PTP 0x2019 maps to GP_ERROR_CAMERA_BUSY (-110, "I/O in progress").
BUSY = re.compile(r'Device Busy|\(-110\b|I/O in progress', re.I)
# A reply that never came: GP_ERROR_IO (-7), GP_ERROR_TIMEOUT (-10), GP_ERROR_IO_USB_FIND (-52) and the PTP layer's words.
LOST = re.compile(r'\((-7|-10|-52)\b|I/O problem|Timeout reading|PTP I/O Error|PTP Timeout|'
                  r'Data expected|Response expected|Could not find the requested device', re.I)
# GP_ERROR_IO_USB_CLAIM (-53): another program holds the camera; retrying will not help.
CLAIMED = re.compile(r'\(-53\b|Could not claim', re.I)

def classify(p):
    text = (p.stderr or '') + (p.stdout or '')
    if p.returncode == 0: return 'ok'
    if CLAIMED.search(text): return 'claimed'
    if BUSY.search(text): return 'busy'
    if LOST.search(text): return 'lost'
    return 'error'

def gp(args, port=None, check=True):
    cmd = [GPHOTO] + (['--port', port] if port else []) + args
    busy = 0; reopened = False
    while True:
        p = subprocess.run(cmd, capture_output=True, text=True)
        kind = classify(p)
        if kind == 'busy' and busy < BUSY_RETRIES:
            delay = BACKOFF * (2 ** busy); busy += 1
            print(f"  camera busy (close any camera menu); retry {busy}/{BUSY_RETRIES} in {delay:.1f}s", file=sys.stderr)
            time.sleep(delay); continue
        if kind == 'lost' and not reopened:
            reopened = True
            print("  no reply from the camera; reopening the session", file=sys.stderr)
            time.sleep(max(1.0, BACKOFF * 3)); continue
        break
    if check and p.returncode != 0:
        hint = {'claimed': "\nAnother program holds the camera (Ekos/INDI, or gvfs-gphoto2-volume-monitor; see README.md for udev/gvfs setup).",
                'busy': "\nThe camera stayed busy. Close any camera menu and try again.",
                'lost': "\nThe camera stopped answering. Check the cable (no shared hub), or switch the camera off and on."}.get(kind, '')
        sys.exit(f"gphoto2 failed ({' '.join(cmd)}):\n{(p.stderr or p.stdout).strip()}{hint}")
    return p

def get_pos(port):
    out = gp(['--get-config', KEY], port).stdout
    m = re.search(r'^Current:\s*(-?\d+)\s*$', out, re.M)
    if not m:
        sys.exit(f"could not read {KEY}; gphoto2 said:\n{out.strip()}")
    return int(m.group(1))

def try_get(port, name):
    p = gp(['--get-config', name], port, check=False)
    m = re.search(r'^Current:\s*(.+?)\s*$', p.stdout, re.M)
    return m.group(1) if p.returncode == 0 and m else None

def set_pos(port, v):
    gp(['--set-config-value', f'{KEY}={int(v)}'], port)

def settle(port, target, wait):
    """Poll until the readback stops changing (or hits the target), up to `wait` seconds."""
    deadline = time.monotonic() + wait; last = None; stable = 0
    while True:
        time.sleep(0.4)
        v = get_pos(port)
        if v == target: return v
        stable = stable + 1 if v == last else 0
        last = v
        if stable >= 2 or time.monotonic() > deadline: return v

def drive(port, target, tol, retries, wait):
    start = get_pos(port)
    print(f"now {start}, target {target}")
    if abs(start - target) <= tol:
        print(f"already within ±{tol}; not moving"); return start
    v = start
    for attempt in range(retries + 1):
        set_pos(port, target)
        v = settle(port, target, wait)
        print(f"  move {attempt + 1}: read back {v} (error {v - target:+d})" + ('' if abs(v - target) <= tol else ', mismatch'))
        if abs(v - target) <= tol: break
    ok = abs(v - target) <= tol
    print(("OK" if ok else "NOT REACHED") + f": position {v}, target {target}, tolerance ±{tol}")
    if not ok: sys.exit(2)
    return v

def load():
    try:
        with open(DB) as f: return json.load(f)
    except FileNotFoundError: return {}

def store(db):
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    tmp = DB + '.tmp'
    with open(tmp, 'w') as f: json.dump(db, f, indent=2, sort_keys=True); f.write('\n')
    os.replace(tmp, DB)

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--port', help='gphoto2 --port, e.g. usb:001,012 (default: auto)')
    ap.add_argument('--tol', type=int, default=0, help='accepted error in position units (default 0)')
    ap.add_argument('--retries', type=int, default=2, help='extra correction moves if the lens lands off target (default 2)')
    ap.add_argument('--wait', type=float, default=6.0, help='seconds to wait for a move to finish (default 6)')
    ap.add_argument('cmd', choices=['get', 'save', 'goto', 'set', 'nudge', 'list', 'rm', 'info'])
    ap.add_argument('arg', nargs='?')
    a = ap.parse_args()
    db = load()
    if a.cmd == 'list':
        if not db: print(f"no saved positions ({DB})")
        for k, r in sorted(db.items()):
            extra = ', '.join(f"{x}={r[x]}" for x in ('focallength', 'lens') if r.get(x))
            print(f"{k:12s} {r['position']:6d}   saved {r['saved']}" + (f"   ({extra})" if extra else '') + (f"   note: {r['note']}" if r.get('note') else ''))
    elif a.cmd == 'rm':
        if not a.arg or a.arg not in db: sys.exit(f"no saved position named {a.arg!r}")
        del db[a.arg]; store(db); print(f"removed {a.arg}")
    elif a.cmd == 'get':
        print(get_pos(a.port))
    elif a.cmd == 'info':
        print(gp(['--get-config', KEY], a.port).stdout.strip())
    elif a.cmd == 'save':
        if not a.arg: sys.exit('usage: xt20-focus save NAME')
        v = get_pos(a.port)
        rec = dict(position=v, saved=datetime.now().astimezone().strftime('%Y-%m-%d %H:%M %Z'))
        fl = try_get(a.port, 'focallength'); rec.update(focallength=fl) if fl else None
        old = db.get(a.arg); db[a.arg] = rec; store(db)
        print(f"saved {a.arg} = {v}" + (f" (was {old['position']})" if old else '') + f"  -> {DB}")
    elif a.cmd == 'goto':
        if not a.arg or a.arg not in db: sys.exit(f"no saved position named {a.arg!r}; try: xt20-focus list")
        r = db[a.arg]
        fl = r.get('focallength')
        if fl:
            now = try_get(a.port, 'focallength')
            if now and now != fl:
                print(f"WARNING: saved at focal length {fl}, camera reports {now}. On a zoom lens the infinity position moves with zoom.")
        drive(a.port, int(r['position']), a.tol, a.retries, a.wait)
    elif a.cmd == 'set':
        if a.arg is None or not re.fullmatch(r'-?\d+', a.arg): sys.exit('usage: xt20-focus set POSITION')
        drive(a.port, int(a.arg), a.tol, a.retries, a.wait)
    elif a.cmd == 'nudge':
        if a.arg is None or not re.fullmatch(r'[+-]?\d+', a.arg): sys.exit('usage: xt20-focus nudge [+|-]N')
        cur = get_pos(a.port); drive(a.port, cur + int(a.arg), a.tol, a.retries, a.wait)

if __name__ == '__main__':
    main()
