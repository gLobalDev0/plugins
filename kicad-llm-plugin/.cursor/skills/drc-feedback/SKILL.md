---
name: drc-feedback
description: >-
  KiCad DRC (Design Rule Check) çıktısını okur, hataları sınıflandırır ve
  tasarım JSON veya pcb_apply düzeltmeleri için eyleme dönük öneri üretir.
  DRC, kural ihlali, clearance veya "Inspect" sonrası kullanılır.
---

# DRC Geri Bildirim İş Akışı

## Ne Zaman Kullanılır?
- Kart çizildikten sonra kullanıcı DRC hatası bildirdiğinde.
- `pcb_apply` sonrası kısa devre, clearance veya iz genişliği şüphesinde.

## Adımlar
1. Kullanıcıdan DRC raporu metnini veya ekran özetini al (hata kodu, katman, koordinat).
2. Hatayı sınıflandır: clearance, track width, unconnected, courtyard, mask.
3. JSON tasarımındaki ilgili alanı işaret et: `tracks`, `track_width_mm`, bileşen `x_mm`/`y_mm`, `zones`.
4. Düzeltme öner; gerekirse sadece metin raporu — otomatik çizim için kullanıcı onayı bekle.
5. Ana sohbete uzun DRC dökümü yapıştırma; özet + madde madde düzeltme listesi ver (context şişmesini önle).

## pcbnew ile yerel kontrol (mümkünse)
- Açık kart: `board = pcbnew.GetBoard()`
- İz genişliği ve net bağlantılarını `pcb_snapshot` özeti ile çapraz doğrula.

## Çıktı formatı
```
DRC Özet: 3 hata, 1 uyarı
[Kritik] J1–U1 GND: clearance 0.15 mm < 0.2 mm → C1 sola 1 mm kaydır
[Uyarı] +20V iz 0.5 mm → track_width_mm 0.8 öner
```
