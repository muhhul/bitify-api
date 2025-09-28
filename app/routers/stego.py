# app/routers/stego.py
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import StreamingResponse
from app.algo import mp3_io, stego_lsb, crypto, pack, metrics
from app.algo import id3_tags
from app.utils.gacha import seed_from_key
import io, numpy as np

router = APIRouter()

@router.post("/check-capacity")
async def check_capacity(mp3: UploadFile = File(...)):
    """Hitung kapasitas maksimal (bytes) untuk nlsb=1..4."""
    mp3_bytes = await mp3.read()
    try:
        pcm, sr, ch, meta = mp3_io.decode_to_pcm(mp3_bytes)
    except Exception as e:
        raise HTTPException(400, f"Failed to decode MP3: {e}")
    frames = len(pcm)
    capacities = {str(n): metrics.capacity_bytes(frames, ch, n) for n in range(1, 9)}
    # Header Bitify minimal 19 byte + panjang nama file (0..255)
    return {
        "sample_rate": sr,
        "channels": ch,
        "frames": frames,
        "duration_sec": frames / sr if sr else None,
        "capacities": capacities,
        "header_overhead_min_bytes": 19,
    }

@router.post("/embed")
async def embed(
    cover: UploadFile = File(...),
    secret: UploadFile = File(...),
    key: str = Form(...),
    nlsb: int = Form(...),
    encrypt: bool = Form(False),
    random_start: bool = Form(False),
):
    if not (1 <= nlsb <= 8):
        raise HTTPException(422, "nlsb must be 1..8")
    key = key[:25]
    cover_bytes = await cover.read()
    secret_bytes = await secret.read()

    pcm, sr, ch, meta = mp3_io.decode_to_pcm(cover_bytes)
    cap = metrics.capacity_bytes(len(pcm), ch, nlsb)

    payload = crypto.vig256(secret_bytes, key) if encrypt else secret_bytes
    hdr = pack.build(
        encrypt, random_start, nlsb,
        size=len(secret_bytes),
        name=secret.filename or "secret.bin",
        crc32=pack.crc32_bytes(secret_bytes),  # CRC plaintext
    )
    full = hdr + payload

    if len(full) > cap:
        raise HTTPException(413, f"Payload exceeds capacity ({len(full)} > {cap})")

    stego_pcm = stego_lsb.embed(pcm, full, key, nlsb, random_start)
    # Kodekan ke MP3 (lossy, LSB bisa hilang), lalu sematkan full ke ID3 PRIV
    mp3_out = mp3_io.encode_from_pcm(stego_pcm, sr, ch)
    mp3_tagged = id3_tags.write_priv(mp3_out, full)

    psnr_db = metrics.psnr(pcm, stego_pcm)
    headers = {
        "X-PSNR": f"{psnr_db:.2f}",
        "X-CAPACITY": str(cap),
        "X-PAYLOAD": str(len(full)),
        "X-FLAGS": f"enc={int(encrypt)},rand={int(random_start)},nlsb={nlsb}",
    }
    return StreamingResponse(io.BytesIO(mp3_tagged), media_type="audio/mpeg", headers=headers)

@router.post("/extract")
async def extract(
    stego: UploadFile = File(...),
    key: str = Form(...),
):
    key = key[:25]
    stego_bytes = await stego.read()

    # 1) Coba ambil dari ID3 PRIV (cepat dan stabil)
    raw = id3_tags.read_priv(stego_bytes)
    if raw is None:
        # 2) Fallback: ekstrak dari LSB PCM (bisa gagal karena lossy)
        pcm, sr, ch, meta = mp3_io.decode_to_pcm(stego_bytes)
        HEADER_MAX = 320
        start_idx = None
        real_nlsb = None
        hdr = None
        consumed = None

        for nlsb in range(1, 9):
            samples_for_hdr = (HEADER_MAX * 8 + nlsb - 1) // nlsb
            raw0 = stego_lsb.extract(
                pcm[:samples_for_hdr],
                nlsb=nlsb,
                key=key,
                random_start=False,
                total_bits=samples_for_hdr * nlsb,
            )
            try:
                h0, c0 = pack.parse(raw0)
                if h0.nlsb == nlsb:
                    hdr, consumed = h0, c0
                    start_idx = 0
                    real_nlsb = nlsb
                    break
            except Exception:
                pass

        if start_idx is None:
            # sliding search (lambat)
            for nlsb in range(1, 9):
                samples_for_hdr = (HEADER_MAX * 8 + nlsb - 1) // nlsb
                step = max(1, samples_for_hdr // 8)
                limit = max(0, len(pcm) - samples_for_hdr)
                i = 0
                while i <= limit:
                    raw_try = stego_lsb.extract(
                        pcm[i : i + samples_for_hdr],
                        nlsb=nlsb,
                        key=key,
                        random_start=False,
                        total_bits=samples_for_hdr * nlsb,
                    )
                    try:
                        h, c = pack.parse(raw_try)
                        if h.nlsb != nlsb:
                            i += step; continue
                        hdr, consumed = h, c
                        start_idx = i
                        real_nlsb = nlsb
                        break
                    except Exception:
                        i += step; continue
                if start_idx is not None:
                    break

        if start_idx is None:
            raise HTTPException(400, "Failed to parse header")

        total_bytes = consumed + hdr.size
        total_bits = total_bytes * 8
        raw = stego_lsb.extract(
            pcm[start_idx:],
            nlsb=real_nlsb,
            key=key,
            random_start=False,
            total_bits=total_bits,
        )

    # Parse header+payload dari PRIV atau LSB
    hdr2, consumed2 = pack.parse(raw)
    payload = raw[consumed2 : consumed2 + hdr2.size]

    # Dekripsi lalu validasi CRC plaintext
    data_bytes = crypto.vig256(payload, key, decrypt=True) if hdr2.encrypt else payload
    if pack.crc32_bytes(data_bytes) != hdr2.crc32:
        raise HTTPException(400, "Bad key or corrupted")

    headers = {"X-FILENAME": hdr2.name}
    return StreamingResponse(io.BytesIO(data_bytes), media_type="application/octet-stream", headers=headers)