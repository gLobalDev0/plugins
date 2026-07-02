from kicad_uav_crew.crew import KicadUavCrew

# Kısa özet — TPM kotası için (tam spec agents/tasks içinde genişletilir)
_USER_REQUEST = (
    "Arduino Nano robotik kontrol kartı: 100x60mm, 2 katman F.Cu/B.Cu, F.Mask/B.Mask. "
    "Merkez Module:Arduino_Nano veya 2x PinHeader_1x15. Sol üst J1 12V klemens + C1 10uF. "
    "Sol alt 2x motor konnektörü + 100nF (3mm yakın). Sağda 4x 3-pin sensör header. "
    "Güç iz 1.2mm, sinyal 0.3mm, via 0.6/0.4mm, GND zone F.Cu+B.Cu, courtyard min 1.5mm. "
    "Çıktı: schema_version 1 JSON (components, tracks, vias, zones, silk_labels)."
)


def run():
    inputs = {
        "user_request": _USER_REQUEST,
    }
    try:
        result = KicadUavCrew().crew().kickoff(inputs=inputs)
        print("\n=== AJANLARIN FİNAL RAPORU ===")
        print(result.raw)
    except Exception as e:
        err = str(e)
        print("\n=== CREW HATASI ===")
        if "rate_limit" in err.lower() or "429" in err:
            print(
                "Groq kota (TPD/TPM) aşıldı.\n"
                "1-2 dakika bekleyip tekrar: crewai run\n"
                "console.groq.com → Usage\n"
            )
        print(err)


if __name__ == "__main__":
    run()
