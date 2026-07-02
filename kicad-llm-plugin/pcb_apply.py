# -*- coding: utf-8 -*-
"""design_spec JSON'unu açık KiCad PCB kartına uygular."""

import os

import pcbnew

KICAD_FP_ROOT = "/usr/share/kicad/footprints"

# type -> (pretty klasörü, footprint adı) — KiCad 8 standart kütüphaneler
FOOTPRINT_MAP = {
    "resistor": ("Resistor_SMD.pretty", "R_0805_2012Metric"),
    "inductor": ("Inductor_SMD.pretty", "L_0805_2012Metric"),
    "diode": ("Diode_SMD.pretty", "D_SOD-123"),
    "capacitor": ("Capacitor_SMD.pretty", "C_0805_2012Metric"),
    "capacitor_electrolytic": ("Capacitor_SMD.pretty", "CP_Elec_6.3x7.7"),
    "regulator_linear": ("Package_TO_SOT_THT.pretty", "TO-220-3_Vertical"),
    "regulator_smd": ("Package_TO_SOT_SMD.pretty", "SOT-223-3_TabPin2"),
    "dc_dc": ("Package_TO_SOT_SMD.pretty", "SOT-223-3_TabPin2"),
    "connector": ("Connector_PinHeader_2.54mm.pretty", "PinHeader_1x02_P2.54mm_Vertical"),
    "connector_in": ("Connector_PinHeader_2.54mm.pretty", "PinHeader_1x02_P2.54mm_Vertical"),
    "connector_out": ("Connector_PinHeader_2.54mm.pretty", "PinHeader_1x02_P2.54mm_Vertical"),
    "generic": ("Resistor_SMD.pretty", "R_0805_2012Metric"),
}

# LibNick:FootprintName -> (pretty, name)
FOOTPRINT_ALIASES = {
    "package_to_sot_tht:to-220-3_vertical": ("Package_TO_SOT_THT.pretty", "TO-220-3_Vertical"),
    "package_to_sot_smd:sot-223-3_tabpin2": ("Package_TO_SOT_SMD.pretty", "SOT-223-3_TabPin2"),
    "capacitor_smd:c_0805_2012metric": ("Capacitor_SMD.pretty", "C_0805_2012Metric"),
    "resistor_smd:r_0805_2012metric": ("Resistor_SMD.pretty", "R_0805_2012Metric"),
    "inductor_smd:l_0805_2012metric": ("Inductor_SMD.pretty", "L_0805_2012Metric"),
    "diode_smd:d_sod-123": ("Diode_SMD.pretty", "D_SOD-123"),
}

LAYER_ALIASES = {
    "f.cu": pcbnew.F_Cu,
    "fcu": pcbnew.F_Cu,
    "top": pcbnew.F_Cu,
    "b.cu": pcbnew.B_Cu,
    "bcu": pcbnew.B_Cu,
    "bottom": pcbnew.B_Cu,
    "in1.cu": getattr(pcbnew, "In1_Cu", pcbnew.F_Cu),
    "in2.cu": getattr(pcbnew, "In2_Cu", pcbnew.B_Cu),
}

# Güç akışı yerleşimi (tahta genişliğine göre x oranı)
_FLOW_X = {
    "connector_in": 0.08,
    "dc_dc": 0.28,
    "regulator_linear": 0.52,
    "regulator_smd": 0.52,
    "connector_out": 0.88,
    "capacitor": 0.45,
    "capacitor_electrolytic": 0.45,
    "resistor": 0.60,
}


def _mm_pos(x_mm, y_mm):
    return pcbnew.VECTOR2I(pcbnew.FromMM(float(x_mm)), pcbnew.FromMM(float(y_mm)))


def _layer_id(name, default=pcbnew.F_Cu):
    if name is None:
        return default
    return LAYER_ALIASES.get(str(name).strip().lower().replace(" ", ""), default)


def _get_or_create_net(board, netname):
    netname = (netname or "").strip()
    if not netname or netname == "(boş)":
        return None
    net = board.FindNet(netname)
    if net is not None:
        return net
    try:
        net = pcbnew.NETINFO_ITEM(board, netname)
        board.Add(net)
        return net
    except Exception:
        return None


def _pretty_folder(lib_nick):
    """Connector_PinHeader_2.54mm -> Connector_PinHeader_2.54mm.pretty"""
    nick = lib_nick.strip()
    if nick.endswith(".pretty"):
        return nick
    if ":" in nick:
        nick = nick.split(":", 1)[0]
    return nick + ".pretty"


