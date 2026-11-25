# X-T20 (fw 2.11) USB Tether Toolkit (Experimental)

> **Experimental.** Tested on one Fujifilm X-T20 on firmware **2.11** only.
> The camera-side change is a single RAM-only ARM32 word applied at SD-boot by
> FujiMod (`x70view`); nothing is written to flash. Pull the SD card and the
> camera is stock. Use at your own risk.

This repository holds the host-side Linux toolkit, INDI driver patch, udev
rule, focus preset helper, busy-recovery helpers, and hardware test notes for
tethering a Fujifilm X-T20 (fw 2.11) over ordinary USB PTP (`04cb:02d4`) with
`gphoto2` and INDI/Ekos (`indi_gphoto_ccd`).

No `x70view` source, decompilation, `xpp` build tools, or firmware/card binaries
are included here. Build the SD-boot card from the **FujiMod / x70view**
project (`usb-tether-xpp` mod).

## How the firmware patch works (offset/opcode summary)

The X-T20 menu has no `USB TETHER AUTO` option, even though the firmware still
carries that path (mode 1). When **PC CONNECTION MODE** is set to **USB RAW
CONV./BACKUP RESTORE** (mode 3), the camera already enumerates the full PTP
personality (`04cb:02d4`, including `InitiateCapture`, `InitiateOpenCapture`,
and Fuji PTP properties), and then runs a mode-3 check in the connect handler
that turns PC priority off and sets the RAW-conversion gate.

- **Target:** Fujifilm X-T20 firmware **2.11**
- **Patch:** at `0x014a5600` (right after `cmp r0, #3` at `0x014a55fc`), change
  the single 32-bit ARM instruction from `bne` (`0x1a00000a`) to unconditional
  `b` (`0xea00000a`).
- **Effect:** skips the RAW-conversion-only block on connect so the session
  behaves like USB TETHER AUTO. Disconnect handling is unchanged and restores
  camera priority; the stored menu setting stays at mode 3.

To build the SD-boot patch card (`FMPATCH.BIN`), use **FujiMod / x70view**'s
`usb-tether-xpp` mod and SD boot v2 loader.

## Safety (read before plugging in)

The USB mode used here (`USB RAW CONV./BACKUP RESTORE`) is a service-grade PTP
mode. Keep these rules in mind:

- **Use only `gphoto2`, INDI (`indi_gphoto_ccd`), or Ekos.** In this mode, the
  camera's PTP stack also accepts Fuji's firmware-upload opcodes
  (`0x900C`/`0x900D`) and settings backup/restore transfers (`SendObjectInfo`/
  `SendObject`). Do not point unknown scripts or tools at the camera in this
  mode.
- **Settings changed over USB stay on the camera.** ISO, white balance, image
  size, and other properties set by a host remain active after unplugging.
  Note your settings beforehand and restore them when done.
- **Never cut power while the camera is on.** Switch the camera off before
  disconnecting power (including dummy-battery / DC-coupler rigs), and switch
  off before unplugging USB when possible.
- **Use a dedicated USB port, not a shared hub.** Shared hubs can cause
  intermittent PTP hangs on Fuji bodies.
- **If a reply goes missing, reopen the session.** Close the host client (or
  disconnect the INDI device) and reconnect rather than sending more requests
  on a desynchronized session. If the camera stays stuck in PTP Device Busy
  (`0x2019`), run `./tools/xt20-release` once (see below).
- **Device Busy (`0x2019`) is normal for a moment** while a camera menu or Q
  menu is open, or right after autofocus.

## Setup

### 1. Boot the FujiMod SD card and set the camera mode

1. On the camera: **SET UP > CONNECTION SETTING > PC CONNECTION MODE = USB RAW
   CONV./BACKUP RESTORE**.
2. Build and prepare an SD-boot v2 card with the `usb-tether-xpp` mod using
   **FujiMod / x70view**.
3. Boot the mod card: pull the battery, reinsert it, then hold the **rear
   command dial + Delete** while switching the camera on.
4. Set the front focus selector to **M** if you want host-driven manual focus
   (`manualfocusdrive`). Exposure follows the camera dials as usual.
