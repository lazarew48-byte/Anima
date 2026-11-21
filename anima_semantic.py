#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
anima_semantic.py — смысловой поиск для Анимы: TF-IDF по словам, тегам
и символьным 3-граммам. Без внешних зависимостей; нейроэмбеддер — опция.

Самостоятельный режим:
    python anima_semantic.py "запрос" pet_memory.json
Подключение к Anima.py (v5): attach_to(agent) добавляет метод поиска агенту.
"""

import json, math, re, sys
from collections import Counter

STOP = set("""и в во не что он на я с со как а то все она так его но да ты к у же вы за бы по
только её мне было вот от меня ещё нет о из ему теперь когда даже ну вдруг ли если уже или ни
где есть надо для мы тебя их чем был этот потому этого какой совсем здесь этом очень также ещё
для был тем был the this that with from have will been were what when then they them there""".split())


def _ngrams3(text):
    t = text.lower()
    return {"$" + t[i:i+3] for i in range(max(0, len(t) - 2))}


class SemanticIndex:
    def __init__(self, facts):
        self.df = Counter()
        self.tfidf = []
        for f in facts:
            fid, text, tags = f.get("id"), f.get("text", ""), f.get("tags") or []
            words = [w for w in re.findall(r"[a-zа-яё0-9]+", text.lower())
                     if len(w) >= 3 and w not in STOP]
            terms = Counter(words + ["#" + t for t in tags] + list(_ngrams3(text)))
            self.tfidf.append((fid, text, terms))
            for t in terms:
                self.df[t] += 1
        self.N = max(1, len(self.tfidf))

    def search(self, query, k=3):
        qwords = [w for w in re.findall(r"[a-zа-яё0-9]+", query.lower())
                  if len(w) >= 3 and w not in STOP]
        qterms = Counter(qwords + list(_ngrams3(query)))
        scored = []
        for fid, text, terms in self.tfidf:
            score = 0.0
            for t, qc in qterms.items():
                if t in terms:
                    idf = math.log(1 + self.N / (1 + self.df[t]))
                    score += qc * idf * (1.0 if not t.startswith("$") else 0.4)
            if score > 0:
                scored.append((score, fid, text))
        scored.sort(reverse=True)
        return [(fid, text, round(s, 3)) for s, fid, text in scored[:k]]


def load_facts(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f).get("facts", [])


def attach_to(agent):
    """Добавляет агенту метод semantic_find(запрос, k) — ядро не меняется."""
    agent.semantic_find = lambda query, k=3: SemanticIndex(agent.facts).search(query, k)
    return agent


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print('использование: python anima_semantic.py "запрос" [файл_памяти.json]')
        sys.exit(1)
    memfile = sys.argv[2] if len(sys.argv) > 2 else "pet_memory.json"
    hits = SemanticIndex(load_facts(memfile)).search(sys.argv[1])
    if not hits:
        print("Ничего не нашлось в памяти — честный пустой ответ.")
    for fid, text, score in hits:
        print("[%s] (%.2f) %s" % (fid, score, text[:120]))