def _parse_footprint_field(fp_str):
    """
    Package_TO_SOT_THT:TO-220-3_Vertical
    veya Package_TO_SOT_THT.pretty/TO-220-3_Vertical
    """
    if not fp_str:
        return None, None
    s = str(fp_str).strip()
    key = s.lower().replace(".pretty", "").replace("/", ":")
    if key in FOOTPRINT_ALIASES:
        return FOOTPRINT_ALIASES[key]
    if ":" in s:
        lib, name = s.split(":", 1)
        return _pretty_folder(lib), name.strip()
    if "/" in s:
        lib, name = s.rsplit("/", 1)
        return _pretty_folder(lib), name.replace(".kicad_mod", "").strip()
    return None, None


def _load_footprint(comp):
    fp_field = comp.get("footprint") or comp.get("fp")
    lib, name = _parse_footprint_field(fp_field)
    if not lib or not name:
        ctype = (comp.get("type") or "generic").lower().replace("-", "_")
        lib, name = FOOTPRINT_MAP.get(ctype, FOOTPRINT_MAP["generic"])
    path = os.path.join(KICAD_FP_ROOT, lib)
    if not os.path.isdir(path):
        return None, "Kütüphane yok: %s" % path
    fp = pcbnew.FootprintLoad(path, name)
    if fp is None:
        return None, "Footprint yüklenemedi: %s:%s" % (lib, name)
    return fp, None


def _set_rotation(footprint, rot_deg):
    try:
        deg = float(rot_deg or 0)
    except (TypeError, ValueError):
        deg = 0.0
    if hasattr(pcbnew, "EDA_ANGLE"):
        footprint.SetOrientation(pcbnew.EDA_ANGLE(deg, pcbnew.DEGREES_T))
    else:
        footprint.SetOrientation(int(deg * 10))


def _enable_render_layers(board):
    """F.Mask / B.Mask / Silk — 3D ve editörde gerçekçi kart görünümü."""
    lines = []
    try:
        enabled = board.GetEnabledLayers()
        vis = board.GetVisibleLayers()
        for attr in ("FrontMask", "BackMask", "FrontSilk", "BackSilk", "FrontPaste", "BackPaste"):
            fn = getattr(pcbnew.LSET, attr, None)
            if callable(fn):
                mask = fn()
                enabled = enabled.AddLayerSet(mask)
                vis = vis.AddLayerSet(mask)
        board.SetEnabledLayers(enabled)
        board.SetVisibleLayers(vis)
        lines.append("Mask/Silk/Paste katmanları etkinleştirildi.")
    except Exception as e:
        lines.append("Katman etkinleştirme: %s" % e)

    try:
        if hasattr(board, "SetSolderMaskMinWidth"):
            board.SetSolderMaskMinWidth(pcbnew.FromMM(0.0))
    except Exception:
        pass
    return lines


def resolve_component_positions(spec):
    """
    anchor_ref + offset_mm ile gruplama; eksik koordinatta güç akışı yerleşimi.
    spec'i yerinde günceller.
    """
    board_mm = spec.get("board_mm") or {}
    w = float(board_mm.get("width", 50))
    h = float(board_mm.get("height", 50))
    y_rail = h * 0.5
    comps = spec.get("components") or []
    by_ref = {}

    for comp in comps:
        ref = comp.get("ref")
        if not ref:
            continue
        anchor = comp.get("anchor_ref")
        if anchor and anchor in by_ref:
            off = comp.get("offset_mm") or [-3.0, -4.0]
            try:
                ox, oy = float(off[0]), float(off[1])
            except (TypeError, IndexError, ValueError):
                ox, oy = -3.0, -4.0
            ax = float(by_ref[anchor].get("x_mm", w * 0.5))
            ay = float(by_ref[anchor].get("y_mm", y_rail))
            comp["x_mm"] = ax + ox
            comp["y_mm"] = ay + oy
        elif comp.get("x_mm") is None and comp.get("y_mm") is None:
            ctype = (comp.get("type") or "generic").lower().replace("-", "_")
            ratio = _FLOW_X.get(ctype, 0.5)
            comp["x_mm"] = w * ratio
            comp["y_mm"] = y_rail
        else:
            if comp.get("x_mm") is None:
                comp["x_mm"] = w * 0.5
            if comp.get("y_mm") is None:
                comp["y_mm"] = y_rail
        by_ref[ref] = comp


def _edge_cut_count(board):
    n = 0
    try:
        for d in board.GetDrawings():
            try:
                if d.GetLayer() == pcbnew.Edge_Cuts:
                    n += 1
            except Exception:
                pass
    except Exception:
        pass
    return n


