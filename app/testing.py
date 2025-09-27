import os, requests, pathlib

BASE_URL = "http://localhost:8000"
DOWNLOADS = r"C:\Users\Axel Santadi\Downloads"

# TODO: ganti path MP3 cover kamu di sini
COVER_MP3 = r"C:\Users\Axel Santadi\Music\おちゃめ機能 -Full ver.- 重音テトSV【SynthesizerVカバー】.mp3"

# TODO: ganti pesan yang ingin di-embed
MESSAGE = "Halo dari Bitify!"

KEY = "abc123"
NLSB = "2"             # 1..4
ENCRYPT = "true"       # "true"/"false"
RANDOM_START = "true"  # "true"/"false"

def main():
    if not os.path.isfile(COVER_MP3):
        raise FileNotFoundError(f"Cover MP3 not found: {COVER_MP3}")
    os.makedirs(DOWNLOADS, exist_ok=True)

    # 1) Embed
    with open(COVER_MP3, "rb") as f:
        files = {
            "cover": (pathlib.Path(COVER_MP3).name, f, "audio/mpeg"),
            "secret": ("message.txt", MESSAGE.encode("utf-8"), "text/plain"),
        }
        data = {"key": KEY, "nlsb": NLSB, "encrypt": ENCRYPT, "random_start": RANDOM_START}
        r = requests.post(f"{BASE_URL}/api/embed", files=files, data=data, timeout=180)

    if r.status_code != 200:
        print("Embed failed:", r.status_code, r.text)
        return

    psnr = r.headers.get("X-PSNR")
    cap = r.headers.get("X-CAPACITY")
    payload = r.headers.get("X-PAYLOAD")

    stego_path = os.path.join(DOWNLOADS, "stego_out.mp3")
    with open(stego_path, "wb") as out:
        out.write(r.content)
    print(f"Stego saved: {stego_path} | PSNR={psnr}dB, capacity={cap}, payload={payload} bytes")

    # 2) Extract (opsional: verifikasi roundtrip)
    with open(stego_path, "rb") as f:
        files = {"stego": ("stego.mp3", f, "audio/mpeg")}
        data = {"key": KEY}
        r2 = requests.post(f"{BASE_URL}/api/extract", files=files, data=data, timeout=180)

    if r2.status_code != 200:
        print("Extract failed:", r2.status_code, r2.text)
        return

    out_name = r2.headers.get("X-FILENAME") or "extracted.bin"
    out_path = os.path.join(DOWNLOADS, out_name)
    with open(out_path, "wb") as out:
        out.write(r2.content)
    print(f"Extracted payload saved: {out_path}")

    try:
        ok = r2.content.decode("utf-8") == MESSAGE
        print("Roundtrip OK:", ok)
    except UnicodeDecodeError:
        print("Roundtrip check skipped (binary payload)")

if __name__ == "__main__":
    main()