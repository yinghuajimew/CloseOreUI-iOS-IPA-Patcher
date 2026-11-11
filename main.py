#!/usr/bin/env python3
# -*- coding: utf-8 -*-



from pathlib import Path
import argparse
import hashlib
import json
import locale
import mmap
import os
import plistlib
import queue
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
import zipfile
import webbrowser
from tkinter import filedialog, messagebox, scrolledtext, ttk
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    HAS_DND = True
except Exception:
    HAS_DND = False
    TkinterDnD = None
    DND_FILES = None
IS_WINDOWS = sys.platform.startswith("win")
REG_PATH = r"Software\iosoreuipatcher"

if IS_WINDOWS:
    try:
        import winreg
    except Exception:
        winreg = None
else:
    winreg = None


def reg_read(name):
    if winreg is None:
        return None
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_READ) as k:
            value, _ = winreg.QueryValueEx(k, name)
            return value
    except Exception:
        return None


def reg_write(name, value):
    if winreg is None:
        return False
    try:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_WRITE) as k:
            winreg.SetValueEx(k, name, 0, winreg.REG_SZ, str(value))
        return True
    except Exception:
        return False
CREDITS_TEXT = (
    "鸣谢\n"
    "========================================\n"
    "\n"
    "【项目作者】\n"
    "  • xiaoli\n"
    "\n"
    "【逆向与补丁思路贡献】\n"
    "  • 奕帆雨顺\n"
    "\n"
    "【测试与反馈】\n"
    "  • xiaoli，奕帆雨顺\n"
    "\n"
    "【特别鸣谢】\n"
    "  • 樱花祭喵（为此项目提供仓库）\n"
    "银果集团（砸壳为我们提供调试，适配机会)\n"
    "感谢以上人员对本项目的贡献与支持。\n"
)

CREDIT_LINKS = [
    "https://space.bilibili.com/498528472/",
    "https://space.bilibili.com/648037057?spm_id_from=333.788.upinfo.head.click",
    "https://3946972582.qzone.qq.com/",
]
CREDIT_BUTTON_TEXTS = ["奕帆雨顺的b站空间", "樱花祭喵的b站空间", "xiaoli的QQ"]

CREDITS_TITLE = "鸣谢"

APP_VERSION = "v1.0.1"

LANG_DIR = Path(__file__).resolve().parent / "lang"
LANG_FILES = {
    "zh-CN": "zh-CN.json",
    "zh-TW": "zh-TW.json",
    "zh-HK": "zh-HK.json",
    "en-US": "en-US.json",
    "ja-JP": "ja-JP.json",
    "ko-KR": "ko-KR.json",
}
LANG_NAMES = {
    "zh-CN": "简体中文（中国大陆）",
    "zh-TW": "繁體中文（台灣）",
    "zh-HK": "繁體中文（香港特別行政區）",
    "en-US": "English (United States)",
    "ja-JP": "日本語",
    "ko-KR": "한국어",
}
FALLBACK_LANG = "en-US"


def match_system_lang():
    try:
        loc = locale.getdefaultlocale()[0] or ""
    except Exception:
        loc = ""
    loc = loc.replace("_", "-")
    low = loc.lower()
    if low.startswith("zh"):
        if "tw" in low or "hant" in low:
            return "zh-TW"
        if "hk" in low or "mo" in low:
            return "zh-HK"
        return "zh-CN"
    if low.startswith("ja"):
        return "ja-JP"
    if low.startswith("ko"):
        return "ko-KR"
    if low.startswith("en"):
        return "en-US"
    return FALLBACK_LANG


def choose_startup_lang():
    first = reg_read("first")
    is_first = first is None or str(first).strip() == "" or str(first).strip() == "1"
    if is_first:
        lang = match_system_lang()
        reg_write("first", "0")
        reg_write("lang", lang)
        return lang
    saved = reg_read("lang")
    if saved in LANG_FILES:
        return saved
    lang = match_system_lang()
    reg_write("lang", lang)
    return lang


def load_lang(code):
    path = LANG_DIR / LANG_FILES.get(code, LANG_FILES[FALLBACK_LANG])
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data, None
    except Exception as e:
        return None, f"{path.name}: {e}"


class I18N:
    def __init__(self, code):
        self.code = code
        self.data = {}
        self.load(code)

    def load(self, code):
        data, err = load_lang(code)
        if data is None:
            data, _ = load_lang(FALLBACK_LANG)
            self.code = FALLBACK_LANG
            if data is None:
                data = {}
        else:
            self.code = code
        self.data = data
        return err

    def t(self, key, **kw):
        s = self.data.get(key, key)
        if kw:
            try:
                return s.format(**kw)
            except Exception:
                return s
        return s

PATCH = bytes.fromhex("00 00 80 52 C0 03 5F D6")
CHUNK = 8 * 1024 * 1024

DYLIB_LIST = [
    "HyniSign.dylib",
    "libhynisloader.dylib",
    "HyniSwizzleFPS.dylib",
]

LC_SEGMENT_64 = 0x19
LC_FUNCTION_STARTS = 0x26

KNOWN_PROLOGUE16 = bytes.fromhex(
    "F6 57 BD A9 "
    "F4 4F 01 A9 "
    "FD 7B 02 A9 "
    "FD 83 00 91"
)

NAME_ANCHORS = (
    b"getTechStackForScreen\x00",
    b"vanilla.screenTechStack\x00",
)

MAX_FUNCTION_BYTES = 0x500
NEAR_XREF_BEFORE = 0x100
NEAR_XREF_AFTER = 0x180

NAMED_MIN_SCORE = 58
STRUCT_MIN_SCORE = 92
STRUCT_MIN_MARGIN = 16


def sx(value, bits):
    sign = 1 << (bits - 1)
    return (value ^ sign) - sign


def u32(mm, off):
    if off < 0 or off + 4 > len(mm):
        return None
    return struct.unpack_from("<I", mm, off)[0]


def u64(mm, off):
    if off < 0 or off + 8 > len(mm):
        return None
    return struct.unpack_from("<Q", mm, off)[0]


def sha256_path(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(CHUNK), b""):
            h.update(block)
    return h.hexdigest()


