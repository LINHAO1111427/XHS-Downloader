#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
video2livephoto —— 把视频转成 iPhone「实况图」(Live Photo)
=========================================================
核心承诺：视频**不重新编码**，采样数据逐字节原样搬运。

只改容器层：
  * ftyp   品牌改为 qt
  * moov   注入 com.apple.quicktime.content.identifier（配对标识）
  * stco   重算 chunk 偏移
  * still  封面图写入 Apple MakerNote 0x0011（同一个 UUID）

零第三方依赖即可完成重封装；封面帧提取优先用 Windows 内置解码器，
也可以用 ffmpeg（可选）或你自己指定的图片。
"""
from __future__ import annotations

import argparse
import json
import os
import struct
import subprocess
import sys
import time
import uuid as uuidlib

VERSION = "1.1.0"

# ===========================================================================
# 1. ISOBMFF (MP4 / QuickTime) 盒子解析 / 序列化
# ===========================================================================

CONTAINERS = {b"moov", b"trak", b"mdia", b"minf", b"stbl", b"dinf", b"edts",
              b"udta", b"mvex", b"moof", b"traf", b"mfra", b"wave", b"gmhd",
              b"ilst", b"ipro", b"sinf", b"schi"}
FULL_CONTAINERS = {b"meta"}
INDEXED_CONTAINERS = {b"ilst"}          # 子盒类型是 4 字节 key 索引的容器


def U16(b, o=0): return int.from_bytes(b[o:o + 2], "big")
def U32(b, o=0): return int.from_bytes(b[o:o + 4], "big")
def U64(b, o=0): return int.from_bytes(b[o:o + 8], "big")


class Box:
    """ISOBMFF 盒子。children 非 None 即容器，否则用 payload。"""

    __slots__ = ("type", "payload", "children", "full", "ver", "flags", "src")

    def __init__(self, btype, payload=b"", children=None, full=False, ver=0, flags=0):
        self.type = btype
        self.payload = payload
        self.children = children
        self.full = full
        self.ver = ver
        self.flags = flags
        self.src = None                       # (offset, total_size, header_size)

    def body(self):
        head = (struct.pack(">B", self.ver) + self.flags.to_bytes(3, "big")) if self.full else b""
        if self.children is not None:
            return head + b"".join(c.serialize() for c in self.children)
        return head + self.payload

    def serialize(self):
        b = self.body()
        n = len(b) + 8
        if n > 0xFFFFFFFF:
            return struct.pack(">I", 1) + self.type + struct.pack(">Q", n + 8) + b
        return struct.pack(">I", n) + self.type + b

    def get(self, btype):
        for c in (self.children or ()):
            if c.type == btype:
                return c
        return None

    def all(self, btype):
        return [c for c in (self.children or ()) if c.type == btype]

    def path(self, *types):
        node = self
        for t in types:
            node = node.get(t)
            if node is None:
                return None
        return node

    def walk(self):
        yield self
        for c in (self.children or ()):
            yield from c.walk()

    def __repr__(self):
        kind = "container" if self.children is not None else "%d bytes" % len(self.payload)
        return "<%s %s>" % (self.type.decode("latin1", "replace"), kind)


def _read_header(data, pos, end):
    if pos + 8 > end:
        return None
    size = U32(data, pos)
    btype = data[pos + 4:pos + 8]
    hdr = 8
    if size == 1:
        if pos + 16 > end:
            return None
        size = U64(data, pos + 8)
        hdr = 16
    elif size == 0:
        size = end - pos
    if size < hdr or pos + size > end:
        return None
    return btype, hdr, size


def parse(data, start=0, end=None, depth=0):
    if end is None:
        end = len(data)
    boxes = []
    pos = start
    while True:
        h = _read_header(data, pos, end)
        if h is None:
            break
        btype, hdr, size = h
        pstart, pend = pos + hdr, pos + size
        box = Box(btype)
        box.src = (pos, size, hdr)
        if btype in CONTAINERS or btype in FULL_CONTAINERS:
            full = btype in FULL_CONTAINERS
            off = pstart
            if full:
                if off + 4 <= pend:
                    box.full = True
                    box.ver = data[off]
                    box.flags = U32(b"\0" + data[off + 1:off + 4])
                    off += 4
                else:
                    full = False
            kids = parse(data, off, pend, depth + 1) if depth < 8 else []
            if kids and sum(k.src[1] for k in kids) == pend - off:
                if btype in INDEXED_CONTAINERS:
                    # ilst 的子盒用二进制 key 索引当"类型"，需要再往里解析一层
                    for k in kids:
                        o = k.src[0] + k.src[2]
                        sub = parse(data, o, o + k.src[1] - k.src[2], depth + 2)
                        if sub and sum(s.src[1] for s in sub) == k.src[1] - k.src[2]:
                            k.children = sub
                box.children = kids
            else:
                box.children = None
                box.full = False
                box.payload = data[pstart:pend]
        else:
            box.payload = data[pstart:pend]
        boxes.append(box)
        pos = pend
        if pos >= end:
            break
    return boxes


def load(path):
    with open(path, "rb") as f:
        data = f.read()
    return data, parse(data)


def clone_box(box):
    return parse(box.serialize())[0]


def leaf(btype, payload=b"", **kw): return Box(btype, payload=payload, **kw)
def container(btype, children, **kw): return Box(btype, children=list(children), **kw)
def full_leaf(btype, payload=b"", ver=0, flags=0):
    return Box(btype, payload=payload, full=True, ver=ver, flags=flags)


# ===========================================================================
# 2. 轨道信息 / 样本表
# ===========================================================================

HANDLER_NAME = {b"vide": "video", b"soun": "audio", b"mdta": "metadata",
                b"meta": "metadata", b"text": "text", b"sbtl": "subtitle"}


class Track:
    def __init__(self, trak):
        self.trak = trak
        self.mdia = trak.path(b"mdia")
        self.minf = trak.path(b"mdia", b"minf")
        self.stbl = trak.path(b"mdia", b"minf", b"stbl")
        hdlr = self.mdia.get(b"hdlr") if self.mdia else None
        self.handler = hdlr.payload[8:12] if hdlr else b"????"
        self.kind = HANDLER_NAME.get(self.handler, self.handler.decode("latin1", "replace"))
        mdhd = self.mdia.get(b"mdhd") if self.mdia else None
        self.timescale = self.duration = 0
        if mdhd:
            p = mdhd.payload
            if mdhd.ver == 1:
                self.timescale, self.duration = U32(p, 20), U64(p, 24)
            else:
                self.timescale, self.duration = U32(p, 12), U32(p, 16)
        self.width = self.height = 0
        tkhd = trak.get(b"tkhd")
        if tkhd:
            p = tkhd.payload
            self.width = U32(p, len(p) - 8) / 65536.0
            self.height = U32(p, len(p) - 4) / 65536.0
        self.codec = "?"
        stsd = self.stbl.get(b"stsd") if self.stbl else None
        if stsd and len(stsd.payload) >= 16:
            self.codec = stsd.payload[12:16].decode("latin1", "replace")
        self.samples = 0
        stsz = self.stbl.get(b"stsz") if self.stbl else None
        if stsz:
            self.samples = U32(stsz.payload, 8)
        self.seconds = self.duration / self.timescale if self.timescale else 0.0
        self.fps = self.samples / self.seconds if self.seconds else 0.0
        self.track_id = U32(tkhd.payload, 12) if tkhd else 0

    def sample_sizes(self):
        stsz = self.stbl.get(b"stsz")
        if stsz is None:
            return []
        p = stsz.payload
        uniform, count = U32(p, 4), U32(p, 8)
        if uniform:
            return [uniform] * count
        return [U32(p, 12 + 4 * i) for i in range(count)]

    def chunk_offsets(self):
        stco = self.stbl.get(b"stco") or self.stbl.get(b"co64")
        if stco is None:
            return [], False
        p = stco.payload
        cnt = U32(p, 4)
        if stco.type == b"co64":
            return [U64(p, 8 + 8 * i) for i in range(cnt)], True
        return [U32(p, 8 + 4 * i) for i in range(cnt)], False

    def sample_ranges(self):
        """按解码顺序给出每个样本的 (file_offset, size)。"""
        stsc = self.stbl.get(b"stsc")
        sizes = self.sample_sizes()
        chunks, _ = self.chunk_offsets()
        if stsc is None or not chunks:
            return []
        sp = stsc.payload
        n = U32(sp, 4)
        ent = [(U32(sp, 8 + 12 * i), U32(sp, 12 + 12 * i)) for i in range(n)]
        per_chunk = []
        for i, (first, spc) in enumerate(ent):
            last = (ent[i + 1][0] - 1) if i + 1 < len(ent) else len(chunks)
            per_chunk += [spc] * max(0, last - first + 1)
        while len(per_chunk) < len(chunks):
            per_chunk.append(per_chunk[-1] if per_chunk else 0)
        out, si = [], 0
        for ci, off in enumerate(chunks):
            cur = off
            for _ in range(per_chunk[ci]):
                if si >= len(sizes):
                    return out
                out.append((cur, sizes[si]))
                cur += sizes[si]
                si += 1
        return out

    def __repr__(self):
        return "<%s %s %.2fs %dx%d fps=%.1f>" % (
            self.kind, self.codec, self.seconds, self.width, self.height, self.fps)


def tracks_of(moov):
    return [Track(t) for t in moov.all(b"trak")]


# ===========================================================================
# 3. Live Photo 元数据构造
# ===========================================================================

KEY_CONTENT_ID = "com.apple.quicktime.content.identifier"

# 配对标识自检不等于手机端兼容性验证；这里不制造相机运动传感器数据。

DATA_UTF8 = 1
DATA_UNDEFINED = 0


def make_hdlr(handler, name=b"\x00"):
    return full_leaf(b"hdlr", struct.pack(">I", 0) + handler + b"\x00" * 12 + name)


def make_keys(keys):
    body = struct.pack(">I", len(keys))
    for k in keys:
        kb = k.encode("utf-8")
        body += struct.pack(">I", len(kb) + 8) + b"mdta" + kb
    return full_leaf(b"keys", body)


def make_ilst(items):
    kids = []
    for idx, flags, value in items:
        kids.append(container(struct.pack(">I", idx),
                              [full_leaf(b"data", b"\x00" * 4 + value, flags=flags)]))
    return container(b"ilst", kids)


def make_moov_meta(content_id, extra_keys=()):
    """moov/meta —— iOS 靠这里的 content.identifier 把图片和视频配成实况图。"""
    keys = [KEY_CONTENT_ID] + list(extra_keys)
    items = [(1, DATA_UTF8, content_id.encode("ascii"))]
    return container(b"meta", [make_hdlr(b"mdta"), make_keys(keys), make_ilst(items)],
                     full=True)


def make_ftyp():
    """QuickTime 品牌。iOS 实况图的视频必须是 .MOV / qt。"""
    return leaf(b"ftyp", b"qt  " + struct.pack(">I", 0x00000200) + b"qt  ")


# --- Apple MakerNote：图片侧的配对标识 (tag 0x0011) --------------------------

def build_makernote(content_id):
    """构造 Apple MakerNote 数据块。

    结构（与 exiftool 的 Apple 定义一致）：
        offset 0  : b"Apple iOS\\x00\\x00\\x01MM"   (14 字节头，MM = 大端)
        offset 14 : IFD0（条目数 + 条目 + 下一 IFD 偏移）
        offset 32 : UUID 字符串
    条目里的偏移量 **相对 maker note 起点**，不是相对内嵌 TIFF 头。
    """
    s = content_id.encode("ascii") + b"\x00"
    ifd_off = 14
    value_off = ifd_off + 2 + 12 + 4          # = 32
    ifd = struct.pack(">H", 1)                                  # 条目数
    ifd += struct.pack(">HHI", 0x0011, 2, len(s))               # tag/type(ASCII)/count
    ifd += struct.pack(">I", value_off)                         # 值偏移
    ifd += struct.pack(">I", 0)                                 # 下一个 IFD = 无
    return b"Apple iOS\x00\x00\x01MM" + ifd + s


def build_exif_app1(content_id):
    """Place Apple MakerNote in the Exif sub-IFD, as required by EXIF readers."""
    mn = build_makernote(content_id)
    tiff = b"MM\x00\x2a" + struct.pack(">I", 8)
    exif_offset, mn_offset = 26, 44
    ifd0 = struct.pack(">H", 1) + struct.pack(">HHII", 0x8769, 4, 1, exif_offset) + struct.pack(">I", 0)
    exif = struct.pack(">H", 1) + struct.pack(">HHII", 0x927C, 7, len(mn), mn_offset) + struct.pack(">I", 0)
    body = b"Exif\x00\x00" + tiff + ifd0 + exif + mn
    return b"\xff\xe1" + struct.pack(">H", len(body) + 2) + body


def read_apple_makernote(jpeg_bytes):
    """把上面写进去的 ContentIdentifier 读回来（自检用）。"""
    i = jpeg_bytes.find(b"Apple iOS\x00\x00\x01MM")
    if i < 0:
        return None
    p = i + 14
    n = U16(jpeg_bytes, p)
    for k in range(n):
        e = p + 2 + 12 * k
        if U16(jpeg_bytes, e) == 0x0011:
            cnt = U32(jpeg_bytes, e + 4)
            off = U32(jpeg_bytes, e + 8)
            raw = jpeg_bytes[i + off:i + off + cnt]
            return raw.rstrip(b"\x00").decode("ascii", "replace")
    return None


def jpeg_segments(data):
    """切出 JPEG 的段列表 [(marker, payload)]，遇到 SOS 停止。"""
    if data[:2] != b"\xff\xd8":
        raise ValueError("不是 JPEG 文件")
    out = []
    i = 2
    while i < len(data) - 1:
        if data[i] != 0xFF:
            i += 1
            continue
        m = data[i + 1]
        if m in (0xD8, 0x01) or 0xD0 <= m <= 0xD7:
            i += 2
            continue
        if m == 0xDA:                                  # SOS -> 后面全是压缩数据
            return out, i
        ln = U16(data, i + 2)
        out.append((m, data[i + 4:i + 2 + ln]))
        i += 2 + ln
    raise ValueError("JPEG 结构异常：找不到 SOS")


def inject_exif(jpeg_bytes, content_id, keep_existing=False):
    """把实况图 EXIF 注入 JPEG。默认丢弃旧 APP1/Exif（视频抽帧本来就没有）。"""
    segs, sos_at = jpeg_segments(jpeg_bytes)
    body = b""
    lead = b""
    for m, payload in segs:
        if m == 0xE1 and payload[:6] == b"Exif\x00\x00" and not keep_existing:
            continue
        raw = b"\xff" + bytes([m]) + struct.pack(">H", len(payload) + 2) + payload
        if m == 0xE0 and not lead:            # JFIF 段保持在最前面
            lead = raw
        else:
            body += raw
    return (b"\xff\xd8" + lead + build_exif_app1(content_id) + body
            + jpeg_bytes[sos_at:])


# ===========================================================================
# 4. 无损重封装引擎
# ===========================================================================

class LivePhotoError(Exception):
    pass


def remux(src_path, out_path, content_id, verify=True):
    """把 MP4 变成 Live Photo 用的 .MOV —— 视频采样数据一字节都不改。"""
    data, top = load(src_path)
    ftyp = next((b for b in top if b.type == b"ftyp"), None)
    moov_src = next((b for b in top if b.type == b"moov"), None)
    if moov_src is None:
        raise LivePhotoError("文件里没有 moov，可能不是 MP4/MOV")
    if moov_src.get(b"mvex") is not None:
        raise LivePhotoError("这是分片 MP4 (fMP4)，请先用 ffmpeg -c copy 转成普通 MP4")

    mdat_boxes = [b for b in top if b.type == b"mdat"]
    if not mdat_boxes:
        raise LivePhotoError("文件里没有 mdat（可能视频数据缺失）")

    moov = clone_box(moov_src)

    # 移除旧的 moov/meta，写入实况图配对标识
    if moov.children is not None:
        moov.children = [c for c in moov.children if c.type != b"meta"]
        moov.children.append(make_moov_meta(content_id))

    out_ftyp = make_ftyp()
    moov_size = len(moov.serialize())
    base = len(out_ftyp.serialize()) + moov_size + 8   # 新 mdat 载荷起点

    ranges = []
    cur = base
    for b in mdat_boxes:
        off, size, hdr = b.src
        plen = size - hdr
        ranges.append((off + hdr, plen, cur))
        cur += plen

    data_off = base
    for box in moov.walk():
        if box.type in (b"stco", b"co64"):
            wide = box.type == b"co64"
            cnt = U32(box.payload, 4)
            body = box.payload[:4] + struct.pack(">I", cnt)   # 保留 version/flags
            for i in range(cnt):
                old = U64(box.payload, 8 + 8 * i) if wide else U32(box.payload, 8 + 4 * i)
                new = None
                for o_start, o_len, n_start in ranges:
                    if o_start <= old < o_start + o_len:
                        new = n_start + (old - o_start)
                        break
                if new is None:
                    raise LivePhotoError("样本偏移 0x%X 不在 mdat 内，无法无损搬运" % old)
                if not wide and new > 0xFFFFFFFF:
                    raise LivePhotoError("超过 4 GiB，需要 co64（暂不支持）")
                body += struct.pack(">Q", new) if wide else struct.pack(">I", new)
            box.payload = body

    if len(moov.serialize()) != moov_size:
        raise LivePhotoError("内部错误：moov 大小在回填偏移后发生变化")

    with open(out_path, "wb") as f:
        f.write(out_ftyp.serialize())
        f.write(moov.serialize())
        f.write(struct.pack(">I", sum(r[1] for r in ranges) + 8) + b"mdat")
        for o_start, o_len, _n in ranges:
            f.write(data[o_start:o_start + o_len])

    result = {"bytes_in": len(data), "bytes_out": os.path.getsize(out_path)}
    if verify:
        result["verified"] = verify_lossless(src_path, out_path)
        if not result["verified"]:
            raise LivePhotoError("校验失败：输出文件的采样数据与源文件不一致")
    return result


def verify_lossless(src_path, dst_path):
    """逐个样本比对：确认视频数据真的一个字节都没变。"""
    _s, stop = load(src_path)
    _d, dtop = load(dst_path)
    smoov = next((b for b in stop if b.type == b"moov"), None)
    dmoov = next((b for b in dtop if b.type == b"moov"), None)
    if not smoov or not dmoov:
        return False
    with open(src_path, "rb") as source_file:
        sd = source_file.read()
    with open(dst_path, "rb") as destination_file:
        dd = destination_file.read()
    stracks = {t.track_id: t for t in tracks_of(smoov)}
    for dt in tracks_of(dmoov):
        st = stracks.get(dt.track_id)
        if st is None:
            continue
        sr, dr = st.sample_ranges(), dt.sample_ranges()
        if len(sr) != len(dr):
            return False
        for (so, ss), (do, ds) in zip(sr, dr):
            if ss != ds or sd[so:so + ss] != dd[do:do + ds]:
                return False
    return True


def probe(path):
    _data, top = load(path)
    moov = next((b for b in top if b.type == b"moov"), None)
    if moov is None:
        raise LivePhotoError("找不到 moov")
    return tracks_of(moov)

# ===========================================================================
# 5. 封面帧提取
# ===========================================================================

def _win_thumbnail(path, want_w, want_h):
    """调用 Windows Shell 缩略图提供程序解码一帧。

    实测：请求 ≥ 原始分辨率的画布时，返回的是**原生分辨率**的真实解码帧
    （不是缓存里的小图放大）。返回 (像素 BGRA, 宽, 高, 画布宽, 画布高)。
    """
    import ctypes
    import ctypes.wintypes as wt

    class GUID(ctypes.Structure):
        _fields_ = [("d1", ctypes.c_uint32), ("d2", ctypes.c_uint16),
                    ("d3", ctypes.c_uint16), ("d4", ctypes.c_ubyte * 8)]

        def __init__(self, s):
            super().__init__()
            a, b, c, d, e = s.strip("{}").split("-")
            self.d1, self.d2, self.d3 = int(a, 16), int(b, 16), int(c, 16)
            for i in range(2):
                self.d4[i] = int(d[i * 2:i * 2 + 2], 16)
            for i in range(6):
                self.d4[2 + i] = int(e[i * 2:i * 2 + 2], 16)

    class BITMAP(ctypes.Structure):
        _fields_ = [("bmType", wt.LONG), ("bmWidth", wt.LONG), ("bmHeight", wt.LONG),
                    ("bmWidthBytes", wt.LONG), ("bmPlanes", wt.WORD),
                    ("bmBitsPixel", wt.WORD), ("bmBits", ctypes.c_void_p)]

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG),
                    ("biPlanes", wt.WORD), ("biBitCount", wt.WORD),
                    ("biCompression", wt.DWORD), ("biSizeImage", wt.DWORD),
                    ("biXPelsPerMeter", wt.LONG), ("biYPelsPerMeter", wt.LONG),
                    ("biClrUsed", wt.DWORD), ("biClrImportant", wt.DWORD)]

    class BITMAPINFO(ctypes.Structure):
        _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wt.DWORD * 3)]

    ole32 = ctypes.windll.ole32
    shell32 = ctypes.windll.shell32
    gdi32 = ctypes.windll.gdi32
    user32 = ctypes.windll.user32
    ole32.CoInitialize(None)

    iid = GUID("{bcc18b79-ba16-442f-80c4-8a59c30c463b}")     # IShellItemImageFactory
    p = ctypes.c_void_p()
    hr = shell32.SHCreateItemFromParsingName(ctypes.c_wchar_p(os.path.abspath(path)),
                                             None, ctypes.byref(iid), ctypes.byref(p))
    if hr < 0 or not p.value:
        raise LivePhotoError("Windows 缩略图接口调用失败 (hr=0x%08X)" % (hr & 0xFFFFFFFF))
    vt = ctypes.cast(p, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    proto = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.c_int64,
                               ctypes.c_int, ctypes.POINTER(ctypes.c_void_p))
    GetImage = proto(vt[3])
    hbm = ctypes.c_void_p()
    size = (want_h << 32) | (want_w & 0xFFFFFFFF)
    hr = GetImage(p, size, 0x1 | 0x100, ctypes.byref(hbm))   # BIGGERSIZEOK | SCALEUP
    if hr < 0 or not hbm.value:
        raise LivePhotoError("系统无法解码该视频的封面帧 (hr=0x%08X)" % (hr & 0xFFFFFFFF))

    bm = BITMAP()
    gdi32.GetObjectW(hbm, ctypes.sizeof(BITMAP), ctypes.byref(bm))
    cw, ch = int(bm.bmWidth), int(bm.bmHeight)

    bi = BITMAPINFO()
    bi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bi.bmiHeader.biWidth = cw
    bi.bmiHeader.biHeight = -ch
    bi.bmiHeader.biPlanes = 1
    bi.bmiHeader.biBitCount = 32
    bi.bmiHeader.biCompression = 0
    hdc = user32.GetDC(None)
    buf = ctypes.create_string_buffer(cw * ch * 4)
    got = gdi32.GetDIBits(hdc, hbm, 0, ch, buf, ctypes.byref(bi), 0)
    user32.ReleaseDC(None, hdc)
    gdi32.DeleteObject(hbm)
    if got == 0:
        raise LivePhotoError("读取解码像素失败")
    return buf.raw, cw, ch


def crop_canvas(raw, cw, ch, vw, vh):
    """缩略图接口把画面按比例放在画布左上角，这里裁回真实尺寸。"""
    if cw == vw and ch == vh:
        return raw, vw, vh
    scale = min(cw / float(vw), ch / float(vh))
    fw, fh = int(round(vw * scale)), int(round(vh * scale))
    if fw <= 0 or fh <= 0 or fw > cw or fh > ch:
        return raw, cw, ch
    rows = [raw[y * cw * 4:(y * cw + fw) * 4] for y in range(fh)]
    return b"".join(rows), fw, fh


def extract_still(video_path, vw, vh):
    """返回 (BGRA 像素, 宽, 高)。"""
    raw, cw, ch = _win_thumbnail(video_path, vw, vh)
    raw, fw, fh = crop_canvas(raw, cw, ch, vw, vh)
    return raw, fw, fh


def encode_jpeg(raw_bgra, w, h, quality=97):
    """BGRA -> JPEG。用 Pillow；通道顺序是 B,G,R,A。"""
    try:
        from PIL import Image
    except ImportError:
        raise LivePhotoError(
            "缺少 Pillow，无法把解码出的画面存成 JPEG。\n"
            "  解决：pip install pillow\n"
            "  或者用 -c/--cover 直接指定一张现成的 JPEG 封面（那条路径不需要 Pillow）")
    img = Image.frombytes("RGBA", (w, h), raw_bgra).convert("RGB")
    import io
    bio = io.BytesIO()
    img.save(bio, "JPEG", quality=quality, subsampling=0, optimize=True)
    return bio.getvalue()


def load_cover(path, quality=97):
    """读取用户指定的封面。JPEG 直接原样复用（连压缩都省了）。"""
    with open(path, "rb") as f:
        blob = f.read()
    if blob[:2] == b"\xff\xd8":
        return blob, True
    try:
        from PIL import Image, ImageOps
    except ImportError:
        raise LivePhotoError("封面不是 JPEG，需要 Pillow 来转换：pip install pillow")
    import io
    img = Image.open(io.BytesIO(blob))
    img = ImageOps.exif_transpose(img).convert("RGB")
    bio = io.BytesIO()
    img.save(bio, "JPEG", quality=quality, subsampling=0, optimize=True)
    return bio.getvalue(), False

# ===========================================================================
# 6. 命令行
# ===========================================================================

BANNER = "video2livephoto %s —— 视频 -> iPhone 实况图（视频不重编码）" % VERSION


def human(n):
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024 or u == "GB":
            return "%.1f %s" % (n, u) if u != "B" else "%d B" % n
        n /= 1024.0


def safe_stem(path):
    stem = os.path.splitext(os.path.basename(path))[0]
    bad = '<>:"/\\|?*'
    stem = "".join(c for c in stem if c not in bad).strip() or "LIVE"
    return stem


def cmd_info(args):
    for path in args.files:
        print("=" * 68)
        print(path)
        try:
            ts = probe(path)
        except LivePhotoError as e:
            print("  读取失败:", e)
            continue
        size = os.path.getsize(path)
        _d, top = load(path)
        names = ", ".join(b.type.decode("latin1", "replace").strip() for b in top)
        print("  大小 %.1f MB   顶层盒子: %s" % (size / 1048576.0, names))
        for i, t in enumerate(ts):
            print("  #%d %-8s %-5s %6.2fs  %s%s  样本=%d  %.1f fps" % (
                i, t.kind, t.codec, t.seconds,
                ("%dx%d " % (t.width, t.height)) if t.width else "",
                ("ts=%d" % t.timescale), t.samples, t.fps))
            if t.kind == "video":
                if t.codec not in ("avc1", "avc3"):
                    print("      ! 编码是 %s，iOS 实况图建议用 H.264(avc1)" % t.codec)
                if t.seconds > 3.0:
                    print("      ! 时长 %.1fs 超过 3 秒，做锁屏壁纸可能被系统拒绝" % t.seconds)
        return 0


def cmd_convert(args):
    """支持一次传多个视频。"""
    files = list(args.video)
    if len(files) > 1 and args.name:
        print("提示: -n/--name 只对单个文件有意义，多文件时已忽略。")
        args.name = None
    results, rc = [], 0
    for i, one in enumerate(files):
        if i:
            print("\n" + "=" * 68)
        code = convert_one(args, one)
        rc = rc or code
        if args.json and code == 0:
            results.append(getattr(args, "_last", None))
    if args.json and len(files) > 1:
        print(json.dumps([r for r in results if r], ensure_ascii=False, indent=1))
    return rc


def convert_one(args, one):
    src = os.path.abspath(one)
    if not os.path.isfile(src):
        print("找不到文件: %s" % src)
        return 2

    tracks = probe(src)
    video = next((t for t in tracks if t.kind == "video"), None)
    if video is None:
        print("这个文件里没有视频轨")
        return 2
    vw, vh = int(round(video.width)), int(round(video.height))

    warns = []
    if video.codec not in ("avc1", "avc3"):
        warns.append("视频编码是 %s，实况图在 iPhone 上建议 H.264；其他编码可能能导入但不上墙。"
                     % video.codec)
    if video.seconds > 3.0:
        warns.append("视频 %.1f 秒，比标准实况图(约 3 秒)长；照片 App 能用，锁屏壁纸可能被拒。"
                     % video.seconds)
    if vw == 0 or vh == 0:
        vw, vh = 1920, 1080

    cid = (args.uuid or str(uuidlib.uuid4())).upper()
    out_dir = os.path.abspath(args.out) if args.out else os.path.dirname(src)
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir, exist_ok=True)
    name = args.name or safe_stem(src)
    jpg_path = os.path.join(out_dir, name + ".JPG")
    mov_path = os.path.join(out_dir, name + ".MOV")

    if not args.quiet:
        print(BANNER)
        print("-" * 68)
        print("输入   : %s  (%.1f MB, %dx%d, %.2fs, %s)" % (
            os.path.basename(src), os.path.getsize(src) / 1048576.0,
            vw, vh, video.seconds, video.codec))

    # --- 封面图 ---------------------------------------------------------
    if args.cover:
        if not args.quiet:
            print("封面   : 使用指定图片 %s" % os.path.basename(args.cover))
        jpeg, was_jpeg = load_cover(args.cover, args.quality)
    else:
        if not args.quiet:
            print("封面   : 从视频解码（Windows 内置解码器，原生分辨率）")
        try:
            raw, fw, fh = extract_still(src, vw, vh)
        except LivePhotoError as e:
            print("抽帧失败:", e)
            print("  改用 -c/--cover 指定一张图片也可以，例如：")
            print("    python livephoto.py \"%s\" -c 封面.jpg" % os.path.basename(src))
            return 3
        jpeg = encode_jpeg(raw, fw, fh, args.quality)
        vw, vh = fw, fh

    jpeg = inject_exif(jpeg, cid, keep_existing=args.keep_exif)
    with open(jpg_path, "wb") as f:
        f.write(jpeg)
    back = read_apple_makernote(jpeg)
    if back != cid:
        print("内部错误：写入的 ContentIdentifier 读回不一致")
        return 4

    # --- 视频 -----------------------------------------------------------
    if not args.quiet:
        print("视频   : 无损重封装中（不重新编码）...")
    try:
        st = remux(src, mov_path, cid, verify=not args.no_verify)
    except LivePhotoError as e:
        print("重封装失败:", e)
        return 5

    result = {
        "uuid": cid,
        "still": jpg_path, "still_bytes": os.path.getsize(jpg_path),
        "movie": mov_path, "movie_bytes": os.path.getsize(mov_path),
        "resolution": [vw, vh],
        "duration": round(video.seconds, 3),
        "lossless_verified": st.get("verified", None),
        "warnings": warns,
    }

    if args.json:
        args._last = result
        if len(args.video) == 1:
            print(json.dumps(result, ensure_ascii=False, indent=1))
        return 0

    print("-" * 68)
    print("配对 ID : %s" % cid)
    print("封面图  : %s  (%.1f MB)   Apple MakerNote 0x0011 已写入" % (
        jpg_path, result["still_bytes"] / 1048576.0))
    print("视频    : %s  (%.1f MB)   content.identifier 已写入" % (
        mov_path, result["movie_bytes"] / 1048576.0))
    if result["lossless_verified"]:
        print("无损校验: 通过 —— 逐样本比对，视频数据与源文件完全一致")
    elif result["lossless_verified"] is False:
        print("无损校验: ！不通过")
    for w in warns:
        print("提示    : %s" % w)
    print("-" * 68)
    print("把这两个文件一起导入 iPhone（照片 App / 隔空投送），")
    print("它们会自动合并成一张实况图。注意：两个文件必须同名，且要一起传。")
    return 0


def build_parser():
    p = argparse.ArgumentParser(
        prog="livephoto", description=BANNER,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""示例:
  python livephoto.py 旅行.mp4
  python livephoto.py 旅行.mp4 -o D:\\实况图 -n IMG_0001
  python livephoto.py 旅行.mp4 -c 封面.jpg          # 用指定图片当封面
  python livephoto.py 旅行.mp4 --uuid 1A2B...-...   # 指定配对 ID
  python livephoto.py info a.mp4 b.mov              # 只看信息
""")
    p.add_argument("video", nargs="*", help="输入视频，可一次给多个 (mp4/mov)")
    p.add_argument("-o", "--out", help="输出目录（默认与输入同目录）")
    p.add_argument("-n", "--name", help="输出文件名（不含扩展名）")
    p.add_argument("-c", "--cover", help="直接指定封面图片，跳过抽帧")
    p.add_argument("-q", "--quality", type=int, default=97, help="封面 JPEG 质量，默认 97")
    p.add_argument("--uuid", help="指定配对 ID（默认随机生成）")
    p.add_argument("--keep-exif", action="store_true", help="保留封面原有的 EXIF")
    p.add_argument("--no-verify", action="store_true", help="跳过无损校验")
    p.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    p.add_argument("--quiet", action="store_true")
    return p


