#!/usr/bin/env python3
"""Splice the X-T20 USB-tether hook, and optionally the red-night overlay,
into an official FujiMod Cap12 FMPATCH.BIN.

This script does not contain Cap12 or other official FujiMod card binaries.
You must provide the official Cap12 FMPATCH.BIN (from the Cap12 zip circulated
in the FujiMod / FujiHack Discord). The official file is verified by SHA-256
before anything is written.

The FMBPATCH 1.1 reader/writer below is a compact, standalone implementation
used only to add Jake's runs to that official file. It is not x70view source.

Examples:
  python3 tools/splice_cap12.py --tether FMPATCH.BIN -o FMPATCH-tether.BIN
  python3 tools/splice_cap12.py --tether --red-night FMPATCH.BIN -o FMPATCH-tether-red.BIN
"""
from __future__ import annotations

import argparse
import hashlib
import struct
import sys
import zlib
from dataclasses import dataclass, replace
from pathlib import Path

# Official Cap12 (X-T20 2.11) FMPATCH.BIN, as shipped in
# fujimod-cap12-xt20-2.11.zip. Users must obtain that zip themselves.
OFFICIAL_CAP12_FMPATCH_SHA256 = (
    "d2e237d048be038bd13ec9735488f34e6c3b9c438180c6c6dd899894966dcbba"
)
# Expected outputs of this script against that official file (so you can check).
SPLICED_TETHER_SHA256 = (
    "99a1c0106d91217c0a8464970e88884d5b257a37d63a7011db01358d2f9a7540"
)
SPLICED_TETHER_RED_SHA256 = (
    "f9a556045de32028af37e5dd130c15451818523d0ac07e0513ec2e2c02a6de59"
)

TETHER_ADDR = 0x014A5600
TETHER_OLD = bytes.fromhex("0a00001a")  # bne 0x014a5630
TETHER_NEW = bytes.fromhex("0a0000ea")  # b  0x014a5630

# Red-night layout in leftover located-0 (after official Cap12 immediates).
ADDON_BASE = 0x2C52A00
THUNK = 0x2C52A00
BOOT_SUB = 0x2C52FB0
MENU_ITEM = 0x2C52FC0
ITEM_SIZE = 0x94
SITE_VGLIB = 0x0CC223C
STOCK_PUSH = bytes.fromhex("f0482de9")       # e92d48f0
CAP12_VGLIB_NEW = bytes.fromhex("38b27cea")  # ea7cb238 -> 0x2beeb24
OUR_VGLIB_NEW = bytes.fromhex("ef417eea")    # ea7e41ef -> 0x2c52a00

CAP12_BOOT_START, CAP12_BOOT_STOP = 0x2C47A10, 0x2C47B40
CAP12_BOOT_COUNT = (CAP12_BOOT_STOP - CAP12_BOOT_START) // 16  # 19
CAP12_MENU_START = 0x2C408F4
CAP12_MENU_COUNT = 132
BOOT_LIT_START, BOOT_LIT_STOP = 0x2C40540, 0x2C40544
BOOT_TABLE = 0x2C53200
BOOT_COUNT = CAP12_BOOT_COUNT + 1
BOOT_STOP = BOOT_TABLE + BOOT_COUNT * 16  # 0x2C53340
MENU_TABLE = 0x2C53400
MENU_COUNT = CAP12_MENU_COUNT + 1
MENU_STOP = MENU_TABLE + MENU_COUNT * ITEM_SIZE  # 0x2C580E4

# 0x94 item-table iterators only. Do not retarget 0x2B938C4 (declaration
# table start) or 0x2BA4DC8 (range-check used by a dispatch helper).
MENU_START_LITS = (0x2B95CA0, 0x2B979C4, 0x2B9CF60, 0x2B9F19C, 0x2BA4D98)
MENU_END_LITS = (0x2B95CA4, 0x2B979C8, 0x2B9CF64, 0x2B9F1A0, 0x2BA4D9C)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def u32(n: int) -> bytes:
    return struct.pack("<I", n)


def word_at(buf: bytes, addr: int) -> int:
    return struct.unpack_from("<I", buf, addr)[0]


# ---------------------------------------------------------------------------
# Compact FMBPATCH 1.1 reader/writer (standalone; not x70view source)
# ---------------------------------------------------------------------------