5. Plug in the USB cable on a direct port. Camera menus lock while a host holds
   the PTP session and return on disconnect or power-off.

To revert to stock, remove the SD card (or boot normally without holding the
buttons) and optionally switch `PC CONNECTION MODE` back.

### 2. Stop `gvfs-gphoto2-volume-monitor` from grabbing the camera (Linux)

GNOME/desktop `gvfs-gphoto2-volume-monitor` opens a PTP session on any device
carrying `ID_GPHOTO2`, which locks out `gphoto2` and INDI (`Could not claim the
USB device`). Choose one:

**Permanent udev rule (X-T20 `04cb:02d4` only):** installs `udev/69-xt20-tether-no-gvfs.rules`,
which clears `ID_GPHOTO2` while adding `TAG+="uaccess"` so non-root desktop
users keep USB permissions:

```sh
sudo install -m 0644 udev/69-xt20-tether-no-gvfs.rules /etc/udev/rules.d/
sudo udevadm control --reload
# Unplug and replug the camera, then verify ID_GPHOTO2 is empty and gphoto2 works:
udevadm info -q property -n /dev/bus/usb/$(lsusb -d 04cb:02d4 | awk '{print $2"/"substr($4,1,3)}') | grep ID_GPHOTO2
gphoto2 --auto-detect
```

To undo:

```sh
sudo rm /etc/udev/rules.d/69-xt20-tether-no-gvfs.rules
sudo udevadm control --reload
# Unplug and replug the camera
```

**Temporary no-root alternative (affects all cameras until logout):**

```sh
systemctl --user stop gvfs-gphoto2-volume-monitor.service
systemctl --user mask --runtime gvfs-gphoto2-volume-monitor.service
# ... tether ...
systemctl --user unmask --runtime gvfs-gphoto2-volume-monitor.service
systemctl --user start gvfs-gphoto2-volume-monitor.service
```

### 3. `gphoto2` CLI and focus presets (`tools/xt20_focus.py`)

```sh
gphoto2 --auto-detect                    # FUJIFILM X-T20, usb:...
gphoto2 --summary
gphoto2 --capture-image-and-download     # 6000x4000 JPEG (dial not on B)
gphoto2 --capture-preview                # single 640x480 preview frame
gphoto2 --set-config-value /main/imgsettings/iso=800
gphoto2 --set-config-value /main/imgsettings/whitebalance=Daylight
gphoto2 --get-config /main/imgsettings/imagesize
gphoto2 --set-config-value /main/actions/manualfocusdrive=515   # absolute position, MF only
gphoto2 --set-config /main/actions/autofocusdrive=1
```

Always use `--set-config-value` (not `--set-config`) for numeric
`manualfocusdrive` values, because the camera publishes `D171` as a 5-entry
enumeration and `--set-config` treats `0..4` as choice indexes.

`tools/xt20_focus.py` saves and restores named focus positions in
`~/.config/xt20-focus/positions.json` with read-back verification, bounded
correction moves, Device Busy (`-110`) doubling backoff, and one session reopen
on I/O errors:

```sh
./tools/xt20_focus.py get
./tools/xt20_focus.py save stars
./tools/xt20_focus.py set 515
./tools/xt20_focus.py goto stars
./tools/xt20_focus.py nudge -3
./tools/xt20_focus.py list
```

### 4. INDI / Ekos (`indi/fuji-stop-preview-v4.patch`)

Stock `indi-3rdparty` v2.2.0 `indi_gphoto_ccd` aborts on `STREAM_OFF` on Fuji
bodies because `gphoto_stop_preview` lacks the Fuji special case that
`gphoto_start_preview` has. Apply `indi/fuji-stop-preview-v4.patch` against
`indi-3rdparty` v2.2.0 (`patch -p0`):

- Calls `gp_camera_exit()` in both `gphoto_stop_preview` and
  `gphoto_start_preview` so every stream or exposure opens a fresh session at
  seqno 1 instead of failing with `0x2019` Busy or grabbing a 640x480 live-view
  frame as the still.
