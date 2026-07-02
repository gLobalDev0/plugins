# KiCad LLM — Robotik Kontrol Kartı (Referans: ELEKTRİK AR-GE V1.0)

Bu metni KiCad eklentisindeki sohbete **tamamen yapıştırın**. Onayladıktan sonra **Uygula** ile çizin.
Önce `footprint-validator` ve `kicad-library-rag` skill'lerini çalıştırın; aşağıdaki footprint'ler sistemde doğrulanmıştır.

---

## GÖREV

Arduino Nano tabanlı, **100 mm × 60 mm**, çift katmanlı (F.Cu + B.Cu) **Robotik Kontrol ve Sensör Kartı** çiz.
Hedef görünüm: merkezde Nano, sol üstte güç/klemens, sol altta motor bloğu, sağda sensör header'ları, üstte RESET, yoğun kırmızı/mavi izler ve GND bakır dolgusu — profesyonel AR-GE kartı.

---

## 1. KART VE KATMANLAR

| Parametre | Değer |
|-----------|--------|
| `board_mm` | width **100**, height **60** |
| `copper_layers` | **2** |
| Kenar | `Edge.Cuts` dikdörtgen |
| Maske | F.Mask + B.Mask etkin (yeşil solder mask) |
| Güç iz kalınlığı | **1.2 mm** (`track_width_mm` güç hatları için) |
| Sinyal iz kalınlığı | **0.3 mm** |
| Via | dış çap **0.6 mm**, matkap **0.4 mm** |
| Courtyard boşluğu | bileşenler arası en az **1.5 mm** |

---

## 2. BİLEŞENLER (SADECE BU FOOTPRINT'LER)

| Ref | Değer | Footprint (Lib:Name) | Bölge (x_mm, y_mm yaklaşık) |
|-----|-------|----------------------|-----------------------------|
| J1 | 12V IN | `TerminalBlock_CUI:TerminalBlock_CUI_TB007-508-02_1x02_P5.08mm_Horizontal` | Sol üst **(8, 12)** |
| C1 | 10uF | `Capacitor_SMD:CP_Elec_6.3x7.7` | J1 yanı **(18, 12)** — C1 courtyard ile J1 arası ≥1.5 mm |
| C2,C3 | 100nF | `Capacitor_SMD:C_0805_2012Metric` | Motor konnektörleri yanı, **≤3 mm** |
| J_M1 | Motor1 | `Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical` | Sol alt **(10, 45)** |
| J_M2 | Motor2 | `Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical` | **(10, 52)** |
| U_NANO | Arduino | `Module:Arduino_Nano` | Merkez **(50, 30)** |
| J_S1..J_S4 | Sensor | `Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical` | Sağ şerit x≈**88**, y=**15, 25, 35, 45** |
| SW1 | RESET | `Button_Switch_THT:SW_Tactile_SPST_Angled_PTS645Vx58-2LFS` | Üst orta **(50, 8)** |
| (ops.) | — | İki adet `PinHeader_1x15` soket Nano altına değil; doğrudan `Module:Arduino_Nano` kullan | — |

**Yerleşim (zoning):**
- MERKEZ: Arduino Nano modülü (USB alt kenara bakacak şekilde `rot_deg` ayarla).
- SOL ÜST: J1 klemens + C1 filtre.
- SOL ALT: J_M1, J_M2 + C2/C3 parazit kapasitörleri konnektöre **max 3 mm**.
- SAĞ: 4× 3-pin sensör header (VCC, GND, SIG).
- ÜST: RESET düğmesi.

---

## 3. ROUTING KURALLARI

1. **VCC / GND:** min **1.2 mm** genişlik; ana omurgalar kart boyunca.
2. **Sinyal:** **0.3 mm**; dikey segmentler ağırlıklı **F.Cu**, yatay segmentler **B.Cu** (çakışmayı önle).
3. **Via:** katman geçişlerinde 0.6 / 0.4 mm.
4. **Zone (GND pour):** hem **F.Cu** hem **B.Cu** — `rect_mm` kartın büyük kısmını kaplasın (pad/iz clearance bırak).
5. **45°** köşe kırılımı; 90° dik köşe yok.
6. Hiçbir courtyard çakışması yok.

---

## 4. SİLK (F.SilkS)

- Kart başlığı: `ELEKTRIK AR-GE ATOLYE GELISTIRME KARTI V1.0` — **(62, 4)** (ASCII, Türkçe karakter sorunu yok).
- Bölge etiketleri: `Motor System` sol alt, `Sensor System` sağ, `Vcc +5V +3.3V` sol üst.
- `silk_labels` ile ref yazıları pad'lere binmesin.

---

## 5. NİHAİ ÇIKTI (ZORUNLU)

Yalnızca **tek** geçerli JSON bloğu (`schema_version: 1`):

```json
{
  "schema_version": 1,
  "title": "Elektrik ARGE Robot Karti V1",
  "board_mm": {"width": 100, "height": 60},
  "copper_layers": 2,
  "track_width_mm": 1.2,
  "via": {"diameter_mm": 0.6, "drill_mm": 0.4},
  "components": [],
  "tracks": [],
  "vias": [],
  "zones": [],
  "silk_labels": []
}
```

`components`, `tracks`, `vias`, `zones`, `silk_labels` alanlarını **dolu** üretin; markdown rapor yazmayın.

---

## 6. ONAY

Parametreler netse kullanıcı **«Onaylıyorum»** yazar; sonra JSON üretilir ve `pcb_apply` çizer.
