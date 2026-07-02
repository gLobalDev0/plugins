# -*- coding: utf-8 -*-
"""
KiCad Action Plugin: PCB bileşen özeti + Groq LLM sohbeti.
Sohbet paneli mümkünse PCB düzenleyici çerçevesinin (wx adı: PcbFrame) altına yapışır;
bulunamazsa yüzen pencereye düşer.
"""

import threading

import pcbnew
import wx

import design_spec
import groq_llm
import pcb_apply
import pcb_snapshot
import power_rails

# KiCad kaynakları: #define PCB_EDIT_FRAME_NAME wxT("PcbFrame")
PCB_FRAME_NAME = "PcbFrame"

_docked_panel = None
_fallback_frame = None

# Uygula düğmesi — aktif / hazır / pasif
_APPLY_CLR_ACTIVE = wx.Colour(34, 139, 72)
_APPLY_CLR_READY = wx.Colour(46, 125, 50)
_APPLY_CLR_IDLE = wx.NullColour


def _iter_footprints(board):
    if board is None:
        return []
    fn = getattr(board, "GetFootprints", None)
    if callable(fn):
        return list(fn())
    return []


def format_pcb_component_report(board):
    """Footprint listesini çok satırlı metin olarak üretir."""
    footprints = _iter_footprints(board)
    lines = [
        "--- PCB bileşen listesi ---",
        "Adet: %d" % len(footprints),
    ]
    for fp in footprints:
        ref = fp.GetReference()
        val = fp.GetValue()
        try:
            pos = fp.GetPosition()
            x_mm = pcbnew.ToMM(pos.x)
            y_mm = pcbnew.ToMM(pos.y)
            loc = "%.2f, %.2f mm" % (x_mm, y_mm)
        except Exception:
            loc = "?"
        lines.append("  %s\t%s\t%s" % (ref, val, loc))
    lines.append("--- liste sonu ---")
    return "\n".join(lines) + "\n"


def list_pcb_components(board):
    report = format_pcb_component_report(board)
    print(report, end="")
    return report


def get_pcb_edit_frame():
    w = wx.FindWindowByName(PCB_FRAME_NAME)
    if isinstance(w, wx.Frame):
        return w
    for tlw in wx.GetTopLevelWindows():
        if not isinstance(tlw, wx.Frame) or not tlw.IsShown():
            continue
        title = tlw.GetTitle()
        if "PCB" in title and (
            "Editor" in title or "Düzenleyici" in title or "éditeur" in title.lower()
        ):
            return tlw
    return None


