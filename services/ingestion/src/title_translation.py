"""Offline machine translation of job titles through a local llama.cpp server.

Owner decision 2026-10-02: titles of vacancies without a human review are
translated automatically by a free, open-weight model that runs on the CI
runner's CPU (llama.cpp server, no external translation service, nothing at
site runtime). A translation is kept only if it passes the checks below; a
title that fails them is not published rather than published wrongly.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.request
from typing import Callable

LOCALES = ("zh-CN", "en", "cs")
ENGINE_VERSION = "llama.cpp-b11347/qwen3-8b-q4km/titles-v1"
DEFAULT_SERVER = "http://127.0.0.1:8080"

SYSTEM_PROMPT = """You translate job titles of Czech universities for a public job board.
Return only JSON: {"en": "...", "cs": "...", "zh-CN": "..."}.
Rules:
- Translate the title faithfully. Never add facts, departments, levels or genders that the title does not state.
- Keep numbers exactly as written (e.g. "úvazek 1,0" -> "1.0 FTE" / "1.0 工作量"; codes such as 560 or "I" stay).
- The title in its own source language stays exactly as given.
- Use standard academic terms:
  odborný asistent / odborná asistentka = Assistant Professor = 助理教授
  asistent / asistentka (academic) = Assistant = 助理
  docent / docentka = Associate Professor = 副教授
  profesor / profesorka = Professor = 教授
  vědecký pracovník / výzkumný pracovník = Researcher = 研究员
  postdoc / postdoktorand = Postdoctoral Researcher = 博士后
  doktorand / Ph.D. student / doktorské studium = PhD student = 博士研究生
  vedoucí katedry = Head of Department = 系主任
  lektor = Lecturer = 讲师
  laborant = Laboratory Technician = 实验室技术员
  fyzická geografie = physical geography = 自然地理
- Czech output uses natural Czech academic job-title wording and translates English terms into Czech:
  Assistant Professor = Odborný asistent / odborná asistentka (never "Asistent profesor")
  Associate Professor = Docent / docentka; Researcher = Výzkumný pracovník / výzkumná pracovnice
  Postdoc / Postdoctoral Researcher = Postdoktorand / postdoktorandka; PhD position = Doktorská pozice
  Engineer = Inženýr / inženýrka; Developer = Vývojář / vývojářka"""

_CJK = re.compile(r"[一-鿿]")
_CZECH_LETTERS = re.compile(r"[áčďéěíňóřšťúůýž]", re.I)
_CZECH_WORDS = re.compile(
    r"\b(?:odborn|asistent|pracovn|výzkum|vyzkum|vědeck|vedeck|katedr|ústav|ustav|fakult|vedoucí|docent|"
    r"doktorsk|laborant|lektor|oboru|pozice|referent)\w*",
    re.I,
)


def title_language(title: str) -> str:
    """The title's own language: Czech when it carries Czech letters or terms."""
    return "cs" if _CZECH_LETTERS.search(title) or _CZECH_WORDS.search(title) else "en"


def cache_key(title: str) -> str:
    raw = f"{ENGINE_VERSION}\n{title.strip()}"
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _numbers(text: str) -> list[str]:
    """Digit groups, with a decimal comma read as a point ("1,0" == "1.0")."""
    return sorted(re.sub(r",", ".", value) for value in re.findall(r"\d+(?:[.,]\d+)?", text))


def validate(title: str, language: str, result: dict) -> list[str]:
    """Reasons a machine translation must not be published; empty when it may."""
    problems: list[str] = []
    for locale in LOCALES:
        value = result.get(locale)
        if not isinstance(value, str) or not value.strip():
            problems.append(f"{locale}-missing")
            continue
        if len(value) > max(3 * len(title), 40) or len(value) < max(2, len(title) // 6):
            problems.append(f"{locale}-length")
        if locale == "zh-CN" and not _CJK.search(value):
            problems.append("zh-CN-not-chinese")
        if locale != "zh-CN" and _CJK.search(value):
            problems.append(f"{locale}-contains-chinese")
        if _numbers(value) != _numbers(title):
            problems.append(f"{locale}-numbers-changed")
    if language in result and result.get(language) != title:
        problems.append(f"{language}-source-not-verbatim")
    return problems


def llama_translate(title: str, language: str, server: str | None = None) -> dict:
    body = {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps({"sourceLanguage": language, "title": title}, ensure_ascii=False)},
        ],
        "temperature": 0,
        "max_tokens": 256,
        "response_format": {"type": "json_object"},
        "chat_template_kwargs": {"enable_thinking": False},
    }
    request = urllib.request.Request(
        f"{server or os.environ.get('TITLE_TRANSLATION_SERVER', DEFAULT_SERVER)}/v1/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=600) as response:
        payload = json.load(response)
    content = payload["choices"][0]["message"]["content"]
    parsed = json.loads(content)
    return {locale: str(parsed.get(locale) or "").strip() for locale in LOCALES}


def translate_title(
    title: str,
    cache: dict[str, dict],
    translate: Callable[[str, str], dict] = llama_translate,
) -> dict:
    """Cached, validated translation of one title.

    Returns {"titles": {...}, "problems": [...], "language": ...}. The source
    language keeps the official title verbatim whatever the model returned.
    """
    key = cache_key(title)
    if key in cache:
        return cache[key]
    language = title_language(title)
    try:
        result = translate(title, language)
    except Exception as exc:  # noqa: BLE001 - a failed call withholds one title
        entry = {"title": title, "language": language, "titles": {}, "problems": [f"engine-error:{type(exc).__name__}"]}
        return entry
    result[language] = title
    problems = validate(title, language, result)
    entry = {
        "title": title,
        "language": language,
        "engine": ENGINE_VERSION,
        "titles": {locale: result[locale] for locale in LOCALES},
        "problems": problems,
    }
    cache[key] = entry
    return entry
