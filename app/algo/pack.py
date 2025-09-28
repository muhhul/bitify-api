# app/algo/pack.py
import struct, zlib
from dataclasses import dataclass

MAGIC = b"BTFY"
VER = 2

@dataclass
class Header:
    encrypt: bool
    random_start: bool
    nlsb: int
    size: int
    name: str
    crc32: int

def build(encrypt: bool, random_start: bool, nlsb: int, size: int, name: str, crc32: int) -> bytes:
    assert 1 <= nlsb <= 8
    flags = (1 if encrypt else 0) \
          | ((1 if random_start else 0) << 1) \
          | (((nlsb - 1) & 0b111) << 2)
    name_b = name.encode("utf-8")[:255]
    return MAGIC + struct.pack("<B", VER) + struct.pack("<B", flags) + struct.pack("<Q", size) + \
            struct.pack("<B", len(name_b)) + name_b + struct.pack("<I", crc32)

def parse(bs: bytes) -> tuple[Header, int]:
    assert bs[:4] == MAGIC, "bad magic"
    ver = bs[4]
    flags = bs[5]
    if ver == 1:
        nlsb = ((flags >> 2) & 0b11) + 1
    elif ver == 2:
        nlsb = ((flags >> 2) & 0b111) + 1
    else:
        raise ValueError("unsupported version")
    encrypt = bool(flags & 1)
    random_start = bool((flags >> 1) & 1)
    size = struct.unpack_from("<Q", bs, 6)[0]
    name_len = bs[14]
    start = 15
    name = bs[start:start+name_len].decode("utf-8", errors="ignore")
    crc32 = struct.unpack_from("<I", bs, start+name_len)[0]
    consumed = start + name_len + 4
    return Header(encrypt, random_start, nlsb, size, name, crc32), consumed

def crc32_bytes(b: bytes) -> int:
    return zlib.crc32(b) & 0xFFFFFFFF