_MAGIC = b"FMBPATCH"
_RESIDENT_MAGIC = 0x52424D46  # 'FMBR' little-endian
_HEADER = 128
_RUN = 20
_GROUP = 12
_RESIDENT_HDR = 32
_OUTCOME = 64
_RESIDENT_DATA = _RESIDENT_HDR + _OUTCOME
_ID_LEN = 24
_FLAG_EXEC, _FLAG_CRC, _FLAG_UNCHECKED, _FLAG_ZERO, _FLAG_CALL = 1, 2, 4, 8, 16
_STOCK_VERBATIM = 4
_OUTCOME_MAGIC, _OUTCOME_VER, _OUTCOME_GROUPS = 0x4354554F, 1, 12
_STATE_FAILED = 0xFFFFFFFF


def _crc32(data: bytes) -> int:
    return zlib.crc32(data) & 0xFFFFFFFF


def _align4(n: int) -> int:
    return (n + 3) & ~3


def _put(blob: bytearray, data: bytes) -> int:
    off = len(blob)
    blob.extend(data)
    return off


@dataclass
class Run:
    address: int
    old: bytes
    new: bytes
    executable: bool = False
    unchecked: bool = False
    call: bool = False
    old_crc32: int | None = None


@dataclass
class Group:
    runs: tuple[Run, ...]
    trigger_site: int


@dataclass
class Patch:
    firmware_id: str
    checks: tuple
    immediate: tuple[Run, ...]
    groups: tuple[Group, ...]
    resident_address: int
    apply_code: bytes
    apply_entry: int
    boot_files: bytes = b""
    boot_files_address: int = 0


def decode_fmbpatch(raw: bytes) -> Patch:
    if len(raw) < _HEADER or raw[:8] != _MAGIC:
        raise ValueError("not an FMBPATCH file")
    major, minor = struct.unpack_from("<HH", raw, 8)
    if major != 1 or minor > 1:
        raise ValueError(f"unsupported FMBPATCH version {major}.{minor}")
    header_size, file_size, expect_crc = struct.unpack_from("<III", raw, 0x0C)
    if header_size != _HEADER or file_size != len(raw):
        raise ValueError("header size or file size mismatch")
    if _crc32(raw[header_size:]) != expect_crc:
        raise ValueError("FMBPATCH CRC mismatch")
    isa, flags = struct.unpack_from("<HH", raw, 0x18)
    if isa != 1 or flags != 0:
        raise ValueError("unsupported ISA or header flags")
    ident = raw[0x1C:0x1C + _ID_LEN]
    firmware_id = ident.split(b"\0", 1)[0].decode("ascii")
    (check_off, check_n, imm_off, imm_n, res_off, res_size, res_addr,
     blob_off, blob_size) = struct.unpack_from("<9I", raw, 0x34)
    bf_off, bf_size, bf_addr = struct.unpack_from("<3I", raw, 0x58)
    blob = raw[blob_off:blob_off + blob_size]
    resident = raw[res_off:res_off + res_size]

    def blob_slice(off: int, n: int) -> bytes:
        return blob[off:off + n]

    checks = []
    for i in range(check_n):
        addr, length, data_off = struct.unpack_from("<III", raw, check_off + i * 12)
        checks.append((addr, blob_slice(data_off, length)))

    immediate = []
    for i in range(imm_n):
        addr, length, old_off, new_off, fl = struct.unpack_from(
            "<IIIII", raw, imm_off + i * _RUN
        )
        unchecked = bool(fl & _FLAG_UNCHECKED)
        old = bytes(length) if unchecked else blob_slice(old_off, length)
        new = bytes(length) if (fl & _FLAG_ZERO) else blob_slice(new_off, length)
        immediate.append(Run(addr, old, new, bool(fl & _FLAG_EXEC), unchecked))

    magic, group_n, group_off, run_off, run_n, res_blob_off, apply_entry, state = (
        struct.unpack_from("<8I", resident)
    )
    if magic != _RESIDENT_MAGIC or state != 0:
        raise ValueError("invalid resident header")
    res_blob = resident[res_blob_off:]
    runs = []
    for i in range(run_n):
        addr, length, old_off, new_off, fl = struct.unpack_from(
            "<IIIII", resident, run_off + i * _RUN
        )
        if fl & _FLAG_CALL:
            runs.append(Run(addr, b"", b"", False, False, True, None))
            continue
        unchecked = bool(fl & _FLAG_UNCHECKED)
        old_crc = None
        if unchecked:
            old = bytes(length)
        elif fl & _FLAG_CRC:
            old_crc, = struct.unpack_from("<I", res_blob, old_off)
            old = b""
        else:
            old = res_blob[old_off:old_off + length]
        new = res_blob[new_off:new_off + length]
        runs.append(Run(addr, old, new, bool(fl & _FLAG_EXEC), unchecked, False, old_crc))

    groups = []
    first = 0
    for i in range(group_n):
        start, count, trigger = struct.unpack_from("<III", resident, group_off + i * _GROUP)
        if start != first:
            raise ValueError("resident groups are not contiguous")
        groups.append(Group(tuple(runs[start:start + count]), trigger))
        first += count

    apply_code = resident[_RESIDENT_DATA:group_off]
    boot_files = raw[bf_off:bf_off + bf_size] if bf_size else b""
    return Patch(
        firmware_id, tuple(checks), tuple(immediate), tuple(groups),
        res_addr, apply_code, apply_entry, boot_files, bf_addr,
    )


