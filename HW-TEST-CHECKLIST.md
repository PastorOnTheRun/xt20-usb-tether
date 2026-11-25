# X-T20 USB tether: hardware test checklist (for when the astro MacBook is back)

_Written 2026-11-24 (ET) before hardware session. First camera session: 2026-11-24 6:30-6:37 PM ET (results inline, marked **[11-24]**; full log in the Results section at the bottom)._
_Rules: one signal at a time on the live camera. Never STREAM_OFF on the stock
indi_gphoto_ccd (it crashes); only on the patched v2 build. Eject SD with
`udisksctl unmount` only, never `udisksctl power-off`. Turn the camera off
before touching the dummy-battery supply or the USB cable._

## Setup
- [x] **[11-24]** Bus 001 Device 002, direct port (per lsusb; hub status not confirmed on rig). Camera on a **direct** MacBook USB port (no hub). PC CONNECTION MODE =
      USB RAW CONV./BACKUP RESTORE. Boot the **tether-only** card (usb-tether-xpp alone).
- [x] **[11-24]** Before: ISO 800, WB Auto, 6000x4000, JPEG Fine, focus M, manualfocusdrive 148, priority mode USB, liveviewsize VGA (also offers XGA/QVGA). Nothing changed except focus (restored to 148).
- [x] **[11-24]** `Fuji Fujifilm X-T20 usb:001,002`; `--summary`: FUJIFILM X-T20, Version 2.11.

## gvfs: udev rule instead of masking
- [x] **[11-24]** gvfs monitor was already active (mask did not survive the reboot); `--summary` worked with it running and nothing held /dev/bus/usb/001/002. Unmask gvfs (`systemctl --user unmask gvfs-gphoto2-volume-monitor.service`, start it).
- [x] **[11-24 6:48 PM ET] PASS after USB unplug/replug.** Device re-enumerated as Bus 001 Device 005 (`usb:001,005`). Live properties: no `ID_GPHOTO2`, `GPHOTO2_DRIVER=PTP`, `TAGS=:seat:uaccess:`, ACL `user:<desktop-user>:rw-`. gvfs-gphoto2-volume-monitor was running and did not hold `/dev/bus/usb/001/005`. Install `udev/69-xt20-tether-no-gvfs.rules`, reload, replug.
- [x] **[11-24 6:48]** no `ID_GPHOTO2` on Device 005; node still
      has a user ACL (`getfacl /dev/bus/usb/BBB/DDD` shows user:<desktop-user>).
- [x] **[11-24 6:48]** preview worked with gvfs running and not holding the node; `--summary` was already proven earlier. `gphoto2 --summary` works as user jake with gvfs running; file manager does not mount the camera.
- [ ] Uninstall the rule, replug: gvfs claims it again (expected), then leave whichever setup preferred.

## Focus tool (`tools/xt20_focus.py`)
- [x] **[11-24] PASS** get=148, save hwtest-start, set 149 (read back 149, error +0), goto hwtest-start (read back 148, error +0). `get`, `save stars`, `set <other>`, `goto stars`: each move prints a
      read-back line; `OK` with error +0 (or a "mismatch" line followed by a correction).
- [x] **[11-24] PASS** separate `gphoto2 --get-config manualfocusdrive` = 148 after goto. **Read-back check:** after `goto`, compare with a separate
      `gphoto2 --get-config manualfocusdrive`; they must match.
- [ ] **[11-24] PENDING (operator by hand).** **Busy while a menu is open:** open the camera MENU (or Q menu) if the host
      session allows it / just before connecting, run `xt20_focus.py get`: expect
      "camera busy ... retry n/5" lines, then success once the menu closes, or the
      "stayed busy" message. Record the exact gphoto2 error text.
- [x] **[11-24] PASS (no busy seen)** autofocusdrive=1 rc 0 (lens 148->354), immediate `get` returned 354 with no busy retries; goto restored 148. Busy right after AF: `gphoto2 --set-config autofocusdrive=1` then immediately
      `xt20_focus.py get`; expect busy retries then a value.
- [ ] (Optional, only with operator OK) Lost reply: unplug the USB cable (not power) mid-`get`: expect
      "reopening the session" then a clear error; replug and confirm `get` works
      without power-cycling. If it needs a power cycle, note it.

