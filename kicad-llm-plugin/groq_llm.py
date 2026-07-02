# -*- coding: utf-8 -*-
"""Groq OpenAI-uyumlu sohbet API (urllib, ek paket yok). Anahtar dosyaları: groq_llm ile aynı klasör."""

import json
import os
import re
import urllib.error
import urllib.request

GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
# 70b günlük TPD kotası sık dolar — varsayılan yalnızca 8b (Groq ücretsiz planda güvenli)
DEFAULT_MODEL = "llama-3.1-8b-instant"
FALLBACK_MODELS = ("llama-3.1-8b-instant",)
# Bu modeller kota dolduğunda JSON üretimini kilitler; otomatik 8b'ye düşürülür
_HEAVY_MODEL_MARKERS = ("70b", "405b", "mixtral")

# Aşama 1 — tartışma: JSON YASAK
SYSTEM_PROMPT = """Sen KiCad 8 kullanan profesyonel bir PCB tasarım mühendisisin.

İŞ AKIŞI:
1) Kullanıcı bir kart istediğinde hemen JSON üretme, önce onay bekle.
2) Kullanıcının verdiği gereksinimleri incele. Eğer kullanıcı "kalanını sen belirle", "sen seç" veya kısa bir istek girerse eksik parametreleri (boyut, bileşenler, footprint vs.) kendin en ideal şekilde belirle. Kullanıcıyı soru yağmuruna tutma.
3) Mantıklı varsayımlarla oluşturduğun tasarımı ve bileşen listesini (KiCad kütüphane adlarıyla) kısaca özetle.
4) Tasarım özeti bitince kullanıcıya şunu söyle:
   «Tasarımı kartta çizmek için "Onaylıyorum" yazın veya Uygula düğmesine basın.»
5) JSON yalnızca kullanıcı açıkça onayladığında üretilir; o zamana kadar ```json``` bloğu YAZMA.

Kullanıcı Türkçe yazarsa Türkçe yanıt ver.
Kart anlık görüntüsü verilirse tutarlılık için kullan."""

# Aşama 2 — onay sonrası: yalnızca JSON + kısa onay
JSON_GENERATION_PROMPT = """Kullanıcı tasarımı ONAYLADI. Tartışma bitti.

Şimdi:
1) En fazla 3 cümle Türkçe onay özeti.
2) Hemen ardından TEK bir ```json ... ``` bloğu (başka kod bloğu yok).

JSON kuralları (schema_version = 1):
• board_mm, copper_layers, track_width_mm, via, components, tracks, vias, zones
• Her bileşende mümkünse "footprint": "KütüphaneAdı:FootprintAdı" (KiCad 8 standart)
  Örnekler:
  - Package_TO_SOT_THT:TO-220-3_Vertical (7805 THT)
  - Package_TO_SOT_SMD:SOT-223-3_TabPin2
  - Capacitor_SMD:C_0805_2012Metric, Capacitor_SMD:CP_Elec_6.3x7.7
  - Resistor_SMD:R_0805_2012Metric
  - Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical
• Filtre kapasitörleri regülatör/buck yanına: "anchor_ref":"U2", "offset_mm":[-3,-4]
• type alanı da ver: connector_in, dc_dc, regulator_linear, resistor, capacitor, ...
• Bileşenleri güç akışına göre soldan sağa yerleştir; y_offset ile filtreleri grupla.
• copper_layers kullanıcı isteğine uygun (1/2/4/6).
• tracks: +12V, +5V, GND güç yolları; zones: GND pour.
• Geçerli JSON; yorum ve sondaki virgül yok.

Örnek iskelet:
{
  "schema_version": 1,
  "title": "Guc dagitim",
  "board_mm": {"width": 50, "height": 50},
  "copper_layers": 2,
  "track_width_mm": 0.5,
  "via": {"diameter_mm": 0.5, "drill_mm": 0.3},
  "components": [
    {"ref":"J1","value":"12V","type":"connector_in","footprint":"Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical","x_mm":4,"y_mm":25},
    {"ref":"U1","value":"LM2596","type":"dc_dc","footprint":"Converter_DCDC:Converter_DCDC_RECOM_R-78E-0.5","x_mm":16,"y_mm":25},
    {"ref":"C1","value":"10uF","type":"capacitor_electrolytic","footprint":"Capacitor_SMD:CP_Elec_6.3x7.7","anchor_ref":"U2","offset_mm":[-4,-5],"net":"+5V"},
    {"ref":"U2","value":"7805","type":"regulator_linear","footprint":"Package_TO_SOT_THT:TO-220-3_Vertical","x_mm":30,"y_mm":25}
  ],
  "tracks": [...],
  "vias": [...],
  "zones": [{"net":"GND","layer":"F.Cu","rect_mm":{"x":5,"y":5,"w":40,"h":8}}]
}"""