class MachO:
    def __init__(self, mm):
        self.mm = mm
        self.segments = []
        self.sections = []
        self.function_starts_cmd = None
        self.text_vmaddr = None
        self.text_fileoff = None
        self.text_filesize = None
        self.image_base = None
        self._parse()

    def _parse(self):
        if len(self.mm) < 32:
            raise RuntimeError("file too small, not a Mach-O")
        magic = struct.unpack_from("<I", self.mm, 0)[0]
        if magic != 0xFEEDFACF:
            raise RuntimeError(
                f"not an ARM64 Mach-O 64-bit little-endian, magic=0x{magic:08X}"
            )
        (
            _magic, _cputype, _cpusubtype, _filetype,
            ncmds, sizeofcmds, _flags, _reserved,
        ) = struct.unpack_from("<IiiIIIII", self.mm, 0)
        off = 32
        end_cmds = min(len(self.mm), 32 + sizeofcmds)
        for _ in range(ncmds):
            if off + 8 > end_cmds:
                break
            cmd, cmdsize = struct.unpack_from("<II", self.mm, off)
            if cmdsize < 8 or off + cmdsize > len(self.mm):
                break
            if cmd == LC_SEGMENT_64 and cmdsize >= 72:
                (
                    _cmd, _cmdsize, segname_raw, vmaddr, vmsize,
                    fileoff, filesize, maxprot, initprot, nsects, flags,
                ) = struct.unpack_from("<II16sQQQQiiII", self.mm, off)
                segname = segname_raw.split(b"\0", 1)[0].decode("ascii", "replace")
                seg = {
                    "name": segname, "vmaddr": vmaddr, "vmsize": vmsize,
                    "fileoff": fileoff, "filesize": filesize,
                    "maxprot": maxprot, "initprot": initprot, "flags": flags,
                }
                self.segments.append(seg)
                if segname == "__TEXT":
                    self.image_base = vmaddr
                sec_off = off + 72
                for _sec in range(nsects):
                    if sec_off + 80 > off + cmdsize:
                        break
                    (
                        sectname_raw, secseg_raw, addr, size, offset,
                        align, reloff, nreloc, secflags,
                        reserved1, reserved2, reserved3,
                    ) = struct.unpack_from("<16s16sQQIIIIIIII", self.mm, sec_off)
                    sectname = sectname_raw.split(b"\0", 1)[0].decode("ascii", "replace")
                    secseg = secseg_raw.split(b"\0", 1)[0].decode("ascii", "replace")
                    sec = {
                        "sectname": sectname, "segname": secseg,
                        "addr": addr, "size": size,
                        "offset": offset, "flags": secflags,
                    }
                    self.sections.append(sec)
                    if secseg == "__TEXT" and sectname == "__text":
                        self.text_vmaddr = addr
                        self.text_fileoff = offset
                        self.text_filesize = size
                    sec_off += 80
            elif cmd == LC_FUNCTION_STARTS and cmdsize >= 16:
                (_cmd, _cmdsize, dataoff, datasize) = struct.unpack_from("<IIII", self.mm, off)
                self.function_starts_cmd = (dataoff, datasize)
            off += cmdsize
        if self.image_base is None:
            if self.segments:
                self.image_base = min(s["vmaddr"] for s in self.segments)
            else:
                raise RuntimeError("no segment found in Mach-O")
        if self.text_fileoff is None:
            executable = [s for s in self.segments if s["initprot"] & 0x4 and s["filesize"]]
            if not executable:
                raise RuntimeError("no executable __text/segment found")
            s = executable[0]
            self.text_vmaddr = s["vmaddr"]
            self.text_fileoff = s["fileoff"]
            self.text_filesize = s["filesize"]

    def file_to_va(self, file_off):
        for s in self.segments:
            a = s["fileoff"]
            b = a + s["filesize"]
            if a <= file_off < b:
                return s["vmaddr"] + (file_off - a)
        return None

    def va_to_file(self, va):
        for s in self.segments:
            a = s["vmaddr"]
            b = a + s["filesize"]
            if a <= va < b:
                file_off = s["fileoff"] + (va - a)
                if 0 <= file_off < len(self.mm):
                    return file_off
        return None

    def in_text_va(self, va):
        return self.text_vmaddr <= va < self.text_vmaddr + self.text_filesize

    def in_text_file(self, off):
        return self.text_fileoff <= off < self.text_fileoff + self.text_filesize

    def function_starts(self):
        if self.function_starts_cmd is None:
            return []
        dataoff, datasize = self.function_starts_cmd
        end = min(len(self.mm), dataoff + datasize)
        pos = dataoff
        current = self.image_base
        result = []
        while pos < end:
            value = 0
            shift = 0
            while pos < end:
                b = self.mm[pos]
                pos += 1
                value |= (b & 0x7F) << shift
                if not (b & 0x80):
                    break
                shift += 7
                if shift > 63:
                    return sorted(set(result))
            if value == 0:
                break
            current += value
            foff = self.va_to_file(current)
            if foff is not None and self.in_text_file(foff):
                result.append(foff)
        return sorted(set(result))
def decode_adrp(w, pc):
    if (w & 0x9F000000) != 0x90000000:
        return None
    immlo = (w >> 29) & 0x3
    immhi = (w >> 5) & 0x7FFFF
    imm21 = sx((immhi << 2) | immlo, 21)
    target = (pc & ~0xFFF) + (imm21 << 12)
    return target, w & 0x1F


def decode_adr(w, pc):
    if (w & 0x9F000000) != 0x10000000:
        return None
    immlo = (w >> 29) & 0x3
    immhi = (w >> 5) & 0x7FFFF
    imm21 = sx((immhi << 2) | immlo, 21)
    return pc + imm21, w & 0x1F


def decode_add_x_imm(w):
    if (w & 0xFF000000) != 0x91000000:
        return None
    rd = w & 0x1F
    rn = (w >> 5) & 0x1F
    imm12 = (w >> 10) & 0xFFF
    shift12 = (w >> 22) & 1
    return rd, rn, imm12 << (12 if shift12 else 0)


def decode_b(w, pc):
    if (w & 0xFC000000) != 0x14000000:
        return None
    return pc + (sx(w & 0x03FFFFFF, 26) << 2)