## No-hub case
- [~] **[11-24] PARTIAL** 10 spaced focus moves (148<->151): 0 errors. Captures not repeated (camera went Device Busy for capture, see INDI section). Repeat capture + `goto` 20x on the direct port: 0 errors expected.
- [ ] **[11-24] PENDING (operator by hand).** (Optional, only if wanted) same through a shared hub; record any hangs.
      Stop at the first hang, switch the camera off, then unplug.

## INDI: STREAM_OFF -> exposure with settle (patched v2 build only)
- [x] **[11-24] BUILT** on the test host without sudo (dev .debs unpacked to `~/xt20capture/build-v2/sysroot`, cmake 4.2.3 from .deb). Binary `~/xt20capture/bin/indi_gphoto_ccd` (copy in `bin-backups/indi_gphoto_ccd.fuji-stop-fix`), run via PATH prefix; /usr/bin untouched. Stock backup `bin-backups/indi_gphoto_ccd.2.2.0` sha256 05d2bf61... matches /usr/bin. Build/install `fuji-stop-preview-v2.patch` per BUILD-ON-MACBOOK.md (backup the stock binary first).
- [x] **[11-24 6:48-6:49] PASS (run2, patched v2).** After USB replug, `gphoto2 --capture-preview` saved `~/xt20capture/hwtest-20261124/thumb_cap-preview2.jpg` (640×480 JPEG, 139376 bytes, exit 0). INDI connect: Detected FUJIFILM Model X-T20. STREAM_ON: 71 frames in 8 s, last size 921600 (640×480×3). Use `indiserver -v` with `| head -c 200M`, NEVER uncapped -vvv. `indiserver -vvv -p 7624 indi_gphoto_ccd`; connect; STREAM_ON once; frames arrive.
- [x] **[11-24 6:49] PASS (run2).** STREAM_OFF after a live stream: state Idle, driver stayed up, no abort. STREAM_ON again: 70 frames in 8 s, same 921600-byte frames. STREAM_OFF: driver stays up (no std::system_error).
- [x] **[11-24 7:05 PM ET] PASS with caveats (run6).** Fixed client (CCD_INFO 3.9 µm first, UPLOAD_MODE CLIENT, wait for exposure, no STREAM_ON during exposure). STREAM_ON 25 frames / 3 s, 921600 bytes; STREAM_OFF Idle; 1 s CCD_EXPOSURE Ok in 3.3 s, `saw_busy True`. File: `~/xt20capture/hwtest-20261124/run6/still-1795565158.fits` (924480 bytes, FITS 640×480×3 8-bit, EXPTIME=1 s, DATE-OBS 2026-11-25T00:05:55.375Z = 7:05:55 PM ET). Same pixel count as live view, not 6000×4000. JPEG preview of it: `still-1795565158.jpg`. The `Fuji: waiting N ms` line is LOGF_DEBUG and did not appear on the client (LOGGING_LEVEL names were wrong; no new ~/.indi driver log). settle=0 not run — camera went busy afterward. CCD_EXPOSURE right away: debug log shows "Fuji: waiting N ms after live view stop",
      frame downloads. No "Error starting exposure".
- [x] **[11-24 6:49] PASS in run2** (70 frames after STREAM_OFF + failed still, then STREAM_ON). Later runs after the interrupted exposure did not resume (busy). STREAM_ON again: frames resume.
- [ ] **[11-24 7:06] NOT RUN.** After the clean still, `gphoto2 --capture-image-and-download` got PTP General Error and a spaced `--capture-preview` got Device Busy; stopped. Repeat with `INDI_GPHOTO_FUJI_SETTLE_MS=0`: does the first exposure fail or
      hit the one retry? (Tells us whether the settle is needed.)
- [ ] **[11-24 7:05] Frame saved but not plate-solved.** The INDI still is 640×480, not 6000×4000, and `solve-field` is not installed. Do not download index files. Capture one frame for an offline plate solve (Align: X-T20 + XC50-230, 3.9 um pixels).

## After
- [x] **[11-24]** Only focus changed; restored to 148. Restore ISO / WB / image size noted at the start.
- [ ] Camera off, then unplug USB / power.
- [ ] Update README status table rows from "not yet" to results; label camera vs emulator.

