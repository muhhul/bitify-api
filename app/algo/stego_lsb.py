# app/algo/stego_lsb.py
from typing import Optional
import numpy as np
from app.utils.gacha import rng_from_key
from app.algo.metrics import capacity_bytes
from typing import Tuple

def _pcm_to_stream(pcm: np.ndarray) -> np.ndarray:
    """Flatten jadi 1D array of samples (int16) interleaved."""
    if pcm.ndim == 2:
        return pcm.reshape(-1)
    return pcm

def _stream_to_pcm(stream: np.ndarray, ch: int) -> np.ndarray:
    if ch == 1:
        return stream.reshape(-1, 1)
    return stream.reshape(-1, ch)

def embed(pcm: np.ndarray, payload: bytes, key: str, nlsb: int, random_start: bool) -> np.ndarray:
    stream = _pcm_to_stream(pcm).astype(np.int32).copy()
    total_samples = stream.size
    cap = (total_samples * nlsb) // 8
    if len(payload) > cap:
        raise ValueError("payload exceeds capacity")

    # bitstream dari payload
    bits = np.unpackbits(np.frombuffer(payload, dtype=np.uint8))

    # posisi awal
    start = 0
    if random_start:
        r = rng_from_key(key)
        start = r.randrange(0, max(1, total_samples - (len(bits)+nlsb-1)//nlsb))

    # tulis per nlsb
    idx = start
    mask_keep = ~((1<<nlsb)-1)
    for i in range(0, len(bits), nlsb):
        chunk = bits[i:i+nlsb]
        if chunk.size < nlsb:
            pad = np.zeros(nlsb - chunk.size, dtype=np.uint8)
            chunk = np.concatenate([chunk, pad], axis=0)
        value = 0
        for b in chunk:
            value = (value<<1) | int(b)
        stream[idx] = (stream[idx] & mask_keep) | value
        idx += 1

    stego = np.clip(stream, -32768, 32767).astype(np.int16)
    return _stream_to_pcm(stego, pcm.shape[1])

def extract(
    pcm: np.ndarray,
    nlsb: int,
    key: str,
    random_start: bool,
    total_bits: int,
    start_hint: Optional[int] = None,   # <- ini
) -> bytes:
    stream = _pcm_to_stream(pcm).astype(np.int32)
    total_samples = stream.size

    if random_start and start_hint is None:
        # saat ekstraksi kita akan membaca header dulu (panjang diketahui sedikit)
        raise ValueError("start_hint required for random_start in generic extract")

    idx = start_hint or 0
    chunks = []
    for _ in range(0, total_bits, nlsb):
        value = stream[idx] & ((1<<nlsb)-1)
        # ubah ke nlsb bits
        chunk = [(value >> (nlsb-1-i)) & 1 for i in range(nlsb)]
        chunks.extend(chunk)
        idx += 1
    # potong ke total_bits persis
    bits = np.array(chunks[:total_bits], dtype=np.uint8)
    bys = np.packbits(bits).tobytes()
    return bys