def decode_bl(w, pc):
    if (w & 0xFC000000) != 0x94000000:
        return None
    return pc + (sx(w & 0x03FFFFFF, 26) << 2)


def decode_ldr_x_literal(w, pc):
    if (w & 0xFF000000) != 0x58000000:
        return None
    disp = sx((w >> 5) & 0x7FFFF, 19) << 2
    return pc + disp, w & 0x1F


def decode_br_reg(w):
    if (w & 0xFFFFFC1F) != 0xD61F0000:
        return None
    return (w >> 5) & 0x1F


def is_ret(w):
    return w == 0xD65F03C0


def is_cbz_cbnz(w):
    return (w & 0x7E000000) == 0x34000000


def is_cmp_w_imm1(w):
    return (w & 0xFFFFFC1F) == 0x7100041F


def is_movz_w_imm1(w):
    return (w & 0xFFFFFFE0) == 0x52800020


def is_movz_w_imm0(w):
    return (w & 0xFFFFFFE0) == 0x52800000


def is_cond_select_to_w0(w):
    return (w & 0x7E00001F) == 0x1A000000


def is_ldr_x_from_x0_30(w):
    return (w & 0xFFFFFFE0) == 0xF9401800


def is_ldr_w_offset_18(w):
    return (w & 0xFFFFFC00) == 0xB9401800


class FunctionIndex:
    def __init__(self, macho):
        self.macho = macho
        self.starts = macho.function_starts()

    def bounds(self, start):
        if not self.starts:
            end = min(len(self.macho.mm), start + MAX_FUNCTION_BYTES)
            return start, end
        import bisect
        i = bisect.bisect_left(self.starts, start)
        if i >= len(self.starts) or self.starts[i] != start:
            i = bisect.bisect_right(self.starts, start) - 1
            if i < 0:
                return start, min(len(self.macho.mm), start + MAX_FUNCTION_BYTES)
            start = self.starts[i]
        if i + 1 < len(self.starts):
            end = self.starts[i + 1]
        else:
            end = min(len(self.macho.mm), start + MAX_FUNCTION_BYTES)
        end = min(end, start + MAX_FUNCTION_BYTES, len(self.macho.mm))
        return start, end

    def start_containing(self, off):
        if not self.starts:
            return off
        import bisect
        i = bisect.bisect_right(self.starts, off) - 1
        return None if i < 0 else self.starts[i]


def score_function(mm, fidx, start):
    start, end = fidx.bounds(start)
    if start < 0 or end <= start:
        return None
    body = bytes(mm[start:end])
    if not body:
        return None
    state = "patched" if body.startswith(PATCH) else "original"
    score = 0
    why = []
    if body.startswith(PATCH):
        score += 8
        why.append("already-patched")
    if body.startswith(KNOWN_PROLOGUE16):
        score += 18
        why.append("known-prologue")
    words = [struct.unpack_from("<I", body, i)[0] for i in range(0, len(body) - 3, 4)]
    if not words:
        return None
    has_ret = any(is_ret(w) for w in words)
    has_cb = any(is_cbz_cbnz(w) for w in words)
    has_cmp = any(is_cmp_w_imm1(w) for w in words)
    has_mov1 = any(is_movz_w_imm1(w) for w in words)
    has_mov0 = any(is_movz_w_imm0(w) for w in words)
    has_sel = any(is_cond_select_to_w0(w) for w in words)
    has_x0_30 = any(is_ldr_x_from_x0_30(w) for w in words)
    has_w18 = any(is_ldr_w_offset_18(w) for w in words)
    bl_count = 0
    base_va = fidx.macho.file_to_va(start)
    if base_va is not None:
        bl_count = sum(
            1 for i, w in enumerate(words)
            if decode_bl(w, base_va + i * 4) is not None
        )
    if has_ret:
        score += 8; why.append("RET")
    if has_cb:
        score += 7; why.append("CBZ/CBNZ")
    if bl_count:
        score += min(9, 3 + bl_count); why.append(f"BLx{bl_count}")
    if has_x0_30:
        score += 22; why.append("LDR-X0+30")
    if has_w18:
        score += 7; why.append("LDR-W+18")
    if has_cmp:
        score += 14; why.append("CMP-#1")
    if has_mov1:
        score += 10; why.append("MOV-#1")
    if has_mov0:
        score += 3; why.append("MOV-#0")
    if has_sel:
        score += 17; why.append("CONDSEL->W0")
    if has_cmp and has_mov1 and has_sel:
        score += 22; why.append("TechStack-return-shape")
    if has_cmp and has_mov1 and has_ret and has_cb:
        score += 10; why.append("branched-TechStack-shape")
    if has_cmp and has_mov0 and has_ret and has_cb:
        score += 16; why.append("legacy-direct-JsonUI-shape")
    size = end - start
    if 0x30 <= size <= 0x280:
        score += 5; why.append(f"size=0x{size:X}")
    elif size > 0x480:
        score -= 8; why.append(f"large=0x{size:X}")
    return {
        "offset": start, "end": end, "size": size,
        "score": score, "state": state, "why": why,
        "first8": bytes(mm[start:start + 8]),
    }


def find_all(mm, needle):
    pos = 0
    while True:
        pos = mm.find(needle, pos)
        if pos < 0:
            break
        yield pos
        pos += 1


def encode_add_x_imm(rd, rn, imm):
    if not (0 <= imm <= 0xFFF):
        return None
    return struct.pack("<I", 0x91000000 | (imm << 10) | (rn << 5) | rd)


def find_string_xrefs(macho, string_off):
    mm = macho.mm
    string_va = macho.file_to_va(string_off)
    if string_va is None:
        return []
    page = string_va & ~0xFFF
    pageoff = string_va & 0xFFF
    start = macho.text_fileoff
    end = min(len(mm), start + macho.text_filesize)
    result = set()
    for rn in range(32):
        needle = encode_add_x_imm(rn, rn, pageoff)
        pos = start
        while True:
            add_off = mm.find(needle, pos, end)
            if add_off < 0:
                break
            if (add_off - macho.text_fileoff) % 4 == 0:
                for step in range(1, 6):
                    adrp_off = add_off - step * 4
                    if adrp_off < start:
                        break
                    w = u32(mm, adrp_off)
                    pc = macho.file_to_va(adrp_off)
                    if pc is None:
                        continue
                    adrp = decode_adrp(w, pc)
                    if adrp is None:
                        continue
                    if adrp[1] == rn and adrp[0] == page:
                        result.add(adrp_off)
                        break
            pos = add_off + 4
    if not result:
        off = start
        while off + 4 <= end:
            w = u32(mm, off)
            pc = macho.file_to_va(off)
            if pc is not None:
                adr = decode_adr(w, pc)
                if adr is not None and adr[0] == string_va:
                    result.add(off)
            off += 4
    return sorted(result)


