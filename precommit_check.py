#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
precommit_check.py — проверка перед пушем.
Ловит: секреты (токены, ключи, hex), пути с именем пользователя,
файлы памяти и .env в индексе git.
Запуск: python precommit_check.py
Код возврата: 0 — можно пушить, 1 — найдены проблемы.
"""

import re
import subprocess
import sys

PATTERNS = [
    ("telegram-токен", re.compile(r"\b\d{8,12}:[A-Za-z0-9_-]{30,}\b")),
    ("api-ключ", re.compile(r"(?i)(api[_-]?key|apikey|secret|token|password)\s*[:=]\s*['\"]?[A-Za-z0-9_.\-]{16,}")),
    ("hex-ключ", re.compile(r"\b[a-f0-9]{32,64}\b")),
    ("yandex-ключ", re.compile(r"\b[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{30,}\.[A-Za-z0-9_-]{10,}\b")),
    ("личный путь", re.compile(r"(?i)C:\\Users\\[A-Za-zА-Яа-я]+\\")),
]

FORBIDDEN_FILES = {"pet_memory.json", ".env", "pet_memory.json.bak"}


def git_files():
    try:
        out = subprocess.run(
            ["git", "ls-files", "-o", "--cached", "--exclude-standard"],
            capture_output=True, text=True, check=True)
        return [f for f in out.stdout.splitlines() if f.strip()]
    except Exception:
        return [f for f in __import__("os").listdir(".") if f.endswith((".py", ".md", ".json"))]


def main():
    problems = []
    files = git_files()
    for path in files:
        base = path.replace("\\", "/").split("/")[-1]
        if base in FORBIDDEN_FILES:
            problems.append("%s: личный/секретный файл не должен попасть в репозиторий" % path)
            continue
        try:
            text = open(path, encoding="utf-8", errors="replace").read()
        except (OSError, PermissionError):
            continue
        for name, rx in PATTERNS:
            for m in rx.finditer(text):
                line = text[:m.start()].count("\n") + 1
                problems.append("%s:%d — %s" % (path, line, name))
    if problems:
        print("НАЙДЕНЫ ПРОБЛЕМЫ — пушить нельзя:")
        for p in problems[:30]:
            print("  " + p)
        return 1
    print("Чисто. Можно пушить.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
