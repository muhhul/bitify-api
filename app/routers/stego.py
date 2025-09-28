# app/routers/stego.py
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import StreamingResponse
from app.algo import mp3_io, stego_lsb, crypto, pack, metrics
from app.algo import id3_tags
from app.utils.gacha import seed_from_key
import io, numpy as np
import time, uuid
import mimetypes
import os

router = APIRouter()
STRICT_AUDIO_ONLY = os.getenv("STRICT_AUDIO_ONLY", "1") == "1"

STEGO_STORE: dict[str, dict] = {}
STEGO_TTL_SEC = 300

def _put_stego(data: bytes, mime: str = "audio/mpeg", filename: str = "stego.mp3") -> str:
    token = uuid.uuid4().hex
    STEGO_STORE[token] = {"data": data, "mime": mime, "ts": time.time(), "filename": filename}
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
    out_format: str = Form("mp3"),
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
    full_payload = hdr + payload

    if len(full_payload) > cap:
        raise HTTPException(413, f"Payload exceeds capacity ({len(full_payload)} > {cap})")

    stego_pcm = stego_lsb.embed(pcm, full_payload, key, nlsb, random_start)
    mp3_out = mp3_io.encode_from_pcm(stego_pcm, sr, ch, bitrate="320k")

    fmt = (out_format or "mp3").lower()
    if fmt == "wav":
        out_bytes = mp3_io.encode_wav_from_pcm(stego_pcm, sr, ch)
        out_mime = "audio/wav"
        out_name = "stego.wav"
    elif fmt == "mp3":
        out_bytes = id3_tags.write_priv(mp3_out, full_payload)
        out_mime = "audio/mpeg"
        out_name = "stego.mp3"
    else:
        raise HTTPException(422, 'out_format must be "wav" or "mp3"')

    psnr_db = metrics.psnr(pcm, stego_pcm)
    quality = max(0.0, min(100.0, (psnr_db - 20.0) * (100.0 / 40.0)))

    token = _put_stego(out_bytes, mime=out_mime, filename=out_name)
    base = str(request.base_url).rstrip("/")
    stego_url = f"{base}/api/download/{token}"

    return {
        "success": True,
        "stegoAudioUrl": stego_url,
        "stegoAudioBlob": None,
        "psnr": round(psnr_db, 2),
        "qualityScore": round(quality, 0),
        "fileSize": len(out_bytes),
        "message": "OK",
    }

@router.post("/extract")
async def extract(
    request: Request,
    stego: UploadFile = File(...),
    key: str = Form(...),
):
    key = key[:25]
    stego_bytes = await stego.read()

    raw_payload = None
    raw_payload = id3_tags.read_priv(stego_bytes)
    
    if raw_payload is None:
        try:
            pcm, sr, ch, meta = mp3_io.decode_to_pcm(stego_bytes)
            HEADER_MAX_BYTES = 320
            start_idx = None
            hdr = None
            consumed = None
            real_nlsb = None

            for nlsb in range(1, 9):
                samples_for_hdr = (HEADER_MAX_BYTES * 8 + nlsb - 1) // nlsb
                if len(pcm) < samples_for_hdr: continue

                raw0 = stego_lsb.extract(
                    pcm[:samples_for_hdr], nlsb=nlsb, key=key,
                    random_start=False, total_bits=samples_for_hdr * nlsb
                )
                try:
                    h0, c0 = pack.parse(raw0)
                    if h0.nlsb == nlsb:
                        hdr, consumed, start_idx, real_nlsb = h0, c0, 0, nlsb
                        break
                except Exception:
                    pass

            if hdr is None:
                raise HTTPException(400, "Failed to find a valid header. The audio may be too distorted or no data exists.")

            total_bytes = consumed + hdr.size
            total_bits = total_bytes * 8
            
            raw_payload = stego_lsb.extract(
                pcm[start_idx:], nlsb=real_nlsb, key=key,
                random_start=False, total_bits=total_bits
            )

        except HTTPException as e:
            raise e
        except Exception as e:
            raise HTTPException(400, f"Failed to extract from LSBs. Data might be corrupted. Details: {e}")

    if raw_payload is None:
        raise HTTPException(400, "Could not find any hidden data.")

    try:
        hdr2, consumed2 = pack.parse(raw_payload)
        payload_only = raw_payload[consumed2 : consumed2 + hdr2.size]

        data_bytes = crypto.vig256(payload_only, key, decrypt=True) if hdr2.encrypt else payload_only
        if pack.crc32_bytes(data_bytes) != hdr2.crc32:
            raise HTTPException(400, "Bad key or corrupted data. CRC32 mismatch.")
    except Exception as e:
        raise HTTPException(400, f"Failed to parse payload header. Details: {e}")

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