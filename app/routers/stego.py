# app/routers/stego.py
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import StreamingResponse
from app.algo import mp3_io, stego_lsb, crypto, pack, metrics
from app.utils.gacha import seed_from_key
import io, numpy as np

router = APIRouter()

@router.post("/embed")
async def embed(
    cover: UploadFile = File(...),
    secret: UploadFile = File(...),
    key: str = Form(...),
    nlsb: int = Form(...),
    encrypt: bool = Form(False),
    random_start: bool = Form(False),
):
    if not (1 <= nlsb <= 4):
        raise HTTPException(422, "nlsb must be 1..4")
    key = key[:25]
    cover_bytes = await cover.read()
    secret_bytes = await secret.read()

    pcm, sr, ch, meta = mp3_io.decode_to_pcm(cover_bytes)
    cap = metrics.capacity_bytes(len(pcm), ch, nlsb)

    payload = crypto.vig256(secret_bytes, key) if encrypt else secret_bytes
    hdr = pack.build(encrypt, random_start, nlsb, size=len(secret_bytes),
                     name=secret.filename or "secret.bin", crc32=pack.crc32_bytes(payload))
    full = hdr + payload

    if len(full) > cap:
        raise HTTPException(413, f"Payload exceeds capacity ({len(full)} > {cap})")

    stego_pcm = stego_lsb.embed(pcm, full, key, nlsb, random_start)
    mp3_out = mp3_io.encode_from_pcm(stego_pcm, sr, ch)

    psnr_db = metrics.psnr(pcm, stego_pcm)
    headers = {
        "X-PSNR": f"{psnr_db:.2f}",
        "X-CAPACITY": str(cap),
        "X-PAYLOAD": str(len(full)),
        "X-FLAGS": f"enc={int(encrypt)},rand={int(random_start)},nlsb={nlsb}",
    }
    return StreamingResponse(io.BytesIO(mp3_out), media_type="audio/mpeg", headers=headers)

@router.post("/extract")
async def extract(
    stego: UploadFile = File(...),
    key: str = Form(...),
):
    key = key[:25]
    stego_bytes = await stego.read()
    pcm, sr, ch, meta = mp3_io.decode_to_pcm(stego_bytes)

    # 1) Baca header dulu dari awal stream (asumsi start=0)
    #   kita tidak tahu panjang header; ambil 256 sampel awal cukup untuk header kecil
    #   length header maksimum ~ 4+1+1+8+1+255+4 = 274 bytes → butuh 274*8/nlsb sampel.
    #   Ambil konservatif 2048 sampel (nlsb min=1) untuk memastikan.
    window = 2048
    for test_nlsb in (1,2,3,4):
        raw = stego_lsb.extract(pcm[:window], nlsb=test_nlsb, key=key, random_start=False, total_bits=window*test_nlsb)
        # coba parse header pada berbagai offset byte
        try:
            hdr, consumed = pack.parse(raw)
            # valid: kita temukan nlsb sebenarnya dari header
            real_nlsb = hdr.nlsb
            break
        except Exception:
            continue
    else:
        raise HTTPException(400, "Failed to parse header")

    # 2) Dengan info header, jika random_start=True → hitung start sama seperti embed
    start_hint = 0
    if hdr.random_start:
        import random
        r = random.Random(seed_from_key(key))
        # hitung jumlah sampel yang dipakai semua payload (header+payload)
        total_bits = (len(raw) * 8)  # raw di atas tidak dipakai lagi; kita hitung ulang yang benar
        total_payload_bytes = (hdr.size + (len(pack.build(hdr.encrypt, hdr.random_start, hdr.nlsb, hdr.size, hdr.name, hdr.crc32))))  # kira-kira
        total_samples_needed = (total_payload_bytes * 8 + real_nlsb - 1) // real_nlsb
        total_samples = (pcm.size)  # flattened
        start_hint = r.randrange(0, max(1, total_samples - total_samples_needed))

    # 3) Ekstrak seluruh bit sesuai panjang (header+payload)
    header_bytes = pack.build(hdr.encrypt, hdr.random_start, real_nlsb, hdr.size, hdr.name, hdr.crc32)
    total_bytes = len(header_bytes) + (hdr.size if hdr.encrypt else hdr.size)
    total_bits = total_bytes * 8
    full = stego_lsb.extract(pcm, nlsb=real_nlsb, key=key, random_start=hdr.random_start,
                             total_bits=total_bits, start_hint=start_hint)

    hdr2, consumed = pack.parse(full)
    payload_enc = full[consumed:consumed+hdr2.size]
    if pack.crc32_bytes(payload_enc) != hdr2.crc32:
        raise HTTPException(400, "CRC mismatch (wrong key or corrupted)")

    payload = crypto.vig256(payload_enc, key, decrypt=True) if hdr2.encrypt else payload_enc
    headers = {"X-FILENAME": hdr2.name, "X-SIZE": str(hdr2.size)}
    return StreamingResponse(io.BytesIO(payload), media_type="application/octet-stream", headers=headers)