def collect_code_targets_near(macho, center):
    mm = macho.mm
    a = max(macho.text_fileoff, center - NEAR_XREF_BEFORE)
    b = min(macho.text_fileoff + macho.text_filesize, center + NEAR_XREF_AFTER)
    targets = set()
    off = a - (a % 4)
    while off + 4 <= b:
        w = u32(mm, off)
        pc = macho.file_to_va(off)
        if pc is None:
            off += 4
            continue
        adr = decode_adr(w, pc)
        if adr is not None and macho.in_text_va(adr[0]):
            foff = macho.va_to_file(adr[0])
            if foff is not None:
                targets.add(foff)
        adrp = decode_adrp(w, pc)
        if adrp is not None:
            page, reg = adrp
            for step in range(1, 5):
                noff = off + step * 4
                if noff + 4 > b:
                    break
                add = decode_add_x_imm(u32(mm, noff))
                if add is None:
                    continue
                _rd, rn, imm = add
                if rn != reg:
                    continue
                va = page + imm
                if macho.in_text_va(va):
                    foff = macho.va_to_file(va)
                    if foff is not None:
                        targets.add(foff)
        bt = decode_b(w, pc)
        if bt is not None and macho.in_text_va(bt):
            foff = macho.va_to_file(bt)
            if foff is not None:
                targets.add(foff)
        blt = decode_bl(w, pc)
        if blt is not None and macho.in_text_va(blt):
            foff = macho.va_to_file(blt)
            if foff is not None:
                targets.add(foff)
        off += 4
    return sorted(targets)


def follow_thunk(macho, target, max_depth=5):
    mm = macho.mm
    seen = set()
    current = target
    for _ in range(max_depth):
        if current in seen:
            break
        seen.add(current)
        if current < 0 or current + 12 > len(mm):
            break
        pc = macho.file_to_va(current)
        if pc is None:
            break
        w0 = u32(mm, current)
        bva = decode_b(w0, pc)
        if bva is not None and macho.in_text_va(bva):
            nxt = macho.va_to_file(bva)
            if nxt is not None:
                current = nxt
                continue
        adrp = decode_adrp(w0, pc)
        if adrp is not None:
            page, base_reg = adrp
            moved = False
            for add_i in (1, 2):
                add = decode_add_x_imm(u32(mm, current + add_i * 4))
                if add is None:
                    continue
                rd, rn, imm = add
                if rn != base_reg:
                    continue
                for br_i in range(add_i + 1, min(add_i + 4, 5)):
                    if decode_br_reg(u32(mm, current + br_i * 4)) == rd:
                        va = page + imm
                        if macho.in_text_va(va):
                            nxt = macho.va_to_file(va)
                            if nxt is not None:
                                current = nxt
                                moved = True
                        break
                if moved:
                    break
            if moved:
                continue
            break
        lit = decode_ldr_x_literal(w0, pc)
        if lit is not None:
            lit_va, rt = lit
            lit_off = macho.va_to_file(lit_va)
            if lit_off is not None:
                ptr = u64(mm, lit_off)
                if ptr is not None and macho.in_text_va(ptr):
                    if decode_br_reg(u32(mm, current + 4)) == rt:
                        nxt = macho.va_to_file(ptr)
                        if nxt is not None:
                            current = nxt
                            continue
        break
    return current


def expand_branch_targets(macho, fidx, target):
    mm = macho.mm
    out = set()
    first = follow_thunk(macho, target)
    out.add(first)
    fstart = fidx.start_containing(first)
    if fstart is None:
        fstart = first
    start, end = fidx.bounds(fstart)
    end = min(end, start + 0x80)
    off = start
    while off + 4 <= end:
        w = u32(mm, off)
        pc = macho.file_to_va(off)
        if pc is None:
            break
        for decoder in (decode_b, decode_bl):
            va = decoder(w, pc)
            if va is None or not macho.in_text_va(va):
                continue
            fo = macho.va_to_file(va)
            if fo is not None:
                out.add(follow_thunk(macho, fo))
        off += 4
    return out


def named_candidates(macho, fidx):
    mm = macho.mm
    evidence = {}
    anchor_hits = []
    for anchor in NAME_ANCHORS:
        for string_off in find_all(mm, anchor):
            for xref in find_string_xrefs(macho, string_off):
                anchor_hits.append(
                    (anchor.decode("ascii", "replace").rstrip("\x00"), string_off, xref)
                )
    for anchor_name, _string_off, xref in anchor_hits:
        for raw_target in collect_code_targets_near(macho, xref):
            for target in expand_branch_targets(macho, fidx, raw_target):
                fstart = fidx.start_containing(target)
                if fstart is None:
                    continue
                info = score_function(mm, fidx, fstart)
                if info is None:
                    continue
                info = dict(info)
                info["base_score"] = info["score"]
                info["score"] += 42
                info["why"] = list(info["why"]) + ["named-registration:" + anchor_name]
                info["xref"] = xref
                old = evidence.get(fstart)
                if old is None or info["score"] > old["score"]:
                    evidence[fstart] = info
    return sorted(evidence.values(), key=lambda x: (-x["score"], x["offset"])), anchor_hits


def structural_candidates(macho, fidx):
    mm = macho.mm
    out = []
    starts = fidx.starts if fidx.starts else list(find_all(mm, KNOWN_PROLOGUE16))
    for start in starts:
        info = score_function(mm, fidx, start)
        if info is None:
            continue
        why = set(info["why"])
        strong = (
            "TechStack-return-shape" in why
            or ("branched-TechStack-shape" in why and "LDR-X0+30" in why)
            or ("legacy-direct-JsonUI-shape" in why and "known-prologue" in why)
        )
        if strong:
            out.append(info)
    return sorted(out, key=lambda x: (-x["score"], x["offset"]))


