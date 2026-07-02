# -*- coding: utf-8 -*-
"""
Açık PCB'nin metin tabanlı 'anlık görüntüsü': footprint, pad ağları, izler, via,
çizimler, bölgeler — LLM bağlamı için. pcbnew API farklarına karşı savunmalı.
"""

import pcbnew

SNAPSHOT_MAX_CHARS = 6000


def _mm(v):
    try:
        return pcbnew.ToMM(int(v))
    except Exception:
        try:
            return pcbnew.ToMM(v)
        except Exception:
            return None


def _pad_iter(footprint):
    gen = getattr(footprint, "Pads", None)
    if callable(gen):
        try:
            return list(gen())
        except Exception:
            pass
    return []


def _item_netname(item):
    for attr in ("GetNetname", "GetNetName"):
        fn = getattr(item, attr, None)
        if callable(fn):
            try:
                return fn() or ""
            except Exception:
                pass
    return ""


def _layer_name(board, layer_id):
    fn = getattr(board, "GetLayerName", None)
    if callable(fn):
        try:
            return fn(layer_id)
        except Exception:
            pass
    return str(layer_id)


def _enabled_copper_names(board):
    names = []
    fn_enabled = getattr(board, "IsLayerEnabled", None)
    fn_cu = getattr(board, "IsCopperLayer", None)
    fn_name = getattr(board, "GetLayerName", None)
    if not all(callable(x) for x in (fn_enabled, fn_cu, fn_name)):
        return names
    lid_max = int(getattr(pcbnew, "PCB_LAYER_ID_COUNT", 64))
    for lid in range(0, lid_max):
        try:
            if fn_enabled(lid) and fn_cu(lid):
                names.append(fn_name(lid))
        except Exception:
            continue
    return names