def cmd_check_update(args):
    """检查是否有新版本。返回码：0 = 已是最新，1 = 有新版本，2 = 检查失败。"""
    try:
        import update as upd
    except ImportError:
        print("找不到 update.py，无法检查更新。")
        return 2
    url = getattr(args, "url", None) or None
    print("当前版本 : %s" % upd.CURRENT_VERSION)
    print("更新地址 : %s" % (url or upd.update_url()))
    r = upd.check(url)
    if r["error"]:
        print("检查失败 : %s" % r["error"])
        return 2
    print("最新版本 : %s" % r["version"])
    if r["has_update"]:
        print("")
        print("*** 发现新版本 ***")
        if r["notes"]:
            print("更新说明 : %s" % r["notes"])
        print("下载地址 : %s" % r["url"])
        if args.open:
            upd.open_url(r["url"])
        return 1
    print("已经是最新版本。")
    return 0


def build_update_parser():
    pu = argparse.ArgumentParser(prog="livephoto check-update",
                                 description="检查是否有新版本")
    pu.add_argument("--url", help="指定版本信息地址（默认用内置的）")
    pu.add_argument("--open", action="store_true", help="有新版本时自动打开下载页")
    return pu


def build_info_parser():
    pi = argparse.ArgumentParser(prog="livephoto info", description="查看视频轨道信息")
    pi.add_argument("files", nargs="+", help="要查看的视频文件")
    return pi


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    argv = list(sys.argv[1:] if argv is None else argv)

    if argv and argv[0] == "check-update":              # 子命令：检查更新
        args = build_update_parser().parse_args(argv[1:])
        return cmd_check_update(args)

    if argv and argv[0] == "info":                      # 子命令：只看信息
        args = build_info_parser().parse_args(argv[1:])
        try:
            return cmd_info(args)
        except LivePhotoError as e:
            print("错误:", e)
            return 1

    p = build_parser()
    args = p.parse_args(argv)
    if not args.video:
        p.print_help()
        print("\n提示: livephoto.py info <视频>      只看视频信息")
        print("      livephoto.py check-update     检查是否有新版本")
        return 1
    try:
        return cmd_convert(args)
    except LivePhotoError as e:
        print("错误:", e)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