def select_target(macho, fidx):
    named, anchor_hits = named_candidates(macho, fidx)
    good_named = [c for c in named if c["base_score"] >= NAMED_MIN_SCORE]
    if good_named:
        best = good_named[0]
        if len(good_named) == 1:
            return best, "named-registration", named, anchor_hits
        if best["score"] - good_named[1]["score"] >= 10:
            return best, "named-registration", named, anchor_hits
    structural = structural_candidates(macho, fidx)
    if structural:
        best = structural[0]
        if best["score"] >= STRUCT_MIN_SCORE:
            if len(structural) == 1:
                return best, "LC_FUNCTION_STARTS-structural", structural, anchor_hits
            if best["score"] - structural[1]["score"] >= STRUCT_MIN_MARGIN:
                return best, "LC_FUNCTION_STARTS-structural", structural, anchor_hits
    merged = named if named else structural
    return None, "ambiguous-or-unsupported", merged, anchor_hits


def describe_candidate(c):
    return (
        f"0x{c['offset']:08X} score={c['score']} state={c['state']} "
        f"first8={c['first8'].hex(' ').upper()} " + ",".join(c["why"])
    )


def analyze_binary(path):
    with path.open("rb") as f:
        with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
            macho = MachO(mm)
            fidx = FunctionIndex(macho)
            best, method, candidates, anchors = select_target(macho, fidx)
            return {
                "best": best, "method": method,
                "candidates": candidates, "anchors": anchors,
                "function_start_count": len(fidx.starts),
            }


def output_name(src, mode="q2"):
    suffix = "_No_oreui_all" if mode == "q1" else "_No_oreui"
    p = src.with_name(src.stem + suffix + ".ipa")
    if not p.exists():
        return p
    i = 2
    while True:
        p = src.with_name(f"{src.stem}{suffix}_{i}.ipa")
        if not p.exists():
            return p
        i += 1


def find_minecraftpe(zf):
    hits = [
        name for name in zf.namelist()
        if (lambda parts: len(parts) == 3 and parts[0] == "Payload"
            and parts[1].endswith(".app") and parts[2] == "minecraftpe")
        (name.split("/"))
    ]
    if len(hits) != 1:
        raise RuntimeError(f"cannot uniquely find minecraftpe, candidates: {len(hits)}")
    return hits[0]


def read_version(zf, mc_entry):
    app_dir = mc_entry.rsplit("/", 1)[0]
    try:
        info = plistlib.loads(zf.read(app_dir + "/Info.plist"))
        return (
            info.get("CFBundleShortVersionString"),
            info.get("CFBundleVersion"),
            info.get("CFBundleIdentifier"),
        )
    except Exception:
        return None, None, None


def extract_to_temp(zf, entry):
    temp = tempfile.NamedTemporaryFile(prefix="oreui_mc_", suffix=".bin", delete=False)
    p = Path(temp.name)
    try:
        with temp:
            with zf.open(entry, "r") as src:
                shutil.copyfileobj(src, temp, length=CHUNK)
        return p
    except Exception:
        try:
            p.unlink()
        except Exception:
            pass
        raise


def clone_info(src):
    dst = zipfile.ZipInfo(src.filename, src.date_time)
    dst.compress_type = src.compress_type
    dst.comment = src.comment
    dst.extra = src.extra
    dst.internal_attr = src.internal_attr
    dst.external_attr = src.external_attr
    dst.create_system = src.create_system
    dst.create_version = src.create_version
    dst.extract_version = src.extract_version
    dst.flag_bits = src.flag_bits & ~0x08
    return dst


def copy_entry(zsrc, zdst, info, patch_offset=None):
    ni = clone_info(info)
    if info.is_dir():
        zdst.writestr(ni, b"")
        return
    with zsrc.open(info, "r") as src:
        with zdst.open(ni, "w", force_zip64=True) as dst:
            pos = 0
            while True:
                raw = src.read(CHUNK)
                if not raw:
                    break
                if patch_offset is None:
                    dst.write(raw)
                else:
                    data = bytearray(raw)
                    a0, a1 = pos, pos + len(data)
                    p0, p1 = patch_offset, patch_offset + len(PATCH)
                    a, b = max(a0, p0), min(a1, p1)
                    if a < b:
                        for absolute in range(a, b):
                            data[absolute - a0] = PATCH[absolute - p0]
                    dst.write(data)
                pos += len(raw)


def write_diag(out_path, source_name, version, digest, result):
    best = result["best"]
    lines = [
        "Minecraft iOS IPA Ore UI Auto Patcher v6 Diagnostic",
        "=" * 72,
        f"Source: {source_name}",
        f"SHA-256: {digest}",
        f"Function starts: {result['function_start_count']}",
        f"Decision method: {result['method']}",
    ]
    if version is not None:
        lines += [
            f"Version: {version[0] or '?'}",
            f"Build: {version[1] or '?'}",
            f"Bundle: {version[2] or '?'}",
        ]
    lines += ["", "Name anchors / XREFs:"]
    if result["anchors"]:
        for name, string_off, xref in result["anchors"][:40]:
            lines.append(f"  {name}: string=0x{string_off:08X} xref=0x{xref:08X}")
    else:
        lines.append("  (none)")
    lines += ["", "Candidates:"]
    if result["candidates"]:
        for c in result["candidates"][:40]:
            lines.append("  " + describe_candidate(c))
    else:
        lines.append("  (none)")
    if best is not None:
        lines += ["", "Selected:", "  " + describe_candidate(best)]
    out_path.write_text("\n".join(lines), encoding="utf-8")


def verify_ipa(output, mc_entry, offset):
    with zipfile.ZipFile(output, "r") as zf:
        bad = zf.testzip()
        if bad is not None:
            raise RuntimeError(f"ZIP CRC check failed: {bad}")
        with zf.open(mc_entry, "r") as f:
            remain = offset
            while remain:
                block = f.read(min(remain, CHUNK))
                if not block:
                    raise RuntimeError("unexpected EOF during verification")
                remain -= len(block)
            if f.read(len(PATCH)) != PATCH:
                raise RuntimeError("patched bytes verification failed")


