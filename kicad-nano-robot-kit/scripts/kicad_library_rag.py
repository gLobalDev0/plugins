# -*- coding: utf-8 -*-
"""KiCad 8 yerel footprint RAG — pad ve courtyard özeti."""

import json
import os
import re
import sys

KICAD_FP_ROOT = "/usr/share/kicad/footprints"


def _pretty(lib_nick):
    n = lib_nick.strip()
    if n.endswith(".pretty"):
        return n
    return n + ".pretty"


def parse_fp(s):
    s = (s or "").strip()
    if ":" in s:
        lib, name = s.split(":", 1)
        return lib.strip(), name.strip()
    return None, None


def _read_mod(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def _extract_pads(text):
    pads = []
    for m in re.finditer(
        r'\(pad\s+"([^"]+)"\s+([^\s]+)\s+\(at\s+([-\d.]+)\s+([-\d.]+)',
        text,
    ):
        pads.append(
            {
                "number": m.group(1),
                "type": m.group(2),
                "x_mm": float(m.group(3)),
                "y_mm": float(m.group(4)),
            }
        )
    return pads


def _extract_bounds(text):
    xs, ys = [], []
    for m in re.finditer(
        r'\(fp_(?:line|rect|circle|arc)[\s\S]*?\(start\s+([-\d.]+)\s+([-\d.]+)\)',
        text,
    ):
        xs.append(float(m.group(1)))
        ys.append(float(m.group(2)))
    for m in re.finditer(
        r'\(end\s+([-\d.]+)\s+([-\d.]+)\)',
        text,
    ):
        xs.append(float(m.group(1)))
        ys.append(float(m.group(2)))
    if not xs:
        return None
    return {
        "min_x_mm": min(xs),
        "max_x_mm": max(xs),
        "min_y_mm": min(ys),
        "max_y_mm": max(ys),
        "width_mm": round(max(xs) - min(xs), 2),
        "height_mm": round(max(ys) - min(ys), 2),
    }


def lookup(lib_nick, fp_name):
    folder = os.path.join(KICAD_FP_ROOT, _pretty(lib_nick))
    mod_path = os.path.join(folder, fp_name + ".kicad_mod")
    if not os.path.isfile(mod_path):
        return {"ok": False, "error": "Dosya yok: %s" % mod_path}
    text = _read_mod(mod_path)
    return {
        "ok": True,
        "lib": lib_nick,
        "footprint": fp_name,
        "path": mod_path,
        "bounds": _extract_bounds(text),
        "pads": _extract_pads(text),
        "pad_count": len(_extract_pads(text)),
    }


def main(argv):
    if len(argv) < 2:
        print("Kullanım: kicad_library_rag.py Lib:Footprint [...]", file=sys.stderr)
        return 2
    out = []
    for raw in argv[1:]:
        lib, name = parse_fp(raw)
        if not lib:
            out.append({"raw": raw, "ok": False, "error": "Geçersiz format"})
            continue
        out.append(lookup(lib, name))
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