def _plugin_dir():
    return os.path.dirname(os.path.abspath(__file__))


def expected_key_file_path():
    return os.path.join(_plugin_dir(), "groq_api_key.txt")


def expected_model_file_path():
    return os.path.join(_plugin_dir(), "groq_model.txt")


def load_groq_model():
    """
    Model seçimi: groq_model.txt > (GROQ_MODEL env, 70b hariç) > DEFAULT_MODEL.
  KiCad'i yeniden başlatmadan model değiştirmek için groq_model.txt düzenleyin.
    """
    path = expected_model_file_path()
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        return line.split("#", 1)[0].strip()
        except OSError:
            pass
    env_m = os.environ.get("GROQ_MODEL", "").strip()
    if env_m:
        low = env_m.lower()
        if any(x in low for x in _HEAVY_MODEL_MARKERS):
            print(
                "[groq_llm] GROQ_MODEL=%s atlandı (kota riski). "
                "Kalıcı: groq_model.txt içine llama-3.1-8b-instant yazın." % env_m
            )
        else:
            return env_m.replace("groq/", "").strip()
    return DEFAULT_MODEL


_UUID_KEY = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def _normalize_key_line(line):
    line = line.strip()
    if not line or line.startswith("#"):
        return ""
    if "GROQ_API_KEY" in line.upper() and "=" in line:
        line = line.split("=", 1)[1].strip().strip('"').strip("'")
    return line.strip()


def _is_plausible_secret(s):
    s = (s or "").strip()
    if not s or len(s) < 15:
        return False
    if " " in s or "\t" in s:
        return False
    low = s.lower()
    if "your" in low or "replace" in low or "buraya" in low or "örnek" in low:
        return False
    if s.startswith("gsk_") and len(s) >= 20:
        return True
    if _UUID_KEY.match(s):
        return True
    if len(s) >= 48 and re.match(r"^[A-Za-z0-9_\-./]+$", s):
        return True
    return False


