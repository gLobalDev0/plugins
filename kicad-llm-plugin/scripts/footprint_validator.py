# -*- coding: utf-8 -*-
"""CLI: footprint kütüphane varlığını doğrular. Örn:
  python3 scripts/footprint_validator.py Resistor_SMD:R_0805_2012Metric
"""

import os
import sys

KICAD_FP_ROOT = "/usr/share/kicad/footprints"


def _pretty_folder(lib_nick):
    nick = lib_nick.strip()
    if nick.endswith(".pretty"):
        return nick
    if ":" in nick:
        nick = nick.split(":", 1)[0]
    return nick + ".pretty"


def parse_fp(s):
    s = (s or "").strip()
    if ":" in s:
        lib, name = s.split(":", 1)
        return lib.strip(), name.strip()
    if "/" in s:
        lib, name = s.rsplit("/", 1)
        return _pretty_folder(lib), name.replace(".kicad_mod", "").strip()
    return None, None


def check_one(lib_nick, fp_name):
    folder = _pretty_folder(lib_nick)
    path = os.path.join(KICAD_FP_ROOT, folder)
    if not os.path.isdir(path):
        return False, "Kütüphane yok: %s" % path
    try:
        import pcbnew

        fp = pcbnew.FootprintLoad(path, fp_name)
        if fp is None:
            return False, "Footprint yüklenemedi: %s:%s" % (lib_nick, fp_name)
        return True, "OK %s:%s" % (lib_nick, fp_name)
    except ImportError:
        mod_path = os.path.join(path, fp_name + ".kicad_mod")
        if os.path.isfile(mod_path):
            return True, "OK (dosya) %s" % mod_path
        return False, "pcbnew yok; modül bulunamadı: %s" % mod_path


def main(argv):
    if len(argv) < 2:
        print("Kullanım: footprint_validator.py Lib:Footprint [...]", file=sys.stderr)
        return 2
    failed = 0
    for raw in argv[1:]:
        lib, name = parse_fp(raw)
        if not lib or not name:
            print("GEÇERSİZ:", raw)
            failed += 1
            continue
        ok, msg = check_one(lib, name)
        print(("OK " if ok else "HATA ") + msg)
        if not ok:
            failed += 1
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
