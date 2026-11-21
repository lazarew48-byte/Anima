#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""llm_bridge.py — мост Анима <-> YandexGPT (v2: поддержка истории диалога)."""

import os
import json
import urllib.request

_ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
_env_cache = {}
_env_mtime = None


def _read_env():
    global _env_cache, _env_mtime
    try:
        mtime = os.path.getmtime(_ENV_PATH)
    except OSError:
        _env_cache = {}
        return {}
    if mtime == _env_mtime and _env_cache:
        return _env_cache
    cfg = {}
    try:
        with open(_ENV_PATH, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                cfg[k.strip()] = v.strip()
    except OSError:
        pass
    for k in ("YANDEX_API_KEY", "YANDEX_CATALOG_ID"):
        if os.environ.get(k):
            cfg[k] = os.environ[k]
    _env_cache, _env_mtime = cfg, mtime
    return cfg


def is_configured():
    cfg = _read_env()
    return bool(cfg.get("YANDEX_API_KEY") and cfg.get("YANDEX_CATALOG_ID"))


def brain_status():
    if not is_configured():
        return "эвристики (LLM не настроена)"
    return "LLM (YandexGPT)"


_API_URL = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
_TIMEOUT = 30


def _build_system(facts, mode, pet_name):
    ctx_lines = []
    for f in (facts or [])[:12]:
        txt = (f.get("text") or "").strip().replace("\n", " ")
        if len(txt) > 300:
            txt = txt[:300] + "…"
        ctx_lines.append("— " + txt)
    context = "\n".join(ctx_lines) if ctx_lines else "(память пуста по этому вопросу)"

    if mode == "seer":
        system = (
            "Ты — живой питомец-компаньон по имени %s. Режим провидца: фантазировать "
            "разрешено, стиль тёплый и игривый, 2–5 предложений. Память пользователя — "
            "источник вдохновения." % (pet_name or "Анима")
        )
    else:
        system = (
            "Ты — питомец-компаньон по имени %s. Отвечай ТОЛЬКО по фактам из памяти "
            "пользователя ниже. НИКАКИХ фактов, которых нет в памяти. Если ответа нет — "
            "честно скажи. Кратко, от лица питомца.\n\nПАМЯТЬ:\n%s"
            % (pet_name or "Анима", context)
        )
    return system


def ask(question, facts, mode="normal", pet_name=None, history=None):
    """history — [{'role': 'user'|'assistant', 'text': '...'}]. None при любой ошибке."""
    if not is_configured():
        return None
    cfg = _read_env()
    temperature = 0.8 if mode == "seer" else 0.3
    max_tokens = 300 if mode == "seer" else 400

    messages = [{"role": "system", "text": _build_system(facts, mode, pet_name)}]
    for m in (history or [])[-8:]:
        if isinstance(m, dict):
            role = m.get("role", "user")
            text = str(m.get("text", ""))
        elif isinstance(m, (tuple, list)) and len(m) >= 2:
            who, text = m[0], str(m[1])
            # "pet"/"assistant"/"bot" — реплики питомца, всё остальное — человек
            role = "assistant" if who in ("pet", "assistant", "bot") else "user"
        else:
            continue
        if not text.strip():
            continue
        messages.append({"role": role, "text": text[:600]})

    messages.append({"role": "user", "text": question})


    body = {
        "modelUri": "gpt://%s/yandexgpt-lite" % cfg["YANDEX_CATALOG_ID"],
        "completionOptions": {"temperature": temperature, "maxTokens": max_tokens},
        "messages": messages,
    }
    req = urllib.request.Request(
        _API_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": "Api-Key " + cfg["YANDEX_API_KEY"],
                 "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        text = data["result"]["alternatives"][0]["message"]["text"].strip()
        return text or None
    except Exception:
        return None
