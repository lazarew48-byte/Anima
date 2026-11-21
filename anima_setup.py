#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
anima_setup.py — установщик и проверка окружения.
1 — проверка окружения; 2 — чистка секретов; 3 — демо-память; 0 — выход.
"""

import os, shutil, sys

HERE = os.path.dirname(os.path.abspath(__file__))
REQUIRED = ["Anima.py", "anima_semantic.py", "anima_secure.py",
            "anima_launcher.py", "anima_setup.py", "demo_memory.json"]


def check_env():
    ok = sys.version_info >= (3, 8)
    print("Python: %s (нужен 3.8+)" % sys.version.split()[0])
    missing = [n for n in REQUIRED if not os.path.exists(os.path.join(HERE, n))]
    if missing:
        print("Отсутствуют файлы:", ", ".join(missing)); ok = False
    mem = "найдена" if os.path.exists(os.path.join(HERE, "pet_memory.json")) else "не создана (не страшно)"
    print("Память:", mem)
    print("Окружение в порядке." if ok else "Окружение требует внимания.")
    return ok


def clean_secrets():
    import anima_secure as sec
    total = 0
    for name in os.listdir(HERE):
        if name.startswith("demo_") or not name.endswith((".py", ".md", ".txt", ".json")):
            continue
        path = os.path.join(HERE, name)
        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read()
        masked = sec.mask_secrets(text)
        if masked != text:
            with open(path, "w", encoding="utf-8") as f:
                f.write(masked)
            print("Замаскированы секреты в:", name)
            total += 1
    print("Ничего не найдено." if not total
          else "Почищено файлов: %d. Токены всё равно отзовите!" % total)


def setup_demo():
    src, dst = os.path.join(HERE, "demo_memory.json"), os.path.join(HERE, "pet_memory.json")
    if not os.path.exists(src):
        print("demo_memory.json не найден"); return
    if os.path.exists(dst):
        if input("pet_memory.json уже есть! Перезаписать? Введите YES: ") != "YES":
            print("Отменено."); return
    shutil.copyfile(src, dst)
    print("Демо-память установлена. Играйтесь; перед своей памятью удалите её.")


MENU = {"1": ("проверка окружения", check_env),
        "2": ("чистка секретов", clean_secrets),
        "3": ("установка демо-памяти", setup_demo)}

if __name__ == "__main__":
    while True:
        print("\n=== Установка Анимы ===")
        for k, (title, _) in MENU.items():
            print(k, "—", title)
        print("0 — выход")
        choice = input("> ").strip()
        if choice == "0":
            break
        if choice in MENU:
            MENU[choice][1]()
