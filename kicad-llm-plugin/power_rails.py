# -*- coding: utf-8 -*-
"""Güç / voltaj niyeti için yerel (Groq dışı) kurallar ve kart üzerine uyarı damgası."""

import pcbnew


def parse_voltage_list(text):
    """'4,4,4' veya '4 4 4' veya '4; 5.5' -> [4.0, 4.0, 4.0]"""
    text = text.replace(";", ",").replace("V", " ").replace("v", " ")
    parts = []
    for chunk in text.replace(",", " ").split():
        chunk = chunk.strip().replace(",", ".")
        if not chunk:
            continue
        try:
            parts.append(float(chunk))
        except ValueError:
            continue
    return parts


def validate_power_intent(vin, vouts, mode_index):
    """
    mode_index: 0=Seri bölme (Kirchhoff toplamı), 1=Ayrı buck çıkışlar, 2=Ortak bara (aynı V)
    Dönüş: (errors: list[str], warnings: list[str])
    """
    errors = []
    warnings = []
    if vin is None or vin <= 0:
        errors.append("Giriş voltajı pozitif bir sayı olmalı.")
        return errors, warnings
    if not vouts:
        errors.append("En az bir çıkış voltajı girin.")
        return errors, warnings
    if any(v <= 0 for v in vouts):
        errors.append("Çıkış voltajları pozitif olmalı (bu basit modelde).")

    mode_index = int(mode_index)

    if mode_index == 0:
        s = sum(vouts)
        if abs(s - vin) > 0.5 + 1e-6:
            errors.append(
                "Seri bölme modelinde çıkışların toplamı (%.2f V) giriş (%.2f V) ile uyumsuz. "
                "Örn. 13 V'u pasif olarak 4+4+4 V yapmaya çalışmak Kirchhoff'a aykırı (toplam 12 V)."
                % (s, vin)
            )
        else:
            warnings.append(
                "Seri bölme: yük akımları değişince düğüm voltajları kayar; "
                "gerçek tasarımda regülasyon veya tolerans hesabı gerekir."
            )

    elif mode_index == 1:
        for i, v in enumerate(vouts, start=1):
            if v >= vin - 0.2:
                errors.append(
                    "Çıkış #%d (%.2f V) girişe çok yakın veya üstünde. "
                    "Tipik buck dönüştürücüde Vout < Vin (düşürücü) beklenir."
                    % (i, v)
                )
        if vin > 60:
            warnings.append(
                "Giriş %.0f V üzeri: creepage/clearance, izolasyon ve "
                "konnektör/klemens nominal değerlerini özellikle doğrulayın." % vin
            )

    elif mode_index == 2:
        for i, v in enumerate(vouts, start=1):
            if abs(v - vin) > max(0.5, 0.05 * vin):
                errors.append(
                    "Ortak bara modelinde çıkış #%d (%.2f V) giriş (%.2f V) ile örtüşmüyor."
                    % (i, v, vin)
                )

    return errors, warnings


def stamp_warnings_on_pcb(board, lines, title="LLM kontrol"):
    """
    Uyarıları Cmts.User katmanına PCB_TEXT olarak yazar (geri al/ sil ile temizlenir).
    Başarısız olursa sessizce [] döner (çağıran konsola yazabilir).
    """
    added = []
    if board is None or not lines:
        return added
    try:
        layer = pcbnew.Cmts_User
    except Exception:
        try:
            layer = pcbnew.Dwgs_User
        except Exception:
            return added

    y_mm = 8.0
    x_mm = 5.0
    for i, msg in enumerate(lines[:14]):
        line = "[%s] %s" % (title, msg)
        if len(line) > 240:
            line = line[:237] + "..."
        try:
            t = pcbnew.PCB_TEXT(board)
            t.SetText(line)
            t.SetLayer(layer)
            pos = pcbnew.VECTOR2I(pcbnew.FromMM(x_mm), pcbnew.FromMM(y_mm + i * 5.0))
            t.SetPosition(pos)
            board.Add(t)
            added.append(t)
        except Exception:
            break
    try:
        pcbnew.Refresh()
    except Exception:
        pass
    return added
