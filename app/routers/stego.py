# app/routers/stego.py
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import StreamingResponse
from app.algo import mp3_io, stego_lsb, crypto, pack, metrics
from app.algo import id3_tags
from app.utils.gacha import seed_from_key
import io, numpy as np
import time, uuid
import mimetypes

router = APIRouter()

STEGO_STORE: dict[str, dict] = {}
STEGO_TTL_SEC = 600  # 10 menit

def _put_stego(data: bytes, mime: str = "audio/mpeg", filename: str = "stego.mp3") -> str:
    token = uuid.uuid4().hex
    STEGO_STORE[token] = {"data": data, "mime": mime, "ts": time.time(), "filename": filename}
    # cleanup sederhana
    now = time.time()
    dead = [k for k, v in STEGO_STORE.items() if now - v["ts"] > STEGO_TTL_SEC]
    for k in dead:
        STEGO_STORE.pop(k, None)
    return token

@router.get("/download/{token}")
def download(token: str):
    item = STEGO_STORE.get(token)
    if not item:
        raise HTTPException(404, "Not found")
    headers = {
        "Content-Disposition": f'attachment; filename="{item["filename"]}"',
        "Content-Length": str(len(item["data"])),
    }
    return StreamingResponse(io.BytesIO(item["data"]), media_type=item["mime"], headers=headers)

@router.post("/check-capacity")
async def check_capacity(
    coverAudio: UploadFile = File(...),
    lsbBits: int = Form(...),
):
    """Hitung kapasitas maksimal (bytes) untuk lsbBits (1..8)."""
    if not (1 <= lsbBits <= 8):
        raise HTTPException(422, "lsbBits must be 1..8")

    mp3_bytes = await coverAudio.read()
    try:
        pcm, sr, ch, meta = mp3_io.decode_to_pcm(mp3_bytes)
    except Exception as e:
        raise HTTPException(400, f"Failed to decode MP3: {e}")
    frames = len(pcm)
    max_bytes = metrics.capacity_bytes(frames, ch, lsbBits)

    return {
        "maxCapacityBytes": int(max_bytes),
        "maxCapacityMB": round(max_bytes / (1024 * 1024), 2),
    }

@router.post("/embed")
async def embed(
    request: Request,
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
        crc32=pack.crc32_bytes(secret_bytes),
    )
    full = hdr + payload

    if len(full) > cap:
        raise HTTPException(413, f"Payload exceeds capacity ({len(full)} > {cap})")

    stego_pcm = stego_lsb.embed(pcm, full, key, nlsb, random_start)
    mp3_out = mp3_io.encode_from_pcm(stego_pcm, sr, ch)
    mp3_tagged = id3_tags.write_priv(mp3_out, full)

    psnr_db = metrics.psnr(pcm, stego_pcm)
    # Skor kualitas sederhana: 0 pada 20 dB, 100 pada 60 dB (dibatasi 0..100)
    quality = max(0.0, min(100.0, (psnr_db - 20.0) * (100.0 / 40.0)))

    token = _put_stego(mp3_tagged, mime="audio/mpeg", filename="stego.mp3")
    base = str(request.base_url).rstrip("/")
    stego_url = f"{base}/api/download/{token}"

    return {
        "success": True,
        "stegoAudioUrl": stego_url,
        # stegoAudioBlob tidak dikirim dari server; frontend bisa fetch URL ini dan membuat Blob sendiri.
        "stegoAudioBlob": None,
        "psnr": round(psnr_db, 2),
        "qualityScore": round(quality, 0),
        "fileSize": len(mp3_tagged),
        "message": "OK",
    }

@router.post("/extract")
async def extract(
    request: Request,                 # ADD: untuk membangun URL unduhan
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

    # Simpan ke store dan kembalikan JSON ExtractResponse
    mime = mimetypes.guess_type(hdr2.name)[0] or "application/octet-stream"
    token = _put_stego(data_bytes, mime=mime, filename=hdr2.name)
    base = str(request.base_url).rstrip("/")
    file_url = f"{base}/api/download/{token}"

    return {
        "success": True,
        "extractedFileUrl": file_url,
        "extractedFileBlob": None,
        "originalFileName": hdr2.name,
        "fileSizeBytes": len(data_bytes),
        "fileType": mime,
        "message": "OK",
    }