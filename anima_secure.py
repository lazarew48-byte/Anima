#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
anima_secure.py — маска секретов на входе + шифрование памяти.
PBKDF2-HMAC-SHA256 (200k) + потоковый шифр на SHA256-CTR + HMAC.
Честно: это не AES — заглушка до релиза (план — AES-GCM через cryptography).
"""

import base64, hashlib, hmac, json, os, re

MAGIC = "ANIMA_ENC_V1"
SECRET_PATTERNS = [
    ("telegram-токен", re.compile(r"\b\d{8,12}:[A-Za-z0-9_-]{30,}\b")),
    ("api-ключ", re.compile(
        r"(?i)(api[_-]?key|apikey|secret|token|password)\s*[:=]\s*['\"]?[A-Za-z0-9_.\-]{16,}")),
    ("hex-ключ", re.compile(r"\b[a-f0-9]{32,64}\b")),
]


def mask_secrets(text):
    for name, rx in SECRET_PATTERNS:
        text = rx.sub("[%s]" % name, text)
    return text


def scan_file(path):
    """Список (строка, тип) с найденными секретами."""
    found = []
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for i, line in enumerate(f, 1):
                for name, rx in SECRET_PATTERNS:
                    if rx.search(line):
                        found.append((i, name))
    except OSError:
        pass
    return found


def _keystream(key, iv, nbytes):
    out, counter = bytearray(), 0
    while len(out) < nbytes:
        out += hashlib.sha256(key + iv + counter.to_bytes(8, "big")).digest()
        counter += 1
    return bytes(out)


def _derive(password, salt):
    pwd = password.encode("utf-8")
    enc = hashlib.pbkdf2_hmac("sha256", pwd, salt, 200_000, dklen=32)
    mac = hashlib.pbkdf2_hmac("sha256", pwd, salt + b"mac", 200_000, dklen=32)
    return enc, mac


def encrypt_memory(obj, password):
    salt, iv = os.urandom(16), os.urandom(16)
    enc, mac = _derive(password, salt)
    plain = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    ct = bytes(a ^ b for a, b in zip(plain, _keystream(enc, iv, len(plain))))
    tag = hmac.new(mac, iv + ct, hashlib.sha256).digest()
    return {"format": MAGIC,
            "salt": base64.b64encode(salt).decode(),
            "iv": base64.b64encode(iv).decode(),
            "data": base64.b64encode(ct).decode(),
            "tag": base64.b64encode(tag).decode()}


def decrypt_memory(blob, password):
    if blob.get("format") != MAGIC:
        raise ValueError("это не зашифрованная память Анимы")
    salt = base64.b64decode(blob["salt"]); iv = base64.b64decode(blob["iv"])
    ct = base64.b64decode(blob["data"]); tag = base64.b64decode(blob["tag"])
    enc, mac = _derive(password, salt)
    if not hmac.compare_digest(hmac.new(mac, iv + ct, hashlib.sha256).digest(), tag):
        raise ValueError("неверный пароль или повреждённая память (HMAC)")
    plain = bytes(a ^ b for a, b in zip(ct, _keystream(enc, iv, len(ct))))
    return json.loads(plain.decode("utf-8"))


def save_encrypted(memory_path, obj, password):
    with open(memory_path, "w", encoding="utf-8") as f:
        json.dump(encrypt_memory(obj, password), f, ensure_ascii=False)


def is_encrypted(memory_path):
    try:
        with open(memory_path, encoding="utf-8") as f:
            return "ANIMA_ENC_V1" in f.read(64)
    except OSError:
        return False


if __name__ == "__main__":
    print("Модуль для лаунчера. Запуск: python anima_launcher.py")