def inject_dylibs(ipa_path, tr, log=print):
    root = Path(__file__).resolve().parent
    zsign = root / "zsign.exe"
    if not zsign.exists():
        raise RuntimeError("zsign.exe not found in script folder")
    for d in DYLIB_LIST:
        if not (root / d).exists():
            raise RuntimeError(f"missing dylib: {d}")
    out = ipa_path.with_name(ipa_path.stem + "_injected.ipa")
    if out.exists():
        out.unlink()
    cmd = [str(zsign), "-a"]
    for d in DYLIB_LIST:
        cmd += ["-l", d]
    cmd += ["-o", str(out), str(ipa_path)]
    log(tr("msg_zsign_cmd", cmd=" ".join(cmd)))
    result = subprocess.run(cmd, cwd=str(root))
    if result.returncode != 0:
        raise RuntimeError("zsign injection failed")
    os.replace(out, ipa_path)
    log(tr("msg_injected", name=ipa_path.name))


def process_ipa(ipa, mode="q2", tr=lambda k, **kw: k, log=print):
    log("")
    log("=" * 72)
    log(ipa.name)
    log("=" * 72)
    temp_mc = None
    try:
        with zipfile.ZipFile(ipa, "r") as zf:
            mc_entry = find_minecraftpe(zf)
            version = read_version(zf, mc_entry)
            log(tr("msg_version", ver=version[0] or "?", build=version[1] or "?"))
            temp_mc = extract_to_temp(zf, mc_entry)
        digest = sha256_path(temp_mc)
        log(tr("msg_sha", sha=digest))
        log(tr("msg_analyzing"))
        result = analyze_binary(temp_mc)
        best = result["best"]
        if best is None:
            diag = ipa.with_name(ipa.stem + "_OreUI_v6_diagnostic.txt")
            write_diag(diag, ipa.name, version, digest, result)
            log(tr("msg_no_target"))
            log(tr("msg_diag", name=diag.name))
            return None
        log(tr("msg_method", method=result["method"]))
        log(tr("msg_selected", desc=describe_candidate(best)))
        if best["state"] == "patched":
            log(tr("msg_already"))
            return None
        offset = best["offset"]
        out = output_name(ipa, mode)
        tmp = out.with_suffix(out.suffix + ".tmp")
        if tmp.exists():
            tmp.unlink()
        log(tr("msg_patch_offset", off=offset))
        log(tr("msg_first8", b=best["first8"].hex(" ").upper()))
        log(tr("msg_patch_bytes", b=PATCH.hex(" ").upper()))
        log(tr("msg_generating", name=out.name))
        try:
            with zipfile.ZipFile(ipa, "r") as src:
                with zipfile.ZipFile(tmp, "w", allowZip64=True) as dst:
                    dst.comment = src.comment
                    for info in src.infolist():
                        copy_entry(
                            src, dst, info,
                            offset if info.filename == mc_entry else None
                        )
            verify_ipa(tmp, mc_entry, offset)
            os.replace(tmp, out)
        except Exception:
            try:
                if tmp.exists():
                    tmp.unlink()
            except Exception:
                pass
            raise
        diag = ipa.with_name(ipa.stem + "_OreUI_v6_result.txt")
        write_diag(diag, ipa.name, version, digest, result)
        if mode == "q1":
            inject_dylibs(out, tr, log=log)
        log(tr("msg_done", name=out.name))
        log(tr("msg_no_overwrite"))
        log(tr("msg_resign"))
        return out
    finally:
        if temp_mc is not None:
            try:
                temp_mc.unlink()
            except Exception:
                pass
