# -*- coding: utf-8 -*-
"""
KiCad yükleyici — asıl eklenti kicad-llm-plugin/ içindedir.
Bu dosya plugins/ kökünde kalmalı; KiCad yalnızca üst düzey .py dosyalarını yükler.
"""

import importlib.util
import os
import sys

_PKG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kicad-llm-plugin")
if _PKG not in sys.path:
    sys.path.insert(0, _PKG)

_MAIN = os.path.join(_PKG, "merhabaa_llm.py")
_spec = importlib.util.spec_from_file_location("kicad_llm_plugin_main", _MAIN)
_mod = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_mod)
