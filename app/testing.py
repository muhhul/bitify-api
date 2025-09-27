import os, requests, pathlib

BASE_URL = "http://localhost:8000"
DOWNLOADS = r"C:\Users\Axel Santadi\Downloads"

COVER_MP3 = r"C:\Users\Axel Santadi\Music\おちゃめ機能 -Full ver.- 重音テトSV【SynthesizerVカバー】.mp3"
MESSAGE = "Halo dari Bitify!"
SECRET_FILE = r"C:\Users\Axel Santadi\20250419_123507.jpg"

KEY = "abc123"
NLSB = "2"
ENCRYPT = "true"
RANDOM_START = "false"

def main():
    if not os.path.isfile(COVER_MP3):
        raise FileNotFoundError(f"Cover MP3 not found: {COVER_MP3}")
    os.makedirs(DOWNLOADS, exist_ok=True)

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
                data = {"key": KEY, "nlsb": NLSB, "encrypt": ENCRYPT, "random_start": RANDOM_START}
                r = requests.post(f"{BASE_URL}/api/embed", files=files, data=data, timeout=180)
        else:
            files = {
                "cover": (pathlib.Path(COVER_MP3).name, f_cover, "audio/mpeg"),
                "secret": ("message.txt", MESSAGE.encode("utf-8"), "text/plain"),
            }
            data = {"key": KEY, "nlsb": NLSB, "encrypt": ENCRYPT, "random_start": RANDOM_START}
            r = requests.post(f"{BASE_URL}/api/embed", files=files, data=data, timeout=180)

    if r.status_code != 200:
        print("Embed failed:", r.status_code, r.text); return

    psnr = r.headers.get("X-PSNR"); cap = r.headers.get("X-CAPACITY"); payload = r.headers.get("X-PAYLOAD")
    stego_path = os.path.join(DOWNLOADS, "stego_out.mp3")
    with open(stego_path, "wb") as out: out.write(r.content)
    print(f"Stego saved: {stego_path} | PSNR={psnr}dB, capacity={cap}, payload={payload} bytes")

    with open(stego_path, "rb") as f:
        files = {"stego": ("stego.mp3", f, "audio/mpeg")}
        data = {"key": KEY}
        r2 = requests.post(f"{BASE_URL}/api/extract", files=files, data=data, timeout=180)

    if r2.status_code != 200:
        print("Extract failed:", r2.status_code, r2.text); return

    out_name = r2.headers.get("X-FILENAME") or "extracted.bin"
    out_path = os.path.join(DOWNLOADS, out_name)
    with open(out_path, "wb") as out: out.write(r2.content)
    print(f"Extracted payload saved: {out_path}")

if __name__ == "__main__":
    main()