class App:
    def __init__(self, root):
        self.root = root
        self.root.geometry("760x640")
        self.root.minsize(680, 560)

        startup_lang = choose_startup_lang()
        self.i18n = I18N(startup_lang)

        self.log_queue = queue.Queue()
        self.worker = None
        self.selected_files = []
        self.out_dir = tk.StringVar(value="")
        self.inject_var = tk.BooleanVar(value=False)
        self.busy = False
        self._widgets = {}

        self._build_ui()
        self._setup_dnd()
        self._apply_lang()
        self._poll_log()

    def tr(self, key, **kw):
        return self.i18n.t(key, **kw)

    def _build_ui(self):
        self.root.grid_rowconfigure(0, weight=3)
        self.root.grid_rowconfigure(1, weight=2)
        self.root.grid_columnconfigure(0, weight=1)

        top = tk.Frame(self.root, padx=10, pady=10)
        top.grid(row=0, column=0, sticky="nsew")

        file_row = tk.Frame(top)
        file_row.pack(fill=tk.X)
        list_frame = tk.Frame(file_row)
        list_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.lbl_files = tk.Label(list_frame, anchor="w")
        self.lbl_files.pack(fill=tk.X)
        self._widgets["files_label"] = self.lbl_files

        self.file_list = tk.Listbox(list_frame, height=5, selectmode=tk.EXTENDED)
        self.file_list.pack(fill=tk.BOTH, expand=True, pady=4)

        btn_col = tk.Frame(file_row)
        btn_col.pack(side=tk.LEFT, fill=tk.Y, padx=8)
        self.btn_add = tk.Button(btn_col, width=14, command=self.add_files)
        self.btn_add.pack(pady=4)
        self.btn_remove = tk.Button(btn_col, width=14, command=self.remove_selected)
        self.btn_remove.pack(pady=4)
        self.btn_clear = tk.Button(btn_col, width=14, command=self.clear_files)
        self.btn_clear.pack(pady=4)
        self._widgets["btn_add"] = self.btn_add
        self._widgets["btn_remove"] = self.btn_remove
        self._widgets["btn_clear"] = self.btn_clear

        self.lbl_dnd = tk.Label(top, fg="#666", anchor="w")
        self.lbl_dnd.pack(fill=tk.X)
        self._widgets["dnd_hint"] = self.lbl_dnd

        opt_row = tk.Frame(top)
        opt_row.pack(fill=tk.X, pady=8)

        self.mode_frame = tk.LabelFrame(opt_row, padx=8, pady=4)
        self.mode_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.chk_inject = tk.Checkbutton(
            self.mode_frame, variable=self.inject_var, wraplength=330, justify=tk.LEFT
        )
        self.chk_inject.pack(anchor="w")
        self._widgets["mode_frame"] = self.mode_frame
        self._widgets["mode_inject"] = self.chk_inject

        self.out_frame = tk.LabelFrame(opt_row, padx=8, pady=4)
        self.out_frame.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=8)
        out_row = tk.Frame(self.out_frame)
        out_row.pack(fill=tk.X)
        tk.Entry(out_row, textvariable=self.out_dir).pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.btn_browse = tk.Button(out_row, width=6, command=self.choose_out_dir)
        self.btn_browse.pack(side=tk.LEFT, padx=4)
        self.btn_open_out = tk.Button(self.out_frame, command=self.open_out_dir)
        self.btn_open_out.pack(anchor="w", pady=4)
        self._widgets["out_frame"] = self.out_frame
        self._widgets["btn_browse"] = self.btn_browse
        self._widgets["btn_open_out"] = self.btn_open_out

        action_row = tk.Frame(top)
        action_row.pack(fill=tk.X)

        self.btn_start = tk.Button(action_row, width=14, command=self.start, bg="#2e7d32", fg="white")
        self.btn_start.pack(side=tk.LEFT)
        self.btn_help = tk.Button(action_row, width=10, command=self.show_help)
        self.btn_help.pack(side=tk.LEFT, padx=6)
        self.btn_credits = tk.Button(action_row, width=10, command=self.show_credits)
        self.btn_credits.pack(side=tk.LEFT)
        self.btn_lang = tk.Button(action_row, width=10, command=self.show_lang)
        self.btn_lang.pack(side=tk.LEFT, padx=6)
        self._widgets["btn_start"] = self.btn_start
        self._widgets["btn_help"] = self.btn_help
        self._widgets["btn_credits"] = self.btn_credits
        self._widgets["btn_lang"] = self.btn_lang

        self.progress = ttk.Progressbar(action_row, mode="determinate")
        self.progress.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=10)

        bottom = tk.Frame(self.root, padx=10, pady=10)
        bottom.grid(row=1, column=0, sticky="nsew")

        self.lbl_log = tk.Label(bottom, anchor="w")
        self.lbl_log.pack(fill=tk.X)
        self._widgets["log_label"] = self.lbl_log
        self.lbl_version = tk.Label(bottom, text=APP_VERSION, anchor="e", fg="#888")
        self.lbl_version.pack(side=tk.BOTTOM, fill=tk.X, anchor="e")

        self.log_text = scrolledtext.ScrolledText(bottom, wrap=tk.WORD, height=8, state=tk.DISABLED)
        self.log_text.pack(fill=tk.BOTH, expand=True, pady=4)

    def _setup_dnd(self):
        if not HAS_DND:
            return
        try:
            self.root.drop_target_register(DND_FILES)
            self.root.dnd_bind("<<Drop>>", self.on_drop)
            for widget in (self.file_list, self.log_text):
                try:
                    widget.drop_target_register(DND_FILES)
                    widget.dnd_bind("<<Drop>>", self.on_drop)
                except Exception:
                    pass
        except Exception:
            pass

    def _apply_lang(self):
        t = self.tr
        self.root.title(t("app_title"))
        self._widgets["files_label"].configure(text=t("files_label"))
        self._widgets["btn_add"].configure(text=t("btn_add"))
        self._widgets["btn_remove"].configure(text=t("btn_remove"))
        self._widgets["btn_clear"].configure(text=t("btn_clear"))
        self._widgets["dnd_hint"].configure(
            text=t("dnd_hint") if HAS_DND else t("dnd_missing"),
            fg="#666" if HAS_DND else "#a00",
        )
        self._widgets["mode_frame"].configure(text=t("mode_frame"))
        self._widgets["mode_inject"].configure(text=t("mode_inject"))
        self._widgets["out_frame"].configure(text=t("out_frame"))
        self._widgets["btn_browse"].configure(text=t("btn_browse"))
        self._widgets["btn_open_out"].configure(text=t("btn_open_out"))
        self._widgets["btn_start"].configure(
            text=t("btn_start_busy") if self.busy else t("btn_start")
        )
        self._widgets["btn_help"].configure(text=t("btn_help"))
        self._widgets["btn_credits"].configure(text=CREDITS_TITLE)
        self._widgets["btn_lang"].configure(text=t("btn_lang"))
        self._widgets["log_label"].configure(text=t("log_label"))

    def set_language(self, code):
        err = self.i18n.load(code)
        if err:
            self.log(f"[lang] {err}")
        reg_write("lang", self.i18n.code)
        self._apply_lang()

    def add_files(self):
        files = filedialog.askopenfilenames(
            title=self.tr("files_label"),
            filetypes=[("IPA", "*.ipa"), ("All", "*.*")],
        )
        self._add_paths([Path(f) for f in files])

    def on_drop(self, event):
        try:
            raw = self.root.tk.splitlist(event.data)
        except Exception:
            raw = event.data.split()
        paths = []
        for item in raw:
            p = Path(item.strip("{}"))
            if p.is_dir():
                paths.extend(sorted(p.glob("*.ipa")))
            else:
                paths.append(p)
        self._add_paths(paths)

    def _add_paths(self, paths):
        existing = {p.resolve() for p in self.selected_files}
        added = 0
        for p in paths:
            if p.suffix.lower() != ".ipa" or not p.is_file():
                continue
            rp = p.resolve()
            if rp in existing:
                continue
            existing.add(rp)
            self.selected_files.append(p)
            self.file_list.insert(tk.END, str(p))
            added += 1
        if added:
            self.log(self.tr("msg_added", added=added, total=len(self.selected_files)))

    def remove_selected(self):
        for i in reversed(list(self.file_list.curselection())):
            self.file_list.delete(i)
            del self.selected_files[i]

    def clear_files(self):
        self.file_list.delete(0, tk.END)
        self.selected_files.clear()

    def choose_out_dir(self):
        d = filedialog.askdirectory(title=self.tr("out_frame"))
        if d:
            self.out_dir.set(d)

    def open_out_dir(self):
        d = self.out_dir.get().strip()
        if not d:
            d = str(self.selected_files[0].parent) if self.selected_files else ""
        if not d or not Path(d).exists():
            messagebox.showwarning(self.tr("app_title"), self.tr("msg_out_missing"))
            return
        try:
            if hasattr(os, "startfile"):
                os.startfile(d)
            elif sys.platform == "darwin":
                subprocess.run(["open", d])
            else:
                subprocess.run(["xdg-open", d])
        except Exception as e:
            messagebox.showerror(
                self.tr("app_title"), self.tr("msg_open_fail", err=e)
            )

    def log(self, msg):
        self.log_queue.put(str(msg))

    def _poll_log(self):
        try:
            while True:
                msg = self.log_queue.get_nowait()
                self.log_text.configure(state=tk.NORMAL)
                self.log_text.insert(tk.END, msg + "\n")
                self.log_text.see(tk.END)
                self.log_text.configure(state=tk.DISABLED)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_log)

    def start(self):
        if self.busy:
            return
        if not self.selected_files:
            messagebox.showinfo(self.tr("app_title"), self.tr("msg_no_files"))
            return
        mode = "q1" if self.inject_var.get() else "q2"
        out_dir = Path(self.out_dir.get().strip()) if self.out_dir.get().strip() else None
        if out_dir is not None:
            try:
                out_dir.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                messagebox.showerror(
                    self.tr("app_title"), self.tr("msg_mkdir_fail", err=e)
                )
                return
        files = list(self.selected_files)
        self.busy = True
        self.btn_start.configure(state=tk.DISABLED, text=self.tr("btn_start_busy"))
        self.progress.configure(maximum=len(files), value=0)
        self.log("=" * 60)
        self.log(self.tr("msg_batch_start", count=len(files), mode=mode))
        self.log("=" * 60)
        self.worker = threading.Thread(
            target=self._run_batch, args=(files, mode, out_dir), daemon=True
        )
        self.worker.start()

    def _run_batch(self, files, mode, out_dir):
        ok, fail = 0, 0
        tr = self.tr
        for i, ipa in enumerate(files, 1):
            self.log("")
            self.log(tr("msg_item", i=i, total=len(files), name=ipa.name))
            try:
                result_ipa = process_ipa(ipa, mode=mode, tr=tr, log=self.log)
                if out_dir is not None and result_ipa is not None:
                    result_ipa = Path(result_ipa)
                    if result_ipa.exists() and result_ipa.parent.resolve() != out_dir.resolve():
                        target = out_dir / result_ipa.name
                        if target.exists():
                            j = 2
                            while True:
                                cand = out_dir / f"{result_ipa.stem}_{j}{result_ipa.suffix}"
                                if not cand.exists():
                                    target = cand
                                    break
                                j += 1
                        shutil.copy2(result_ipa, target)
                        self.log(tr("msg_copied", path=str(target)))
                ok += 1
            except Exception as e:
                fail += 1
                self.log(tr("msg_fail", type=type(e).__name__, err=e))
            finally:
                self.root.after(0, lambda v=i: self.progress.configure(value=v))
        self.log("")
        self.log("=" * 60)
        self.log(tr("msg_batch_done", ok=ok, fail=fail))
        self.log("=" * 60)
        self.root.after(0, self._finish)

    def _finish(self):
        self.busy = False
        self.btn_start.configure(state=tk.NORMAL, text=self.tr("btn_start"))

    def _text_window(self, title, text, w=540, h=460):
        win = tk.Toplevel(self.root)
        win.title(title)
        win.geometry(f"{w}x{h}")
        txt = scrolledtext.ScrolledText(win, wrap=tk.WORD)
        txt.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        txt.insert(tk.END, text)
        txt.configure(state=tk.DISABLED)
        tk.Button(win, text=self.tr("btn_close"), command=win.destroy).pack(pady=8)

    def show_help(self):
        self._text_window(self.tr("help_title"), self.tr("help_text"))

    def show_credits(self):
        """鸣谢窗口：锁字符串文本 + 3 个固定文字按钮打开链接。"""
        win = tk.Toplevel(self.root)
        win.title(CREDITS_TITLE)
        win.geometry("520x480")
        win.transient(self.root)
        win.grab_set()

        txt = scrolledtext.ScrolledText(win, wrap=tk.WORD)
        txt.pack(fill=tk.BOTH, expand=True, padx=8, pady=(8, 4))
        txt.insert(tk.END, CREDITS_TEXT)
        txt.configure(state=tk.DISABLED)

        def make_open(idx):
            def _open():
                url = (CREDIT_LINKS[idx] or "").strip()
                if not url:
                    messagebox.showinfo(CREDITS_TITLE, "链接未设置。")
                    return
                try:
                    webbrowser.open(url)
                except Exception as e:
                    messagebox.showerror(CREDITS_TITLE, f"无法打开链接：{e}")
            return _open

        btn_row = tk.Frame(win)
        btn_row.pack(fill=tk.X, padx=8, pady=(4, 8))
        for i in range(3):
            tk.Button(
                btn_row, text=CREDIT_BUTTON_TEXTS[i], width=14,
                command=make_open(i)
            ).pack(side=tk.LEFT, expand=True, padx=4)

        tk.Button(win, text=self.tr("btn_close"), command=win.destroy).pack(pady=(0, 8))

    def show_lang(self):
        win = tk.Toplevel(self.root)
        win.title(self.tr("lang_title"))
        win.geometry("360x300")
        win.transient(self.root)
        win.grab_set()
        tk.Label(win, text=self.tr("lang_title"), anchor="w").pack(fill=tk.X, padx=12, pady=8)
        var = tk.StringVar(value=self.i18n.code)
        for code in ("zh-CN", "zh-TW", "zh-HK", "en-US", "ja-JP", "ko-KR"):
            tk.Radiobutton(
                win, text=LANG_NAMES[code], value=code, variable=var, anchor="w"
            ).pack(fill=tk.X, padx=16, pady=2)
        btn_row = tk.Frame(win)
        btn_row.pack(fill=tk.X, padx=12, pady=10)
        def on_ok():
            self.set_language(var.get())
            win.destroy()
        def on_cancel():
            win.destroy()
        tk.Button(btn_row, text="OK", width=10, command=on_ok).pack(side=tk.RIGHT)
        tk.Button(btn_row, text=self.tr("btn_close"), width=10, command=on_cancel).pack(side=tk.RIGHT, padx=6)


def main():
    root = TkinterDnD.Tk() if HAS_DND else tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
