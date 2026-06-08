"""
ZeroTrace — main UI
CustomTkinter dark-themed desktop app for Windows.
"""

import json
import threading
import logging
from tkinter import messagebox, simpledialog

import customtkinter as ctk

import fast_flags as ff
import presets as ps
from proxy import AssetBlockerProxy, CRYPTO_OK, PROXY_PORT

logging.basicConfig(level=logging.INFO, format='%(levelname)s %(name)s: %(message)s')

ctk.set_appearance_mode('dark')
ctk.set_default_color_theme('blue')

# Colours
C_GREEN  = '#4ade80'
C_RED    = '#f87171'
C_YELLOW = '#fbbf24'
C_GRAY   = '#6b7280'
C_DARK   = '#1e1e2e'
C_PANEL  = '#2a2a3e'
C_BTN_DEL = ('#7f1d1d', '#991b1b')


class ZeroTraceApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title('ZeroTrace')
        self.geometry('960x620')
        self.minsize(860, 560)
        self.configure(fg_color=C_DARK)

        self._proxy = AssetBlockerProxy()
        self._preset_name: str = ''
        self._status_job: str | None = None

        self._build_layout()
        self._load_presets_list()
        self._refresh_status()

        self.protocol('WM_DELETE_WINDOW', self._on_close)

    # ─── Layout ───────────────────────────────────────────────────────────────

    def _build_layout(self):
        self._build_sidebar()
        self._build_main()

    def _build_sidebar(self):
        sb = ctk.CTkFrame(self, width=210, corner_radius=0, fg_color=C_PANEL)
        sb.pack(side='left', fill='y')
        sb.pack_propagate(False)

        # Logo
        ctk.CTkLabel(
            sb, text='ZeroTrace',
            font=ctk.CTkFont(size=24, weight='bold'),
            text_color='white',
        ).pack(pady=(24, 0))
        ctk.CTkLabel(
            sb, text='Roblox Optimizer',
            font=ctk.CTkFont(size=11),
            text_color=C_GRAY,
        ).pack(pady=(2, 18))

        _divider(sb)

        # Preset selector
        _label(sb, 'PRESET', padx=14)
        self._preset_var = ctk.StringVar()
        self._preset_combo = ctk.CTkComboBox(
            sb, variable=self._preset_var,
            command=self._on_preset_select,
            width=182, height=32,
        )
        self._preset_combo.pack(padx=14, pady=(4, 8))

        ctk.CTkButton(
            sb, text='Save Preset', height=32,
            command=self._save_preset,
        ).pack(padx=14, pady=3, fill='x')

        ctk.CTkButton(
            sb, text='Delete Preset', height=32,
            fg_color=C_BTN_DEL[0], hover_color=C_BTN_DEL[1],
            command=self._delete_preset,
        ).pack(padx=14, pady=3, fill='x')

        _divider(sb)

        # Roblox detection
        _label(sb, 'ROBLOX', padx=14)
        self._roblox_label = ctk.CTkLabel(
            sb, text='● Detecting…',
            font=ctk.CTkFont(size=11), text_color=C_GRAY, anchor='w',
        )
        self._roblox_label.pack(padx=14, pady=(2, 4), fill='x')

        self._version_label = ctk.CTkLabel(
            sb, text='',
            font=ctk.CTkFont(size=10), text_color=C_GRAY, anchor='w',
            wraplength=180,
        )
        self._version_label.pack(padx=14, fill='x')

        # Push everything else to bottom
        ctk.CTkFrame(sb, fg_color='transparent').pack(expand=True)

        ctk.CTkLabel(
            sb, text='v1.0.0  |  github/zerotrace',
            font=ctk.CTkFont(size=9), text_color=C_GRAY,
        ).pack(pady=10)

    def _build_main(self):
        main = ctk.CTkFrame(self, corner_radius=0, fg_color='transparent')
        main.pack(side='left', fill='both', expand=True, padx=16, pady=16)

        self._tabs = ctk.CTkTabview(main, fg_color=C_PANEL, segmented_button_fg_color=C_DARK)
        self._tabs.pack(fill='both', expand=True)
        self._tabs.add('⚡  Fast Flags')
        self._tabs.add('🛡  Asset Blocker')

        self._build_flags_tab()
        self._build_blocker_tab()

    # ── Fast Flags tab ────────────────────────────────────────────────────────

    def _build_flags_tab(self):
        tab = self._tabs.tab('⚡  Fast Flags')

        top = ctk.CTkFrame(tab, fg_color='transparent')
        top.pack(fill='x', pady=(8, 6))

        # Status pill
        self._flags_pill = _StatusPill(top, 'Inactive')
        self._flags_pill.pack(side='left', padx=6)

        # Buttons
        btn_frame = ctk.CTkFrame(top, fg_color='transparent')
        btn_frame.pack(side='right', padx=4)

        ctk.CTkButton(
            btn_frame, text='Apply Flags', width=120, height=34,
            font=ctk.CTkFont(weight='bold'),
            command=self._apply_flags,
        ).pack(side='left', padx=4)

        ctk.CTkButton(
            btn_frame, text='Restore Default', width=130, height=34,
            fg_color='#374151', hover_color='#4b5563',
            command=self._restore_flags,
        ).pack(side='left', padx=4)

        ctk.CTkLabel(
            tab, text='Flags (JSON) — edit before applying:',
            anchor='w', text_color=C_GRAY, font=ctk.CTkFont(size=11),
        ).pack(fill='x', padx=4, pady=(4, 2))

        self._flags_box = ctk.CTkTextbox(
            tab,
            font=ctk.CTkFont(family='Consolas', size=11),
            fg_color='#12121e',
            wrap='none',
        )
        self._flags_box.pack(fill='both', expand=True, pady=(0, 4))

    # ── Asset Blocker tab ─────────────────────────────────────────────────────

    def _build_blocker_tab(self):
        tab = self._tabs.tab('🛡  Asset Blocker')

        # Header row
        hdr = ctk.CTkFrame(tab, fg_color='transparent')
        hdr.pack(fill='x', pady=(8, 4))

        ctk.CTkLabel(
            hdr, text='Asset Blocker Proxy',
            font=ctk.CTkFont(size=15, weight='bold'),
        ).pack(side='left', padx=6)

        self._proxy_switch = ctk.CTkSwitch(
            hdr, text='', width=46,
            command=self._toggle_proxy,
        )
        self._proxy_switch.pack(side='right', padx=10)

        # Proxy status
        self._proxy_pill = _StatusPill(tab, 'Inactive')
        self._proxy_pill.pack(anchor='w', padx=6, pady=(0, 6))

        # Info banner
        ctk.CTkLabel(
            tab,
            text=(
                'Intercepts HTTPS traffic to assetdelivery.roblox.com and blocks listed asset IDs.\n'
                'System proxy is set automatically when the proxy is active.'
            ),
            text_color=C_GRAY, font=ctk.CTkFont(size=10),
            justify='left', anchor='w',
        ).pack(fill='x', padx=6, pady=(0, 6))

        # CA certificate section
        if CRYPTO_OK:
            cert_frame = ctk.CTkFrame(tab, fg_color=C_DARK, corner_radius=8)
            cert_frame.pack(fill='x', padx=4, pady=(0, 8))

            ctk.CTkLabel(
                cert_frame,
                text='SSL Certificate  (required for HTTPS interception)',
                font=ctk.CTkFont(size=12, weight='bold'),
            ).pack(padx=12, pady=(10, 4), anchor='w')

            self._ca_status_label = ctk.CTkLabel(
                cert_frame, text='● Checking…',
                font=ctk.CTkFont(size=11), text_color=C_GRAY, anchor='w',
            )
            self._ca_status_label.pack(padx=12, pady=(0, 4), fill='x')

            cert_btns = ctk.CTkFrame(cert_frame, fg_color='transparent')
            cert_btns.pack(padx=12, pady=(0, 10), anchor='w')

            ctk.CTkButton(
                cert_btns, text='Install CA Certificate', width=170, height=30,
                fg_color='#1d4ed8', hover_color='#2563eb',
                command=self._install_ca,
            ).pack(side='left', padx=(0, 6))

            ctk.CTkButton(
                cert_btns, text='Uninstall CA Certificate', width=170, height=30,
                fg_color='#374151', hover_color='#4b5563',
                command=self._uninstall_ca,
            ).pack(side='left')
        else:
            ctk.CTkLabel(
                tab,
                text='⚠  cryptography package not installed — HTTPS interception disabled.\n'
                     'Run:  pip install cryptography',
                text_color=C_YELLOW, font=ctk.CTkFont(size=11),
                anchor='w', justify='left',
            ).pack(fill='x', padx=6, pady=4)

        # Blocked assets editor
        ctk.CTkLabel(
            tab, text='Blocked Asset IDs (one per line):',
            anchor='w', text_color=C_GRAY, font=ctk.CTkFont(size=11),
        ).pack(fill='x', padx=6, pady=(0, 2))

        self._assets_box = ctk.CTkTextbox(
            tab,
            font=ctk.CTkFont(family='Consolas', size=11),
            fg_color='#12121e',
        )
        self._assets_box.pack(fill='both', expand=True, pady=(0, 4))

        ctk.CTkLabel(
            tab, text='Changes to the list take effect immediately on the running proxy.',
            text_color=C_GRAY, font=ctk.CTkFont(size=10), anchor='w',
        ).pack(fill='x', padx=6)

        # Live-update proxy whenever the text changes
        self._assets_box.bind('<KeyRelease>', self._on_assets_changed)

    # ─── Preset helpers ───────────────────────────────────────────────────────

    def _load_presets_list(self):
        names = ps.list_presets()
        self._preset_combo.configure(values=names)
        self._preset_combo.set(names[0])
        self._load_preset(names[0])

    def _load_preset(self, name: str):
        data = ps.load_preset(name)
        if data is None:
            data = {'name': name, 'fast_flags': {}, 'blocked_assets': []}
        self._preset_name = name
        self._populate_from_preset(data)

    def _populate_from_preset(self, data: dict):
        flags = data.get('fast_flags', {})
        assets = data.get('blocked_assets', [])

        self._flags_box.delete('1.0', 'end')
        self._flags_box.insert('1.0', json.dumps(flags, indent=2))

        self._assets_box.delete('1.0', 'end')
        self._assets_box.insert('1.0', '\n'.join(str(a) for a in assets))

        self._proxy.set_blocked(assets)

    def _on_preset_select(self, name: str):
        self._load_preset(name)

    def _save_preset(self):
        name = simpledialog.askstring(
            'Save Preset', 'Preset name:',
            initialvalue=self._preset_name,
            parent=self,
        )
        if not name:
            return
        try:
            flags = json.loads(self._flags_box.get('1.0', 'end').strip() or '{}')
        except json.JSONDecodeError:
            messagebox.showerror('Invalid JSON', 'The Fast Flags content is not valid JSON.', parent=self)
            return
        assets = _parse_asset_ids(self._assets_box.get('1.0', 'end'))
        ps.save_preset(name, {'name': name, 'fast_flags': flags, 'blocked_assets': assets})
        names = ps.list_presets()
        self._preset_combo.configure(values=names)
        self._preset_combo.set(name)
        self._preset_name = name
        self._show_toast(f'Preset "{name}" saved.')

    def _delete_preset(self):
        name = self._preset_combo.get()
        if ps.is_bundled(name):
            messagebox.showwarning('Built-in preset', 'Built-in presets cannot be deleted.', parent=self)
            return
        if not messagebox.askyesno('Delete preset', f'Delete "{name}"?', parent=self):
            return
        ps.delete_preset(name)
        self._load_presets_list()

    # ─── Fast Flags ───────────────────────────────────────────────────────────

    def _apply_flags(self):
        try:
            raw = self._flags_box.get('1.0', 'end').strip()
            flags = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            messagebox.showerror('Invalid JSON', 'Fix the JSON before applying.', parent=self)
            return
        try:
            ff.apply_flags(flags)
            self._refresh_status()
            self._show_toast('Fast Flags applied. Restart Roblox to take effect.')
        except RuntimeError as e:
            messagebox.showerror('Error', str(e), parent=self)

    def _restore_flags(self):
        removed = ff.restore_flags()
        self._refresh_status()
        if removed:
            self._show_toast('ClientAppSettings.json removed. Roblox defaults restored.')
        else:
            self._show_toast('No flags file found — already clean.')

    # ─── Asset Blocker ────────────────────────────────────────────────────────

    def _toggle_proxy(self):
        if self._proxy_switch.get():
            success = self._proxy.start()
            if not success:
                self._proxy_switch.deselect()
                messagebox.showerror(
                    'Proxy Error',
                    f'Could not bind to port {PROXY_PORT}.\n'
                    'Another process may be using it.',
                    parent=self,
                )
        else:
            self._proxy.stop()
        self._refresh_status()

    def _install_ca(self):
        if not messagebox.askyesno(
            'Install Certificate',
            'ZeroTrace will install a local CA certificate to the Windows '
            'Trusted Root store.\n\nThis is needed to intercept HTTPS traffic '
            'for asset blocking.\nYou may see a UAC prompt.\n\nContinue?',
            parent=self,
        ):
            return
        # Run in thread to avoid freezing UI
        def _do():
            ok = self._proxy.install_ca()
            self.after(0, lambda: self._on_ca_install_done(ok))
        threading.Thread(target=_do, daemon=True).start()

    def _on_ca_install_done(self, ok: bool):
        if ok:
            self._show_toast('CA Certificate installed successfully.')
        else:
            messagebox.showerror(
                'Install Failed',
                'Could not install the certificate.\n'
                'Try running ZeroTrace as Administrator.',
                parent=self,
            )
        self._refresh_status()

    def _uninstall_ca(self):
        if not messagebox.askyesno('Uninstall', 'Remove ZeroTrace CA Certificate?', parent=self):
            return
        def _do():
            ok = self._proxy.uninstall_ca()
            self.after(0, lambda: self._refresh_status())
            if ok:
                self.after(0, lambda: self._show_toast('CA Certificate removed.'))
        threading.Thread(target=_do, daemon=True).start()

    def _on_assets_changed(self, _event=None):
        raw = self._assets_box.get('1.0', 'end')
        assets = _parse_asset_ids(raw)
        self._proxy.set_blocked(assets)

    # ─── Status refresh ───────────────────────────────────────────────────────

    def _refresh_status(self):
        # Roblox
        if ff.roblox_found():
            self._roblox_label.configure(text='● Found', text_color=C_GREEN)
            ver = ff.get_roblox_version_label()
            self._version_label.configure(text=ver)
        else:
            self._roblox_label.configure(text='● Not found', text_color=C_RED)
            self._version_label.configure(text='Check %LOCALAPPDATA%\\Roblox\\Versions')

        # Fast flags
        if ff.flags_active():
            self._flags_pill.set_active('Active — flags applied')
        else:
            self._flags_pill.set_inactive('Inactive')

        # Proxy
        if self._proxy.running:
            self._proxy_pill.set_active(f'Active — proxy on port {PROXY_PORT}')
        else:
            self._proxy_pill.set_inactive('Inactive')

        # CA cert
        if CRYPTO_OK and hasattr(self, '_ca_status_label'):
            def _check():
                installed = self._proxy.ca_installed()
                def _update():
                    if installed:
                        self._ca_status_label.configure(
                            text='● Certificate installed', text_color=C_GREEN
                        )
                    else:
                        self._ca_status_label.configure(
                            text='● Certificate not installed — click Install to enable HTTPS blocking',
                            text_color=C_YELLOW,
                        )
                self.after(0, _update)
            threading.Thread(target=_check, daemon=True).start()

        # Schedule next auto-refresh (every 5 s)
        if self._status_job:
            self.after_cancel(self._status_job)
        self._status_job = self.after(5000, self._refresh_status)

    # ─── Toast notification ───────────────────────────────────────────────────

    def _show_toast(self, msg: str):
        toast = ctk.CTkToplevel(self)
        toast.overrideredirect(True)
        toast.attributes('-topmost', True)
        toast.configure(fg_color='#1e3a5f')

        ctk.CTkLabel(
            toast, text=msg,
            font=ctk.CTkFont(size=12),
            text_color='white',
            padx=18, pady=10,
        ).pack()

        # Position bottom-right of main window
        self.update_idletasks()
        x = self.winfo_x() + self.winfo_width() - 340
        y = self.winfo_y() + self.winfo_height() - 70
        toast.geometry(f'+{x}+{y}')
        toast.after(2800, toast.destroy)

    # ─── Close ────────────────────────────────────────────────────────────────

    def _on_close(self):
        if self._proxy.running:
            self._proxy.stop()
        self.destroy()