def encode_fmbpatch(patch: Patch) -> bytes:
    file_blob = bytearray()
    check_table = bytearray()
    for addr, data in patch.checks:
        check_table.extend(struct.pack("<III", addr, len(data), _put(file_blob, data)))

    imm_table = bytearray()
    for run in patch.immediate:
        old, new = bytes(run.old), bytes(run.new)
        if len(old) != len(new):
            raise ValueError("immediate run old/new length mismatch")
        flags = _FLAG_EXEC if run.executable else 0
        if run.unchecked:
            old_off = 0
            flags |= _FLAG_UNCHECKED
        else:
            old_off = _put(file_blob, old)
        if run.unchecked and not any(new):
            new_off = 0
            flags |= _FLAG_ZERO
        else:
            new_off = _put(file_blob, new)
        imm_table.extend(struct.pack("<IIIII", run.address, len(old), old_off, new_off, flags))

    apply_code = bytes(patch.apply_code)
    resident = bytearray(_RESIDENT_DATA)
    resident.extend(apply_code)
    while len(resident) % 4:
        resident.append(0)
    all_runs = tuple(run for group in patch.groups for run in group.runs)
    group_off = len(resident)
    resident.extend(b"\0" * (_GROUP * len(patch.groups)))
    run_off = len(resident)
    resident.extend(b"\0" * (_RUN * len(all_runs)))
    resident.extend(b"\0" * ((len(all_runs) + 7) // 8))
    while len(resident) % 4:
        resident.append(0)
    res_blob_off = len(resident)
    zero_size = max(
        (len(run.old) for run in all_runs if not any(run.old) and not run.unchecked),
        default=0,
    )
    res_blob = bytearray(zero_size)
    run_entries = bytearray()
    for run in all_runs:
        old, new = bytes(run.old), bytes(run.new)
        flags = _FLAG_EXEC if run.executable else 0
        length = len(new) if run.old_crc32 is not None else len(old)
        if run.call:
            old_off = 0
            flags = _FLAG_CALL
            length = 0
            new = b""
        elif run.unchecked:
            old_off = 0
            flags |= _FLAG_UNCHECKED
        elif run.old_crc32 is not None:
            old_off = _put(res_blob, struct.pack("<I", run.old_crc32))
            flags |= _FLAG_CRC
        elif not any(old):
            old_off = 0
        elif len(old) > _STOCK_VERBATIM:
            old_off = _put(res_blob, struct.pack("<I", _crc32(old)))
            flags |= _FLAG_CRC
        else:
            old_off = _put(res_blob, old)
        run_entries.extend(
            struct.pack("<IIIII", run.address, length, old_off, _put(res_blob, new), flags)
        )
    group_entries = bytearray()
    first = 0
    for group in patch.groups:
        group_entries.extend(struct.pack("<III", first, len(group.runs), group.trigger_site))
        first += len(group.runs)
    resident[group_off:group_off + len(group_entries)] = group_entries
    resident[run_off:run_off + len(run_entries)] = run_entries
    resident.extend(res_blob)
    struct.pack_into(
        "<8I", resident, 0,
        _RESIDENT_MAGIC, len(patch.groups), group_off, run_off, len(all_runs),
        res_blob_off, patch.apply_entry, 0,
    )
    struct.pack_into(
        "<13I", resident, _RESIDENT_HDR,
        _OUTCOME_MAGIC, _OUTCOME_VER, _OUTCOME, 0, len(patch.groups), 0,
        _STATE_FAILED, 0, 0, 0, 0, 0, 0,
    )

    check_off = _HEADER
    imm_off = _align4(check_off + len(check_table))
    res_off = _align4(imm_off + len(imm_table))
    blob_off = _align4(res_off + len(resident))
    boot = bytes(patch.boot_files)
    boot_off = _align4(blob_off + len(file_blob)) if boot else 0
    total = (boot_off + len(boot)) if boot else (blob_off + len(file_blob))
    out = bytearray(total)
    out[0:8] = _MAGIC
    struct.pack_into("<HH", out, 0x08, 1, 1)
    struct.pack_into("<I", out, 0x0C, _HEADER)
    struct.pack_into("<I", out, 0x10, total)
    struct.pack_into("<HH", out, 0x18, 1, 0)
    ident = patch.firmware_id.encode("ascii") + b"\0"
    out[0x1C:0x1C + _ID_LEN] = ident.ljust(_ID_LEN, b"\0")
    struct.pack_into(
        "<9I", out, 0x34,
        check_off, len(patch.checks), imm_off, len(patch.immediate),
        res_off, len(resident), patch.resident_address, blob_off, len(file_blob),
    )
    out[check_off:check_off + len(check_table)] = check_table
    out[imm_off:imm_off + len(imm_table)] = imm_table
    out[res_off:res_off + len(resident)] = resident
    out[blob_off:blob_off + len(file_blob)] = file_blob
    if boot:
        struct.pack_into("<III", out, 0x58, boot_off, len(boot), patch.boot_files_address)
        out[boot_off:boot_off + len(boot)] = boot
    struct.pack_into("<I", out, 0x14, _crc32(bytes(out[_HEADER:])))
    return bytes(out)


def materialize_immediates(patch: Patch, lo: int, hi: int) -> bytearray:
    """Rebuild a RAM window from immediate runs (official Cap12 tables live here)."""
    buf = bytearray(hi - lo)
    for run in patch.immediate:
        if run.address + len(run.new) <= lo or run.address >= hi:
            continue
        start = max(run.address, lo)
        end = min(run.address + len(run.new), hi)
        buf[start - lo:end - lo] = run.new[start - run.address:end - run.address]
    return buf


# ---------------------------------------------------------------------------
# Splices
# ---------------------------------------------------------------------------

def add_tether_hook(patch: Patch) -> Patch:
    g1 = patch.groups[1]
    if any(r.address == TETHER_ADDR for r in g1.runs):
        hook = next(r for r in g1.runs if r.address == TETHER_ADDR)
        if hook.new != TETHER_NEW:
            raise SystemExit("group 1 already has a different run at 0x014a5600")
        return patch
    run = Run(TETHER_ADDR, TETHER_OLD, TETHER_NEW, executable=True)
    runs = tuple(sorted(g1.runs + (run,), key=lambda r: r.address))
    groups = tuple(
        Group(runs, g.trigger_site) if i == 1 else g
        for i, g in enumerate(patch.groups)
    )
    return replace(patch, groups=groups)


def add_red_night(patch: Patch, addon: bytes) -> Patch:
    if any(r.address == ADDON_BASE for r in patch.immediate):
        raise SystemExit("this FMPATCH already has a run at the red-night base")
    ram = materialize_immediates(patch, 0x2B70000, ADDON_BASE)
    base = 0x2B70000

    def at(addr: int, n: int) -> bytes:
        return bytes(ram[addr - base:addr - base + n])

    if word_at(ram, BOOT_LIT_START - base) != CAP12_BOOT_START:
        raise SystemExit("BootSettings start literal is not official Cap12")
    if word_at(ram, BOOT_LIT_STOP - base) != CAP12_BOOT_STOP:
        raise SystemExit("BootSettings stop literal is not official Cap12")
    for a in MENU_START_LITS:
        if word_at(ram, a - base) != CAP12_MENU_START:
            raise SystemExit(f"menu start literal at {a:#x} is not official Cap12")
    official_menu_end = CAP12_MENU_START + CAP12_MENU_COUNT * ITEM_SIZE
    for a in MENU_END_LITS:
        if word_at(ram, a - base) != official_menu_end:
            raise SystemExit(f"menu end literal at {a:#x} is not official Cap12")

    if BOOT_SUB - ADDON_BASE + 16 > len(addon) or MENU_ITEM - ADDON_BASE + ITEM_SIZE > len(addon):
        raise SystemExit("addon.bin is shorter than the linked symbols expect")

    payload = bytearray(MENU_STOP - ADDON_BASE)
    payload[: len(addon)] = addon
    boot = at(CAP12_BOOT_START, CAP12_BOOT_COUNT * 16)
    off = BOOT_TABLE - ADDON_BASE
    payload[off:off + len(boot)] = boot
    sub = addon[BOOT_SUB - ADDON_BASE:BOOT_SUB - ADDON_BASE + 16]
    payload[off + len(boot):off + len(boot) + 16] = sub
    menu = at(CAP12_MENU_START, CAP12_MENU_COUNT * ITEM_SIZE)
    off = MENU_TABLE - ADDON_BASE
    payload[off:off + len(menu)] = menu
    item = addon[MENU_ITEM - ADDON_BASE:MENU_ITEM - ADDON_BASE + ITEM_SIZE]
    payload[off + len(menu):off + len(menu) + ITEM_SIZE] = item

    immediate = patch.immediate + (
        Run(ADDON_BASE, b"\x00" * len(payload), bytes(payload), executable=True, unchecked=True),
    )

    g0 = patch.groups[0]
    new_runs = []
    found = False
    for r in g0.runs:
        if r.address == SITE_VGLIB:
            if r.old != STOCK_PUSH or r.new != CAP12_VGLIB_NEW:
                raise SystemExit(
                    f"unexpected Cap12 vglib run old={r.old.hex()} new={r.new.hex()}"
                )
            new_runs.append(replace(r, new=OUR_VGLIB_NEW))
            found = True
        else:
            new_runs.append(r)
    if not found:
        raise SystemExit("official Cap12 group 0 is missing the 0xcc223c hook")

    extras = [
        Run(BOOT_LIT_START, u32(CAP12_BOOT_START), u32(BOOT_TABLE), executable=True),
        Run(BOOT_LIT_STOP, u32(CAP12_BOOT_STOP), u32(BOOT_STOP), executable=True),
    ]
    for a in MENU_START_LITS:
        extras.append(Run(a, u32(CAP12_MENU_START), u32(MENU_TABLE), executable=True))
    for a in MENU_END_LITS:
        extras.append(Run(a, u32(official_menu_end), u32(MENU_STOP), executable=True))
    occupied = {r.address for r in new_runs}
    for r in extras:
        if r.address in occupied:
            raise SystemExit(f"literal site {r.address:#x} already has a group run")
    new_runs = tuple(sorted(new_runs + extras, key=lambda r: r.address))
    groups = tuple(
        Group(new_runs, g.trigger_site) if i == 0 else g
        for i, g in enumerate(patch.groups)
    )
    return replace(patch, immediate=immediate, groups=groups)


def main(argv: list[str] | None = None) -> int:
    here = Path(__file__).resolve().parent
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("official", type=Path, help="official Cap12 FMPATCH.BIN")
    ap.add_argument("-o", "--output", type=Path, required=True, help="spliced FMPATCH.BIN to write")
    ap.add_argument("--tether", action="store_true", help="add the 0x014a5600 USB tether hook")
    ap.add_argument("--red-night", action="store_true", dest="red_night",
                    help="add the relocated red-night overlay (implies leftover-RAM payload)")
    ap.add_argument("--addon", type=Path, default=here / "red-night" / "addon.bin",
                    help="linked red-night payload (default: tools/red-night/addon.bin)")
    ap.add_argument("--force-hash", action="store_true",
                    help="skip the official-Cap12 SHA-256 check (not recommended)")
    args = ap.parse_args(argv)
    if not args.tether and not args.red_night:
        ap.error("specify --tether and/or --red-night")

    src = args.official.read_bytes()
    digest = sha256(src)
    if digest != OFFICIAL_CAP12_FMPATCH_SHA256 and not args.force_hash:
        raise SystemExit(
            f"input SHA-256 is {digest}, expected official Cap12 "
            f"{OFFICIAL_CAP12_FMPATCH_SHA256}. Get the official cap12 zip from "
            f"the FujiMod Discord and pass its card/FMPATCH.BIN. Use "
            f"--force-hash only if you know the file is a compatible Cap12 patch."
        )
    patch = decode_fmbpatch(src)
    if encode_fmbpatch(patch) != src and digest == OFFICIAL_CAP12_FMPATCH_SHA256:
        raise SystemExit("internal encoder did not round-trip official Cap12; refusing to splice")
    if args.tether:
        patch = add_tether_hook(patch)
    if args.red_night:
        patch = add_red_night(patch, args.addon.read_bytes())
    out = encode_fmbpatch(patch)
    if encode_fmbpatch(decode_fmbpatch(out)) != out:
        raise SystemExit("spliced patch did not round-trip; refusing to write")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(out)
    out_sha = sha256(out)
    print(f"wrote {args.output} ({len(out)} bytes)")
    print(f"sha256 {out_sha}")
    expected = None
    if args.tether and args.red_night and digest == OFFICIAL_CAP12_FMPATCH_SHA256:
        expected = SPLICED_TETHER_RED_SHA256
    elif args.tether and not args.red_night and digest == OFFICIAL_CAP12_FMPATCH_SHA256:
        expected = SPLICED_TETHER_SHA256
    if expected:
        if out_sha != expected:
            raise SystemExit(f"output hash mismatch: expected {expected}")
        print("hash matches the expected spliced file")
    return 0


if __name__ == "__main__":
    sys.exit(main())
