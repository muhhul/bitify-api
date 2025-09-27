# app/algo/id3_tags.py
import tempfile, os
from typing import Optional
from mutagen.id3 import ID3, ID3NoHeaderError, PRIV

OWNER = "bitify"  # identifier khusus kita

def write_priv(mp3_bytes: bytes, data: bytes, owner: str = OWNER) -> bytes:
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        f.write(mp3_bytes)
        path = f.name
    try:
        try:
            id3 = ID3(path)
        except ID3NoHeaderError:
            id3 = ID3()
        # Hapus PRIV lama milik owner yang sama
        for key in list(id3.keys()):
            fr = id3.getall(key)
            for frame in fr:
                if isinstance(frame, PRIV) and frame.owner == owner:
                    id3.delall(key)
        id3.add(PRIV(owner=owner, data=data))
        id3.save(path, v2_version=3)
        with open(path, "rb") as f2:
            return f2.read()
    finally:
        try: os.remove(path)
        except: pass

def read_priv(mp3_bytes: bytes, owner: str = OWNER) -> Optional[bytes]:
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        f.write(mp3_bytes)
        path = f.name
    try:
        try:
            id3 = ID3(path)
        except ID3NoHeaderError:
            return None
        for frame in id3.getall("PRIV"):
            if isinstance(frame, PRIV) and frame.owner == owner:
                return bytes(frame.data)
        return None
    finally:
        try: os.remove(path)
        except: pass