## Results 2026-11-24 (camera session 6:30-6:37 PM ET, Linux astro host)

Artifacts on the test host: `~/xt20capture/hwtest-20261124/` (settings-before.txt, af-busy.txt,
indi_seq.py client, run1/client-*.log, indiserver-v2-settle750.log [indiserver -v, capped with head -c 200M],
preview-debug.txt [gphoto2 --debug of the busy preview]). Build tree `~/xt20capture/build-v2/`.

- PASS: detect/summary (fw 2.11), focus get/save/set/goto with read-back, AF then immediate get, 10 spaced moves, STREAM_OFF on patched v2 does not abort the driver.
- FAIL/BLOCKED: every live-view and still capture (gphoto2 CLI and INDI) got PTP Device Busy 0x2019 /
  PTP General Error, from the very first STREAM_ON. The camera answered property reads and focus writes the whole time.
  Not caused by INDI holding the camera (nothing else had the device open). Needs operator to look at the camera
  (close any menu/playback, wake screen) or switch it off and on, then rerun the INDI section.
- NOT RUN (need sudo): udev rule install. NOT RUN (operator by hand): busy-while-menu, hub case, lost-reply unplug.
- NOT RUN: settle=0 comparison, plate solve (needs a frame; no local solve-field).
- Side find: `/main/capturesettings/liveviewsize` offers XGA (1024x768?) besides VGA/QVGA; untested.

Rerun: `cd ~/xt20capture/hwtest-20261124 && (PATH=$HOME/xt20capture/bin:$PATH setsid bash -c 'indiserver -v -p 7624 indi_gphoto_ccd 2>&1 | head -c 200M > indiserver-run2.log' &)`,
then `mkdir run2 && timeout 240 python3 indi_seq.py run2`, then `pkill -x indiserver`.

## Results 2026-11-24 (second try, 6:39-6:41 PM ET)

Operator installed the udev rule at 6:39 PM and said the camera was ready (power-cycled, mod boot, USB RAW CONV, shooting screen) at 6:40 PM.

- **gphoto2 quoting message:** not a wrapper, alias, PATH, or popt bug. It is the standard footer gphoto2 prints after any failed command (`Please make sure there is sufficient quoting around the arguments.`). The real error is on the lines above it. A `tail` of the output shows only the footer.
- **Udev rule:** installed, and a simulated `udevadm test` add confirms it clears `ID_GPHOTO2`. The live node still has `ID_GPHOTO2=1` on Bus 001 Device 002; the camera did not re-enumerate. A physical USB unplug/replug (or `sudo udevadm trigger`) is required before we can verify that gvfs leaves it alone.
- **Preview retry:** stopped gvfs so it would not hold the device, waited, then one `gphoto2 --capture-preview --filename=cap-preview.jpg`. Still `PTP Device Busy` (0x2019 / -110). An earlier probe in the same window, while gvfs still held the node, was also busy. Stopped after those two spaced tries; no INDI sequence, no settle=0 run, no XGA change, no photo, no plate solve.
- **Cleanup:** no indiserver was started. Disk 69 GB free (35%). gvfs-gphoto2-volume-monitor is running again (dbus activation, new pid) and was not holding the USB node on the last check.

Next: unplug and replug the USB cable (leave the camera on the shooting screen), then rerun one preview and, if it works, the INDI STREAM_ON / STREAM_OFF / photo / STREAM_ON sequence, settle=0, and one XGA live-view size check (restore VGA afterward).

## Results 2026-11-24 (third try, 6:47-6:53 PM ET, after USB unplug/replug)

Operator unplugged USB, power-cycled, mod-booted, and replugged. Camera on the shooting screen.

