import os, requests, pathlib, mimetypes
from typing import Optional

BASE_URL = "http://localhost:8000"
DOWNLOADS = r"C:\Users\Axel Santadi\Downloads"

COVER_MP3 = r"C:\Users\Axel Santadi\Music\おちゃめ機能 -Full ver.- 重音テトSV【SynthesizerVカバー】.mp3"
MESSAGE = "Halo dari Bitify!"
SECRET_FILE = r"C:\Users\Axel Santadi\Downloads\Hoshimachi_Suisei.jpeg"

# Sesuaikan dengan server: di stego.py, STRICT_AUDIO_ONLY default "1"
STRICT_AUDIO_ONLY = True

KEY = "abc123"
NLSB = "8"               # "1".."8"
ENCRYPT = True           # bool -> dikirim sebagai "true"/"false"
RANDOM_START = False     # harus False karena extractor mencari header di awal
TIMEOUT = 600
OUTPUT_FORMAT = "mp3"    # "wav" (LSB lossless) atau "mp3" (ID3 PRIV)

def _utf8_len(s: str) -> int:
    return len(s.encode("utf-8")[:255])

def _human(n: int) -> str:
    for u in ("B","KB","MB","GB"):
        if n < 1024: return f"{n:.0f}{u}"
        n /= 1024
    return f"{n:.1f}TB"

def _pick_file_dialog() -> Optional[str]:
    # Windows file picker; aman jika gagal (headless), akan return None
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        path = filedialog.askopenfilename(
            title="Pilih file rahasia (apa saja)",
            initialdir=str(pathlib.Path.home())
        )
        root.update()
        root.destroy()
        return path if path else None
    except Exception:
        return None

def check_capacity(cover_path: str, lsb_bits: int):
    with open(cover_path, "rb") as f:
        files = {"coverAudio": (pathlib.Path(cover_path).name, f, "audio/mpeg")}
        data = {"lsbBits": str(int(lsb_bits))}
        r = requests.post(f"{BASE_URL}/api/check-capacity", files=files, data=data, timeout=TIMEOUT)
    if r.status_code != 200:
        raise RuntimeError(f"check-capacity failed: {r.status_code} {r.text}")
    return r.json()  # { maxCapacityBytes, maxCapacityMB }

def health_check() -> bool:
    try:
        r = requests.get(f"{BASE_URL}/api/health", timeout=10)
        return r.status_code == 200
    except Exception:
        return False