def _add_board_outline(board, w_mm, h_mm):
    if _edge_cut_count(board) > 0:
        return "Kenar çizgisi zaten var; yeni dikdörtgen eklenmedi."
    w_mm, h_mm = float(w_mm), float(h_mm)
    corners = [(0, 0), (w_mm, 0), (w_mm, h_mm), (0, h_mm), (0, 0)]
    for i in range(len(corners) - 1):
        x1, y1 = corners[i]
        x2, y2 = corners[i + 1]
        seg = pcbnew.PCB_SHAPE(board)
        seg.SetShape(pcbnew.SHAPE_T_SEGMENT)
        seg.SetLayer(pcbnew.Edge_Cuts)
        seg.SetStart(_mm_pos(x1, y1))
        seg.SetEnd(_mm_pos(x2, y2))
        seg.SetWidth(pcbnew.FromMM(0.12))
        board.Add(seg)
    return "Tahta kenarı %.1f x %.1f mm (Edge.Cuts)" % (w_mm, h_mm)


def _set_copper_layer_count(board, n):
    n = int(n)
    fn = getattr(board, "SetCopperLayerCount", None)
    if not callable(fn):
        return "Katman sayısı API yok; hedef: %d katman." % n
    try:
        fn(n)
        return "Bakır katman sayısı: %d" % n
    except Exception as e:
        return "Katman ayarı başarısız: %s" % e


def _remove_footprints_by_ref(board, refs):
    refs = set(refs)
    removed = 0
    fn = getattr(board, "GetFootprints", None)
    if not callable(fn):
        return 0
    for fp in list(fn()):
        try:
            if fp.GetReference() in refs:
                board.Remove(fp)
                removed += 1
        except Exception:
            pass
    return removed


def _place_component(board, comp):
    ref = (comp.get("ref") or "U?").strip()
    val = comp.get("value") or ref
    x = float(comp.get("x_mm", 5))
    y = float(comp.get("y_mm", 5))
    rot = comp.get("rot_deg", 0)
    fp_field = comp.get("footprint") or comp.get("type")

    fp, err = _load_footprint(comp)
    if err:
        return None, err

    board.Add(fp)
    fp.SetReference(ref)
    fp.SetValue(str(val)[:80])
    fp.SetPosition(_mm_pos(x, y))
    _set_rotation(fp, rot)

    lib_id = comp.get("footprint") or ""
    if lib_id and hasattr(fp, "SetFPID"):
        try:
            fp.SetFPID(pcbnew.LIB_ID(lib_id.split(":")[0], lib_id.split(":")[-1]))
        except Exception:
            pass

    net = comp.get("net")
    if net:
        ni = _get_or_create_net(board, net)
        if ni:
            for pad in fp.Pads():
                try:
                    pad.SetNet(ni)
                except Exception:
                    pass

    fp_name = comp.get("footprint") or comp.get("type", "?")
    return fp, "%s @ %.1f,%.1f mm [%s]" % (ref, x, y, fp_name)


def _add_track(board, tr, default_width_mm):
    pts = tr.get("points_mm") or []
    if len(pts) < 2:
        return "İz atlandı."
    width = float(tr.get("width_mm", default_width_mm))
    layer = _layer_id(tr.get("layer"))
    net = _get_or_create_net(board, tr.get("net"))
    added = 0
    for i in range(len(pts) - 1):
        p0, p1 = pts[i], pts[i + 1]
        seg = pcbnew.PCB_TRACK(board)
        seg.SetStart(_mm_pos(p0[0], p0[1]))
        seg.SetEnd(_mm_pos(p1[0], p1[1]))
        seg.SetWidth(pcbnew.FromMM(width))
        seg.SetLayer(layer)
        if net:
            seg.SetNet(net)
        board.Add(seg)
        added += 1
    return "%d iz (%s)" % (added, tr.get("net") or "-")


def _add_via(board, via, defaults):
    x = float(via.get("x_mm", 0))
    y = float(via.get("y_mm", 0))
    d = float(via.get("diameter_mm", defaults.get("diameter_mm", 0.5)))
    drill = float(via.get("drill_mm", defaults.get("drill_mm", 0.3)))
    v = pcbnew.PCB_VIA(board)
    v.SetPosition(_mm_pos(x, y))
    v.SetWidth(pcbnew.FromMM(d))
    v.SetDrill(pcbnew.FromMM(drill))
    net = _get_or_create_net(board, via.get("net"))
    if net:
        v.SetNet(net)
    board.Add(v)
    return "Via %.1f,%.1f" % (x, y)