- **Udev / gvfs:** PASS. Bus 001 Device 005 (was 002). `ID_GPHOTO2` cleared. `GPHOTO2_DRIVER=PTP`, `uaccess`, ACL user:<desktop-user>. gvfs running, not holding the device node.
- **gphoto2 preview:** PASS. Full output was only `Saving file as thumb_cap-preview2.jpg` (exit 0). File: `~/xt20capture/hwtest-20261124/thumb_cap-preview2.jpg`, 640×480 JPEG, 139376 bytes. (gphoto2 prefixed `thumb_` onto the filename.)
- **INDI patched v2, run2 (`indiserver -v`, log capped at 200M):** STREAM_ON 71 frames / 8 s, 921600 bytes (640×480×3). STREAM_OFF Idle, driver stayed up. Immediate 1 s CCD_EXPOSURE Alert (pixel size was 0; settle code not reached). STREAM_ON again 70 frames, then clean disconnect.
- **INDI still capture:** not a clean pass. With CCD_INFO set to 3.9 µm, exposure does start after STREAM_OFF, but run3's client raced on a leftover Alert and opened live view mid-exposure. run4 then got live-view busy, and the still failed at 62 s with `Exposure failed to save image... Unspecified error` (no file). No settle debug line captured, so settle=0 was not run.
- **After that, camera went busy again:** `gphoto2 --capture-image-and-download` → PTP General Error; one spaced `--capture-preview` → PTP Device Busy (-110). Stopped. No XGA test, no plate solve (`solve-field` not installed; no still file anyway).
- **Cleanup:** indiserver killed. Disk 69 GB free (35%). gvfs still running (udev rule is doing its job).

Needs another USB unplug / camera power-cycle to finish: a clean INDI still after STREAM_OFF (client wait is now fixed), the settle=0 comparison, and one XGA live-view size check (restore VGA afterward).

## Results 2026-11-24 (fourth try, 7:04-7:07 PM ET, after another USB unplug/replug)

Operator unplugged, power-cycled, mod-booted and replugged at 7:04 PM.

- **USB / udev:** Bus 001 Device 007 (was 005). `ID_GPHOTO2` still cleared. gvfs running, not holding the node.
- **INDI patched v2, run6 (`indiserver -v`, 200 MB cap, STEPS=on,off,expo, STREAM_SECS=3):**
  - STREAM_ON: 25 frames in 3 s, 921600 bytes (640×480×3).
  - STREAM_OFF: Idle, driver stayed up.
  - CCD_INFO set to 3.9 µm / 6000×4000, UPLOAD_MODE CLIENT. 1 s exposure: Ok in 3.3 s (`Starting 1 seconds exposure`, then still downloaded).
  - Still: `~/xt20capture/hwtest-20261124/run6/still-1795565158.fits` — 924480 bytes, FITS NAXIS 640×480×3, 8-bit, EXPTIME=1 s, INSTRUME='GPhoto CCD', DATE-OBS `2026-11-25T00:05:55.375` UTC (7:05:55 PM ET). This is live-view size, not a 6000×4000 JPEG. Driver also warned that telescope focal length and aperture were missing.
  - `Fuji: waiting N ms` was not captured (LOGF_DEBUG did not reach the client).
- **After disconnect:** `gphoto2 --capture-image-and-download` → PTP General Error; one spaced `--capture-preview` → PTP Device Busy (-110). Stopped. settle=0 and XGA not run.
- **Box copies** (for display): `local test folder still-1795565158.fits`, `still-1795565158.jpg` (converted, 640×480), `stream-frame.jpg` (live-view frame from the same run), `thumb_cap-preview2.jpg` (earlier gphoto2 preview, 640×480, 139376 bytes).
- **Cleanup:** indiserver killed. Disk 69 GB free (35%). gvfs running.

Still needs another camera reset for settle=0 and the XGA live-view size check (restore VGA afterward). Also worth checking why the INDI still is 640×480 instead of 6000×4000 (capture/encode format or frame size left over from streaming).

### [11-24] Code investigation and diagnostics, 7:11–7:22 PM ET (details: indi/FINDINGS.md)
- [x] **Root cause of the 640x480 still (high confidence).**
  - Patch v2's Fuji stop_preview left libgphoto2's open capture (0x101c) active, so INDI's bulb start failed with -1, and the return value was ignored.
  - The bulb event wait then either timed out or grabbed the live-view object 0x80000001.
  - CLI bulb without live view gives **6000x4000** (bulb-192549.jpg, 15.1 MB, about 13 s after the start). The tether mod is not at fault.
  - The CLI `--capture-image-and-download` General Error is the shoot returning 0x2002 with the dial on B.