def main():
    if not health_check():
        print("Server not ready at /api/health"); return

    if not os.path.isfile(COVER_MP3):
        raise FileNotFoundError(f"Cover MP3 not found: {COVER_MP3}")
    os.makedirs(DOWNLOADS, exist_ok=True)

    nlsb = str(int(NLSB))  # normalisasi
    print(f"STRICT_AUDIO_ONLY={STRICT_AUDIO_ONLY} | RANDOM_START={RANDOM_START} | OUT={OUTPUT_FORMAT}")

    # Tentukan sumber secret: variabel, picker (untuk WAV), atau MESSAGE
    selected_secret = SECRET_FILE if (SECRET_FILE and os.path.isfile(SECRET_FILE)) else None
    is_wav = (OUTPUT_FORMAT or "mp3").lower() == "wav"
    if selected_secret is None:
        picked = _pick_file_dialog()
        if picked and os.path.isfile(picked):
            selected_secret = picked

    # 1) Cek kapasitas untuk NLSB terpilih
    info = check_capacity(COVER_MP3, int(nlsb))
    cap = int(info["maxCapacityBytes"])

    # Hitung kebutuhan total = header(19 + len(nama)) + payload (lihat app.algo.pack.build)
    if selected_secret and os.path.isfile(selected_secret):
        name = pathlib.Path(selected_secret).name
        payload_size = os.path.getsize(selected_secret)
    else:
        name = "message.txt"
        payload_size = len(MESSAGE.encode("utf-8"))
    header_overhead = 19 + _utf8_len(name)
    need = header_overhead + payload_size

    print(f"Capacity (nlsb={nlsb}): {cap} bytes | Need: {need} bytes (header {header_overhead}, payload {_human(payload_size)})")
    if need > cap:
        print(f"Payload exceeds capacity ({need} > {cap}). Pilih lagu lebih panjang atau naikkan NLSB."); return

    # 2) Embed → terima JSON EmbedResponse, lalu unduh stegoAudioUrl
    with open(COVER_MP3, "rb") as f_cover:
        if selected_secret and os.path.isfile(selected_secret):
            sf_name = pathlib.Path(selected_secret).name
            guessed_mime, _ = mimetypes.guess_type(sf_name)
            mime = guessed_mime or "application/octet-stream"
            with open(selected_secret, "rb") as f_secret:
                files = {
                    "cover": (pathlib.Path(COVER_MP3).name, f_cover, "audio/mpeg"),
                    "secret": (sf_name, f_secret, mime),
                }
                data = {
                    "key": KEY,
                    "nlsb": nlsb,
                    "encrypt": str(ENCRYPT).lower(),
                    "random_start": str(RANDOM_START).lower(),
                    "out_format": OUTPUT_FORMAT,
                }
                r = requests.post(f"{BASE_URL}/api/embed", files=files, data=data, timeout=TIMEOUT)
        else:
            files = {
                "cover": (pathlib.Path(COVER_MP3).name, f_cover, "audio/mpeg"),
                "secret": ("message.txt", MESSAGE.encode("utf-8"), "text/plain"),
            }
            data = {
                "key": KEY,
                "nlsb": nlsb,
                "encrypt": str(ENCRYPT).lower(),
                "random_start": str(RANDOM_START).lower(),
                "out_format": OUTPUT_FORMAT,       # kirim pilihan format
            }
            r = requests.post(f"{BASE_URL}/api/embed", files=files, data=data, timeout=TIMEOUT)

    if r.status_code != 200:
        print("Embed failed:", r.status_code, r.text); return

    eresp = r.json()
    if not eresp.get("success"):
        print("Embed not successful:", eresp); return

    stego_url = eresp["stegoAudioUrl"]
    psnr = eresp.get("psnr"); q = eresp.get("qualityScore"); fsize = eresp.get("fileSize")
    print(f"Embed OK | PSNR={psnr} dB, quality={q}, size={_human(fsize)} | url={stego_url}")

    # Simpan sesuai format
    stego_fname = "stego_out.wav" if is_wav else "stego_out.mp3"
    stego_mime = "audio/wav" if is_wav else "audio/mpeg"
    stego_path = os.path.join(DOWNLOADS, stego_fname)

    r_dl = requests.get(stego_url, timeout=TIMEOUT)
    if r_dl.status_code != 200:
        print("Download stego failed:", r_dl.status_code, r_dl.text); return
    with open(stego_path, "wb") as out:
        out.write(r_dl.content)
    print(f"Stego saved: {stego_path}")

    # 3) Extract → terima JSON ExtractResponse, lalu unduh extractedFileUrl
    with open(stego_path, "rb") as f:
        files = {"stego": (stego_fname, f, stego_mime)}
        data = {"key": KEY}
        r2 = requests.post(f"{BASE_URL}/api/extract", files=files, data=data, timeout=TIMEOUT)

    if r2.status_code != 200:
        print("Extract failed:", r2.status_code, r2.text); return

    xresp = r2.json()
    if not xresp.get("success"):
        print("Extract not successful:", xresp); return

    extracted_url = xresp["extractedFileUrl"]
    orig_name = xresp.get("originalFileName") or "extracted.bin"
    out_path = os.path.join(DOWNLOADS, orig_name)

    r_xd = requests.get(extracted_url, timeout=TIMEOUT)
    if r_xd.status_code != 200:
        print("Download extracted failed:", r_xd.status_code, r_xd.text); return
    with open(out_path, "wb") as out:
        out.write(r_xd.content)
    print(f"Extracted payload saved: {out_path} ({_human(len(r_xd.content))}, type={xresp.get('fileType')})")

if __name__ == "__main__":
    main()