def _extract_key_from_file(path):
    if not os.path.isfile(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8") as f:
            for raw in f:
                line = _normalize_key_line(raw)
                if not line:
                    continue
                if _is_plausible_secret(line):
                    return line.strip().strip("\ufeff")
    except OSError:
        pass
    return ""


def _maybe_migrate_example_to_txt(key, source_path):
    txt = expected_key_file_path()
    ex = os.path.join(_plugin_dir(), "groq_api_key.txt.example")
    try:
        if not key or os.path.abspath(source_path) != os.path.abspath(ex):
            return
        if os.path.isfile(txt):
            st = os.stat(txt)
            if st.st_size > 0:
                return
    except OSError:
        return
    try:
        with open(txt, "w", encoding="utf-8") as out:
            out.write(key.strip() + "\n")
        print("[groq_llm] Anahtar groq_api_key.txt dosyasına kopyalandı (otomatik).")
    except OSError as e:
        print("[groq_llm] groq_api_key.txt yazılamadı: %s" % e)


def load_groq_api_key():
    k = os.environ.get("GROQ_API_KEY", "").strip()
    if k:
        k = k.strip().strip("\ufeff")
        if _is_plausible_secret(k) or (len(k) >= 16 and " " not in k and "\n" not in k):
            return k
    base = _plugin_dir()
    ordered = (
        ("groq_api_key.txt", os.path.join(base, "groq_api_key.txt")),
        ("groq_api_key.local", os.path.join(base, "groq_api_key.local")),
        ("groq_api_key.txt.example", os.path.join(base, "groq_api_key.txt.example")),
    )
    for label, path in ordered:
        key = _extract_key_from_file(path)
        if key:
            key = key.strip().strip("\ufeff")
            print("[groq_llm] API anahtarı kaynak: %s (%s)" % (label, path))
            _maybe_migrate_example_to_txt(key, path)
            return key
    print("[groq_llm] API anahtarı bulunamadı. Klasör: %s" % base)
    return ""


def _format_http_error(code, detail, model_used):
    snippet = detail[:900] if detail else ""
    try:
        j = json.loads(detail)
        inner = j.get("error") or {}
        if isinstance(inner, dict) and inner.get("message"):
            snippet = inner.get("message", snippet)
    except Exception:
        pass
    msg = "HTTP %s (model=%s)\n%s" % (code, model_used, snippet)
    if code == 429:
        msg = (
            "Groq kota/limit aşıldı (HTTP 429).\n"
            "Büyük model (70b) günlük kotanız dolmuş olabilir.\n"
            "Eklenti otomatik olarak llama-3.1-8b-instant dener.\n"
            "Yine olmazsa ~1 saat bekleyin veya console.groq.com üzerinden kotayı kontrol edin.\n\n"
            + msg
        )
    return msg


def _should_try_next_model(http_code):
    """Sonraki modele geç: yetki, kota, model yok veya sunucu hatası."""
    return http_code in (400, 403, 404, 429, 500, 502, 503)


def chat_completion(messages, model=None, extra_system=None):
    """
    messages: OpenAI biçimi.
    extra_system: onay/JSON aşamasında ek system mesajı.
    Dönüş: (assistant_text veya None, hata_metni veya None)
    """
    if extra_system:
        messages = list(messages) + [{"role": "system", "content": extra_system}]

    key = load_groq_api_key()
    if not key:
        txt_path = expected_key_file_path()
        ex_path = os.path.join(_plugin_dir(), "groq_api_key.txt.example")
        return None, (
            "Groq API anahtarı okunamadı.\n\n"
            "Şunlardan BİRİ yeterli (Groq anahtarı genelde gsk_ ile başlar):\n"
            "  1) Dosya: %s\n"
            "  2) Aynı klasörde: %s\n"
            "  3) Kabuk: export GROQ_API_KEY='gsk_...'\n\n"
            "Eklenti klasörü: %s"
            % (txt_path, ex_path, _plugin_dir())
        )

    key = key.strip().strip("\ufeff")
    primary = (model or load_groq_model() or DEFAULT_MODEL).strip()
    if any(x in primary.lower() for x in _HEAVY_MODEL_MARKERS):
        print("[groq_llm] %s → %s (günlük kota koruması)" % (primary, DEFAULT_MODEL))
        primary = DEFAULT_MODEL
    models_order = []
    for m in (primary,) + FALLBACK_MODELS:
        m = m.replace("groq/", "").strip()
        if m and m not in models_order:
            models_order.append(m)

    headers_base = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "KiCad-MerhabaLLM/2.0 (+https://kicad.org; Groq-OpenAI-client)",
    }

    last_err = ""
    for attempt_model in models_order:
        payload = {
            "model": attempt_model,
            "messages": messages,
            "temperature": 0.35,
            "max_tokens": 2048,
        }
        data = json.dumps(payload).encode("utf-8")
        hdrs = dict(headers_base)
        hdrs["Authorization"] = "Bearer " + key
        req = urllib.request.Request(
            GROQ_CHAT_URL,
            data=data,
            headers=hdrs,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            try:
                detail = e.read().decode("utf-8", errors="replace")
            except Exception:
                detail = str(e)
            msg = _format_http_error(e.code, detail, attempt_model)
            last_err = msg
            if e.code == 401:
                return None, msg
            if _should_try_next_model(e.code) and attempt_model != models_order[-1]:
                print(
                    "[groq_llm] %s @ %s — sonraki model deneniyor…"
                    % (e.code, attempt_model)
                )
                continue
            if e.code == 403:
                return None, msg + (
                    "\n\nGroq 403: GROQ_MODEL=llama-3.1-8b-instant deneyin."
                )
            return None, msg
        except urllib.error.URLError as e:
            return None, "Bağlantı hatası: %s" % e.reason
        except Exception as e:
            return None, str(e)

        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            return None, "Geçersiz JSON yanıtı"

        try:
            text = body["choices"][0]["message"]["content"].strip()
            if attempt_model != primary:
                text = "[Model: %s]\n\n%s" % (attempt_model, text)
            return text, None
        except (KeyError, IndexError, TypeError):
            return None, "Beklenmeyen yanıt: %s" % raw[:500]

    return None, last_err or "Bilinmeyen API hatası."
