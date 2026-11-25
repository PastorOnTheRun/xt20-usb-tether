# Patch v4 + Hardware Retest Results (2026-11-24, 7:24–7:38 PM ET)

## 1. Three additional root causes uncovered during v3/v4 hardware testing
1. **Why stills after live view were still cropped to 640x480 (`run10`)**:
   - `GPhotoCCD::streamLiveView()` calls `PrimaryCCD.setFrame(0, 0, previewW, previewH)` (`640x480`), and `StopStreaming()` never restored the pre-stream frame.
   - On the next still, `grabImage()` decoded the full `6000x4000` JPEG (`72,000,000` bytes) and then subframed/cropped it down to `640x480` (`924,480`-byte FITS).
   - **Fix in v4 (`gphoto_ccd.h`, `gphoto_ccd.cpp`)**: `StartStreaming()` saves `(subX, subY, subW, subH)` and resets `liveVideoWidth/Height`; `StopStreaming()` restores `PrimaryCCD.setFrame(...)` (falling back to `XRes x YRes`).
2. **Why `STREAM_ON` #2 failed with `I/O in progress` (`0x2019`) after a still (`run9`, `run10`, `diag9`)**:
   - Two independent triggers:
     a) Leaving any still image in `/store_10000001` (RAM tether buffer; `SDCardImageSP` defaulted to `Save` because Fuji has no `capturetarget` widget) causes the X-T20 to reject `0x101c` (`InitiateOpenCapture`) and `0xd207` (`PriorityMode`) with `0x2019 Device Busy`. Deleting `/store_10000001` cleared `0x101c` immediately (`diag9`: `PREV:0`).
     b) Calling `capture_preview` in the same libgphoto2 session right after a still exposure also returned `0x2019` until `gp_camera_exit()` closed the session.
   - **Fix in v4 (`gphoto_ccd.cpp`, `gphoto_driver.cpp`)**:
     - `updateProperties()` defaults `CCD_SD_CARD_ACTION` to `Delete` on Fuji bodies when `CaptureTargetSP` is absent.
     - `gphoto_start_preview()` on Fuji also calls `gp_camera_exit()` so `STREAM_ON` always opens a fresh session at seqno 1.
3. **Why `FORMAT_1` (`RAW`, `49,032 KB` `.raf`) timed out at 21 s with `I/O problem` (`run8`, `diag8`)**:
   - Verified in `diag8/getfile-debug.txt`: `GetObjectInfo (0x1008)` and the `GetObject (0x1009)` data container header both report `0x02fe1e00` (`50,208,256` payload bytes), **but the X-T20 sends only `0x00fe1e00` (`16,653,824` bytes = `size & 0x00ffffff`)** followed immediately by the 12-byte `PTP_RC_OK` response (`0c 00 00 00 03 00 01 20 0c 00 00 00`).
   - `libgphoto2`'s `ptp_usb_getdata()` treats the 12-byte `OK` packet as payload data and blocks for 20 s (`USB_NORMAL_TIMEOUT`) waiting for the missing `0x02000000` (32 MiB), failing with `GP_ERROR_IO` / `PTP Timeout`.
   - `libgphoto2` disables `GetPartialObject (0x101b)` for all Fuji bodies (`library.c:8892`, issue #653), even though the X-T20 advertises `0x101b` in DeviceInfo.
   - `FORMAT_2` (`JPEG Fine`, ~13–15 MB < 16 MiB) transfers cleanly in ~0.35 s and decodes to a full `6000x4000` 3-plane FITS (`72,002,880` bytes). Testing `0x101b` chunked reads or compressed RAW (<16 MiB?) is the next step if `.raf` over USB is needed.

## 2. Retest results on Linux astro test host (v4 binary `~/xt20capture/bin/indi_gphoto_ccd`, `/usr/bin` untouched)
- **`run11` (`CAPTURE_FORMAT=FORMAT_2`, `STEPS=on,off,expo,on,off,expo`, `EXPO=1`, `STREAM_SECS=3`)**: **PASS**
  - Cycle 1: `Fuji start preview: gp_camera_exit -> No error` -> 22 stream frames (`640x480`) -> `Fuji stop preview: gp_camera_exit -> No error` -> 1 s bulb -> `still-1-1795566914.fits` (**72,002,880 bytes, `6000x4000x3`**).
  - Cycle 2 (same session): `Fuji start preview: gp_camera_exit -> No error` -> 19 stream frames (`640x480`) -> `Fuji stop preview: gp_camera_exit -> No error` -> 1 s bulb -> `still-2-1795566946.fits` (**72,002,880 bytes, `6000x4000x3`**).
  - Downsized visual verification: `local test artifact `still-v4-6000x4000.jpg`` (1500x1000, upright indoor frame).
- **`run12` (`Force BULB = Off` -> `expo` -> `Force BULB = On` -> `on,off,expo`)**: **PASS**
  - `Force BULB = Off` (`1 s`) actually succeeded via `shutterspeed=36 (1s)` -> `still-1-1795567015.fits` (`6000x4000`, 72,002,880 bytes), then switched back to `Force BULB = On` + `STREAM_ON` (20 frames) + `STREAM_OFF` + `1 s` bulb -> `still-2-1795567042.fits` (`6000x4000`, 72,002,880 bytes) with no replug.
  - Because `Force BULB = Off` did not fail, `fuji_release_capture()` did not need to fire in `run12`; `STREAM_ON` mid-exposure was not forced because concurrent `gp_camera_exit()` during an open bulb isn't mutexed with the capture thread.
- **Plate solver check**: `libstellarsolver` and KStars astrometry index files (`~/.local/share/kstars/astrometry/index-4119..4210.fits`) are present on the MacBook, but no standalone CLI solver (`solve-field` / `astap`) is installed (and the test frame is an indoor room shot).
