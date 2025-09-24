# app/algo/metrics.py
import numpy as np, math

def capacity_bytes(num_samples: int, channels: int, nlsb: int) -> int:
    return (num_samples * channels * nlsb) // 8

def psnr(orig: np.ndarray, stego: np.ndarray) -> float:
    o = orig.astype(np.int64)
    s = stego.astype(np.int64)
    mse = ((o - s) ** 2).mean()
    if mse == 0: return 100.0
    max_i = 32767.0
    return 20 * math.log10(max_i) - 10 * math.log10(mse)