def _apply_silk_labels(board, spec):
    """Referans yazılarını (F.SilkS) çakışmayacak koordinatlara taşır."""
    labels = spec.get("silk_labels") or []
    if not labels:
        return []
    fn = getattr(board, "GetFootprints", None)
    if not callable(fn):
        return []
    by_ref = {fp.GetReference(): fp for fp in fn()}
    lines = []
    for item in labels:
        ref = (item.get("ref") or "").strip()
        fp = by_ref.get(ref)
        if fp is None:
            continue
        try:
            x = float(item.get("x_mm", 0))
            y = float(item.get("y_mm", 0))
        except (TypeError, ValueError):
            continue
        for getter in ("Reference", "Value"):
            fn_txt = getattr(fp, getter, None)
            if not callable(fn_txt):
                continue
            try:
                txt = fn_txt()
                if txt is not None:
                    txt.SetPosition(_mm_pos(x, y))
                    if hasattr(txt, "SetLayer"):
                        txt.SetLayer(pcbnew.F_SilkS)
            except Exception:
                pass
        val_y = item.get("value_y_mm")
        if val_y is not None and callable(getattr(fp, "Value", None)):
            try:
                vy = float(val_y)
                fp.Value().SetPosition(_mm_pos(x + float(item.get("value_dx_mm", 0)), vy))
            except Exception:
                pass
        lines.append("Silk %s -> %.1f,%.1f mm" % (ref, x, y))
    return lines


def _add_zone(board, zone):
    rect = zone.get("rect_mm") or zone.get("rect") or {}
    x = float(rect.get("x", rect.get("x_mm", 0)))
    y = float(rect.get("y", rect.get("y_mm", 0)))
    w = float(rect.get("w", rect.get("width_mm", 10)))
    h = float(rect.get("h", rect.get("height_mm", 10)))
    layer = _layer_id(zone.get("layer"))
    chain = pcbnew.SHAPE_LINE_CHAIN()
    for px, py in [(x, y), (x + w, y), (x + w, y + h), (x, y + h), (x, y)]:
        chain.Append(_mm_pos(px, py))
    if hasattr(chain, "SetClosed"):
        chain.SetClosed(True)
    z = pcbnew.ZONE(board)
    z.SetLayer(layer)
    z.AddPolygon(chain)
    z.SetIsFilled(True)
    net = _get_or_create_net(board, zone.get("net"))
    if net:
        z.SetNet(net)
    board.Add(z)
    return "Zone %s %.0fx%.0f" % (zone.get("net") or "?", w, h)


def apply_design(board, spec, replace_refs=True):
    logs = []
    errors = []
    if board is None:
        return logs, ["Açık PCB kartı yok."]

    resolve_component_positions(spec)

    board_mm = spec.get("board_mm") or {}
    w = float(board_mm.get("width", 50))
    h = float(board_mm.get("height", 50))
    default_w = float(spec.get("track_width_mm", 0.5))
    via_def = spec.get("via") if isinstance(spec.get("via"), dict) else {}

    for line in _enable_render_layers(board):
        logs.append(line)

    logs.append(_set_copper_layer_count(board, spec.get("copper_layers", 2)))
    logs.append(_add_board_outline(board, w, h))

    comps = spec.get("components") or []
    refs = [c.get("ref") for c in comps if c.get("ref")]
    if replace_refs and refs:
        n = _remove_footprints_by_ref(board, refs)
        if n:
            logs.append("%d footprint yenilendi." % n)

    for comp in comps:
        fp, msg = _place_component(board, comp)
        if fp is None:
            errors.append(msg)
        else:
            logs.append(msg)

    for tr in spec.get("tracks") or []:
        logs.append(_add_track(board, tr, default_w))

    for via in spec.get("vias") or []:
        logs.append(_add_via(board, via, via_def))

    for zone in spec.get("zones") or []:
        logs.append(_add_zone(board, zone))

    for line in _apply_silk_labels(board, spec):
        logs.append(line)

    title = (spec.get("title") or "LLM")[:50]
    try:
        t = pcbnew.PCB_TEXT(board)
        t.SetText("[%s]" % title)
        t.SetLayer(pcbnew.F_SilkS)
        t.SetPosition(_mm_pos(2, 2))
        board.Add(t)
    except Exception:
        pass

    try:
        pcbnew.Refresh()
    except Exception:
        pass

    return logs, errors