- [x] **Root cause of the stuck PTP busy (0x2019) (high confidence).**
  - An aborted Fuji capture sequence leaves the camera mid-release. It is not a missing CloseSession; clean exits are fine.
- [x] The USB port reset (`~/xt20capture/bin/xt20-usb-reset`, USBDEVFS_RESET) ran OK but **did not clear busy**.
- [x] The **PTP release** clears busy with no replug: `~/xt20capture/bin/xt20-release` (d208=4 + opcode 0x100e).
- [x] liveviewsize=XGA works and gives **1024x768** live view. Restored to VGA afterwards.
- [ ] **Patch v3** (`fuji-stop-preview-v3.patch`): Fuji stop_preview calls gp_camera_exit (TerminateOpenCapture + CloseSession, fresh session at seqno 1), release on a failed capture, bulb start or timeout, and the capture rc is checked.
  - Syntax-checked, but not yet built or tested. To test: rebuild, then on,off,expo with the dial on B and download timeout ≥ 20 s. Expect a 6000x4000 FITS.
- [ ] The settle=0 comparison is still not run (probably moot with v3).

### [11-24] Patch v4 build & repeatability retest, 7:25–7:38 PM ET (details: indi/FINDINGS.md)
- [x] **v4 built and installed** to `~/xt20capture/bin/indi_gphoto_ccd` (backups: `indi_gphoto_ccd.fuji-stop-fix-v2`, `-v3`, `-v4`; `/usr/bin/indi_gphoto_ccd` untouched, sha256 `05d2bf61...`).
- [x] **Found & fixed two more INDI bugs (`run8`–`run10`, `diag8`–`diag9`)**:
  - `streamLiveView()` set `PrimaryCCD.setFrame(0,0,640,480)` and `StopStreaming()` never restored it, cropping subsequent `6000x4000` stills to `640x480`. Fixed in v4 (`gphoto_ccd.cpp/h`).
  - Leaving any still in `/store_10000001` (`SDCardImageSP=Save`) or calling `capture_preview` after a still in the same session caused `0x101c` (`STREAM_ON`) to return `0x2019 Device Busy`. Fixed in v4 (`gphoto_start_preview` calls `gp_camera_exit` on Fuji; `CCD_SD_CARD_ACTION` defaults to `Delete` when `CaptureTargetSP` is absent on Fuji).
- [x] **Repeatability test PASS (`run11`, `FORMAT_2` JPEG Fine)**: two consecutive `STREAM_ON -> STREAM_OFF -> 1 s bulb` cycles in a single session produced 22 + 19 live-view frames (`640x480`) and two **6000x4000 FITS** stills (`72,002,880` bytes each), `gp_camera_exit -> No error` on every start/stop, no replug. Visual check saved at `local test folder still-v4-6000x4000.jpg`.
- [x] **Mode switch test PASS (`run12`, `FORMAT_2`)**: `Force BULB = Off` (`1 s` predefined shutter) -> `6000x4000` FITS -> `Force BULB = On` -> `STREAM_ON` (20 frames) -> `STREAM_OFF` -> `1 s` bulb -> `6000x4000` FITS in one session, no replug. (`Force BULB = Off` succeeded instead of failing, so `fuji_release_capture()` wasn't triggered; concurrent `STREAM_ON` mid-exposure was skipped as unsafe without mutexing `gp_camera_exit`.)
- [ ] **Open issue for `.raf` (RAW) over USB (`run8`, `diag8`)**: `DSCF0002.raf` (`50,208,256` bytes = `0x02fe1e00`) truncated in `GetObject (0x1009)` at `0x00fe1e00` (`size & 0x00ffffff` = 16,653,824 bytes) before the camera sent `PTP_RC_OK`, causing a 20 s USB timeout (`I/O problem`). `FORMAT_2` (`JPEG Fine`, ~15 MB < 16 MiB) works; test `GetPartialObject (0x101b)` or compressed RAW if `.raf` via INDI is needed.
- [ ] **Plate solve**: `libstellarsolver` + KStars astrometry indexes (`~/.local/share/kstars/astrometry/index-4119..4210.fits`) are on the test host, but no CLI solver (`solve-field`/`astap`) is installed and no sky frame is captured yet.
