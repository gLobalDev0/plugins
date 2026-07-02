---
name: footprint-validator
description: >-
  Kullanıcının istediği bileşenlerin (footprint) sistemde kurulu olup olmadığını
  pcbnew API ve dosya sistemi ile doğrular. "Kartı çiz", "Bileşenleri kontrol et"
  veya JSON üretiminden hemen önce tetiklenir.
---

# Footprint Doğrulama İş Akışı

## Ne Zaman Kullanılır?
- AI bir JSON şeması üretmeden veya kart üzerine eleman yerleştirmeden hemen önce bu yetenek dinamik olarak yüklenir.

## Adım Adım Çalıştırma Protokolü
1. Kullanıcının talep ettiği footprint isimlerini ayıkla (ör. `Resistor_SMD:R_0805_2012Metric`, `Capacitor_SMD:C_0805_2012Metric`).
2. Her `Kütüphane:Footprint` çifti için kütüphane klasörünün varlığını kontrol et:
   - Varsayılan yol: `/usr/share/kicad/footprints/<Kütüphane>.pretty/`
   - Proje betiği: `python3 scripts/footprint_validator.py Resistor_SMD:R_0805_2012Metric ...`
3. Kütüphane veya footprint yoksa şemayı çizmeye geçme; kullanıcıyı **Kütüphane eksik** diye uyar ve eksik `.pretty` adını listele.
4. Tümü geçerliyse kısa özet: `Footprint doğrulama: N/N OK` — ardından `senior-pcb-reviewer` alt ajanına geçilebilir.

## Python (pcbnew) kontrolü
```python
import os
import pcbnew

KICAD_FP_ROOT = "/usr/share/kicad/footprints"

def lib_folder(lib_nick):
    nick = lib_nick.strip()
    if nick.endswith(".pretty"):
        return nick
    return nick + ".pretty"

def footprint_exists(lib_nick, fp_name):
    path = os.path.join(KICAD_FP_ROOT, lib_folder(lib_nick))
    if not os.path.isdir(path):
        return False, "Kütüphane yok: %s" % path
    fp = pcbnew.FootprintLoad(path, fp_name)
    return fp is not None, path
```

## Yasak
- Doğrulama başarısızken uydurma kütüphane adı (ör. hayali `Inductor_SMD` varyantları) önerme.
