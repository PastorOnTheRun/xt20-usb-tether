# X-T20 (fw 2.11) USB Tether Toolkit (Experimental)

> **Experimental.** Tested on one Fujifilm X-T20 on firmware **2.11** only.
> The camera-side change is a single RAM-only ARM32 word applied at SD-boot by
> FujiMod (`x70view`); nothing is written to flash. Pull the SD card and the
> camera is stock. Use at your own risk.

This repository holds the host-side Linux toolkit, INDI driver patch, udev
rule, focus preset helper, busy-recovery helpers, and hardware test notes for
tethering a Fujifilm X-T20 (fw 2.11) over ordinary USB PTP (`04cb:02d4`) with
`gphoto2` and INDI/Ekos (`indi_gphoto_ccd`).

No `x70view` source, decompilation, `xpp` build tools, official FujiMod card
binaries, or Cap12 builds are included here. Official Cap12 has to be
downloaded from the FujiMod / FujiHack Discord; this repo only ships a splice
script that adds the USB tether hook (and, optionally, the red-night overlay)
to that official `FMPATCH.BIN`.

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

To build an SD-boot card, either use **FujiMod / x70view**'s `usb-tether-xpp`
mod, or start from official **Cap12** and run the splice in
[Building a Cap12 SD card](#building-a-cap12-sd-card-optional) below.
The optional red-night overlay is documented in
[Red night screen add-on](#red-night-screen-add-on-optional).

If you want to unlock the same ability on another Fuji body or firmware,
see [PORTING.md](PORTING.md) for a step-by-step write-up of how this X-T20
2.11 port was found, tested, and what broke on the host side.


## Building a Cap12 SD card (optional)

Official **Cap12** (iXralum, `MariMul-xt20-cap12` at `8d14a2ce19`) is the
current FujiMod development card for the X-T20 on firmware **2.11**. It adds
the Focal UI, a new bootloader, Q-menu save, C1–C7 marks, and other mods.
This repository does **not** redistribute official Cap12 binaries: FujiMod
does not circulate ready-made builds outside its own channels, and Cap12
contains derived firmware data.

Get the official zip yourself from the [FujiMod / FujiHack
Discord](https://discord.gg/UZXDktvAZP), then add the USB tether hook with
`tools/splice_cap12.py`. That is the same single-instruction RAM patch
described above (`0x014a5600`, `bne` → `b`). Nothing is written to camera
flash.

The Cap12 + tether combination has been tested on the **emulator only**.
Real-camera testing is still pending. The earlier hardware results in
[Tested on camera](#tested-on-camera-2026-11-24-and-known-limits) used a
different (cap11-era) FujiMod card.

**Firmware 2.11 only.** Check the version screen (hold DISP/BACK while
switching the camera on). Do not use this card on any other firmware, and
never start a firmware update, service / JIG mode, or PC firmware update
with this card in the camera.

### 1. Verify the official zip

From `fujimod-cap12-xt20-2.11.zip` (SHA-256
`ce50b683a11664fbbebbebefd35a1c6876dcfb207bd3abdac486dce75ab7e04d`), check:

| File | SHA-256 |
| --- | --- |
| `card/FMPATCH.BIN` | `d2e237d048be038bd13ec9735488f34e6c3b9c438180c6c6dd899894966dcbba` |
| `card/ffboot.bin` | `8b177b2247fd13bbbe3d0b4165c8d7e56b4538b1fbcb3918778fa017fc9e6f46` |
| `card/ffsys.bin` | `d72448807cd394f157e31f38f1fb8eac4f628b7ddb674fa1fc1c447c68103d8e` |

### 2. Splice the USB tether hook

```sh
python3 tools/splice_cap12.py --tether path/to/official/FMPATCH.BIN \
    -o FMPATCH.BIN
# expected sha256:
# 99a1c0106d91217c0a8464970e88884d5b257a37d63a7011db01358d2f9a7540
```

The script refuses to run if the input hash is not official Cap12. It only
adds the group-1 run at `0x014a5600`. Official `ffboot.bin`, `ffsys.bin`,
`manifest.json`, recipes, and the rest of the Cap12 card stay as you
downloaded them.

### 3. Copy the card and boot the mods

Copy the official Cap12 `card/` contents to the **root** of an
in-camera-formatted SD card, replacing only `FMPATCH.BIN` with the spliced
file. Keep any existing `FUJIMOD/SETTINGS.JSN` already on the card; this
package does not ship one.

Boot the mods the Cap12 way: camera off, card inserted, **hold the rear
command dial pressed in and the Delete (trash) button**, switch the camera
on, and release both after about three seconds. Switching on **normally**
(no key combination), or starting **without the card**, runs stock firmware
— that is also the recovery path if a boot does not come up. If the camera
freezes, remove the battery, wait a few seconds, and put it back.

Set **PC CONNECTION MODE** to **USB RAW CONV./BACKUP RESTORE** as in
[Setup](#setup) below, then use `gphoto2` or INDI the same way as on the
earlier card.

### Known Cap12 limits

- One user in the FujiMod Discord has reported official Cap12 itself failing
  to boot. This splice uses that same official `ffboot.bin` bootloader; the
  emulator does not execute that 73 KiB loader path.
- Focal UI is still unfinished in official Cap12 (some stock-menu flashes,
  leftover placeholder Q tiles). It can be turned off under USER SETTINGS →
  MOD SETTING → FEATURE DISPLAY.
- The MOVIE-recording issue reported on Cap11 was not retested here.
- Use a **stock film** (PROVIA, etc.) in the current settings, C1–C7, and
  film bracketing before removing the card, so a later stock boot is not
  left on an added film the body does not know.

## Red night screen add-on (optional)

An optional **RED NIGHT SCREEN** overlay for astro and other dark-site work:
it tints the shooting HUD, menus, and live view red, and leaves captured
photos in normal colour. On the camera it is
**SET UP > SCREEN SET-UP > RED NIGHT SCREEN** with three choices:

- **OFF** — no tint
- **RED** — full red overlay
- **RED DIM** — dimmer red overlay

The choice is stored in `FUJIMOD/SETTINGS.JSN` under the `red_night` section
if that file already exists on the card. This repository does not ship a
`SETTINGS.JSN`, so your other mod settings are left alone. After a mod boot,
a saved RED / RED DIM choice is applied on the first shooting screen (no
need to open the menu first).

This is a standalone relocation of the overlay into the free RAM at the end
of official Cap12 (`0x2C52A00`), so it does not overwrite Cap12's Focal UI
or cached-arena data. The OSD hook at `0xcc223c` (already used by Cap12)
is chained: our thunk recolors, then Cap12's handler and stock firmware
still run.

### Status and limits

- **Tested on the emulator only. Real-camera testing of this Cap12 port is
  pending.** (An earlier revision of the same overlay was used on a real
  X-T20 with a cap11-era card; that does not prove this Cap12 relocation.)
- Firmware **2.11 only**, same recovery as Cap12: start normally (no rear
  dial + Delete), or start without the card, for stock firmware.
- On the emulator the tint looks **blue**. That is the emulator's pixel
  order, not what the camera shows; on the body the overlay is red.
- Q / Fn assignment of RED NIGHT SCREEN may be incomplete (the SCREEN
  SET-UP item is present; the 12-byte menu-settings declaration table was
  not extended).
- If a Focal-only surface ever skipped the hooked output path, turn
  **FEATURE DISPLAY** off. In emulator tests, the stock shooting HUD and
  the I.Q. menu both tinted with FEATURE DISPLAY left at its default.

### Splice it in

You still need official Cap12, as above. This combines the tether hook and
the overlay in one `FMPATCH.BIN`:

```sh
python3 tools/splice_cap12.py --tether --red-night path/to/official/FMPATCH.BIN \
    -o FMPATCH.BIN
# expected sha256:
# f9a556045de32028af37e5dd130c15451818523d0ac07e0513ec2e2c02a6de59
```

Sources and a pre-linked `addon.bin` are in [`tools/red-night/`](tools/red-night/).
You do not need an ARM toolchain unless you want to rebuild the payload.

Install the spliced `FMPATCH.BIN` the same way as the Cap12-only splice,
keeping official `ffboot.bin` / `ffsys.bin` and any existing
`SETTINGS.JSN`. Then, on the camera (once hardware testing is done): set
RED NIGHT SCREEN to RED or RED DIM from SET UP > SCREEN SET-UP, and confirm
photos are still normal colour.

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
2. Prepare the SD-boot card: either build `usb-tether-xpp` with **FujiMod /
   x70view**, or splice official Cap12 as in
   [Building a Cap12 SD card](#building-a-cap12-sd-card-optional) (and
   optionally [Red night screen add-on](#red-night-screen-add-on-optional)).
3. Boot the mod card: pull the battery, reinsert it, then hold the **rear
   command dial + Delete** while switching the camera on. (On Cap12, switching
   on without that combination starts stock firmware and is the recovery path.)
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
- **iXralum** — official FujiMod Cap12 for the X-T20 (Focal UI, new
  bootloader, and the Cap12 card this repo's splice starts from).
- **FujiMod / `x70view` contributors** — X-T20 2.11 SD boot v2 loader and mod
  toolchain.
