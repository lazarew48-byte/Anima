#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pet Agent v3 — цифровой питомец с памятью, фантазиями и кормлением файлами.

Запуск:  python pet_agent.py
Нужен только стандартный Python 3.8+. Никаких установок.

Память: pet_memory.json рядом со скриптом. НЕ удаляйте его — это душа питомца.
"""

import json, os, re, sys, time, random, hashlib, zipfile

try:
    import tkinter as tk
    from tkinter import filedialog, scrolledtext
    HAVE_GUI = True
except Exception:
    HAVE_GUI = False

MEMORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pet_memory.json")

CONFIG = {
    "max_facts_per_file": 120,   # максимум новых фактов из одного файла
    "chunk_len": 220,            # длина куска текста (символы)
    "zip_max_files": 30,         # максимум файлов из архива
    "max_rows_csv": 100,         # максимум строк таблицы
    "max_json_entries": 150,     # максимум полей JSON
    "quarantine_threshold": -2,  # доверие ниже или равно — карантин
}

STOP = set("""и в во не что он на я с со как а то все она так его но да ты к у же вы за бы по
только её мне было вот от меня ещё нет о из ему теперь когда даже ну вдруг ли если уже или ни
быть был него до вас нибудь опять уж вам сказал ведь там потом себя ничего ей может они тут
где есть надо ней для мы тебя их чем была сам чтоб без будто человек чего раз тоже себе под
жизнь будет ж тогда кто этот говорил того потому этого какой совсем ним здесь этом почти мой
тем чтобы нее кажется сейчас были куда зачем всех можно при об хорошо эту перед иногда лучше
чуть том нельзя такой им более всегда конечно всю между это очень просто также ещё типа"""
    .split())

TEXT_EXTS = {".txt", ".md", ".log", ".tsv", ".py", ".ini", ".cfg", ".conf", ".html",
             ".css", ".js", ".ts", ".sh", ".yaml", ".yml", ".toml", ".rst", ".xml",
             ".svg", ".srt", ".bat", ".sql", ".tex", ".env"}

LEVELS = [(0, "🥚 Яйцо"), (50, "🐣 Птенчик"), (150, "🌱 Подросток"),
          (350, "🐦 Юнец"), (700, "🦅 Взрослый помощник")]

DREAM_TEMPLATES = [
    "мне снилось, что {a}… и почему-то это было связано с {b}. не спрашивай, у снов нет логики",
    "странный сон: {a} вдруг стало {b}. когда проснулся — почти поверил",
    "видел сон, где {a} и {b} спорили, кто из них важнее. ничего не решил",
    "мне грезилось: {a}… а потом всё это оказалось {b}. во сне это имело смысл, честно",
]


def tokenize(text):
    words = re.findall(r"[a-zа-яё0-9]+", text.lower())
    return [w for w in words if (len(w) >= 4 or w.isdigit()) and w not in STOP]


def short(s, n=90):
    s = re.sub(r"\s+", " ", s).strip()
    return s if len(s) <= n else s[:n].rstrip() + "…"


class PetAgent:
    """Мозг питомца. Полностью отделён от интерфейса: можно тестировать без окна."""

    def __init__(self, memory_path=MEMORY_FILE):
        self.memory_path = memory_path
        self.state = {"energy": 70, "mood": 70, "cleanliness": 100, "xp": 0,
                      "imagination": 20, "accepted_dreams": 0, "rejected_dreams": 0}
        self.facts = []          # [{"id","text","tags","trust","source","created"}]
        self.quarantine = []     # факты, наказанные дважды
        self.hashes = set()      # защита от дублей
        self._next_id = 1
        self.last_fact_ids = []  # факты из последнего фактического ответа
        self.last_dream_ids = [] # факты, из которых собран последний сон
        self.last_kind = None    # "fact" | "dream" | None
        self.load()

    # ---------- хранение ----------

    def load(self):
        if not os.path.exists(self.memory_path):
            return
        try:
            with open(self.memory_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            print("Не смог прочитать память, начинаю с чистого листа")
            return
        self.state.update(data.get("state", {}))
        self.facts = data.get("facts", [])
        self.quarantine = data.get("quarantine", [])
        self._next_id = data.get("next_id", len(self.facts) + 1)
        for f in self.facts + self.quarantine:
            self.hashes.add(f.get("hash", ""))

    def save(self):
        data = {"state": self.state, "facts": self.facts,
                "quarantine": self.quarantine, "next_id": self._next_id}
        for f in self.facts + self.quarantine:
            f["hash"] = hashlib.sha1(re.sub(r"\s+", " ", f["text"]).strip().lower()
                                     .encode("utf-8")).hexdigest()[:16]
        with open(self.memory_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)

    def level(self):
        name = LEVELS[0][1]
        for need, nm in LEVELS:
            if self.state["xp"] >= need:
                name = nm
        return name

    def level_idx(self):
        idx = 0
        for i, (need, _) in enumerate(LEVELS):
            if self.state["xp"] >= need:
                idx = i
        return idx

    # ---------- добавление фактов ----------

    def _add_fact(self, text, source, extra_tags=None):
        norm = re.sub(r"\s+", " ", text).strip().lower()
        if len(norm) < 5:
            return False
        h = hashlib.sha1(norm.encode("utf-8")).hexdigest()[:16]
        if h in self.hashes:
            return False
        self.hashes.add(h)
        fact = {"id": self._next_id, "text": text.strip(),
                "tags": self.make_tags(text, extra_tags), "trust": 0,
                "source": source, "created": time.strftime("%Y-%m-%d %H:%M")}
        self.facts.append(fact)
        self._next_id += 1
        return True

    def make_tags(self, text, extra=None):
        tags = set(tokenize(text))
        if extra:
            tags |= {t.lower() for t in extra if t}
        return sorted(tags)[:15]

    def feed_text(self, text, source="разговор"):
        text = re.sub(r"^запомни[:\s]*", "", text.strip(), flags=re.I)
        added = skipped = 0
        for chunk in self.chunk_text(text, source):
            if self._add_fact(chunk, source):
                added += 1
            else:
                skipped += 1
        self.state["energy"] = min(100, self.state["energy"] + 8)
        self.state["xp"] += 3 + added * 2
        return added, skipped

    # ---------- парсеры файлов ----------

    @staticmethod
    def read_text_any(path):
        with open(path, "rb") as f:
            data = f.read()
        for enc in ("utf-8-sig", "utf-8", "cp1251"):
            try:
                return data.decode(enc)
            except UnicodeDecodeError:
                continue
        return data.decode("utf-8", errors="replace")

    def chunk_text(self, text, source):
        parts = re.split(r"(?<=[.!?;])\s+|\n+", text)
        chunks, buf = [], ""
        for p in parts:
            p = p.strip()
            if not p:
                continue
            if not buf or len(buf) + len(p) + 1 <= CONFIG["chunk_len"]:
                buf = (buf + " " + p).strip()
            else:
                chunks.append(buf)
                buf = p
            while len(buf) > CONFIG["chunk_len"] * 2:
                chunks.append(buf[:CONFIG["chunk_len"] * 2])
                buf = buf[CONFIG["chunk_len"] * 2:]
        if buf:
            chunks.append(buf)
        return chunks[:CONFIG["max_facts_per_file"]]

    @staticmethod
    def _flatten_json(obj, prefix=""):
        items = []
        if isinstance(obj, dict):
            for k, v in obj.items():
                items += PetAgent._flatten_json(v, f"{prefix}.{k}" if prefix else str(k))
        elif isinstance(obj, list):
            for i, v in enumerate(obj[:20]):
                items += PetAgent._flatten_json(v, f"{prefix}[{i}]")
        else:
            s = str(obj).strip()
            if s:
                items.append((prefix, s[:300]))
        return items

    def parse_json(self, text, name):
        try:
            obj = json.loads(text)
        except Exception:
            return self.chunk_text(text, name)
        flat = self._flatten_json(obj)
        chunks = [f"{name} | {prefix}: {val}" for prefix, val in flat[:CONFIG["max_json_entries"]]]
        return chunks or self.chunk_text(text, name)

    def parse_csv(self, text, name):
        lines = [l for l in text.splitlines() if l.strip()]
        if len(lines) < 2:
            return self.chunk_text(text, name)
        delim = max([",", ";", "\t"], key=lambda d: lines[0].count(d))
        if lines[0].count(delim) == 0:
            return self.chunk_text(text, name)
        header = [h.strip() for h in lines[0].split(delim)]
        chunks = []
        for row in lines[1:CONFIG["max_rows_csv"] + 1]:
            cells = [c.strip() for c in row.split(delim)]
            pairs = "; ".join(f"{h}={v}" for h, v in zip(header, cells) if v)
            if pairs:
                chunks.append(f"{name}: {pairs}")
        return chunks or self.chunk_text(text, name)

    def parse_py(self, text, name):
        funcs = re.findall(r"^\s*(?:async\s+)?def\s+(\w+)|^\s*class\s+(\w+)", text, re.M)
        names = [a or b for a, b in funcs]
        chunks = []
        for c in self.chunk_text(text, name):
            extra = [n for n in names if re.search(r"\b" + n + r"\b", c)]
            chunks.append((c, extra))
        return chunks

    def parse_file(self, path):
        """Возвращает (chunks, error). chunks — список строк или (строка, доп.теги)."""
        name = os.path.basename(path)
        ext = os.path.splitext(path)[1].lower()
        if ext == ".zip":
            return self.parse_zip(path)
        with open(path, "rb") as f:
            raw = f.read(4096)
        if b"\x00" in raw:
            return None, (f"{name} — двоичный формат, не перевариваю. Пока умею: txt, md, "
                          f"py, json, csv, log, yaml, ini и архивы zip")
        text = self.read_text_any(path)
        if not text.strip():
            return [], f"{name} — пустой файл, есть нечего"
        if ext == ".json":
            return self.parse_json(text, name), None
        if ext == ".csv":
            return self.parse_csv(text, name), None
        if ext == ".py":
            return self.parse_py(text, name), None
        return self.chunk_text(text, name), None

    def parse_zip(self, path):
        name = os.path.basename(path)
        chunks, taken = [], 0
        try:
            with zipfile.ZipFile(path) as z:
                for info in z.namelist():
                    if taken >= CONFIG["zip_max_files"]:
                        break
                    if info.endswith("/"):
                        continue
                    inner_ext = os.path.splitext(info)[1].lower()
                    if inner_ext not in TEXT_EXTS and inner_ext not in (".json", ".csv", ".md"):
                        continue
                    try:
                        data = z.read(info)
                    except Exception:
                        continue
                    if b"\x00" in data[:4096]:
                        continue
                    for enc in ("utf-8-sig", "utf-8", "cp1251"):
                        try:
                            text = data.decode(enc)
                            break
                        except UnicodeDecodeError:
                            text = None
                    if text is None:
                        text = data.decode("utf-8", errors="replace")
                    inner_name = f"{name}/{os.path.basename(info)}"
                    if info.lower().endswith(".json"):
                        chunks += self.parse_json(text, inner_name)
                    elif info.lower().endswith(".csv"):
                        chunks += self.parse_csv(text, inner_name)
                    elif info.lower().endswith(".py"):
                        chunks += [c if isinstance(c, tuple) else (c, []) for c in self.parse_py(text, inner_name)]
                    else:
                        chunks += [(c, []) for c in self.chunk_text(text, inner_name)]
                    taken += 1
        except Exception as e:
            return None, f"{name} — не смог открыть архив: {e}"
        if not chunks:
            return [], f"{name} — в архиве нет текстовых файлов, которые я умею есть"
        return chunks, None

    def feed_file(self, path):
        chunks, error = self.parse_file(path)
        if error is not None:
            return None, error
        if not chunks:
            return None, "из файла не извлеклось ни одного куска текста"
        source = os.path.basename(path)
        added = skipped = 0
        for c in chunks:
            if isinstance(c, tuple):
                text, extra = c
            else:
                text, extra = c, []
            if self._add_fact(text, source, extra):
                added += 1
            else:
                skipped += 1
        self.state["energy"] = min(100, self.state["energy"] + 25)
        self.state["mood"] = min(100, self.state["mood"] + 5)
        self.state["xp"] += 5 + added * 3
        note = ""
        if skipped:
            note = f" ({skipped} кусков уже были в памяти — дубли не повторяю)"
        return added, f"{source}: съел {added} кусков{note}"

    # ---------- поиск и ответы ----------

    def active_facts(self):
        qids = {f["id"] for f in self.quarantine}
        return [f for f in self.facts if f["id"] not in qids]

    def find(self, q):
        cleaned = re.sub(r"^(что такое|кто такой|кто такая|найди|расскажи про|расскажи|"
                         r"покажи|напомни|прочитай)\s+", "", q.strip(), flags=re.I).strip("?!. ")
        tokens = tokenize(cleaned)
        if not tokens:
            return [], cleaned
        scored = []
        for f in self.active_facts():
            tl = f["text"].lower()
            tset = set(f["tags"])
            score = 0
            for t in tokens:
                if t in tset:
                    score += 2
                elif any(tag[:4] == t[:4] for tag in tset):
                    score += 1
                elif t in tl:
                    score += 1
            if len(tokens) >= 2 and all(t in tset or t in tl for t in tokens):
                score += 4
            if len(cleaned) >= 6 and cleaned.lower() in tl:
                score += 6
            if f["trust"] > 0:
                score += f["trust"] * 0.5
            if score > 0:
                scored.append((score, f))
        scored.sort(key=lambda x: (-x[0], -x[1]["trust"], x[1]["id"]))
        return [f for _, f in scored[:3]], cleaned

    def query(self, text):
        if self.level_idx() == 0:
            self.state["energy"] = max(0, self.state["energy"] - 1)
            return [("err", "пиу… пиу… 🥚 я ещё яйцо! покорми меня — напиши «запомни: …» или нажми «Скормить файл»")]
        found, cleaned = self.find(text)
        self.state["xp"] += 2
        self.state["energy"] = max(0, self.state["energy"] - 1)
        msgs = []
        if not found:
            msgs.append(("err", f"честно: про «{short(cleaned, 40)}» в моей памяти ничего нет. "
                                f"я не выдумываю — покорми меня этим знанием"))
            self.last_fact_ids = []
            self.last_kind = None
            return msgs
        if self.level_idx() == 1:
            f = found[0]
            self.last_fact_ids = [f["id"]]
            self.last_kind = "fact"
            msgs.append(("pet", f"нашёл! [{f['source']}, запись #{f['id']}]: {short(f['text'], 150)}"))
        elif self.level_idx() == 2:
            f = found[0]
            self.last_fact_ids = [f["id"]]
            self.last_kind = "fact"
            msgs.append(("pet", f"нашёл в памяти [{f['source']}, #{f['id']}, доверие {f['trust']}]: "
                                f"{short(f['text'], 200)}"))
        else:
            parts = []
            for f in found[:2]:
                parts.append(f"«{short(f['text'], 160)}» [{f['source']}, #{f['id']}, доверие {f['trust']}]")
            self.last_fact_ids = [f["id"] for f in found[:2]]
            self.last_kind = "fact"
            msgs.append(("pet", "нашёл целых два куска: " + " и ".join(parts)))
        if random.random() < self.dream_chance():
            msgs += self.dream()
            self.last_kind = "fact"   # сон рядом, но ругать надо факт
        return msgs

    # ---------- фантазии ----------

    def dream_chance(self):
        s = self.state
        return min(0.05 + s["imagination"] / 800 + max(0, (30 - s["energy"])) / 150, 0.6)

    def dream(self, topic=None):
        pool = self.active_facts()
        if topic:
            tokens = set(tokenize(topic))
            filtered = [f for f in pool if tokens & set(f["tags"])]
            if filtered:
                pool = filtered
        if len(pool) < 2:
            return [("err", "мне не из чего грезить — покорми меня хотя бы двумя знаниями")]
        a, b = random.sample(pool, 2)
        tpl = random.choice(DREAM_TEMPLATES)
        dream_text = "🌙 " + tpl.format(a=short(a["text"], 80), b=short(b["text"], 80))
        self.last_dream_ids = [a["id"], b["id"]]
        self.last_kind = "dream"
        self.state["xp"] += 3
        self.state["energy"] = max(0, self.state["energy"] - 3)
        return [("fant", dream_text)]

    def vote(self, genius):
        if not self.last_dream_ids:
            return [("sys", "голосовать можно только за сны 🌙 — сначала попроси меня пофантазировать")]
        if genius:
            self.state["imagination"] = min(100, self.state["imagination"] + 8)
            self.state["accepted_dreams"] += 1
            self.state["mood"] = min(100, self.state["mood"] + 5)
            self.state["xp"] += 5
            self.last_dream_ids = []
            return [("sys", f"🌈 фантазия принята! воображение: {self.state['imagination']}%. "
                            f"буду грезить чаще и в этом вкусе")]
        self.state["imagination"] = max(0, self.state["imagination"] - 2)
        self.state["rejected_dreams"] += 1
        self.state["mood"] = max(0, self.state["mood"] - 3)
        self.last_dream_ids = []
        return [("sys", f"бывает 🫥 воображение: {self.state['imagination']}%")]

    def correct(self):
        if self.last_kind == "dream" and not self.last_fact_ids:
            return self.vote(False)
        if not self.last_fact_ids:
            return [("sys", "а что именно я перепутал? сначала задай вопрос, потом ругай 🙂")]
        quarantined = []
        for fid in self.last_fact_ids:
            for f in self.facts:
                if f["id"] == fid:
                    f["trust"] -= 1
                    if f["trust"] <= CONFIG["quarantine_threshold"]:
                        self.quarantine.append(f)
                        self.facts.remove(f)
                        quarantined.append(f["id"])
        self.state["cleanliness"] = max(0, self.state["cleanliness"] - 10)
        self.state["mood"] = max(0, self.state["mood"] - 5)
        self.state["xp"] += 3
        self.last_fact_ids = []
        self.last_kind = None
        msg = "🧹 убрался! виновные записи наказаны"
        if quarantined:
            msg += f", записи {quarantined} отправлены в карантин — больше не использую их"
        return [("sys", msg)]

    def status(self):
        s = self.state
        q = len(self.quarantine)
        sources = sorted({f["source"] for f in self.active_facts()})
        src = ", ".join(sources[:5]) + ("…" if len(sources) > 5 else "")
        return [("sys", f"я — {self.level()}. сытость {s['energy']}%, настроение {s['mood']}%, "
                        f"чистота {s['cleanliness']}%, воображение {s['imagination']}% 🌙. "
                        f"опыт {s['xp']}. в памяти {len(self.active_facts())} активных записей, "
                        f"{q} в карантине. ел из источников: {src or 'пока никого не кормил'}")]

    # ---------- диспетчер ----------

    def process(self, text):
        t = text.strip()
        low = t.lower()
        if not t:
            return [("sys", "я слушаю…")]
        if low.startswith("запомни"):
            a, s = self.feed_text(t)
            msg = f"🍽 съел {a} новых кусков" + (f", {s} дублей пропустил" if s else "")
            msgs = [("pet", msg)]
            if random.random() < 0.15 and self.level_idx() >= 1:
                msgs += self.dream()
            return msgs
        if "файл" in low and low in ("файл", "скормить файл", "файлы", "скормить файлы"):
            return [("sys", "__FILE_DIALOG__")]
        if re.search(r"пофантазир|сон|сни|грез", low):
            m = re.search(r"(?:про|из|на тему)\s+(.+)$", t, re.I)
            return self.dream(m.group(1) if m else None)
        if "гениально" in low or "круто" in low or "нравится" in low:
            return self.vote(True)
        if low.startswith("бред") or low.startswith("фу ") or low == "бред":
            return self.vote(False)
        if re.search(r"ошиб|неправ|врань", low):
            return self.correct()
        if re.search(r"как ты|статус|кто ты", low):
            return self.status()
        return self.query(t)


# ================= ОКНО =================

if HAVE_GUI:

    class PetWindow:
        def __init__(self, root, agent):
            self.agent = agent
            self.root = root
            root.title("Pet Agent v3 — питомец с фантазиями")
            root.geometry("660x740")
            root.configure(bg="#1e1f28")

            top = tk.Frame(root, bg="#1e1f28")
            top.pack(fill="x", padx=14, pady=(12, 4))
            self.face = tk.Label(top, text="", font=("Segoe UI Emoji", 34), bg="#1e1f28")
            self.face.pack(side="left")
            self.stats = tk.Label(top, text="", font=("Segoe UI", 10), fg="#c8c9d4",
                                  bg="#1e1f28", justify="left")
            self.stats.pack(side="left", padx=12)

            self.chat = scrolledtext.ScrolledText(root, bg="#262833", fg="#e8e9f0",
                                                  font=("Consolas", 11), wrap="word",
                                                  state="disabled", bd=0, padx=12, pady=10)
            self.chat.pack(fill="both", expand=True, padx=14, pady=8)
            for tag, cfg in {
                "pet":  {"foreground": "#7ec8ff"},
                "fant": {"foreground": "#ff9ed2", "font": ("Consolas", 11, "italic")},
                "err":  {"foreground": "#ff6b6b"},
                "sys":  {"foreground": "#9aa0b5"},
                "user": {"foreground": "#ffffff", "font": ("Consolas", 11, "bold")},
            }.items():
                self.chat.tag_configure(tag, **cfg)

            btns = tk.Frame(root, bg="#1e1f28")
            btns.pack(fill="x", padx=14)
            for label, cmd in [("Как ты", lambda: self.send("как ты")),
                               ("Пофантазировать 🌙", lambda: self.send("пофантазируй")),
                               ("Гениально 🌈", lambda: self.send("гениально")),
                               ("Бред", lambda: self.send("бред")),
                               ("Ты ошибся 🧹", lambda: self.send("ты ошибся")),
                               ("🍽 Скормить файл", self.pick_file)]:
                tk.Button(btns, text=label, command=cmd, bg="#34374a", fg="#e8e9f0",
                          relief="flat", padx=8, pady=3, font=("Segoe UI", 9)).pack(side="left", padx=(0, 6), pady=4)

            entry_frame = tk.Frame(root, bg="#1e1f28")
            entry_frame.pack(fill="x", padx=14, pady=(4, 12))
            self.entry = tk.Entry(entry_frame, bg="#2c2f3d", fg="#e8e9f0", insertbackground="#e8e9f0",
                                  font=("Consolas", 12), bd=0)
            self.entry.pack(side="left", fill="x", expand=True, ipady=6, ipadx=6)
            self.entry.bind("<Return>", self.on_enter)
            tk.Button(entry_frame, text="→", command=self.on_enter, bg="#4a63e7", fg="white",
                      relief="flat", font=("Segoe UI", 11, "bold"), padx=14, pady=4).pack(side="left", padx=(8, 0))

            self.refresh()
            self.out("sys", "Питомец вылупился! Покорми его: напиши «запомни: …» или нажми «🍽 Скормить файл».\n"
                            "Синие ответы — факты из памяти, розовые 🌙 — фантазии (голосуй за них!)")

        def refresh(self):
            s = self.agent.state
            faces = {0: "🥚", 1: "🐣", 2: "🌱", 3: "🐦", 4: "🦅"}
            mood = "😊" if s["mood"] > 60 else ("😐" if s["mood"] > 30 else "🥴")
            self.face.config(text=faces[self.agent.level_idx()] + mood)
            self.stats.config(text=f"{self.agent.level()}\n"
                                   f"сытость {s['energy']}%  настроение {s['mood']}%  "
                                   f"чистота {s['cleanliness']}%\n"
                                   f"воображение {s['imagination']}% 🌙  опыт {s['xp']}  "
                                   f"записей {len(self.agent.active_facts())}")

        def out(self, tag, text):
            self.chat.config(state="normal")
            self.chat.insert("end", text + "\n\n", tag)
            self.chat.config(state="disabled")
            self.chat.see("end")

        def handle(self, msgs):
            for tag, m in msgs:
                if m == "__FILE_DIALOG__":
                    self.pick_file()
                    continue
                self.out(tag, m)
            self.refresh()

        def send(self, text):
            if not text.strip():
                return
            self.out("user", "Ты: " + text)
            self.entry.delete(0, "end")
            self.handle(self.agent.process(text))

        def on_enter(self, event=None):
            self.send(self.entry.get())

        def pick_file(self):
            paths = filedialog.askopenfilenames(
                title="Скормить питомцу файлы",
                filetypes=[("Текст и данные", "*.txt *.md *.log *.csv *.tsv *.py *.json "
                            "*.yaml *.yml *.toml *.ini *.cfg *.html *.css *.js *.sql *.zip"),
                           ("Все файлы", "*.*")])
            for p in paths:
                res, err = self.agent.feed_file(p)
                if err:
                    self.out("err", err)
                else:
                    self.out("pet", res)
            self.refresh()
            self.agent.save()

        def on_close(self):
            self.agent.save()
            self.root.destroy()


def main():
    if not HAVE_GUI:
        print("tkinter недоступен в этой среде — окно не запускается.")
        sys.exit(1)
    agent = PetAgent()
    root = tk.Tk()
    win = PetWindow(root, agent)
    root.protocol("WM_DELETE_WINDOW", win.on_close)
    root.mainloop()


if __name__ == "__main__":
    main()
