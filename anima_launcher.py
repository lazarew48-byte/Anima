#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
anima_launcher.py — защищённый запуск Анимы:
1) скан секретов в файлах проекта; 2) расшифровка памяти паролем;
3) запуск Anima.py; 4) при выходе — предложение зашифровать снова.
"""

import getpass, json, os, runpy, sys

import anima_secure as sec

HERE = os.path.dirname(os.path.abspath(__file__))
MEMORY = os.path.join(HERE, "pet_memory.json")


def main():
    print("=== Защищённый запуск Анимы ===")
    # 1. скан секретов (демо-файлы не сканируем — там намеренные фейки)
    problems = []
    for name in os.listdir(HERE):
        if name.startswith("demo_") or name == "pet_memory.json":
            continue
        if name.endswith((".py", ".md", ".txt", ".json")):
            for line, kind in sec.scan_file(os.path.join(HERE, name)):
                problems.append("%s:%d — %s" % (name, line, kind))
    if problems:
        print("Найдены секреты — запустите `python anima_setup.py` (пункт 2):")
        for p in problems[:10]:
            print("  " + p)
        return 1
    # 2. память
    if os.path.exists(MEMORY) and sec.is_encrypted(MEMORY):
        pwd = getpass.getpass("Пароль памяти: ")
        try:
            with open(MEMORY, encoding="utf-8") as f:
                data = sec.decrypt_memory(json.load(f), pwd)
            with open(MEMORY, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=1)
            print("Память расшифрована.")
        except ValueError as e:
            print("Запуск отменён: %s" % e)
            return 1
    # 3. ядро
    try:
        runpy.run_path(os.path.join(HERE, "Anima.py"), run_name="__main__")
    except SystemExit:
        pass
    # 4. обратное шифрование
    if os.path.exists(MEMORY) and not sec.is_encrypted(MEMORY):
        answer = input("Зашифровать память перед выходом? [Y/n]: ").strip().lower()
        if answer in ("", "y", "yes", "д"):
            pwd = getpass.getpass("Пароль: ")
            with open(MEMORY, encoding="utf-8") as f:
                obj = json.load(f)
            sec.save_encrypted(MEMORY, obj, pwd)
            print("Память зашифрована.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