def build_expert_snapshot(board, max_chars=None):
    """
    LLM'e gönderilecek zengin kart özeti (düz metin).
    max_chars: JSON/onay isteklerinde token tasarrufu (ör. 3500).
    """
    limit = int(max_chars) if max_chars else SNAPSHOT_MAX_CHARS
    if board is None:
        return "Geçerli kart yok (GetBoard() None)."

    lines = ["=== KiCad PCB anlık görüntüsü ==="]

    try:
        path = board.GetFileName() or "(kaydedilmemiş?)"
    except Exception:
        path = "?"
    lines.append("Dosya: %s" % path)

    size_txt = "bilinmiyor"
    try:
        bb = board.GetBoardEdgesBoundingBox()
        w, h = _mm(bb.GetWidth()), _mm(bb.GetHeight())
        if w is not None and h is not None:
            size_txt = "%.1f x %.1f mm (kenar kutusu)" % (w, h)
    except Exception:
        try:
            bb = board.GetBoundingBox()
            w, h = _mm(bb.GetWidth()), _mm(bb.GetHeight())
            if w is not None and h is not None:
                size_txt = "%.1f x %.1f mm (içerik kutusu)" % (w, h)
        except Exception:
            pass
    lines.append("Tahta boyutu (yaklaşık): %s" % size_txt)

    cu = _enabled_copper_names(board)
    if cu:
        lines.append("Aktif bakır katmanları: %s" % ", ".join(cu))
    else:
        lines.append("Aktif bakır katmanları: (okunamadı)")

    fps = []
    fn = getattr(board, "GetFootprints", None)
    if callable(fn):
        try:
            fps = list(fn())
        except Exception:
            fps = []

    lines.append("")
    lines.append("--- Footprint listesi (%d) ---" % len(fps))
    net_counts = {}
    for fp in fps:
        ref = fp.GetReference()
        val = fp.GetValue()
        try:
            layer = _layer_name(board, fp.GetLayer())
        except Exception:
            layer = "?"
        try:
            pos = fp.GetPosition()
            xm, ym = _mm(pos.x), _mm(pos.y)
            pos_s = (
                "%.2f, %.2f mm" % (xm, ym) if xm is not None and ym is not None else "?"
            )
        except Exception:
            pos_s = "?"
        try:
            ang = fp.GetOrientation()
            if hasattr(ang, "AsDegrees"):
                rot_s = "%.1f°" % ang.AsDegrees()
            elif hasattr(ang, "Degrees"):
                rot_s = "%.1f°" % ang.Degrees()
            else:
                rot_s = "?"
        except Exception:
            rot_s = "?"

        pads = _pad_iter(fp)
        pad_parts = []
        for pad in pads[:24]:
            try:
                pname = pad.GetName()
            except Exception:
                pname = "?"
            nname = _item_netname(pad) or "(boş)"
            pad_parts.append("%s:%s" % (pname, nname))
            net_counts[nname] = net_counts.get(nname, 0) + 1
        pad_extra = len(pads) - len(pad_parts)
        pad_s = " ".join(pad_parts)
        if pad_extra > 0:
            pad_s += " …(+%d pad)" % pad_extra

        lines.append(
            "  %s | val=%s | kat=%s | pos=%s | rot=%s | pad: %s"
            % (ref, val, layer, pos_s, rot_s, pad_s or "(pad yok)")
        )

    lines.append("")
    lines.append("--- İzler / via ---")
    n_seg = 0
    n_via = 0
    layers_tracks = {}
    try:
        tracks = list(board.GetTracks())
    except Exception:
        tracks = []

    for t in tracks:
        cls = t.GetClass()
        if cls == "PCB_VIA":
            n_via += 1
        else:
            n_seg += 1
            try:
                lid = t.GetLayer()
                ln = _layer_name(board, lid)
                layers_tracks[ln] = layers_tracks.get(ln, 0) + 1
            except Exception:
                pass
        nn = _item_netname(t)
        if nn:
            net_counts[nn] = net_counts.get(nn, 0) + 1

    lines.append("Segment sayısı (tahmini bakır parça): %d" % n_seg)
    lines.append("Via sayısı: %d" % n_via)
    if layers_tracks:
        top_layers = sorted(layers_tracks.items(), key=lambda x: -x[1])[:12]
        lines.append("İz yoğunluğu (kat): " + ", ".join("%s:%d" % x for x in top_layers))

    lines.append("")
    lines.append("--- Ağlar (pad+izden sayım, üst 40) ---")
    for name, cnt in sorted(net_counts.items(), key=lambda x: -x[1])[:40]:
        lines.append("  %s : %d" % (name, cnt))

    lines.append("")
    lines.append("--- Bakır bölgeleri (zone) ---")
    try:
        ac = board.GetAreaCount()
    except Exception:
        ac = 0
    lines.append("Bölge sayısı: %d" % ac)
    for i in range(min(ac, 15)):
        try:
            z = board.GetArea(i)
            zname = ""
            gn = getattr(z, "GetZoneName", None)
            if callable(gn):
                try:
                    zname = gn() or ""
                except Exception:
                    zname = ""
            if not zname:
                zname = "(adsız)"
            zlayer = _layer_name(board, z.GetLayer())
            lines.append("  [%d] %s @ %s" % (i, zname, zlayer))
        except Exception:
            break

    lines.append("")
    lines.append("--- Çizimler (özet) ---")
    edge = silk = other = 0
    try:
        for d in board.GetDrawings():
            try:
                lid = d.GetLayer()
            except Exception:
                other += 1
                continue
            try:
                if lid == pcbnew.Edge_Cuts:
                    edge += 1
                elif lid in (pcbnew.F_SilkS, pcbnew.B_SilkS):
                    silk += 1
                else:
                    other += 1
            except Exception:
                other += 1
    except Exception:
        pass
    lines.append(
        "Çizim öğeleri: Edge_Cuts=%d, Silk=%d, diğer=%d" % (edge, silk, other)
    )

    text = "\n".join(lines)

    if len(text) > limit:
        head = text[: limit // 2]
        tail = text[-limit // 2 :]
        text = (
            head
            + "\n\n... [ORTA KISIM KISALTILDI: kart çok büyük; tam liste konsolda değil] ...\n\n"
            + tail
        )
    return text + "\n=== anlık görüntü sonu ===\n"