- Saves and restores `PrimaryCCD` frame bounds around `StartStreaming()` /
  `StopStreaming()` so stills after live view stay 6000x4000.
- Defaults `CCD_SD_CARD_ACTION` to `Delete` when `CaptureTargetSP` is absent on
  Fuji, clearing `/store_10000001` so leftover stills do not block the next
  `STREAM_ON`.
- Checks `gp_camera_capture` return codes and sends `d208=4` + `0x100e` on
  failed or timed-out captures.

**Important limit — use JPEG Fine, not RAW (`.raf`):** uncompressed `.raf`
files over 16 MiB (~48 MiB on X-T20) fail over USB. `GetObjectInfo`/`GetObject`
advertises the full size (e.g. `0x02fe1e00`), but the X-T20 sends only
`size & 0x00ffffff` bytes before `PTP_RC_OK`, causing a 20 s USB timeout
(`I/O problem`). Use **JPEG Fine** (`FORMAT_2` in INDI, ~13–15 MB). See
[`indi/FINDINGS.md`](indi/FINDINGS.md) for the packet-level diagnosis.

### 5. Recovering from stuck PTP Device Busy (`0x2019`)

If an aborted capture leaves the camera returning `PTP Device Busy` (`0x2019`)
on every preview/capture attempt, stop `indiserver` and run:

```sh
./tools/xt20-release
```

This sends `d208=4` followed by `opcode=0x100e,0x0,0x0`, which cleared stuck
busy on hardware without replugging. (`./tools/xt20-usb-reset` performs a
clean unheld `USBDEVFS_RESET` ioctl on `04cb:02d4`, which resets the Linux USB
node but does not clear the camera's internal busy state.)

## Tested on camera (2026-11-24) and known limits

Tested on one X-T20 (fw 2.11, XF 50-230mm, Linux host, camera booted with a
combined FujiMod X-T20 card):

- `gphoto2`: `--auto-detect`, `--summary`, `--capture-image-and-download`
  (6000x4000 JPEG), `--capture-preview` (640x480 JPEG), `liveviewsize=XGA`
  (1024x768), ISO/WB/image-size set & read back, bulb capture + download.
- `tools/xt20_focus.py`: `get`, `save`, `set`, `goto`, post-`autofocusdrive`
  `get`/`goto`, and 10 spaced moves (0 errors, read-back verified).
- `udev/69-xt20-tether-no-gvfs.rules`: verified across USB replug with
  `gvfs-gphoto2-volume-monitor` running.
- `indi_gphoto_ccd` v2.2.0 + `indi/fuji-stop-preview-v4.patch`: repeated
  `STREAM_ON` (640x480, ~48 fps) -> `STREAM_OFF` -> 1 s bulb cycles and
  `Force BULB = Off` (1 s) -> `On` -> stream -> bulb all produced full
  6000x4000 FITS stills (`FORMAT_2` JPEG Fine) in one session with no replug.
- `tools/xt20-release`: cleared stuck `0x2019` busy without replugging.

Known limits / not yet tested on camera:

- RAW `.raf` (>16 MiB) fails over USB (use JPEG Fine).
- `xt20_focus.py` busy-retry and session-reopen paths are tested only against a
  fake `gphoto2` harness (`tools/test_xt20_focus.py`).
- Device Busy while a camera menu is open, arbitrary CLI shutter/aperture
  writes, sky plate solving, and X RAW STUDIO / FUJIFILM X Acquire are untested.

Full checklist and findings: [`HW-TEST-CHECKLIST.md`](HW-TEST-CHECKLIST.md) and
[`indi/FINDINGS.md`](indi/FINDINGS.md).

## Credits

Built on earlier Fuji PTP research shared in the FujiMod community:

- **Daniel Cook** — Fuji wireless/USB tether notes (Get after Set, Device Busy
  while a menu is open, firmware-upload opcode warnings).
- **tiredboffin** — Fuji PTP notes (`gvfs-gphoto2` session lock, reopening the
  session after a lost reply, settings persistence after tethered changes).
- **FujiMod / `x70view` contributors** — X-T20 2.11 SD boot v2 loader and mod
  toolchain.
