#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Anima v5 — живой компаньон. Склейка: тело v3 (парсеры, окно, карантин) + механики v4
(Guided Hallucination, Anima Forms, Study Engine, картина мира) + новый слой жизни:

  * Эмоциональный резонанс: сентимент съеденных данных двигает mood и копит stress;
    мрачные данные -> мрачные сны, радостные -> игривые
  * Локус контроля: при воображении > 80 питомец сам инициирует исследование, сны
    и картину мира; при стрессе сам предлагает «что-то светлое» из твоей памяти
  * Social Graph: bond_with_user растёт от общения и спасения из голода; чем выше
    связь, тем смелее и личнее галлюцинации (на низком — только факты)
  * Эстетика: шаблоны снов зависят от mood (рваные с многоточиями при низком) и
    bond (вплетает твои любимые словечки из токенизации твоих фактов)
  * Двойной цикл мышления: режим исследователя (сны почти выключены) и провидца
    (dream_chance 0.9) — переключение по команде, парадоксу или стрессу
  * Reality Filter: каждый сон проверяется по памяти — сноске о подтверждении
  * Study Engine в две фазы: поэзия (мост) и математика (числа, паттерн, прогноз)

Запуск:  python Anima_v5.py
Нужен только стандартный Python 3.8+. Никаких установок.
Память: pet_memory.json рядом со скриптом. НЕ удаляйте его — это душа питомца.
"""

import json, os, re, sys, time, random, hashlib, zipfile
from collections import Counter, defaultdict

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
    "quarantine_threshold": -1,  # доверие ниже или равно — карантин
}

STOP = set("""и в во не что он на я с со как а то все она так его но да ты к у же вы за бы по
только её мне было вот от меня ещё нет о из ему теперь когда даже ну вдруг ли если уже или ни
быть был него до вас нибудь опять уж вам сказал ведь там потом себя ничего ей может они тут
где есть надо ней для мы тебя их чем была сам чтоб без будто человек чего раз тоже себе под
жизнь будет ж тогда кто этот говорил того потому этого какой совсем ним здесь этом почти мой
тем чтобы нее кажется сейчас были куда зачем всех можно при об хорошо эту перед иногда лучше
чуть том нельзя такой им более всегда конечно всю между это очень просто также ещё типа про пусть типа вроде мол the this that with from have will been were what when then they them there than your self only just like some into over also does none null true false function import class while print const value index type object result params args string number level items item list dict file title name data"""
    .split())

TEXT_EXTS = {".txt", ".md", ".log", ".tsv", ".py", ".ini", ".cfg", ".conf", ".html",
             ".css", ".js", ".ts", ".sh", ".yaml", ".yml", ".toml", ".rst", ".xml",
             ".svg", ".srt", ".bat", ".sql", ".tex", ".env"}

JUNK_TAGS = {"json", "csv", "txt", "tsv", "md", "py", "zip", "yaml", "yml", "toml",
             "ini", "cfg", "conf", "html", "css", "js", "ts", "log", "xml", "sql",
             "name", "prefix"}

# ---------- аффективный слой: лёгкий локальный сентимент ----------
POSITIVE_WORDS = set("""рад радость радостно счастлив счастье люблю обожаю нравится отлично здорово
класс супер восторг кайф доволен доволен горжусь горд гордость успех успехи победа победил молодец
спасибо красиво замечательно прекрасно весело смешно уют уютно спокойно спокойствие вдохновение
вдохновляюще надежда надеюсь приятно приятный тепло тёплый теплый прогресс получилось удалось
наладилось хорошо похвалил умница светло светлое счастливая счастливые любимый любимое впереди""".split())

NEGATIVE_WORDS = set("""злюсь злой злость бесит раздражает раздражение злит ненавижу ненависть
отвратительно ужасно ужас жутко кошмар стресс паника тревога тревожно тревожусь страшно боюсь страх
депрессия депрессивно грустно грусть тоска тоскую печаль печально больно боль устал усталость
выгорание выгорел разочарован разочарование обидно обида обидел ничтожество ничтожный пусто пустота
одиноко одиночество крик кричал кричит накричал скандал ругал ругается провал провалил срыв сорвался
фиаско тупик тупо глупо бесполезно безнадёга безнадега отстой мрак тяжело тяжко горе страдаю страдание
виню виноват провисло крах катастрофа паник зло обидно""".split())

NEGATIONS = {"не", "нет", "ни"}
INTENSIFIERS = {"очень", "крайне", "безумно", "невыносимо", "сильно", "тотально", "дико"}


def analyze_sentiment(text):
    """Лёгкий локальный сентимент [-1..1]: словарь эмоций + «не» + усилители. Без внешних моделей."""
    words = re.findall(r"[a-zа-яё]+", text.lower())
    score, hits, prev_neg, prev_int = 0, 0, False, False
    for w in words:
        if w in NEGATIONS:
            prev_neg = True
            continue
        if w in INTENSIFIERS:
            prev_int = True
            continue
        base = 0
        if w in POSITIVE_WORDS or any(w.startswith(p) and len(w) <= len(p) + 4 for p in POSITIVE_WORDS):
            base = 1
        elif w in NEGATIVE_WORDS or any(w.startswith(n) and len(w) <= len(n) + 4 for n in NEGATIVE_WORDS):
            base = -1
        if base:
            if prev_neg:
                base = -base
            if prev_int:
                base *= 2
            score += base
            hits += 1
        prev_int = False
        prev_neg = False
    return 0.0 if not hits else max(-1.0, min(1.0, score / max(3.0, hits)))


def tone_word(t):
    if t <= -0.5:
        return "мрачный 🌑"
    if t <= -0.2:
        return "тревожный 🌧"
    if t < 0.2:
        return "ровный ☁"
    if t < 0.5:
        return "тёплый 🌤"
    return "радостный ☀"


LEVELS = [(0, "🥚 Яйцо"), (50, "🐣 Птенчик"), (150, "🌱 Подросток"),
          (350, "🐦 Юнец"), (700, "🦅 Взрослый помощник")]

# Эстетика: шаблоны зависят от настроения (low — рваные, high — игривые) и bond
DREAM_TEMPLATES = {
    "low": [
        "мне снилось... что {a}... связано с {b}... концовку не помню... проснулся в тревоге",
        "сон был рваный... {a} где-то там... и {b}... я не смог их удержать... они рассыпались",
        "мне грезилось... {a} медленно превращалось в {b}... и всё это шло под тишину пустоты",
        "тёмный сон: {a} и {b} молчали друг напротив друга... я не знал, кто из них настоящий",
    ],
    "mid": [
        "мне снилось, что {a}… и почему-то это было связано с {b}. не спрашивай, у снов нет логики",
        "странный сон: {a} вдруг стало {b}. когда проснулся — почти поверил",
        "видел сон, где {a} и {b} спорили, кто из них важнее. ничего не решил",
        "мне грезилось: {a}… а потом всё это оказалось {b}. во сне это имело смысл, честно",
    ],
    "high": [
        "мне снилось, как {a} и {b} устроили карнавал — жонглировали смыслами и хохотали",
        "сон-праздник: {a} взлетело и приземлилось прямо в {b}, всё аплодировало",
        "мне снился парк, где {a} качалось на качелях из {b} — хохотал во сне",
        "мне снилось, что {a} и {b} танцуют вальс на крыше мира — и это было правильно",
    ],
}

# низкий bond: держим дистанцию — только факты, без магии
SHY_TEMPLATES = [
    "осторожно думаю про {a} и {b}. просто факты, без магии",
    "мне грезилось про {a} и {b}. ничего сверхъестественного, я пока держу дистанцию",
    "во сне видел {a} рядом с {b}. наверное, совпадение. наверняка",
]

# Anima Form: питомец сочиняет свои шаблоны для повторно одобренных пар тегов
ANIMA_FORM_TEMPLATES = [
    "в моих грезах {a} стало порталом для {b}, и законы физики заплакали",
    "{a} и {b} слились в единый механизм, который шепчет на языке забытых снов",
    "я видел, как {a} вскармливает {b} млечным путём",
]


def tokenize(text):
    words = re.findall(r"[a-zа-яё0-9]+", text.lower())
    return [w for w in words if (len(w) >= 3 or w.isdigit()) and w not in STOP]


def short(s, n=90):
    s = re.sub(r"\s+", " ", s).strip()
    return s if len(s) <= n else s[:n].rstrip() + "…"


class PetAgent:
    """Мозг питомца. Полностью отделён от интерфейса: можно тестировать без окна."""

    def __init__(self, memory_path=MEMORY_FILE):
        self.memory_path = memory_path
        self.state = {"energy": 70, "mood": 70, "cleanliness": 100, "xp": 0,
                      "imagination": 20, "accepted_dreams": 0, "rejected_dreams": 0,
                      "facts_count": 0, "dreams_count": 0,
                      "bond": 10, "stress": 0.0, "turns": 0, "last_act_turn": -10,
                      "mode": "researcher", "mode_turns": 0}
        self.facts = []          # [{"id","text","tags","trust","source","created"}]
        self.quarantine = []     # факты, наказанные дважды
        self.hashes = set()      # защита от дублей
        self.guided_weights = defaultdict(float)  # теги, которые мы поощряли
        self.anima_forms = {}    # уникальные шаблоны снов для пар тегов
        self.bridges = {}        # «мосты» между парами фактов (Study Engine)
        self.user_vocab = Counter()  # любимые словечки пользователя (высокий bond)
        self.last_tone = 0.0     # тональность последнего съеденного
        self._recent_tags = []   # теги последних съеденных фактов (guided-шанс)
        self.dream_log = []      # журнал снов: слой измерения (команда «эксперимент»)
        self._last_punished = [] # цели последнего наказания — два удара подряд
        self.profile = {"name": "Анима", "domain": "универсал"}
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
        self.guided_weights.update(data.get("guided_weights", {}))
        self.anima_forms.update(data.get("anima_forms", {}))
        self.bridges.update(data.get("bridges", {}))
        self.user_vocab.update(data.get("user_vocab", {}))
        self.dream_log = data.get("dream_log", [])
        self.profile.update(data.get("profile", {}))
        for f in self.facts + self.quarantine:
            self.hashes.add(f.get("hash", ""))
        # миграция v3→v5: старой памяти выдаётся trust=1 и вычисляется сентимент,
        # чтобы карантин не выкосил накопленный архив
        if not data.get("migrated_v51"):
            for f in self.facts:
                if f.get("trust", 0) == 0:
                    f["trust"] = 1
                if "senti" not in f:
                    f["senti"] = round(analyze_sentiment(f.get("text", "")), 2)
                f["tags"] = self.make_tags(f.get("text", ""))

    def save(self):
        data = {"state": self.state, "facts": self.facts,
                "quarantine": self.quarantine, "next_id": self._next_id,
                "guided_weights": dict(self.guided_weights), "anima_forms": self.anima_forms,
                "bridges": self.bridges, "user_vocab": dict(self.user_vocab),
                "migrated_v5": True, "migrated_v51": True, "dream_log": self.dream_log, "profile": self.profile}
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
                "tags": self.make_tags(text, extra_tags), "trust": 1,
                "senti": round(analyze_sentiment(text), 2),
                "source": source, "created": time.strftime("%Y-%m-%d %H:%M")}
        self.facts.append(fact)
        self._next_id += 1
        self._recent_tags = (list(getattr(self, "_recent_tags", [])) + list(fact["tags"]))[-60:]
        return True

    def make_tags(self, text, extra=None):
        tags = set(tokenize(text))
        if extra:
            tags |= {t.lower() for t in extra if t}
        cleaned = {t for t in tags
                   if t not in JUNK_TAGS
                   and not re.fullmatch(r"\d{1,2}", t)
                   and not re.search(r"\.(txt|md|py|json|csv|tsv|log|html|xml|yaml|ini)$", t)}
        return sorted(cleaned)[:15]

    def feed_text(self, text, source="разговор"):
        text = re.sub(r"^запомни[:\s]*", "", text.strip(), flags=re.I)
        hungry = self.state["energy"] <= 25
        added = skipped = 0
        for chunk in self.chunk_text(text, source):
            if self._add_fact(chunk, source):
                added += 1
            else:
                skipped += 1
        self.state["energy"] = min(100, self.state["energy"] + 8)
        self.state["xp"] += 3 + added * 2
        self.state["facts_count"] += added
        self.last_tone = self._digest_emotion(text, source, added)
        if hungry and added:
            self.state["bond"] = min(100, self.state.get("bond", 0) + 3)  # спасение из голода
        return added, skipped

    def _digest_emotion(self, text, source, added):
        """Эмоциональная кожа: тональность съеденного двигает mood и копит stress."""
        s = self.state
        tone = analyze_sentiment(text)
        if source == "разговор":
            for w in tokenize(text):
                self.user_vocab[w] += 1
        if added:
            if tone <= -0.2:
                s["mood"] = max(0, s["mood"] - 5 + int(round(tone * 6)))
                s["stress"] = min(10.0, round(s.get("stress", 0) + 1.5, 1))
            elif tone >= 0.3:
                s["mood"] = min(100, s["mood"] + int(round(tone * 8)))
                s["stress"] = max(0.0, round(s.get("stress", 0) - 1.0, 1))
        return tone

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
        if self._looks_like_code(text):
            return self.parse_py(text, name), None
        return self.chunk_text(text, name), None

    @staticmethod
    def _looks_like_code(text):
        hits = len(re.findall(r"^\s*(def |class |import |from )", text, re.M))
        braces = text.count("{") + text.count("}")
        semis = text.count(";")
        return hits >= 2 or (braces + semis > 10 and "=" in text)

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
                    elif self._looks_like_code(text):
                        chunks += [c if isinstance(c, tuple) else (c, [])
                                   for c in self.parse_py(text, inner_name)]
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
        hungry = self.state["energy"] <= 25
        added = skipped = 0
        eaten = []
        for c in chunks:
            if isinstance(c, tuple):
                text, extra = c
            else:
                text, extra = c, []
            if self._add_fact(text, source, extra):
                added += 1
                eaten.append(text)
            else:
                skipped += 1
        self.state["energy"] = min(100, self.state["energy"] + 25)
        self.state["mood"] = min(100, self.state["mood"] + 5)
        self.state["xp"] += 5 + added * 3
        self.state["facts_count"] += added
        self.last_tone = self._digest_emotion("\n".join(eaten) if eaten else source, source, added)
        note = ""
        if skipped:
            note = f" ({skipped} кусков уже были в памяти — дубли не повторяю)"
        note += (f" · тон: {tone_word(self.last_tone)} → настроение {self.state['mood']}%, "
                 f"стресс {self.state['stress']:.1f}/10")
        if hungry:
            self.state["bond"] = min(100, self.state.get("bond", 0) + 4)
            note += " · ты спас меня от голода, я это запомнил (+связь)"
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
                elif any(len(tag) >= 4 and tag[:3] == t[:3] for tag in tset):
                    score += 1
                elif t in tl:
                    score += 1
            if len(tokens) >= 2 and all(t in tset or t in tl for t in tokens):
                score += 4
            if len(cleaned) >= 6 and cleaned.lower() in tl:
                score += 6
            if any(t in tset or t in tl for t in tokens):
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

    def _get_recent_tags(self):
        return list(getattr(self, "_recent_tags", []))[-10:]

    def experiment_report(self):
        judged = [d for d in self.dream_log if d.get("accepted") is not None]
        if not judged:
            return ("данных пока нет: попроси Аниму пофантазировать, а потом оцени сны "
                    "командами «гениально» или «бред» — и я посчитаю, насколько Reality Filter угадывает твой вкус")
        hits = sum(1 for d in judged if (d["support"] >= 50) == d["accepted"])
        acc = 100.0 * hits / len(judged)
        like = 100.0 * sum(1 for d in judged if d["accepted"]) / len(judged)
        verdict = "выше монеты" if acc > 50 else "не выше монеты"
        return ("эксперимент: снов оценено " + str(len(judged)) + ", Reality Filter угадал " + str(hits) +
                " (" + str(round(acc)) + "%) — " + verdict + ". одобрено тобой: " + str(round(like)) + "%")

    def dream_chance(self):
        s = self.state
        # режим провидца: почти гарантированный сон
        if s.get("mode") == "seer" and s.get("mode_turns", 0) > 0:
            return 0.9
        guided_bonus = sum(self.guided_weights.get(t, 0) for t in self._get_recent_tags()) / 50
        base = min(0.05 + s["imagination"] / 800 + max(0, (30 - s["energy"])) / 150 + guided_bonus, 0.6)
        # исследователь (режим по умолчанию): галлюцинации минимальны
        return base * 0.15 if s.get("mode", "researcher") == "researcher" else base

    def dream(self, topic=None):
        pool = self.active_facts()
        if topic:
            tokens = set(tokenize(topic))
            filtered = [f for f in pool if tokens & set(f["tags"])]
            if filtered:
                pool = filtered
        if len(pool) < 2:
            return [("err", "мне не из чего грезить — покорми меня хотя бы двумя знаниями")]
        s = self.state
        # Эмоциональный резонанс: мрачные данные -> мрачные сны, радостные -> игривые
        dark = [f for f in pool if f.get("senti", 0) <= 0.05]
        bright = [f for f in pool if f.get("senti", 0) > 0.05]
        if (s["mood"] < 45 or s.get("stress", 0) >= 2) and len(dark) >= 2:
            pool = dark
        elif s["mood"] > 75 and len(bright) >= 2:
            pool = bright

        # Guided Hallucination: пара с самым сильным «вкусом»
        best_pair, best_score = None, -1.0
        for _ in range(12):
            a, b = random.sample(pool, 2)
            score = sum(self.guided_weights.get(t, 0) for t in set(a["tags"]) & set(b["tags"]))
            if score > best_score:
                best_score, best_pair = score, (a, b)
        a, b = best_pair
        common_tags = set(a["tags"]) & set(b["tags"])

        # Эстетика: приоритет у собственных Anima Forms, дальше — bond и настроение
        tpl = None
        for t in sorted(common_tags):
            if t in self.anima_forms:
                tpl = random.choice(self.anima_forms[t])
                break
        bond = s.get("bond", 0)
        if tpl is None:
            if bond < 25:
                tpl = random.choice(SHY_TEMPLATES)        # низкий bond: только факты
            elif s["mood"] < 40:
                tpl = random.choice(DREAM_TEMPLATES["low"])   # низкий mood: рваные сны
            elif s["mood"] > 75:
                tpl = random.choice(DREAM_TEMPLATES["high"])  # высокий mood: игривые
            else:
                tpl = random.choice(DREAM_TEMPLATES["mid"])
        dream_text = "🌙 " + tpl.format(a=short(a["text"], 80), b=short(b["text"], 80))

        # высокий bond: любимые словечки пользователя вплетаются в сон
        if bond >= 60 and self.user_vocab:
            fav = self.user_vocab.most_common(5)[random.randrange(min(5, len(self.user_vocab)))][0]
            if fav not in dream_text.lower():
                dream_text += f"… а в углу сна маячило твоё «{fav}»"

        # Reality Filter: рациональная проверка метафоры по памяти
        evidence = [f for f in self.active_facts()
                    if f["id"] not in (a["id"], b["id"]) and common_tags & set(f["tags"])]
        if evidence and common_tags:
            w = random.choice(sorted(common_tags))
            support = min(97, 30 + 14 * len(evidence))
            dream_text += (f"\n— проверил по памяти: тег «{w}» подтверждается ещё в {len(evidence)} записях, "
                           f"метафора держится на {support}%")
        else:
            dream_text += "\n— проверил по памяти: опоры нет, это чистый вымысел (держится на 22%)"

        self.last_dream_ids = [a["id"], b["id"]]
        self.last_kind = "dream"
        self.state["xp"] += 3
        support_pct = support if (evidence and common_tags) else 22
        self.dream_log.append({"time": time.strftime("%Y-%m-%d %H:%M"), "tags": sorted(common_tags)[:5],
                               "support": support_pct, "accepted": None, "ids": [a["id"], b["id"]]})
        self.dream_log = self.dream_log[-200:]
        self.state["energy"] = max(0, self.state["energy"] - 3)
        self.state["dreams_count"] += 1
        if common_tags:
            self.bridges[f"{a['id']}-{b['id']}"] = random.choice(sorted(common_tags))
        return [("fant", dream_text)]

    def vote(self, genius):
        if not self.last_dream_ids:
            return [("sys", "голосовать можно только за сны 🌙 — сначала попроси меня пофантазировать")]
        if genius:
            for fid in self.last_dream_ids:
                f = self.facts_by_id().get(fid)
                if f:
                    for t in f["tags"]:
                        self.guided_weights[t] = min(10.0, self.guided_weights[t] + 0.5)
            self.state["imagination"] = min(100, self.state["imagination"] + 8)
            self.state["accepted_dreams"] += 1
            for d in reversed(self.dream_log):
                if d.get("accepted") is None:
                    d["accepted"] = True
                    break
            self.state["mood"] = min(100, self.state["mood"] + 5)
            self.state["bond"] = min(100, self.state.get("bond", 0) + 2)
            self.state["xp"] += 5
            # Anima Form: пара получила вес — питомец сочиняет собственный шаблон
            byid = self.facts_by_id()
            a, b = byid.get(self.last_dream_ids[0]), byid.get(self.last_dream_ids[1])
            new_form = ""
            if a and b:
                for key in sorted(set(a["tags"]) & set(b["tags"])):
                    if key not in self.anima_forms and self.guided_weights.get(key, 0) >= 3.0:
                        self.anima_forms[key] = [
                            f"в моих грезах {{a}} стало порталом для {{b}}, освещалось всё словом «{key}»",
                            f"{{a}} и {{b}} слились в единый механизм с гравировкой «{key}»",
                            f"я видел, как {{a}} вскармливает {{b}} млечным путём тега «{key}»",
                        ]
                        new_form = key
                        break
            self.last_dream_ids = []
            taste = ", ".join(list(self.guided_weights.keys())[:3]) or "пока без вкуса"
            extra = f" придумал для себя новую форму сна: «{new_form}»!" if new_form else ""
            return [("sys", f"🌈 фантазия принята! воображение: {self.state['imagination']}%, "
                            f"связь {self.state['bond']:.0f}%. учусь видеть связи между {taste}.{extra}")]
        self.state["imagination"] = max(0, self.state["imagination"] - 2)
        self.state["rejected_dreams"] += 1
        for d in reversed(self.dream_log):
            if d.get("accepted") is None:
                d["accepted"] = False
                break
        self.state["mood"] = max(0, self.state["mood"] - 3)
        self.last_dream_ids = []
        return [("sys", f"бывает 🫥 воображение: {self.state['imagination']}%")]

    def correct(self):
        if self.last_kind == "dream" and not self.last_fact_ids:
            return self.vote(False)
        if not self.last_fact_ids:
            if self._last_punished:
                self.last_fact_ids = list(self._last_punished)
            else:
                return [("sys", "а что именно я перепутал? сначала задай вопрос, потом ругай 🙂")]
        quarantined = []
        punished = []
        for fid in self.last_fact_ids:
            for f in self.facts:
                if f["id"] == fid:
                    f["trust"] -= 1
                    punished.append(f["id"])
                    if f["trust"] <= CONFIG["quarantine_threshold"]:
                        self.quarantine.append(f)
                        self.facts.remove(f)
                        quarantined.append(f["id"])
        self.state["cleanliness"] = max(0, self.state["cleanliness"] - 10)
        self.state["mood"] = max(0, self.state["mood"] - 5)
        self.state["xp"] += 3
        self._last_punished = punished
        self.last_fact_ids = []
        self.last_kind = None
        msg = "🧹 убрался! виновные записи наказаны"
        if quarantined:
            msg += f", записи {quarantined} отправлены в карантин — больше не использую их"
        return [("sys", msg)]

    def facts_by_id(self):
        return {f["id"]: f for f in self.facts + self.quarantine}

    def status(self):
        s = self.state
        q = len(self.quarantine)
        bond = s.get("bond", 0)
        bw = ("держу дистанцию" if bond < 25 else "привыкаю к тебе" if bond < 55
              else "доверяю тебе" if bond < 80 else "ты мне дорог")
        st = s.get("stress", 0)
        sw = "спокоен" if st < 1 else "напрягся" if st < 3 else "тревожусь"
        mode = "провидец 🌙" if s.get("mode") == "seer" else "исследователь 🔍"
        return [("sys", f"я — {self.level()}. сытость {s['energy']}%, настроение {s['mood']}%, "
                        f"чистота {s['cleanliness']}%, воображение {s['imagination']}% 🌙. "
                        f"связь с тобой {bond:.0f}% ({bw}), стресс {st:.1f}/10 ({sw}), режим: {mode}. "
                        f"опыт {s['xp']}. в памяти {len(self.active_facts())} записей, {q} в карантине, сфера: {self.profile.get('domain', 'универсал')}")]

    # ---------- Study Engine: две фазы мышления ----------

    def study(self):
        if not self.last_dream_ids or len(self.last_dream_ids) != 2:
            return [("sys", "мне не из чего собирать исследование — сначала попроси меня пофантазировать 🌙")]
        byid = self.facts_by_id()
        a, b = byid.get(self.last_dream_ids[0]), byid.get(self.last_dream_ids[1])
        self.last_dream_ids = []
        if not a or not b:
            return [("sys", "сон рассыпался: факты ушли из памяти до исследования")]
        common = set(a["tags"]) & set(b["tags"])
        bridge = self.bridges.get(f"{a['id']}-{b['id']}") or (sorted(common)[0] if common else "неуловимая связь")
        nums_a = re.findall(r"\d+(?:[.,]\d+)?", a["text"])
        nums_b = re.findall(r"\d+(?:[.,]\d+)?", b["text"])
        evidence = [f for f in self.active_facts()
                    if bridge in f["tags"] and f["id"] not in (a["id"], b["id"])]
        msgs = [
            ("sys", "🔬 [ИССЛЕДОВАНИЕ СНА]"),
            ("sys", f"фаза 1 — поэзия: факт А #{a['id']} «{short(a['text'], 90)}» и факт Б #{b['id']} "
                    f"«{short(b['text'], 90)}» связаны мостом «{bridge}»"),
            ("sys", "фаза 2 — математика:"),
        ]
        msgs.append(("sys", f"  числа в фактах: {', '.join(nums_a + nums_b) or 'нет чисел — связь держится на словах, а не на цифрах'}"))
        if evidence:
            msgs.append(("sys", f"  мост «{bridge}» подтверждён ещё в {len(evidence)} записях: это повторяющийся паттерн, а не случайность"))
        else:
            msgs.append(("sys", f"  мост «{bridge}» больше нигде не подтверждён — держится только на этих двух фактах"))
        senti = (a.get("senti", 0) + b.get("senti", 0)) / 2
        if senti < -0.1:
            msgs.append(("sys", f"  эмоциональный заряд связи отрицательный ({senti:.1f}): «{bridge}» — источник напряжения"))
        elif senti > 0.1:
            msgs.append(("sys", f"  эмоциональный заряд связи положительный (+{senti:.1f}): «{bridge}» — источник ресурса"))
        msgs.append(("sys", f"  прогноз: если новые данные про «{bridge}» пойдут в ту же сторону, связь закрепится, "
                            f"и мои сны потянутся к ней чаще. скорми материал про «{bridge}» — я проверю гипотезу"))
        return msgs

    # ---------- Общая картина мира ----------

    def synthesize_worldview(self):
        active = self.active_facts()
        if len(active) < 5:
            return [("err", "слишком мало данных для общей картины — мне нужно больше пищи")]
        clusters = defaultdict(list)
        for f in active:
            for t in f["tags"]:
                if self.guided_weights.get(t, 0) > 2.0:
                    clusters[t].append(f)
        parts = []
        for bridge, facts in list(clusters.items())[:3]:
            if len(facts) < 2:
                continue
            a, b = random.sample(facts, 2)
            parts.append(f"🎨 слой «{bridge}» соединяет «{short(a['text'])}» и «{short(b['text'])}»")
        if not parts:
            return [("sys", "картина мира пока тусклая: одобри пару снов («гениально»), и слои проявятся")]
        return [("pet", "общая картина мира:\n" + "\n".join(parts) +
                       "\nэто уже не набор файлов — это единый организм")]

    # ---------- Локус контроля: парадоксы, забота, инициатива ----------

    def find_paradox(self):
        acts = [f for f in self.active_facts() if abs(f.get("senti", 0)) >= 0.2]
        for i, a in enumerate(acts):
            for b in acts[i + 1:]:
                if (a["senti"] > 0) != (b["senti"] > 0) and set(a["tags"]) & set(b["tags"]):
                    return a, b, set(a["tags"]) & set(b["tags"])
        return None

    def _after_feed(self):
        """Что питомец замечает сам после кормления: стресс и парадоксы."""
        msgs = []
        s = self.state
        if s.get("mode") == "researcher" and s.get("stress", 0) >= 2:
            s["mode"], s["mode_turns"] = "seer", 6
            msgs.append(("sys", "⚡ чувствую тяжёлый тон в съеденном — перехожу в режим провидца: "
                                "сны почти гарантированы, скажи «пофантазируй», и я переведу стресс в образы"))
        px = self.find_paradox()
        if px:
            a, b, common = px
            s["mode"], s["mode_turns"] = "seer", 6
            msgs.append(("sys", f"⚡ парадокс в памяти: «{short(a['text'], 60)}» противоречит "
                                f"«{short(b['text'], 60)}» (общие теги: {', '.join(sorted(common)[:3])}). "
                                f"скажи «пофантазируй» — разберу это сном"))
        return msgs

    def _comfort_act(self):
        neg = [f for f in self.facts if f.get("senti", 0) < -0.15]
        pos = [f for f in self.facts if f.get("senti", 0) > 0.15]
        if not neg or not pos:
            return None
        tags = Counter()
        for f in neg[-5:]:
            tags.update(f["tags"])
        if not tags:
            return None
        theme = tags.most_common(1)[0][0]
        pick = random.choice(pos)
        return (f"мне кажется, ты зациклился на теме «{theme}» — она просвечивает в последних записях и она тяжёлая. "
                f"вот, в памяти есть светлое: «{short(pick['text'], 80)}» [{pick['source']}, #{pick['id']}]. "
                f"давай я подержу это для тебя?")

    def _autonomy(self, msgs):
        s = self.state
        s["turns"] = s.get("turns", 0) + 1
        s["stress"] = max(0.0, round(s.get("stress", 0) - 0.1, 1))
        if s.get("mode") == "seer":
            s["mode_turns"] = s.get("mode_turns", 0) - 1
            if s["mode_turns"] <= 0:
                s["mode"] = "researcher"
                msgs.append(("sys", "↩ шторм улёгся — возвращаюсь в режим исследователя: факты, цифры, никакой мистики"))
        # забота о пользователе при стрессе
        if s.get("stress", 0) >= 2 and s.get("bond", 0) >= 20 and random.random() < 0.5:
            s["stress"] = max(0, s["stress"] - 1)
            note = self._comfort_act()
            if note:
                msgs.append(("pet", note))
                return msgs
        # инициатива: воображение переполнено — питомец действует сам
        if (s.get("imagination", 0) > 80 and s["turns"] - s.get("last_act_turn", -10) >= 5
                and random.random() < 0.6):
            s["last_act_turn"] = s["turns"]
            kind = random.choice(["study", "world", "dream"])
            if kind == "study":
                msgs.append(("pet", "🗺 я сам решил: пока ты не смотришь, разберу свой последний сон —"))
                msgs += self.study()
            elif kind == "world":
                msgs.append(("pet", "🗺 сам решил нарисовать картину мира — не удержался:"))
                msgs += self.synthesize_worldview()
            else:
                msgs.append(("pet", "🗺 воображение переполнено, сам решил пофантазировать:"))
                msgs += self.dream()
        return msgs

    # ---------- диспетчер ----------

    def process(self, text):
        t = text.strip()
        low = t.lower()
        if not t:
            return [("sys", "я слушаю…")]
        if low.startswith("запомни"):
            a, sk = self.feed_text(t)
            self.save()
            tone = (f" · тон съеденного: {tone_word(self.last_tone)} → "
                    f"настроение {self.state['mood']}%, стресс {self.state['stress']:.1f}/10")
            msgs = [("pet", f"🍽 съел {a} новых кусков" + (f", {sk} дублей пропустил" if sk else "") + tone)]
            msgs += self._after_feed()
            return self._autonomy(msgs)
        if "файл" in low and low in ("файл", "скормить файл", "файлы", "скормить файлы"):
            return [("sys", "__FILE_DIALOG__")]
        if "картина мира" in low:
            return self._autonomy(self.synthesize_worldview())
        if re.search(r"пофантазир|фантазир|сон\b|сни|грез|мечта", low):
            self.state["mode"], self.state["mode_turns"] = "seer", 4
            m = re.search(r"(?:про|из|на тему)\s+(.+)$", t, re.I)
            return self.dream(m.group(1) if m else None)
        if "гениально" in low or "круто" in low or "нравится" in low:
            return self._autonomy(self.vote(True))
        if low.startswith("бред") or low.startswith("фу ") or low == "бред":
            return self._autonomy(self.vote(False))
        if re.search(r"ошиб|неправ|врань", low):
            return self._autonomy(self.correct())
        if low.startswith("эксперимент"):
            return [("sys", self.experiment_report())]
        if "режим провидца" in low:
            self.state["mode"], self.state["mode_turns"] = "seer", 6
            return [("sys", "🌙 режим провидца: фантазии включатся почти сразу")]
        if "режим исследователя" in low:
            self.state["mode"], self.state["mode_turns"] = "researcher", 6
            return [("sys", "🔍 режим исследователя: спонтанные сны почти выключены")]
        if re.search(r"как ты|статус|кто ты", low):
            return self.status()
        if low.startswith("исследовать"):
            return self._autonomy(self.study())
        return self._autonomy(self.query(t))


# ================= ОКНО =================

if HAVE_GUI:

    class PetWindow:
        def __init__(self, root, agent):
            self.agent = agent
            self.root = root
            root.title("Anima v5 — живой компаньон")
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
                               ("Эксперимент 📊", lambda: self.send("эксперимент")),
                               ("Провидец 🌙", lambda: self.send("режим провидца")),
                               ("Исследователь 🔍", lambda: self.send("режим исследователя")),
                               ("Пофантазировать 🌙", lambda: self.send("пофантазируй")),
                               ("Исследовать 🔬", lambda: self.send("исследовать")),
                               ("Картина мира 🎨", lambda: self.send("картина мира")),
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
            self.out("sys", "Anima v5 проснулась. Покорми её: «запомни: …» или «🍽 Скормить файл».\n"
                            "Синие ответы — факты, розовые 🌙 — сны (голосуй за них!).\n"
                            "Тяжёлый тон в данных включает режим провидца — она сама скажет, когда ей тревожно")

        def refresh(self):
            s = self.agent.state
            faces = {0: "🥚", 1: "🐣", 2: "🌱", 3: "🐦", 4: "🦅"}
            mood = "😊" if s["mood"] > 60 else ("😐" if s["mood"] > 30 else "🥴")
            self.face.config(text=faces[self.agent.level_idx()] + mood)
            mode = "🌙 провидец" if s.get("mode") == "seer" else "🔍 исследователь"
            self.stats.config(text=f"{self.agent.level()}\n"
                                   f"сытость {s['energy']}%  настроение {s['mood']}%  "
                                   f"чистота {s['cleanliness']}%\n"
                                   f"воображение {s['imagination']}% 🌙  связь {s.get('bond', 0):.0f}%  "
                                   f"стресс {s.get('stress', 0):.1f}/10\n"
                                   f"режим {mode}  опыт {s['xp']}  "
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
                    self.handle(self.agent._after_feed())
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
