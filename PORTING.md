# Porting USB PTP tethering to other Fujifilm bodies

This is a “how we actually did it” guide for unlocking ordinary USB PTP
tethering (`gphoto2`, INDI, Ekos) on a Fujifilm body that already has a hidden
or half-finished tether path, but does not offer a working USB TETHER mode in
the menu.

It is written from one successful port: **Fujifilm X-T20 firmware 2.11**, one
camera, November 24, 2026. Everything marked “on the X-T20” is measured.
Everything about other bodies is a reasoned guess until someone repeats the
same checks on that body and firmware.

The camera-side change itself is built with **FujiMod / [x70view](https://github.com/justjake/x70view)**
(the `usb-tether-xpp` mod and the SD boot v2 loader). This public repo does
not contain that source, any decompilation, or any firmware or card binaries.
Use this write-up as a map, then do the work in FujiMod.

Host-side helpers that already exist here (`indi/fuji-stop-preview-v4.patch`,
`udev/69-xt20-tether-no-gvfs.rules`, `tools/xt20_focus.py`, `tools/xt20-release`,
`tools/xt20-usb-reset`) may transfer to other Fuji bodies with only a VID/PID
or manufacturer-string tweak — or they may not. Retest each one.

## 1. What we were trying to unlock

The goal is not a new capture engine. The firmware already knows how to:

- enumerate a full PTP “PC shoot” personality
- accept `InitiateCapture` / `InitiateOpenCapture`
- expose Fuji properties (priority mode, capture control, manual focus, ISO, WB)
- autofocus, shoot, and hand a JPEG back over USB

On the X-T20, that path is the X-T2 family’s **USB TETHER AUTO** mode (stored
USB mode 1). The firmware still has it. The X-T20 menu does not offer it.

What the X-T20 menu *does* offer is **PC CONNECTION MODE = USB RAW
CONV./BACKUP RESTORE** (stored USB mode 3). In that mode the camera already
enumerates the full PTP personality — VID/PID `04cb:02d4`, including
`InitiateCapture` — and then, on connect, a mode-3-only block turns PC
priority off and raises a RAW-conversion flag. After that, `D207`
(PriorityMode) answers `0x200a` and `InitiateCapture` answers `0x2002`, so
`gphoto2` can see the camera but cannot take control or shoot.

The firmware patch is one ARM32 instruction: at `0x014a5600`, right after
`cmp r0, #3` at `0x014a55fc`, change `bne` (`0x1a00000a`) to unconditional
`b` (`0xea00000a`). The mode-3-only block is skipped. Mode 3 then behaves like
hidden mode 1. Disconnect handling is left alone and still restores CAMERA
priority. The stored setting stays at 3. Nothing is written to flash; the
change lives in RAM for that boot only.

An earlier idea — flip the “keep the buttons unlocked” immediate a few bytes
later — did **not** open capture. That was a useful dead end: the capture
refusal is the RAW/backup flag, not the control-priority flag. If you go
looking on another body, do not stop at “the UI locks on connect.”

## 2. Prerequisites and safety

Do this work on a body and firmware you are willing to power-cycle a lot.
Prefer a RAM-only SD-boot loader (FujiMod SD boot v2 on the X-T20) so pulling
the card returns the camera to stock.

**Before any camera session**

- Back up the SD card you will boot (copy the whole card image, or at least
  `FMPATCH.BIN` / `ffboot.bin` and any `FUJIMOD/` files you care about).
- Note the camera’s current settings (ISO, WB, image size, focus position, PC
  CONNECTION MODE). Properties set over USB stay on the camera after you
  unplug.
- Use a **direct USB port**, not a shared hub. Shared hubs have caused
  intermittent PTP hangs on Fuji bodies.
- Have a recovery plan written down before you plug in (see below).
- Work with **one signal at a time** on a live camera. Do not fire live view,
  a still, a config write, and a reset overlapping each other.

**While the camera is in USB RAW CONV./BACKUP RESTORE**

This is a service-grade PTP mode, not a toy. The PTP stack also accepts
Fuji’s **firmware-upload opcodes `0x900C` and `0x900D`**, plus settings
backup/restore transfers (`SendObjectInfo` / `SendObject`). Use only
`gphoto2`, INDI (`indi_gphoto_ccd`), or Ekos. Do not point unknown scripts,
vendor “backup” tools, or firmware flashers at the camera in this mode.
Nothing in this repo sends `0x900C`/`0x900D`. Do not add that.

**Recovery (in this order)**

1. Close the host program (or disconnect the INDI device) and open a fresh
   PTP session. A missing reply often means the session sequence number is
   stale; more requests on the old session make it worse.
2. If every command returns PTP Device Busy (`0x2019`), stop `indiserver` and
   try the release sequence in `tools/xt20-release`: set `d208=4`, then
   `opcode=0x100e,0x0,0x0`. On the X-T20 this cleared a mid-shot hang without
   a replug. A Linux `USBDEVFS_RESET` (`tools/xt20-usb-reset`) reset the USB
   node cleanly but **did not** clear the camera’s internal busy state.
3. If release fails twice, spaced: switch the camera **off**, then unplug USB
   (and the dummy battery / DC coupler, if you use one). Never cut power
   while the camera is on. Never use `udisksctl power-off` on the SD reader.
4. Pull the SD card, boot stock, and confirm the camera is itself again.

**Logs.** Never run `indiserver -vvv` (or any debug logger) into an uncapped
file. Pipe through a cap such as `| head -c 200M` and stop the server when
the test ends. An uncapped debug log filled a disk during this work.

## 3. How the hidden mode and the PTP personality were found

On the X-T20 the search was roughly:

1. **Read the menu and the stored USB-mode setting.**
   `SET UP > CONNECTION SETTING > PC CONNECTION MODE` is backed by a settings
   parameter (on the X-T20, setp `0xBE`). The values that mattered were:

   - mode 1 — USB TETHER AUTO, present in firmware, **absent from the menu**
   - mode 3 — USB RAW CONV./BACKUP RESTORE, the mode the menu does offer

   Other bodies will use different menu wording and maybe different numbers.
   Search firmware strings and the settings table for `USB RAW CONV`,
   `BACKUP RESTORE`, `USB TETHER`, `PC CONNECTION`, and nearby mode enums.

2. **Plug in stock (no patch) in each mode and look at USB enumeration.**
   Record VID/PID, bInterfaceClass, and a PTP `GetDeviceInfo` (`0x1001`).
   On the X-T20, mode 3 already showed `04cb:02d4` and advertised
   `InitiateCapture` (`0x100e`), `InitiateOpenCapture` (`0x101c`), and a large
   Fuji property list. So the personality was already the tether one. The
   failure was later, on connect.

   Expect the product ID to change by body (`04cb:xxxx`). Do not copy
   `02d4` into a udev rule for a different camera.

3. **Try the host sequence stock, before writing a patch.**
   Open a session, set PriorityMode `D207=2` (PC), then `InitiateCapture`.
   On stock X-T20 mode 3, `D207` came back `0x200a` and `InitiateCapture`
   came back `0x2002`. That is the “I see the camera, but it will not
   shoot” signature.

4. **Compare with hidden mode 1** (in the emulator we poked the stored USB
   mode in RAM; on a camera, only do this if you have a safe, reversible way
   to set a hidden enum). Stock mode 1 accepted `D207` and `InitiateCapture`
   and returned a 6000×4000 JPEG. That told us the capture path was already
   finished — we needed the mode-3 connect path to stop special-casing
   itself, not a new PTP implementation.

Useful PTP names to search and to log, on any body:

| What | Why it matters |
| --- | --- |
| VID `04cb`, product ID | udev rules and “is this the tether personality?” |
| `GetDeviceInfo` (`0x1001`) ops `0x100e`, `0x101c`, `0x101b` | capture, open-capture / live view, optional partial object |
| `D207` PriorityMode | PC vs CAMERA priority |
| `D208` capture control | AF / shoot / release values (`0x0200`, `0x0304`, `0x0004` on the X-T20) |
| `D171` / `manualfocusdrive` | absolute MF position, if the body publishes it |
| PTP responses `0x2001` (OK), `0x2002` (General Error), `0x200a` (Access Denied), `0x2019` (Device Busy) | gate vs hang vs “menu is open” |

Credits for several of these habits: Daniel Cook’s Fuji tether notes (Get
after Set, Device Busy while a menu is open, firmware-upload opcodes) and
tiredboffin’s PTP notes (`gvfs` session lock, reopen the session after a
lost reply, settings persist after tethered changes).

## 4. Finding the gating branch in the firmware

This is the camera-side core of the port. Do it in FujiMod / x70view with
that project’s decompiler, symbol database, and word-only hook tools. Do
not ship firmware images, decompilation dumps, or built card files in a
public toolkit repo.

On the X-T20 we looked for the function that runs when a PC-shoot USB
session comes up (in this firmware it is named `ui_shooting_connect_action`,
driven by a “shooting connect” UI event). The connect argument:

1. Marks the body as in PC-record mode for every PC USB mode.
2. Reads the stored USB mode (setp `0xBE`) and **compares it with 3**
   (`cmp r0, #3` at `0x014a55fc`).
3. If the mode is *not* 3, it branches over the next block (`bne` at
   `0x014a5600`).
4. If the mode *is* 3, it falls through: force CAMERA-side (PC priority
   off) and set the private RAW/backup flag.
5. Later capture and property gates read that flag, which is why `D207`
   and `InitiateCapture` are refused only in mode 3.

Hidden mode 1 never enters that block, which is why stock mode 1 already
works.

**What to search for on another body**

- Cross-references to the USB-mode setting (the analogue of setp `0xBE`).
- A compare with the RAW-CONV / backup-restore mode number, immediately
  followed by a `bne`/`beq` that skips or enters a “set RAW/backup flag /
  force priority” block.
- Callers or callees named like `input_raw_backup_set`,
  `input_pc_control_mode_set`, `rec_capture_available`, or strings such as
  `SYS_USB_PC_SHOOT` / `USB TETHER`.
- The disconnect / unplug path. On the X-T20 it already restored CAMERA
  priority and cleared both flags for modes 1 and 3. We left it alone.
  If you change connect, make sure unplug still cleans up.

**How we chose the one-word patch**

The smallest change that made mode 3 identical to mode 1 was to turn that
`bne` into an unconditional `b`, so even mode 3 skips the RAW-conversion
block. One code word, no persistent writes, stored setting stays 3.

Confirm your candidate the same way, in this order:

1. **Static:** the instruction you will replace really is the branch after
   the mode compare, and the fall-through really sets the flag that the
   capture/property gates read.
2. **Control build:** same card with the *stock* word, mode 3: `D207` and
   `InitiateCapture` still refused. If the control already works, you are
   looking at the wrong gate (or this body does not need a patch).
3. **Patched mode 3:** `D207` and `InitiateCapture` accepted, one object
   downloaded, nothing unexpected written to the SD card, unplug restores
   CAMERA priority.
4. **Stock hidden mode 1**, if you can reach it safely (emulator poke, or a
   documented hidden setting): should match the patched mode-3 result,
   ideally byte-identical for a fixed test JPEG. That is the best evidence
   you re-enabled a stock path rather than inventing a new one.

If the body already offers USB TETHER AUTO in the menu and it already
works, you do not need this patch. If mode 3 is refused *and* there is no
mode-1 path in the firmware, this exact trick may not exist — start again
from enumeration and the connect handler, and do not force a `bne→b` at a
guessed offset.

Offsets, mode numbers, and hook addresses will move between bodies and
even between firmware versions of the same body. `0x014a5600` is an X-T20
2.11 fact, not a constant you can transplant.

## 5. Using FujiMod / x70view to build and prove a patch

Work in the FujiMod / x70view tree for the target body:

- Declare the connect-action symbol and pin the stock bytes of the
  instruction you will change (so a firmware update cannot silently
  mismatch).
- Prefer a **word-only** RAM patch applied by the SD boot loader. On this
  port, a word-only mod linked an empty region and the patch builder at
  first refused the card as “empty or overlapping XPP mod runs”; that is a
  toolchain detail to watch if your patch also has no payload bytes.
- Keep the mod **opt-in** (not in the default body recipe) until it has
  been tested on a camera.
- Rehearse over **modeled USB** if the body has an emulator board: boot to
  REC, set the USB mode, plug in, and replay the libgphoto2 Fuji capture
  sequence (open session, `D207=2`, AF, shoot, `GetObject`, `DeleteObject`,
  unplug). Keep a control run and, if possible, a stock mode-1 run.

Build a **tether-only card** for the rehearsal even if your daily camera
card also carries other mods. On the X-T20, emulator proof used the
tether-only card; the first hardware sessions used a combined card. The
tether-only card has not yet been on the physical X-T20, and that is a
gap worth closing on any port.

## 6. Emulator testing — and where it lies

The emulator was decisive for the *connect gate* and almost silent about
*live view*.

What the X-T20 modeled-USB rehearsal caught well:

- VID/PID and advertised ops
- `D207` / `InitiateCapture` accepted vs refused
- A 6000×4000 JPEG object on the success path, none on the control path
- No files written to the virtual SD card
- Unplug restored CAMERA priority

What it did **not** catch:

- **USB live view.** `InitiateOpenCapture` plus object `0x80000001` never
  produced a frame, and the session then stopped answering. Stock hidden
  mode 1 did the same thing in the emulator, so this was an emulator
  limit (or an unmodeled path), not a patch bug. On the real camera,
  live view worked at 640×480 and at XGA (1024×768).
- Host-side problems: `gvfs` grabbing the device, INDI `STREAM_OFF`
  aborting the driver, frame-size leftover after streaming, leftover
  RAM-tether files, the RAW `GetObject` truncation, stuck `0x2019` after
  an aborted shot. All of those showed up only on hardware.

Treat a green emulator run as necessary, not sufficient. Do not debug live
view against a model that cannot produce a frame. And do not skip the
control build: a rehearsal that only runs the patched word cannot tell you
that you are still looking at stock behaviour.

## 7. Hardware bring-up order

Once you have a RAM-only card and a backup, use a fixed order. Stop at the
first failure, recover, and only then change one variable.

On the camera: set **PC CONNECTION MODE = USB RAW CONV./BACKUP RESTORE**,
boot the mod card the usual FujiMod way, focus selector on **M** if you
want host MF, exposure on the dials, USB on a direct port.

On the host, one command at a time:

1. **Detect.** `lsusb -d 04cb:` and `gphoto2 --auto-detect`. Confirm the
   product ID you expected. If `Could not claim the USB device`, fix `gvfs`
   (section 8) before anything else.
2. **Summary.** `gphoto2 --summary` — body name and firmware version.
3. **Still capture + download.**
   `gphoto2 --capture-image-and-download`.
   Confirm dimensions (on the X-T20, 6000×4000 JPEG). If the dial is on
   **B**, a non-bulb shoot may return PTP General Error; use a bulb capture
   or take the dial off B. Do not confuse that with a failed patch.
4. **Single preview.** `gphoto2 --capture-preview`.
5. **Config set and read back.** ISO, white balance, image size. Confirm
   the values stuck, and remember to put them back afterwards.
6. **Focus.** Read `manualfocusdrive` (or the body’s equivalent), set a
   nearby value, read it back, then restore. Then one `autofocusdrive`,
   wait a moment (Device Busy right after AF is normal), and read again.
7. **Bulb.** A short bulb (1 s is enough) with download. On the X-T20 the
   JPEG arrived about 12–13 seconds after a 1 s bulb, so give the download
   a long timeout (≥ 20 s).
8. **Only then INDI / Ekos.** Connect `indi_gphoto_ccd`. `STREAM_ON` and
   confirm frames. `STREAM_OFF` and confirm the driver stays up. Then one
   still, and check it is full resolution, not a leftover live-view frame.
   Repeat the cycle in one session without replugging.

A combined “everything at once” script will hide which step broke the
camera. The X-T20 bring-up spent a long time stuck in `0x2019` after an
interrupted still; doing one action at a time is how we isolated it.

## 8. Host-side gotchas we hit (and what to try first)

These were the surprises after the firmware word was already correct.
Several are likely shared by other Fuji bodies; none are proven past the
X-T20.

### 8.1 Desktop `gvfs` claims the camera

`gvfs-gphoto2-volume-monitor` opens a PTP session on any device with the
udev property `ID_GPHOTO2`, fails, and keeps the session. `gphoto2` / INDI
then print `Could not claim the USB device`. `UDISKS_IGNORE` does not fix
this.

On the X-T20 we install `udev/69-xt20-tether-no-gvfs.rules`, which clears
`ID_GPHOTO2` on `04cb:02d4` and adds `TAG+="uaccess"` so a desktop user
keeps access. After install, unplug and replug (a reload alone is not
enough). For a port, copy the rule and change the product ID. The no-root
alternative is a session-only
`systemctl --user mask --runtime gvfs-gphoto2-volume-monitor.service`.

### 8.2 Stock INDI `STREAM_OFF` aborts the driver

In `indi-3rdparty` v2.2.0, `gphoto_start_preview` special-cases Fuji
(no `viewfinder_widget`) but `gphoto_stop_preview` does not. `STREAM_OFF`
returns failure and a later `join()` on an already-joined live thread
aborts `indi_gphoto_ccd` with `std::system_error`.

Until a fix is in upstream INDI, apply `indi/fuji-stop-preview-v4.patch`
against v2.2.0 (`patch -p0`). The patch keys off the manufacturer string
containing `Fuji`, so it is written for Fuji bodies in general, but it has
only been run on this X-T20. Do not `STREAM_OFF` on the stock binary.

### 8.3 After live view, stills come out 640×480

Two separate bugs stacked here. First, a no-op Fuji `stop_preview` left
libgphoto2’s open capture (`0x101c`) running. The next bulb start failed
silently, and the driver grabbed live-view object `0x80000001` as the
“still.” Closing the preview with `gp_camera_exit()` (TerminateOpenCapture
+ CloseSession, next call opens a fresh session at sequence 1) fixed that.

Second, even with a real 6000×4000 JPEG in hand, `streamLiveView()` had
called `PrimaryCCD.setFrame(0, 0, previewW, previewH)` and
`StopStreaming()` never restored the pre-stream frame, so `grabImage()`
cropped the full JPEG down to 640×480. v4 saves and restores those bounds.

If a “still” is letterboxed preview-sized, check both: did the bulb
actually start, and did INDI restore `PrimaryCCD`’s frame?

### 8.4 Leftover files in the RAM tether buffer (`0x2019` on the next live view)

Fuji USB tether often has no `capturetarget` widget; stills live in RAM
(`/store_10000001` on the X-T20). Leaving a file there, or calling
`capture_preview` in the same libgphoto2 session right after a still, made
the next `InitiateOpenCapture` (`0x101c`) and even `D207` return Device
Busy `0x2019`. v4 defaults `CCD_SD_CARD_ACTION` to **Delete** when that
widget is missing, and also `gp_camera_exit()`s before starting preview.

If `STREAM_ON` works once and fails after the first still, list and delete
the RAM store before chasing firmware.

### 8.5 Aborted capture leaves the body busy until “the release”

An interrupted Fuji capture (failed shoot on bulb, or live view started
mid-exposure) can leave the camera mid-release. After that, *every*
operation in a fresh session still returns `0x2019`. This is not a missing
`CloseSession`.

On the X-T20, this cleared it without a replug:

```sh
gphoto2 --set-config d208=4
gphoto2 --set-config opcode=0x100e,0x0,0x0
```

(`tools/xt20-release` is that sequence; the second step erroring when the
camera is already idle is harmless. Run it once, do not loop it.) A USB
port reset did not help. Try this before you pull the cable, and check
whether `d208=4` is even a valid capture-control value on the new body.

### 8.6 RAW `.raf` files over 16 MiB fail over USB

This one may or may not follow you to other bodies, but it is easy to
waste a day on.

On the X-T20, a ~48 MiB `.raf` advertised `GetObjectInfo` / `GetObject`
size `0x02fe1e00`. The camera then sent only `size & 0x00ffffff` bytes
(`0x00fe1e00`, 16,653,824) and immediately the 12-byte `PTP_RC_OK`.
libgphoto2 treated the OK packet as payload and blocked until a 20 s
timeout (`I/O problem`). libgphoto2 also disables `GetPartialObject`
(`0x101b`) for all Fuji bodies, even when the camera advertises it.

JPEG Fine (~13–15 MB, under 16 MiB) transferred in a fraction of a second
and decoded to a full 6000×4000 still. For bring-up, **use JPEG Fine**.
If you need RAW, try saving it to the SD card and copying it later, or
experiment carefully with `0x101b` chunked reads — we have not proven
either path yet. See [`indi/FINDINGS.md`](indi/FINDINGS.md).

### 8.7 A few smaller X-T20 specifics

- After `autofocusdrive`, the next request can get Device Busy; wait or
  retry with backoff (`tools/xt20_focus.py` does this).
- `manualfocusdrive` is published as a five-entry enumeration. Use
  `gphoto2 --set-config-value`, not `--set-config`, or a small position
  is treated as a choice index.
- libgphoto2’s X-T20 entry has capture flags 0; the CLI and INDI still
  worked. Do not assume a missing flag means “unsupported.”
- Camera menus lock while a host holds the session; that is stock
  behaviour with PC priority, not a hang.

## 9. Test checklist template

Copy this for each new body and firmware. Fill in every row with “yes /
no / not run” and a short note. A patch that has only an emulator receipt
is not ready to share as “working.”

**Setup**

- [ ] Body, firmware version, lens
- [ ] Card backed up; recovery steps written down
- [ ] PC CONNECTION MODE set to USB RAW CONV./BACKUP RESTORE (or the
      local equivalent); recorded the stored mode number
- [ ] RAM-only SD-boot card with *only* the tether word, plus a stock
      control card
- [ ] Direct USB port; host OS and `gphoto2` / INDI versions noted
- [ ] udev / `gvfs` handled; `ID_GPHOTO2` checked after a replug

**Firmware gate (emulator, then camera)**

- [ ] Stock mode 3: `D207` / `InitiateCapture` refused (control)
- [ ] Patched mode 3: session, `D207=PC`, AF, shoot, object downloaded
- [ ] Unplug restores CAMERA priority; stored USB mode still the stock
      menu value
- [ ] Stock hidden tether mode, if reachable, matches the patched result
- [ ] Nothing unexpected written to the SD card during a tethered JPEG

**gphoto2 on the camera**

- [ ] `--auto-detect` and `--summary` (name + firmware)
- [ ] `--capture-image-and-download` at full still size
- [ ] `--capture-preview`; plus any extra live-view sizes the body offers
- [ ] ISO / WB / image size set and read back
- [ ] Manual focus set and read back; one AF then a delayed get
- [ ] Short bulb + download (long download timeout)

**INDI / Ekos (patched driver only)**

- [ ] Connect: body, firmware, lens, focuser if expected
- [ ] `STREAM_ON` frames at the expected preview size
- [ ] `STREAM_OFF` leaves the driver up (stock v2.2.0 will not)
- [ ] Still after `STREAM_OFF` is full resolution, not preview-sized
- [ ] Second `STREAM_ON` → `STREAM_OFF` → still in the same session, no
      replug
- [ ] JPEG Fine works; RAW over USB measured (pass, or truncated, or
      written only to the card)

**Recovery**

- [ ] Release sequence (`d208=4` + `0x100e`, or the body’s equivalent)
      clears a stuck `0x2019` without a replug — or documented that it
      does not
- [ ] Camera off, then unplug, returns to a healthy stock boot without
      the card

**Still optional / easy to over-claim**

- [ ] Tether-only card on the physical camera (not just a combined card)
- [ ] Device Busy while a camera menu is open
- [ ] Sky frame + plate solve
- [ ] X RAW STUDIO / FUJIFILM X Acquire in this USB mode (retest; this
      mode is also used for in-camera RAW conversion on other bodies)
- [ ] Arbitrary shutter / aperture writes over PTP

## 10. Sharing results

Test heavily before you upload. A firmware word that boots is easy to
publish and hard to walk back if it is wrong on someone else’s camera.

When you do share:

- Open a **draft** pull request against FujiMod / x70view, marked
  experimental, with the exact body and firmware, the instruction you
  changed (address + stock word + new word), emulator receipts, and an
  honest camera checklist. Separate “tested on camera” from “emulator
  only” from “host test only.”
- Do not add firmware images, dumps, or built card files to the PR.
- Credit prior PTP notes you relied on, and mention nearby work that uses
  the same USB mode (on this project, in-camera RAW conversion lives in
  justjake/fujimod#259 and justjake/x70view#436). Those bodies should be
  left alone if your hook is body-specific; if you patched a shared file,
  say so.
- If you only have host-side findings (a udev product ID, a RAW
  truncation, a release opcode), a short issue or a follow-up on an
  existing draft is enough. Please do not present an X-T20 fact as a
  universal Fuji fact.

Questions or corrections about this X-T20 port can go on the draft PR
([justjake/x70view#1589](https://github.com/justjake/x70view/pull/1589))
if you have access, or on this toolkit repo. The X-T20 patch is still
experimental: one camera, firmware 2.11 only.
