# app/algo/mp3_io.py
import subprocess, tempfile, os, wave, numpy as np
import io

def _ffmpeg_bytes_to_wav_bytes(mp3_bytes: bytes) -> bytes:
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f_in:
        f_in.write(mp3_bytes); in_path = f_in.name
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f_out:
        out_path = f_out.name
    try:
        cmd = ["ffmpeg", "-y", "-i", in_path, "-acodec", "pcm_s16le", out_path]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        with open(out_path, "rb") as f:
            return f.read()
    finally:
        for p in (in_path, out_path):
            try: os.remove(p)
            except: pass
    return pcm.copy(), sr, ch, meta

def decode_to_pcm(mp3_bytes: bytes):
    """return pcm:int16 ndarray shape (N, C), sr:int, ch:int"""
    wav_bytes = _ffmpeg_bytes_to_wav_bytes(mp3_bytes)
    import io
    with wave.open(io.BytesIO(wav_bytes), "rb") as w:
        ch = w.getnchannels()
        sr = w.getframerate()
        nframes = w.getnframes()
        frames = w.readframes(nframes)
    pcm = np.frombuffer(frames, dtype=np.int16)
    if ch > 1:
        pcm = pcm.reshape(-1, ch)
    else:
        pcm = pcm.reshape(-1, 1)
    meta = {"bit_depth": 16}
    return pcm.copy(), sr, ch, meta

def encode_from_pcm(pcm: "np.ndarray", sr: int, ch: int, bitrate: str = "192k") -> bytes:
    """pcm shape (N, C) int16 -> mp3 bytes"""
    if pcm.ndim == 1:
        pcm = pcm.reshape(-1, 1)
    assert pcm.shape[1] == ch
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f_wav:
        import wave
        with wave.open(f_wav, "wb") as w:
            w.setnchannels(ch)
            w.setsampwidth(2)
            w.setframerate(sr)
            w.writeframes(pcm.astype("<i2").tobytes())
        wav_path = f_wav.name
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f_mp3:
        mp3_path = f_mp3.name
    try:
        cmd = ["ffmpeg", "-y", "-i", wav_path, "-b:a", bitrate, mp3_path]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return open(mp3_path, "rb").read()
    finally:
        for p in (wav_path, mp3_path):
            try: os.remove(p)
            except: pass

def encode_wav_from_pcm(pcm: "np.ndarray", sr: int, ch: int) -> bytes:
    """pcm (N,C) int16 -> WAV bytes (lossless)"""
    if pcm.ndim == 1:
        pcm = pcm.reshape(-1, 1)
    assert pcm.shape[1] == ch
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(ch)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.astype("<i2").tobytes())
    return buf.getvalue()