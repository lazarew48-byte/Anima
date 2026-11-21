#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
chat_window.py — отдельное окно «болталки» для Анимы.
Запуск: python chat_window.py
Команды: /режим  /очистить  /выход
Без LLM честно показывает найденные факты из памяти.
"""

import os
import re
import json
import tkinter as tk
from tkinter import scrolledtext

import llm_bridge

_DIR = os.path.dirname(os.path.abspath(__file__))
MEMORY_FILE = os.path.join(_DIR, "pet_memory.json")

STOP = set("""и в на с что как это же а но или из-за по для от до при про
под над без бы ли уж вот там тут если когда чтобы потому поэтому
который которые которая был была было были быть будет будут
твой ваш наш их её его они мы вы я ты он она оно
return def class import from not for in if else elif try except while
print true false none self int str float list dict set""".split())


def _tokens(text):
    words = re.findall(r"[а-яёa-z0-9]{3,}", (text or "").lower())
    return [w[:6] for w in words if w not in STOP]


def _stem(w):
    for suf in ("ами", "ями", "ов", "ев", "ах", "ях", "ой", "ий", "ый", "ая",
                "яя", "ую", "юю", "ем", "ом", "ам", "ям", "ей", "е", "и", "ы", "у", "ю", "а", "я", "о"):
        if w.endswith(suf) and len(w) - len(suf) >= 4:
            return w[: len(w) - len(suf)]
    return w


def load_memory():
    try:
        with open(MEMORY_FILE, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {"facts": [], "profile": {"name": "Анима"}}


def find_facts(query, memory, top=10):
    qt = [_stem(w) for w in _tokens(query)]
    if not qt:
        return []
    scored = []
    for f in memory.get("facts", []):
        ftags = set(f.get("tags", []))
        score = 0
        for w in qt:
            for t in ftags:
                tw = _stem(t)
                if w == tw or tw.startswith(w) or w.startswith(tw):
                    score += 1
        if score:
            scored.append((score, f))
    scored.sort(key=lambda x: (-x[0], -x[1].get("trust", 0)))
    return [f for _, f in scored[:top]]


class ChatApp:
    def __init__(self, root):
        self.root = root
        root.title("Анима — болталка (LLM)")
        root.geometry("640x520")

        self.memory = load_memory()
        self.pet_name = self.memory.get("profile", {}).get("name", "Анима")
        self.mode = "researcher"
        self.history = []

        self.chat = scrolledtext.ScrolledText(root, wrap=tk.WORD, state="disabled",
                                              font=("Consolas", 11))
        self.chat.pack(fill="both", expand=True, padx=6, pady=6)

        bottom = tk.Frame(root)
        bottom.pack(fill="x", padx=6, pady=6)
        self.entry = tk.Entry(bottom, font=("Consolas", 11))
        self.entry.pack(side="left", fill="x", expand=True)
        self.entry.bind("<Return>", self.on_send)
        tk.Button(bottom, text="Отправить", command=self.on_send).pack(side="right", padx=(4, 0))

        self._say("Анима", "Привет! Болталка — отдельное окно для разговора.\n"
                           "Память: %d фактов. Мозг: %s\nКоманды: /режим, /очистить, /выход"
                  % (len(self.memory.get("facts", [])), llm_bridge.brain_status()))

    def _say(self, who, text):
        self.chat.configure(state="normal")
        self.chat.insert("end", "%s: %s\n\n" % (who, text))
        self.chat.see("end")
        self.chat.configure(state="disabled")

    def on_send(self, event=None):
        msg = self.entry.get().strip()
        if not msg:
            return
        self.entry.delete(0, "end")

        if msg == "/очистить":
            self.history = []
            self.chat.configure(state="normal")
            self.chat.delete("1.0", "end")
            self.chat.configure(state="disabled")
            self._say("Анима", "Переписка стёрта.")
            return
        if msg == "/режим":
            self.mode = "seer" if self.mode != "seer" else "researcher"
            self._say("Анима", "Режим: %s" % ("провидец (фантазирую)" if self.mode == "seer"
                                              else "исследователь (только факты)"))
            return
        if msg == "/выход":
            self.root.destroy()
            return

        self._say("Ты", msg)
        facts = find_facts(msg, self.memory)
        used = ", ".join("#%s" % f.get("id") for f in facts[:5]) or "—"
        self._say("…", "факты: %s | мозг: %s" % (used, llm_bridge.brain_status()))

        answer = llm_bridge.ask(msg, facts, mode=self.mode, pet_name=self.pet_name)
        if answer:
            self._say(self.pet_name, answer)
            self.history.append({"role": "user", "text": msg})
            self.history.append({"role": "assistant", "text": answer})
        else:
            if facts:
                lines = ["— %s" % (f.get("text", "")[:200]) for f in facts[:5]]
                self._say(self.pet_name + " (без LLM)",
                          "Модель не отвечает, держи что нашла в памяти:\n" + "\n".join(lines))
            else:
                self._say(self.pet_name + " (без LLM)",
                          "Модель не отвечает и в памяти по этому ничего нет. "
                          "Проверь .env (ключ и каталог) и интернет.")


def main():
    root = tk.Tk()
    ChatApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