class VoltageIntentDialog(wx.Dialog):
    """Giriş/çıkış voltajları ve topo modu için yerel kural kontrolü."""

    def __init__(self, parent, chat_panel):
        super().__init__(
            parent,
            title="Güç: voltaj mantığı kontrolü",
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        self._chat = chat_panel
        root = wx.BoxSizer(wx.VERTICAL)
        g = wx.FlexGridSizer(0, 2, 6, 10)
        g.AddGrowableCol(1, 1)

        g.Add(wx.StaticText(self, label="Giriş (V):"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.vin_tc = wx.TextCtrl(self, value="12")
        g.Add(self.vin_tc, 1, wx.EXPAND)

        g.Add(wx.StaticText(self, label="Çıkışlar (V, virgül veya boşluk):"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.vouts_tc = wx.TextCtrl(self, value="4, 4, 4")
        g.Add(self.vouts_tc, 1, wx.EXPAND)

        g.Add(wx.StaticText(self, label="Model:"), 0, wx.ALIGN_CENTER_VERTICAL)
        modes = [
            "Seri bölme: çıkışların toplamı = giriş (Kirchhoff)",
            "Ayrı DC-DC (buck): her çıkış < giriş",
            "Ortak bara: her çıkış ≈ giriş (aynı potansiyel)",
        ]
        self.mode_ch = wx.Choice(self, choices=modes)
        self.mode_ch.SetSelection(1)
        g.Add(self.mode_ch, 1, wx.EXPAND)

        root.Add(g, 0, wx.EXPAND | wx.ALL, 10)
        self.stamp_cb = wx.CheckBox(
            self,
            label="Hata/uyarıları kart üzerine yaz (Cmts.User katmanı, PCB_TEXT)",
        )
        self.stamp_cb.SetValue(True)
        root.Add(self.stamp_cb, 0, wx.LEFT | wx.RIGHT, 10)

        btns = wx.StdDialogButtonSizer()
        ok = wx.Button(self, wx.ID_ANY, "Kontrol et")
        ca = wx.Button(self, wx.ID_CANCEL, "İptal")
        ok.Bind(wx.EVT_BUTTON, self.on_ok)
        btns.AddButton(ok)
        btns.AddButton(ca)
        btns.Realize()
        root.Add(btns, 0, wx.EXPAND | wx.ALL, 10)
        self.SetSizer(root)
        self.Fit()

    def on_ok(self, event):
        try:
            vin = float(self.vin_tc.GetValue().replace(",", ".").strip())
        except ValueError:
            wx.MessageBox("Giriş voltajı geçerli bir sayı olmalı.", "Hata", wx.OK | wx.ICON_WARNING)
            return
        vouts = power_rails.parse_voltage_list(self.vouts_tc.GetValue())
        mode = self.mode_ch.GetSelection()
        errs, warns = power_rails.validate_power_intent(vin, vouts, mode)

        lines = [
            "=== Voltaj / topo kontrolü (yerel kural) ===",
            "Giriş: %.2f V" % vin,
            "Çıkışlar: %s" % (vouts if vouts else "(boş)"),
            "Model: #%d" % mode,
        ]
        if errs:
            lines.append("[HATALAR]")
            lines.extend("  • " + e for e in errs)
        if warns:
            lines.append("[UYARILAR]")
            lines.extend("  • " + w for w in warns)
        if not errs and not warns:
            lines.append("Bu basit modele göre tutarlı görünüyor (yine de gerçek devreyi doğrulayın).")

        self._chat.output.AppendText("\n" + "\n".join(lines) + "\n\n")

        if self.stamp_cb.GetValue() and (errs or warns):
            board = pcbnew.GetBoard()
            stamp_lines = errs + warns
            added = power_rails.stamp_warnings_on_pcb(board, stamp_lines)
            if added:
                self._chat.output.AppendText(
                    "[Kart] %d satır Cmts.User üzerine yazıldı (geri al ile silinebilir).\n\n"
                    % len(added)
                )
            else:
                self._chat.output.AppendText(
                    "[Kart] Metin yazılamadı (pcbnew sürümü / izin); yalnızca yukarıdaki metne bakın.\n\n"
                )

        self.EndModal(wx.ID_OK)


class DockedChatPanel(wx.Panel):
    """PcbFrame altına yerleşen sohbet paneli."""

    def __init__(self, parent, dock_at_bottom=True):
        super().__init__(
            parent,
            style=wx.BORDER_SIMPLE | wx.TAB_TRAVERSAL | wx.CLIP_CHILDREN,
        )
        self._parent = parent
        self._dock_at_bottom = dock_at_bottom
        self._dock_h = 280
        self._messages = [{"role": "system", "content": groq_llm.SYSTEM_PROMPT}]
        self._pending_spec = None
        self._last_assistant_text = ""
        self._design_ready = False
        self._busy = False

        root = wx.BoxSizer(wx.VERTICAL)

        # Üst: sohbet geçmişi
        self.output = wx.TextCtrl(
            self,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_WORDWRAP | wx.HSCROLL,
        )
        root.Add(self.output, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 4)

        # Araç çubuğu
        tools = wx.BoxSizer(wx.HORIZONTAL)
        self.scan_btn = wx.Button(self, label="Kart taraması")
        self.volt_btn = wx.Button(self, label="Voltaj kontrolü")
        self.hide_btn = wx.Button(self, label="Gizle")
        tools.Add(self.scan_btn, 0, wx.RIGHT, 4)
        tools.Add(self.volt_btn, 0, wx.RIGHT, 4)
        tools.AddStretchSpacer(1)
        tools.Add(self.hide_btn, 0)
        root.Add(tools, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 4)

        # Uygula — belirgin
        self.apply_btn = wx.Button(self, label="Uygula — önce tasarımı onaylayın")
        self.apply_btn.Enable(False)
        self.apply_btn.SetMinSize((-1, 32))
        self.apply_btn.SetToolTip(
            "Tasarım onaylandıktan sonra JSON üretilir ve karta çizilir.\n"
            "Sohbette «Onaylıyorum» yazabilir veya bu düğmeye basabilirsiniz."
        )
        root.Add(self.apply_btn, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 4)

        self.status_lbl = wx.StaticText(
            self,
            label="Önce gereksinimleri konuşun; onay sonrası JSON üretilir.",
        )
        root.Add(self.status_lbl, 0, wx.LEFT | wx.RIGHT | wx.TOP, 6)

        # Alt: giriş + Gönder
        input_row = wx.BoxSizer(wx.HORIZONTAL)
        self.input = wx.TextCtrl(
            self,
            style=wx.TE_PROCESS_ENTER | wx.TE_MULTILINE,
            size=(-1, 44),
        )
        if hasattr(self.input, "SetHint"):
            self.input.SetHint("Mesajınız… (onay: Onaylıyorum)")
        input_row.Add(self.input, 1, wx.EXPAND | wx.RIGHT, 4)
        self.send_btn = wx.Button(self, label="Gönder")
        self.send_btn.SetMinSize((72, 44))
        input_row.Add(self.send_btn, 0, wx.EXPAND)
        root.Add(input_row, 0, wx.EXPAND | wx.ALL, 4)

        self.SetSizer(root)
        self._style_apply_button("idle")

        self.Bind(wx.EVT_BUTTON, self.on_send, self.send_btn)
        self.Bind(wx.EVT_TEXT_ENTER, self.on_send, self.input)
        self.Bind(wx.EVT_BUTTON, self.on_scan, self.scan_btn)
        self.Bind(wx.EVT_BUTTON, self.on_voltage_dialog, self.volt_btn)
        self.Bind(wx.EVT_BUTTON, self.on_apply, self.apply_btn)
        self.Bind(wx.EVT_BUTTON, self.on_hide, self.hide_btn)

        parent.Bind(wx.EVT_SIZE, self.on_parent_size)
        wx.CallAfter(self.sync_layout)

    def on_parent_size(self, event):
        self.sync_layout()
        event.Skip()

    def sync_layout(self):
        parent = self._parent
        if not parent:
            return
        try:
            w, h = parent.GetClientSize()
        except RuntimeError:
            return
        if not self._dock_at_bottom:
            self.SetSize(0, 0, w, h)
            self.SetPosition((0, 0))
            return
        self._dock_h = min(380, max(200, int(h * 0.30)))
        self.SetSize(0, h - self._dock_h, w, self._dock_h)
        self.SetPosition((0, h - self._dock_h))
        self.Raise()

    def on_hide(self, event):
        self.Hide()

    def _trim_messages(self):
        m = self._messages
        if len(m) <= 10:
            return m
        return [m[0]] + m[-9:]

    def on_voltage_dialog(self, event):
        dlg = VoltageIntentDialog(self, self)
        dlg.ShowModal()
        dlg.Destroy()

    def on_scan(self, event):
        board = pcbnew.GetBoard()
        snap = pcb_snapshot.build_expert_snapshot(board)
        self.output.AppendText("\n--- [Kart taraması — LLM ile aynı özet] ---\n%s\n" % snap)

    def _style_apply_button(self, mode):
        """mode: idle | ready | active"""
        btn = self.apply_btn
        if mode == "active":
            btn.SetBackgroundColour(_APPLY_CLR_ACTIVE)
            btn.SetForegroundColour(wx.WHITE)
            btn.Enable(True)
        elif mode == "ready":
            btn.SetBackgroundColour(_APPLY_CLR_READY)
            btn.SetForegroundColour(wx.WHITE)
            btn.Enable(True)
        else:
            btn.SetBackgroundColour(_APPLY_CLR_IDLE)
            btn.SetForegroundColour(wx.BLACK)
            btn.Enable(False)

    def _set_busy(self, busy):
        self._busy = busy
        self.send_btn.Enable(not busy)
        self.input.Enable(not busy)
        self.scan_btn.Enable(not busy)
        self.volt_btn.Enable(not busy)
        if busy:
            self.apply_btn.Enable(False)
            self.status_lbl.SetLabel("Groq API yanıt bekleniyor… (llama-3.1-8b-instant)")
        elif not self._design_ready and self._pending_spec is None:
            self.status_lbl.SetLabel(
                "Önce gereksinimleri konuşun; onay sonrası JSON üretilir."
            )

    def _update_apply_button(self, assistant_text):
        self._last_assistant_text = assistant_text or ""
        spec, _errs = design_spec.parse_from_assistant(self._last_assistant_text)
        self._pending_spec = spec
        proposed = design_spec.assistant_proposed_design(self._last_assistant_text)
        self._design_ready = proposed or spec is not None

        if spec is not None:
            title = spec.get("title") or "tasarım"
            n = len(spec.get("components") or [])
            self.apply_btn.SetLabel("Uygula — karta çiz (%s, %d parça)" % (title[:20], n))
            self._style_apply_button("active")
            self.status_lbl.SetLabel(
                "JSON hazır. Uygula ile karta çizin (3D: Alt+3, mask katmanları açık)."
            )
        elif self._design_ready:
            self.apply_btn.SetLabel("Uygula — onayla ve JSON üret")
            self._style_apply_button("ready")
            self.status_lbl.SetLabel(
                "Tasarım özeti hazır. «Onaylıyorum» yazın veya Uygula ile JSON isteyin."
            )
        else:
            self.apply_btn.SetLabel("Uygula — önce tasarımı onaylayın")
            self._style_apply_button("idle")
            self.status_lbl.SetLabel(
                "Önce gereksinimleri konuşun; onay sonrası JSON üretilir."
            )

    def _run_llm(self, user_block, display_user_text, json_mode=False, after_ok=None):
        self._set_busy(True)
        self._messages.append({"role": "user", "content": user_block})

        def worker():
            reply, err = None, None
            try:
                msgs = self._trim_messages()
                extra = groq_llm.JSON_GENERATION_PROMPT if json_mode else None
                reply, err = groq_llm.chat_completion(msgs, extra_system=extra)
            except Exception as ex:
                err = "Beklenmeyen hata: %s" % ex

            def finish():
                self._set_busy(False)
                if err:
                    self.output.AppendText("[Hata]\n%s\n\n" % err)
                    if self._messages and self._messages[-1].get("role") == "user":
                        self._messages.pop()
                else:
                    self.output.AppendText("[Asistan]\n%s\n\n" % reply)
                    self._messages.append({"role": "assistant", "content": reply})
                    self._update_apply_button(reply)
                    if after_ok:
                        after_ok(reply)
                self.input.SetFocus()

            wx.CallAfter(finish)

        threading.Thread(target=worker, daemon=True).start()

    def _request_json_from_llm(self, after_ok=None):
        """Onay sonrası JSON üret (sohbet geçmişi + JSON talimatı)."""
        board = pcbnew.GetBoard()
        ctx = pcb_snapshot.build_expert_snapshot(board, max_chars=3500)
        user_text = "Onaylıyorum. Tartıştığımız tasarımı uygulanabilir JSON olarak üret."
        user_block = "[Güncel PCB]\n%s\n\n[Kullanıcı — ONAY]\n%s" % (ctx, user_text)
        self.output.AppendText("[Sen — onay]\n%s\n\n" % user_text)
        self._run_llm(user_block, user_text, json_mode=True, after_ok=after_ok)

    def _apply_spec_to_board(self, spec):
        board = pcbnew.GetBoard()
        if board is None:
            wx.MessageBox("Açık bir PCB kartı gerekli.", "Uygula", wx.OK | wx.ICON_WARNING)
            return
        bm = spec.get("board_mm") or {}
        msg = (
            "Karta çizilecek:\n"
            "• Kenar (yoksa) %.0f×%.0f mm, %d katman\n"
            "• Mask/Silk katmanları, %d bileşen, iz/via/zone\n\n"
            "Devam?"
        ) % (
            float(bm.get("width", 50)),
            float(bm.get("height", 50)),
            int(spec.get("copper_layers", 2)),
            len(spec.get("components") or []),
        )
        if wx.MessageBox(msg, "Tasarımı uygula", wx.YES_NO | wx.ICON_QUESTION) != wx.YES:
            return
        self._set_busy(True)
        logs, errors = pcb_apply.apply_design(board, spec)
        self.output.AppendText("\n=== [Kart çizildi] ===\n")
        for line in logs:
            self.output.AppendText("  • %s\n" % line)
        if errors:
            self.output.AppendText("[Hatalar]\n")
            for e in errors:
                self.output.AppendText("  • %s\n" % e)
        self.output.AppendText(
            "\nKaydedin → DRC → View→3D Viewer (Alt+3) ile yeşil maskayı kontrol edin.\n\n"
        )
        self._set_busy(False)
        self._update_apply_button(self._last_assistant_text)
        try:
            frame = get_pcb_edit_frame()
            if frame:
                frame.Refresh()
        except Exception:
            pass

    def on_apply(self, event):
        if self._busy:
            return
        spec = self._pending_spec
        if spec is None:
            spec, errs = design_spec.parse_from_assistant(self._last_assistant_text)

        if spec is not None:
            self._apply_spec_to_board(spec)
            return

        if not self._design_ready:
            wx.MessageBox(
                "Henüz onaylanacak bir tasarım özeti yok.\n\n"
                "Önce kart gereksinimlerinizi yazın; asistan soruları yanıtladıktan sonra "
                "«Onaylıyorum» deyin veya tekrar Uygula'ya basın.",
                "Uygula",
                wx.OK | wx.ICON_INFORMATION,
            )
            return

        if wx.MessageBox(
            "Tasarımı onaylayıp JSON üretmek istiyor musunuz?\n"
            "(Ardından karta çizim için tekrar sorulacak.)",
            "JSON üret",
            wx.YES_NO | wx.ICON_QUESTION,
        ) != wx.YES:
            return

        def after_json(reply):
            sp, errs = design_spec.parse_from_assistant(reply)
            if sp and wx.MessageBox(
                "JSON alındı. Karta şimdi çizilsin mi?",
                "Çizim",
                wx.YES_NO | wx.ICON_QUESTION,
            ) == wx.YES:
                self._apply_spec_to_board(sp)
            elif not sp and errs:
                self.output.AppendText("[Not] %s\n\n" % errs[0])

        self._request_json_from_llm(after_ok=after_json)

    def on_send(self, event):
        text = self.input.GetValue().strip()
        if not text or self._busy:
            return

        board = pcbnew.GetBoard()
        ctx = pcb_snapshot.build_expert_snapshot(board)
        json_mode = design_spec.is_approval_message(text)

        if json_mode:
            ctx = pcb_snapshot.build_expert_snapshot(board, max_chars=3500)
            user_block = (
                "[Güncel PCB]\n%s\n\n[Kullanıcı — TASARIM ONAYI]\n%s"
                % (ctx, text)
            )
        else:
            user_block = "[Güncel PCB]\n%s\n\n[Kullanıcı]\n%s" % (ctx, text)

        self.output.AppendText("[Sen]\n%s\n\n" % text)
        self.output.AppendText("[Sistem] Groq'a gönderiliyor…\n\n")
        self.input.SetValue("")

        if json_mode:

            def after_json(reply):
                sp, errs = design_spec.parse_from_assistant(reply)
                if sp and wx.MessageBox(
                    "JSON hazır. Karta şimdi çizilsin mi?",
                    "Çizim",
                    wx.YES_NO | wx.ICON_QUESTION,
                ) == wx.YES:
                    self._apply_spec_to_board(sp)
                elif not sp and errs:
                    self.output.AppendText("[Not] %s\n\n" % errs[0])

            self._run_llm(user_block, text, json_mode=True, after_ok=after_json)
        else:
            self._run_llm(user_block, text, json_mode=False)


class ChatFrame(wx.Frame):
    """PcbFrame bulunamazsa kullanılan yedek pencere."""

    def __init__(self):
        style = wx.DEFAULT_FRAME_STYLE | wx.STAY_ON_TOP
        super().__init__(None, title="LLM Sohbet (yedek pencere)", style=style, size=(480, 400))
        self.panel = DockedChatPanel(self, dock_at_bottom=False)

        self.Bind(wx.EVT_CLOSE, self.on_close)

    def on_close(self, event):
        self.Hide()
        event.Veto()


def _show_ui(pcb_report):
    global _docked_panel, _fallback_frame
    parent = get_pcb_edit_frame()

    if parent is not None:
        panel_ok = False
        if _docked_panel is not None:
            try:
                panel_ok = _docked_panel.GetParent() is parent
            except RuntimeError:
                panel_ok = False
        if not panel_ok:
            if _docked_panel is not None:
                try:
                    _docked_panel.Destroy()
                except Exception:
                    pass
            _docked_panel = DockedChatPanel(parent, dock_at_bottom=True)
        if pcb_report:
            _docked_panel.output.AppendText(pcb_report)
        _docked_panel.Show()
        _docked_panel.sync_layout()
        _docked_panel.Raise()
        return

    if _fallback_frame is None:
        _fallback_frame = ChatFrame()
    if pcb_report:
        _fallback_frame.panel.output.AppendText(pcb_report)
    _fallback_frame.Show()
    _fallback_frame.Raise()


class MerhabaLLM(pcbnew.ActionPlugin):
    def defaults(self):
        self.name = "LLM Mesaj Testi"
        self.category = "AITools"
        self.description = (
            "Groq LLM asistanı; tasarım JSON'u + Uygula ile footprint/iz/via/zone çizer."
        )
        self.show_toolbar_button = True

    def Run(self):
        board = pcbnew.GetBoard()
        report = list_pcb_components(board)
        k = groq_llm.load_groq_api_key()
        if k:
            print("[merhabaa_llm] Groq API anahtarı yüklendi (%d karakter)." % len(k))
        else:
            print(
                "[merhabaa_llm] Groq anahtarı YOK. Beklenen dosya:\n  %s"
                % groq_llm.expected_key_file_path()
            )
        wx.CallAfter(_show_ui, report)


MerhabaLLM().register()
