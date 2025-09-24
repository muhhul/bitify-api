# app/utils/gacha.py
import hashlib, random

def seed_from_key(key: str) -> int:
    h = hashlib.blake2b(key.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(h, "little")

def rng_from_key(key: str) -> random.Random:
    return random.Random(seed_from_key(key))
