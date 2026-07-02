# -*- coding: utf-8 -*-
"""Asistan yanıtından uygulanabilir PCB tasarım JSON'u çıkarma ve doğrulama."""

import json
import re

SCHEMA_VERSION = 1

# Kullanıcı onayı — JSON üretimini tetikler
_APPROVAL_RE = re.compile(
    r"(?i)^\s*("
    r"onayl[ıi]yorum|onaylad[ıi]m|onayla|"
    r"uygula|tamam[,.]?\s*çiz|çiz(?:elim|sin)?|"
    r"haz[ıi]r(?:ım)?|json\s*üret|başla|"
    r"devam\s*et|kart[ıa]\s*çiz"
    r")\s*[.!]?$",
)

# Asistan tasarım önerdi (JSON yokken Uygula'yı «hazır» göstermek için)
_PROPOSED_HINTS = (
    "onaylıyorum",
    "uygula düğmes",
    "uygula buton",
    "tasarımı kartta çizmek",
    "özet tasarım",
    "önerilen bileşen",
    "eksik parametre",
    "topoloji",
)


def is_approval_message(text):
    """Kullanıcı metni onay / çiz komutu mu?"""
    if not text:
        return False
    t = text.strip()
    if _APPROVAL_RE.match(t):
        return True
    low = t.lower()
    if len(t) < 80 and any(k in low for k in ("onaylıyorum", "onayladım", "json üret", "kartı çiz")):
        return True
    return False


def assistant_proposed_design(text):
    """Asistan tartışma sonunda tasarım önerdi mi (henüz JSON olmasa bile)?"""
    if not text:
        return False
    low = text.lower()
    if extract_json_block(text):
        return True
    hits = sum(1 for h in _PROPOSED_HINTS if h in low)
    return hits >= 2


def extract_json_block(text):
    """Metinden ilk geçerli tasarım JSON nesnesini döndürür veya None."""
    if not text:
        return None
    for pat in (
        r"```json\s*(\{.*?\})\s*```",
        r"```\s*(\{.*?\})\s*```",
    ):
        m = re.search(pat, text, re.DOTALL | re.IGNORECASE)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                continue
    start = text.find('{"schema_version"')
    if start < 0:
        start = text.find("{")
    if start < 0:
        return None
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                chunk = text[start : i + 1]
                try:
                    obj = json.loads(chunk)
                    if isinstance(obj, dict) and obj.get("schema_version") is not None:
                        return obj
                except json.JSONDecodeError:
                    return None
    return None


def validate_spec(spec):
    errs = []
    if not isinstance(spec, dict):
        return None, ["Tasarım verisi bir JSON nesnesi olmalı."]
    if spec.get("schema_version") != SCHEMA_VERSION:
        errs.append(
            "schema_version %s bekleniyor (bulunan: %s)."
            % (SCHEMA_VERSION, spec.get("schema_version"))
        )
    board = spec.get("board_mm")
    if not isinstance(board, dict):
        errs.append("board_mm {width, height} zorunlu.")
    else:
        for k in ("width", "height"):
            try:
                float(board[k])
            except (TypeError, ValueError, KeyError):
                errs.append("board_mm.%s sayı olmalı." % k)
    try:
        n = int(spec.get("copper_layers", 2))
        if n not in (1, 2, 4, 6):
            errs.append("copper_layers 1, 2, 4 veya 6 olmalı.")
    except (TypeError, ValueError):
        errs.append("copper_layers tam sayı olmalı.")
    if not isinstance(spec.get("components"), list):
        errs.append("components bir dizi olmalı.")
    for key in ("tracks", "vias", "zones"):
        if key in spec and not isinstance(spec[key], list):
            errs.append("%s bir dizi olmalı." % key)
    if errs:
        return None, errs
    return spec, []


def parse_from_assistant(text):
    raw = extract_json_block(text)
    if raw is None:
        return None, [
            "Uygulanabilir JSON yok. Önce sohbette tasarımı netleştirin, "
            "sonra «Onaylıyorum» yazın veya Uygula ile JSON isteyin."
        ]
    return validate_spec(raw)
