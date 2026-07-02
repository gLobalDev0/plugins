---
name: kicad-library-rag
description: >-
  Kullanıcı yeni bir bileşen yerleşimi istediğinde, yerel Linux KiCad 8 footprint
  dizinini tarayarak gerçek pad ölçülerini ve kılıf sınırlarını ajan belleğine
  enjekte eder. "Şemayı doğrula", "Bileşen ekle" veya JSON üretimi öncesi tetiklenir.
---

# KiCad Yerel Kütüphane RAG Boru Hattı

## Ne Zaman Tetiklenir?
- "Şemayı doğrula", "Bileşen ekle" veya yeni bir yerleşim şeması (JSON) üretilmesi istendiğinde otomatik olarak devreye girer.

## Erişim Adımları (Workflow)
1. Tasarımda geçecek olan kütüphane adını tespit et (Örn: `Resistor_SMD`, `Module`).
2. `/usr/share/kicad/footprints/{Kütüphane_Adı}.pretty/` dizinine yerel bir okuma araması gerçekleştir.
3. İlgili parçanın `.kicad_mod` dosyasını ayrıştırarak (parse) şu kritik verileri çek:
   - `courtyard` / `fp_line` / `fp_rect` sınır koordinatları (fiziksel çakışma önleme).
   - `pad` numaraları, konumları ve ölçüleri.
4. Elde edilen bu gerçek verileri, çizim yapan `track-router-agent` ve denetleyen `senior-pcb-reviewer` ajanlarına **True Context** olarak teslim et.

## Komut (proje kökünden)
```bash
python3 scripts/kicad_library_rag.py Module:Arduino_Nano Capacitor_SMD:CP_Elec_6.3x7.7
```

Çıktıyı JSON üretmeden önce prompt bağlamına yapıştır; uydurma footprint veya pad boyutu kullanma.

## Yasak
- Kütüphane dizininde bulunmayan footprint adı üretmek.
- Courtyard verisi olmadan bileşenleri üst üste yerleştirmek.
