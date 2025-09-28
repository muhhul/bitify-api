import os, requests, pathlib

BASE_URL = "http://localhost:8000"
DOWNLOADS = r"C:\Users\Axel Santadi\Downloads"

COVER_MP3 = r"C:\Users\Axel Santadi\Music\おちゃめ機能 -Full ver.- 重音テトSV【SynthesizerVカバー】.mp3"
MESSAGE = "Halo dari Bitify!"
SECRET_FILE = r"C:\Users\Axel Santadi\Downloads\Sorasaki.Hina.full.3919571.jpg"  # set None untuk kirim MESSAGE

KEY = "abc123"
NLSB = "2"              # "1".."4"
ENCRYPT = "true"        # "true"/"false"
RANDOM_START = "false"  # "true"/"false"
TIMEOUT = 180

def _utf8_len(s: str) -> int:
    return len(s.encode("utf-8")[:255])

def _human(n: int) -> str:
    for u in ("B","KB","MB","GB"):
        if n < 1024: return f"{n:.0f}{u}"
        n /= 1024
    return f"{n:.1f}TB"

def check_capacity(cover_path: str):
    with open(cover_path, "rb") as f:
        files = {"mp3": (pathlib.Path(cover_path).name, f, "audio/mpeg")}
        r = requests.post(f"{BASE_URL}/api/check-capacity", files=files, timeout=TIMEOUT)
    if r.status_code != 200:
        raise RuntimeError(f"check-capacity failed: {r.status_code} {r.text}")
    return r.json()

def main():
    if not os.path.isfile(COVER_MP3):
        raise FileNotFoundError(f"Cover MP3 not found: {COVER_MP3}")
    os.makedirs(DOWNLOADS, exist_ok=True)

    # 1) Cek kapasitas
    info = check_capacity(COVER_MP3)
    caps = info["capacities"]  # dict: "1","2","3","4" -> bytes
    nlsb = str(int(NLSB))      # normalisasi
    if nlsb not in caps:
        raise ValueError(f"Invalid NLSB: {NLSB}")

    # Hitung kebutuhan total = header(19 + len(nama)) + payload
    if SECRET_FILE and os.path.isfile(SECRET_FILE):
        name = pathlib.Path(SECRET_FILE).name
        payload_size = os.path.getsize(SECRET_FILE)
    else:
        name = "message.txt"
        payload_size = len(MESSAGE.encode("utf-8"))
    header_overhead = 19 + _utf8_len(name)
    need = header_overhead + payload_size
    cap = int(caps[nlsb])

    print(f"Capacity (nlsb={nlsb}): {cap} bytes | Need: {need} bytes "
          f"(header {header_overhead}, payload {_human(payload_size)})")
    if need > cap:
        print(f"Payload exceeds capacity ({need} > {cap}). Pilih lagu lebih panjang atau naikkan NLSB.")
        return

    # 2) Embed
    with open(COVER_MP3, "rb") as f_cover:
        if SECRET_FILE and os.path.isfile(SECRET_FILE):
            sf_name = pathlib.Path(SECRET_FILE).name
            ext = sf_name.lower().split(".")[-1]
            mime = "image/jpeg" if ext in ("jpg", "jpeg") else "application/octet-stream"
            with open(SECRET_FILE, "rb") as f_secret:
                files = {
                    "cover": (pathlib.Path(COVER_MP3).name, f_cover, "audio/mpeg"),
                    "secret": (sf_name, f_secret, mime),
                }
                data = {"key": KEY, "nlsb": nlsb, "encrypt": ENCRYPT, "random_start": RANDOM_START}
                r = requests.post(f"{BASE_URL}/api/embed", files=files, data=data, timeout=TIMEOUT)
        else:
            files = {
                "cover": (pathlib.Path(COVER_MP3).name, f_cover, "audio/mpeg"),
                "secret": ("message.txt", MESSAGE.encode("utf-8"), "text/plain"),
            }
            data = {"key": KEY, "nlsb": nlsb, "encrypt": ENCRYPT, "random_start": RANDOM_START}
            r = requests.post(f"{BASE_URL}/api/embed", files=files, data=data, timeout=TIMEOUT)

    if r.status_code != 200:
        print("Embed failed:", r.status_code, r.text); return

    psnr = r.headers.get("X-PSNR"); cap_hdr = r.headers.get("X-CAPACITY"); payload_hdr = r.headers.get("X-PAYLOAD")
    stego_path = os.path.join(DOWNLOADS, "stego_out.mp3")
    with open(stego_path, "wb") as out: out.write(r.content)
    print(f"Stego saved: {stego_path} | PSNR={psnr} dB, capacity={cap_hdr}, payload={payload_hdr} bytes")

    # 3) Extract
    with open(stego_path, "rb") as f:
        files = {"stego": ("stego.mp3", f, "audio/mpeg")}
        data = {"key": KEY}
        r2 = requests.post(f"{BASE_URL}/api/extract", files=files, data=data, timeout=TIMEOUT)

    if r2.status_code != 200:
        print("Extract failed:", r2.status_code, r2.text); return

    out_name = r2.headers.get("X-FILENAME") or "extracted.bin"
    out_path = os.path.join(DOWNLOADS, out_name)
    with open(out_path, "wb") as out: out.write(r2.content)
    print(f"Extracted payload saved: {out_path}")

if __name__ == "__main__":
    main()