# ─── Reusable widgets ─────────────────────────────────────────────────────────

class _StatusPill(ctk.CTkFrame):
    def __init__(self, parent, initial_text='', **kwargs):
        super().__init__(parent, corner_radius=20, fg_color='#374151', **kwargs)
        self._label = ctk.CTkLabel(
            self, text=f'● {initial_text}',
            font=ctk.CTkFont(size=11),
            text_color=C_GRAY,
            padx=10, pady=4,
        )
        self._label.pack()

    def set_active(self, text: str):
        self.configure(fg_color='#14532d')
        self._label.configure(text=f'● {text}', text_color=C_GREEN)

    def set_inactive(self, text: str):
        self.configure(fg_color='#374151')
        self._label.configure(text=f'● {text}', text_color=C_GRAY)

    def set_warning(self, text: str):
        self.configure(fg_color='#78350f')
        self._label.configure(text=f'● {text}', text_color=C_YELLOW)


def _label(parent, text: str, padx=0):
    ctk.CTkLabel(
        parent, text=text,
        font=ctk.CTkFont(size=9, weight='bold'),
        text_color=C_GRAY, anchor='w',
    ).pack(padx=padx, pady=(10, 0), fill='x')


def _divider(parent):
    ctk.CTkFrame(parent, height=1, fg_color='#374151').pack(fill='x', padx=12, pady=8)


def _parse_asset_ids(raw: str) -> list[int]:
    ids = []
    for line in raw.splitlines():
        line = line.strip()
        if line.isdigit():
            ids.append(int(line))
    return ids
