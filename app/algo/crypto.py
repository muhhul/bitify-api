# app/algo/crypto.py
def _kstream(key: str):
    kb = key.encode("utf-8")
    if not kb: raise ValueError("empty key")
    while True:
        for b in kb:
            yield b

def vig256(data: bytes, key: str, decrypt: bool=False) -> bytes:
    out = bytearray(len(data))
    ks = _kstream(key)
    if decrypt:
        for i, x in enumerate(data):
            out[i] = (x - next(ks)) % 256
    else:
        for i, x in enumerate(data):
            out[i] = (x + next(ks)) % 256
    return bytes(out)
