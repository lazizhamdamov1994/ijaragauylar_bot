"""
Ijaraga Uylar - Windows desktop admin dasturi.

Imkoniyatlar:
  - Yangi e'lon joylash (mahalliy rasmlar yoki OLX havolasidan)
  - Kutilayotgan e'lon/obuna so'rovlarini tasdiqlash/rad etish
  - Asosiy statistikani ko'rish

Server bilan /api/desktop/* orqali (web/api_desktop.py) ishlaydi - token
botdan /desktop_token buyrug'i bilan olinadi.

Dizayn: CustomTkinter (saytdagi #FF3B5C korall brend palitrasiga mos),
chap tomonda sidebar navigatsiya, o'ng tomonda karta-uslubidagi kontent.
"""
import os
import sys
import tempfile
import threading
import tkinter as tk
import urllib.request
from tkinter import filedialog, messagebox, simpledialog

import customtkinter as ctk

from api_client import ApiClient, ApiError, load_config, save_config

# ---------------------------------------------------------------------------
# Brend palitrasi (static/site.css dagi --brand/--ink/--muted token'lariga mos)
# ---------------------------------------------------------------------------
C = {
    "brand": "#FF3B5C",
    "brand_dark": "#E01E45",
    "brand_light": "#FFEBEF",
    "gold": "#D6960B",
    "ink": "#101826",
    "ink_soft": "#1A2436",
    "muted": "#6B7690",
    "line": "#E7EAF1",
    "bg": "#FFFFFF",
    "bg_soft": "#F6F8FA",
    "success": "#1F9D55",
    "success_bg": "#EAFBF1",
    "danger": "#E0334B",
    "danger_bg": "#FDEDEF",
    "warning": "#B8720A",
    "warning_bg": "#FDF3DE",
}

RENTAL_TYPES = [
    ("uzoq_muddat", "Uzoq muddatli ijara"),
    ("kunlik", "Kunlik ijara"),
    ("dacha", "Dacha"),
    ("mehmonxona", "Mehmonxona"),
]

ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")  # faqat bazaviy shakllar uchun - ranglarni o'zimiz belgilaymiz


def run_in_background(fn, on_done=None, on_error=None):
    """GUI oqimini (mainloop) bloklamasdan tarmoq chaqiruvini fon ipida
    bajaradi, natija/xatoni Tkinter'ning o'z navbatiga (thread-safe)
    qaytaradi."""
    def worker():
        try:
            result = fn()
        except Exception as e:
            if on_error:
                # MUHIM: `e` ni lambda'ning standart argumentiga bog'laymiz -
                # Python `except ... as e` bloki tugagach `e`ni avtomatik
                # o'chiradi, shuning uchun keyinroq (root.after orqali)
                # chaqiriladigan lambda ichida oddiy closure sifatida "e"
                # ishlatilsa, NameError beradi.
                root_ref.after(0, lambda e=e: on_error(e))
            return
        if on_done:
            root_ref.after(0, lambda: on_done(result))
    threading.Thread(target=worker, daemon=True).start()


# Fizik tugma kodlari (Windows'da klaviatura tiliga bog'liq EMAS - lotin,
# kiril yoki boshqa tartibda ham bir xil) - standart Tk Ctrl+V/C/X bog'lanishi
# esa harfning o'zi (keysym) bo'yicha ishlaydi, shuning uchun rus/o'zbek kiril
# klaviatura tartibida Ctrl+V/C/X umuman ishlamay qolishi mumkin edi.
_VK_PASTE, _VK_COPY, _VK_CUT, _VK_SELECT_ALL = 86, 67, 88, 65  # V, C, X, A


def _universal_clipboard_handler(event):
    if not (event.state & 0x4):  # Ctrl bosilganmi
        return
    widget = event.widget
    if event.keycode == _VK_PASTE:
        try:
            widget.event_generate("<<Paste>>")
        except tk.TclError:
            pass
        return "break"
    if event.keycode == _VK_COPY:
        try:
            widget.event_generate("<<Copy>>")
        except tk.TclError:
            pass
        return "break"
    if event.keycode == _VK_CUT:
        try:
            widget.event_generate("<<Cut>>")
        except tk.TclError:
            pass
        return "break"
    if event.keycode == _VK_SELECT_ALL and hasattr(widget, "selection_range"):
        try:
            widget.selection_range(0, "end")
        except tk.TclError:
            pass
        return "break"


root_ref = None  # ildiz oyna - run_in_background() uchun (modul darajasida, bitta oyna bo'lgani uchun)


def _resource_path(name: str) -> str:
    """PyInstaller --onefile bilan yig'ilganda fayllar vaqtinchalik
    papkaga (_MEIPASS) ochiladi - shuni ham, oddiy ishga tushirishni ham
    qo'llab-quvvatlaydi."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


def section_header(parent, title: str, subtitle: str = ""):
    wrap = ctk.CTkFrame(parent, fg_color="transparent")
    wrap.pack(fill="x", padx=28, pady=(24, 4))
    ctk.CTkLabel(wrap, text=title, font=ctk.CTkFont(size=22, weight="bold"), text_color=C["ink"]).pack(anchor="w")
    if subtitle:
        ctk.CTkLabel(wrap, text=subtitle, font=ctk.CTkFont(size=13), text_color=C["muted"]).pack(anchor="w", pady=(2, 0))
    return wrap


def card(parent, **kwargs):
    defaults = dict(fg_color=C["bg"], corner_radius=16, border_width=1, border_color=C["line"])
    defaults.update(kwargs)
    return ctk.CTkFrame(parent, **defaults)


def primary_button(parent, text, command, **kwargs):
    defaults = dict(
        fg_color=C["brand"], hover_color=C["brand_dark"], text_color="white",
        font=ctk.CTkFont(size=13, weight="bold"), corner_radius=10, height=38,
    )
    defaults.update(kwargs)
    return ctk.CTkButton(parent, text=text, command=command, **defaults)


def secondary_button(parent, text, command, **kwargs):
    defaults = dict(
        fg_color="transparent", hover_color=C["bg_soft"], text_color=C["ink"],
        border_width=1, border_color=C["line"],
        font=ctk.CTkFont(size=13), corner_radius=10, height=38,
    )
    defaults.update(kwargs)
    return ctk.CTkButton(parent, text=text, command=command, **defaults)


def styled_entry(parent, textvariable=None, placeholder="", width=360, show=None):
    kwargs = dict(
        textvariable=textvariable, width=width, height=38, corner_radius=10,
        fg_color=C["bg_soft"], border_color=C["line"], border_width=1,
        text_color=C["ink"], placeholder_text=placeholder,
        placeholder_text_color=C["muted"],
    )
    if show:
        kwargs["show"] = show
    return ctk.CTkEntry(parent, **kwargs)


class StatusPill(ctk.CTkLabel):
    """Yashil/qizil/sariq fonli status ko'rsatkichi - oddiy rangli matn
    o'rniga dashboard'larda keng tarqalgan "pill" uslubi."""

    _STYLES = {
        "success": (C["success_bg"], C["success"]),
        "error": (C["danger_bg"], C["danger"]),
        "warning": (C["warning_bg"], C["warning"]),
        "neutral": (C["bg_soft"], C["muted"]),
    }

    def __init__(self, parent, **kwargs):
        super().__init__(
            parent, text="", corner_radius=8, fg_color=C["bg_soft"], text_color=C["muted"],
            font=ctk.CTkFont(size=12, weight="bold"), height=30, padx=12, **kwargs,
        )

    def set(self, text: str, kind: str = "neutral"):
        bg, fg = self._STYLES.get(kind, self._STYLES["neutral"])
        self.configure(text=text, fg_color=bg if text else C["bg_soft"], text_color=fg)

    def clear(self):
        self.configure(text="", fg_color=C["bg_soft"])


NAV_ITEMS = [
    ("settings", "⚙", "Sozlamalar"),
    ("new_listing", "➕", "Yangi e'lon"),
    ("pending", "\U0001F4CB", "Kutilayotganlar"),
    ("stats", "\U0001F4CA", "Statistika"),
]


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        global root_ref
        root_ref = self

        self.title("Ijaraga Uylar — Admin")
        self.geometry("1120x720")
        self.minsize(960, 600)
        self.configure(fg_color=C["bg_soft"])
        self.bind_all("<Control-KeyPress>", _universal_clipboard_handler)
        try:
            self.iconbitmap(_resource_path("app_icon.ico"))
        except Exception:
            pass  # Linuxda .ico ba'zan qo'llab-quvvatlanmaydi - Windows'da ishlayveradi

        cfg = load_config()
        self.client = ApiClient(cfg.get("server_url", ""), cfg.get("token", ""))
        self.photo_paths: list[str] = []

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._build_sidebar()

        self.content = ctk.CTkFrame(self, fg_color=C["bg_soft"])
        self.content.grid(row=0, column=1, sticky="nsew")
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=1)

        self.pages = {}
        self.nav_buttons = {}
        for key, icon, label in NAV_ITEMS:
            page_cls = {
                "settings": SettingsPage, "new_listing": NewListingPage,
                "pending": PendingPage, "stats": StatsPage,
            }[key]
            page = page_cls(self.content, self)
            page.grid(row=0, column=0, sticky="nsew")
            self.pages[key] = page

        self._active = None
        self.show_page("settings" if not cfg.get("token") else "stats")
        if self.client.server_url and self.client.token:
            self.pages["stats"].refresh()

    def _build_sidebar(self):
        sidebar = ctk.CTkFrame(self, width=236, fg_color=C["ink"], corner_radius=0)
        sidebar.grid(row=0, column=0, sticky="nsw")
        sidebar.grid_propagate(False)

        brand_wrap = ctk.CTkFrame(sidebar, fg_color="transparent")
        brand_wrap.pack(fill="x", padx=22, pady=(28, 30))
        logo = ctk.CTkFrame(brand_wrap, width=40, height=40, corner_radius=12, fg_color=C["brand"])
        logo.pack(side="left")
        logo.pack_propagate(False)
        ctk.CTkLabel(logo, text="\U0001F3E0", font=ctk.CTkFont(size=18)).place(relx=0.5, rely=0.5, anchor="center")
        text_wrap = ctk.CTkFrame(brand_wrap, fg_color="transparent")
        text_wrap.pack(side="left", padx=(12, 0))
        ctk.CTkLabel(text_wrap, text="Ijaraga Uylar", font=ctk.CTkFont(size=16, weight="bold"), text_color="white").pack(anchor="w")
        ctk.CTkLabel(text_wrap, text="Admin panel", font=ctk.CTkFont(size=11), text_color="#8B93A7").pack(anchor="w")

        self._nav_frame = ctk.CTkFrame(sidebar, fg_color="transparent")
        self._nav_frame.pack(fill="x", padx=14)
        self._nav_buttons = {}
        for key, icon, label in NAV_ITEMS:
            btn = ctk.CTkButton(
                self._nav_frame, text=f"  {icon}   {label}", anchor="w",
                fg_color="transparent", hover_color="#1E293D", text_color="#C7CDDB",
                font=ctk.CTkFont(size=13, weight="bold"), corner_radius=10, height=42,
                command=lambda k=key: self.show_page(k),
            )
            btn.pack(fill="x", pady=3)
            self._nav_buttons[key] = btn

        footer = ctk.CTkFrame(sidebar, fg_color="transparent")
        footer.pack(side="bottom", fill="x", padx=22, pady=20)
        self._conn_dot = ctk.CTkLabel(footer, text="●", text_color=C["muted"], font=ctk.CTkFont(size=10))
        self._conn_dot.pack(side="left")
        self._conn_label = ctk.CTkLabel(footer, text="Ulanmagan", text_color="#8B93A7", font=ctk.CTkFont(size=11))
        self._conn_label.pack(side="left", padx=(6, 0))

    def set_connection_status(self, ok: bool, name: str = ""):
        if ok:
            self._conn_dot.configure(text_color=C["success"])
            self._conn_label.configure(text=f"Ulangan: {name}" if name else "Ulangan")
        else:
            self._conn_dot.configure(text_color=C["danger"])
            self._conn_label.configure(text="Ulanmagan")

    def show_page(self, key: str):
        for k, btn in self._nav_buttons.items():
            if k == key:
                btn.configure(fg_color=C["brand"], text_color="white", hover_color=C["brand_dark"])
            else:
                btn.configure(fg_color="transparent", text_color="#C7CDDB", hover_color="#1E293D")
        self.pages[key].tkraise()
        self._active = key


class SettingsPage(ctk.CTkFrame):
    def __init__(self, parent, app: App):
        super().__init__(parent, fg_color=C["bg_soft"])
        self.app = app
        section_header(self, "Sozlamalar", "Serverga ulanish uchun manzil va tokenni kiriting.")

        c = card(self)
        c.pack(fill="x", padx=28, pady=(12, 0))
        inner = ctk.CTkFrame(c, fg_color="transparent")
        inner.pack(fill="x", padx=24, pady=22)

        ctk.CTkLabel(inner, text="Server manzili", font=ctk.CTkFont(size=12, weight="bold"), text_color=C["ink"]).pack(anchor="w")
        self.server_var = tk.StringVar(value=app.client.server_url)
        styled_entry(inner, textvariable=self.server_var, placeholder="https://ijaragauylar.uz", width=420).pack(anchor="w", pady=(6, 18))

        ctk.CTkLabel(inner, text="Token", font=ctk.CTkFont(size=12, weight="bold"), text_color=C["ink"]).pack(anchor="w")
        self.token_var = tk.StringVar(value=app.client.token)
        styled_entry(inner, textvariable=self.token_var, placeholder="Botdan /desktop_token bilan oling", width=420, show="•").pack(anchor="w", pady=(6, 18))

        row = ctk.CTkFrame(inner, fg_color="transparent")
        row.pack(anchor="w")
        primary_button(row, "\U0001F4BE  Saqlash va tekshirish", self.save_and_test, width=220).pack(side="left")
        self.status = StatusPill(row)
        self.status.pack(side="left", padx=(14, 0))

        note = card(self, fg_color=C["brand_light"], border_width=0)
        note.pack(fill="x", padx=28, pady=(18, 24))
        ctk.CTkLabel(
            note,
            text=(
                "ℹ  Telegram botda admin sifatida /desktop_token buyrug'ini yuboring — bot sizga "
                "shaxsiy xabarda token yuboradi. Uni hech kimga ko'rsatmang. Token \"o'g'irlangan\" deb "
                "o'ylasangiz, botga /desktop_token_revoke yuboring."
            ),
            text_color=C["brand_dark"], font=ctk.CTkFont(size=12), wraplength=760, justify="left",
        ).pack(anchor="w", padx=18, pady=14)

    def save_and_test(self):
        server_url = self.server_var.get().strip()
        token = self.token_var.get().strip()
        if not server_url or not token:
            messagebox.showwarning("Diqqat", "Server manzili va tokenni to'ldiring.")
            return
        save_config(server_url, token)
        self.app.client = ApiClient(server_url, token)
        self.status.set("Tekshirilmoqda...", "neutral")

        def done(result):
            name = result.get("full_name") or result.get("username") or "Admin"
            self.status.set(f"✓ Ulandi: {name}", "success")
            self.app.set_connection_status(True, name)

        def error(e):
            self.status.set(f"✕ {e}", "error")
            self.app.set_connection_status(False)

        run_in_background(self.app.client.me, done, error)


class NewListingPage(ctk.CTkFrame):
    def __init__(self, parent, app: App):
        super().__init__(parent, fg_color=C["bg_soft"])
        self.app = app
        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True)

        section_header(scroll, "Yangi e'lon", "E'lon ma'lumotlarini kiriting va rasm qo'shing.")

        form_card = card(scroll)
        form_card.pack(fill="x", padx=28, pady=(12, 0))
        form = ctk.CTkFrame(form_card, fg_color="transparent")
        form.pack(fill="x", padx=24, pady=22)
        form.grid_columnconfigure(1, weight=1)

        self.fields = {}
        rows = [
            ("manzil", "Manzil *"), ("narx", "Narxi *"), ("xona", "Xonalar soni"),
            ("moljal", "Mo'ljal"), ("kimlarga", "Kimlarga"), ("qulaylik", "Qulayliklar"),
            ("telefon", "Telefon *"),
        ]
        for i, (key, label) in enumerate(rows):
            ctk.CTkLabel(form, text=label, font=ctk.CTkFont(size=12, weight="bold"), text_color=C["ink"]).grid(row=i, column=0, sticky="w", pady=7, padx=(0, 16))
            var = tk.StringVar()
            styled_entry(form, textvariable=var, width=440).grid(row=i, column=1, sticky="we", pady=7)
            self.fields[key] = var

        ctk.CTkLabel(form, text="Ijara turi", font=ctk.CTkFont(size=12, weight="bold"), text_color=C["ink"]).grid(row=len(rows), column=0, sticky="w", pady=7, padx=(0, 16))
        self.rental_type_var = tk.StringVar(value=RENTAL_TYPES[0][0])
        option = ctk.CTkOptionMenu(
            form, values=[label for _, label in RENTAL_TYPES], width=440, height=38, corner_radius=10,
            fg_color=C["bg_soft"], button_color=C["brand"], button_hover_color=C["brand_dark"],
            text_color=C["ink"], dropdown_fg_color=C["bg"],
            command=lambda sel: self.rental_type_var.set(dict((v, k) for k, v in RENTAL_TYPES)[sel]),
        )
        option.set(RENTAL_TYPES[0][1])
        option.grid(row=len(rows), column=1, sticky="w", pady=7)

        # ---- Rasmlar ----
        photo_card = card(scroll)
        photo_card.pack(fill="x", padx=28, pady=(18, 0))
        photo_inner = ctk.CTkFrame(photo_card, fg_color="transparent")
        photo_inner.pack(fill="x", padx=24, pady=22)

        ctk.CTkLabel(photo_inner, text="Rasmlar", font=ctk.CTkFont(size=15, weight="bold"), text_color=C["ink"]).pack(anchor="w", pady=(0, 12))

        btn_row = ctk.CTkFrame(photo_inner, fg_color="transparent")
        btn_row.pack(fill="x")
        secondary_button(btn_row, "\U0001F4C1  Kompyuterdan rasm qo'shish", self.add_local_photos, width=230).pack(side="left")
        secondary_button(btn_row, "\U0001F5D1  Tozalash", self.clear_photos, width=120).pack(side="left", padx=(10, 0))

        olx_row = ctk.CTkFrame(photo_inner, fg_color="transparent")
        olx_row.pack(fill="x", pady=(14, 0))
        self.olx_url_var = tk.StringVar()
        styled_entry(olx_row, textvariable=self.olx_url_var, placeholder="OLX e'lon havolasi (https://www.olx.uz/...)", width=380).pack(side="left")
        secondary_button(olx_row, "\U0001F310  OLX'dan rasm olish", self.fetch_olx_photos, width=180).pack(side="left", padx=(10, 0))

        self.photo_list_frame = ctk.CTkFrame(photo_inner, fg_color=C["bg_soft"], corner_radius=10)
        self.photo_list_frame.pack(fill="x", pady=(14, 0))
        self._photo_rows = []
        self._render_photo_list()

        self.olx_status = StatusPill(photo_inner)
        self.olx_status.pack(anchor="w", pady=(10, 0))

        self.status = StatusPill(scroll)
        self.status.pack(anchor="w", padx=28, pady=(18, 8))
        primary_button(scroll, "✅  Kanalga joylash", self.submit, width=220).pack(anchor="w", padx=28, pady=(0, 28))

    def _render_photo_list(self):
        for w in self.photo_list_frame.winfo_children():
            w.destroy()
        if not self.app.photo_paths:
            ctk.CTkLabel(self.photo_list_frame, text="Hali rasm qo'shilmagan.", text_color=C["muted"], font=ctk.CTkFont(size=12)).pack(anchor="w", padx=14, pady=14)
            return
        for idx, path in enumerate(self.app.photo_paths):
            row = ctk.CTkFrame(self.photo_list_frame, fg_color="transparent")
            row.pack(fill="x", padx=10, pady=(6, 0))
            ctk.CTkLabel(row, text=f"\U0001F5BC  {os.path.basename(path)}", font=ctk.CTkFont(size=12), text_color=C["ink"]).pack(side="left")
            ctk.CTkButton(
                row, text="✕", width=26, height=26, corner_radius=8,
                fg_color="transparent", hover_color=C["danger_bg"], text_color=C["muted"],
                command=lambda i=idx: self._remove_photo(i),
            ).pack(side="right")
        ctk.CTkFrame(self.photo_list_frame, fg_color="transparent", height=8).pack()

    def _remove_photo(self, idx):
        if 0 <= idx < len(self.app.photo_paths):
            del self.app.photo_paths[idx]
        self._render_photo_list()

    def add_local_photos(self):
        paths = filedialog.askopenfilenames(
            title="Rasmlarni tanlang", filetypes=[("Rasmlar", "*.jpg *.jpeg *.png *.webp")],
        )
        for p in paths:
            self.app.photo_paths.append(p)
        self._render_photo_list()

    def clear_photos(self):
        self.app.photo_paths.clear()
        self._render_photo_list()

    def fetch_olx_photos(self):
        url = self.olx_url_var.get().strip()
        if not url:
            messagebox.showwarning("Diqqat", "OLX havolasini kiriting.")
            return
        self.olx_status.set("OLX'dan rasmlar qidirilmoqda...", "neutral")

        def done(photo_urls):
            if not photo_urls:
                self.olx_status.set("Rasm topilmadi - rasmlarni qo'lda yuklang.", "warning")
                return
            self.olx_status.set(f"{len(photo_urls)} ta rasm topildi, yuklab olinmoqda...", "neutral")
            run_in_background(lambda: self._download_olx_photos(photo_urls), self._olx_download_done, self._olx_error)

        def error(e):
            self.olx_status.set(
                f"⚠ OLX'dan rasm topib bo'lmadi ({e}). Rasmlarni qo'lda yuklang.",
                "warning",
            )
        run_in_background(lambda: self.app.client.olx_photos(url), done, error)

    def _download_olx_photos(self, photo_urls: list) -> list:
        tmpdir = tempfile.mkdtemp(prefix="olx_photos_")
        saved = []
        for i, url in enumerate(photo_urls):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = resp.read()
                path = os.path.join(tmpdir, f"olx_{i}.jpg")
                with open(path, "wb") as f:
                    f.write(data)
                saved.append(path)
            except Exception:
                continue
        return saved

    def _olx_download_done(self, paths: list):
        self.app.photo_paths.extend(paths)
        self._render_photo_list()
        self.olx_status.set(f"✓ {len(paths)} ta rasm qo'shildi. Tekshirib, keraksizlarini olib tashlang.", "success")

    def _olx_error(self, e):
        self.olx_status.set(f"⚠ Rasmlarni yuklab olishda xatolik: {e}", "warning")

    def submit(self):
        manzil = self.fields["manzil"].get().strip()
        narx = self.fields["narx"].get().strip()
        telefon = self.fields["telefon"].get().strip()
        if not manzil or not narx or not telefon:
            messagebox.showwarning("Diqqat", "Manzil, narx va telefon maydonlari majburiy.")
            return
        if not self.app.photo_paths:
            messagebox.showwarning("Diqqat", "Kamida bitta rasm qo'shing.")
            return

        fields = {
            "manzil": manzil, "narx": narx, "telefon": telefon,
            "xona": self.fields["xona"].get().strip(),
            "moljal": self.fields["moljal"].get().strip(),
            "kimlarga": self.fields["kimlarga"].get().strip(),
            "qulaylik": self.fields["qulaylik"].get().strip(),
            "rental_type": self.rental_type_var.get(),
        }
        photo_paths = list(self.app.photo_paths)
        self.status.set("Joylanmoqda...", "neutral")

        def done(result):
            if result.get("posted"):
                self.status.set(f"✓ E'lon #{result['listing_id']} kanalga joylandi!", "success")
            else:
                self.status.set(f"⚠ E'lon #{result['listing_id']} saqlandi, lekin kanalga joylanmadi.", "warning")
            self.clear_photos()
            for var in self.fields.values():
                var.set("")

        def error(e):
            self.status.set(f"✕ {e}", "error")

        run_in_background(lambda: self.app.client.create_listing(fields, photo_paths), done, error)


class PendingPage(ctk.CTkFrame):
    def __init__(self, parent, app: App):
        super().__init__(parent, fg_color=C["bg_soft"])
        self.app = app
        header = section_header(self, "Kutilayotganlar", "Tasdiq kutayotgan e'lon va obuna so'rovlari.")
        secondary_button(header, "\U0001F504  Yangilash", self.refresh, width=130).pack(anchor="w", pady=(10, 0))

        self.list_frame = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.list_frame.pack(fill="both", expand=True, padx=28, pady=(8, 8))

        self.status = StatusPill(self)
        self.status.pack(anchor="w", padx=28, pady=(0, 16))

        self._empty_label = None

    def refresh(self):
        self.status.set("Yuklanmoqda...", "neutral")

        def done(data):
            for w in self.list_frame.winfo_children():
                w.destroy()
            listings = data.get("listings", [])
            subs = data.get("subscriptions", [])
            if not listings and not subs:
                ctk.CTkLabel(self.list_frame, text="Hozircha kutilayotgan so'rov yo'q.", text_color=C["muted"]).pack(anchor="w", pady=20)
            for listing in listings:
                info = f"{listing.get('manzil', '')} — {listing.get('narx', '')} — {listing.get('telefon', '')}"
                self._add_row("E'lon", listing["id"], info, "listing")
            for sub in subs:
                info = f"user_id: {sub.get('user_id')} — {sub.get('price_charged', 0):,} so'm"
                self._add_row("Obuna", sub["id"], info, "subscription")
            self.status.set(f"{len(listings) + len(subs)} ta kutilayotgan so'rov.", "neutral")

        def error(e):
            self.status.set(f"✕ {e}", "error")

        run_in_background(self.app.client.pending, done, error)

    def _add_row(self, kind_label, obj_id, info, kind):
        row = card(self.list_frame, border_width=1)
        row.pack(fill="x", pady=6)
        inner = ctk.CTkFrame(row, fg_color="transparent")
        inner.pack(fill="x", padx=16, pady=12)
        inner.grid_columnconfigure(1, weight=1)

        badge_color = C["brand"] if kind == "listing" else C["gold"]
        badge = ctk.CTkLabel(inner, text=f" {kind_label} #{obj_id} ", fg_color=badge_color, text_color="white",
                              corner_radius=8, font=ctk.CTkFont(size=11, weight="bold"), height=24)
        badge.grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(inner, text=info, text_color=C["ink_soft"], font=ctk.CTkFont(size=13), anchor="w",
                     wraplength=520, justify="left").grid(row=0, column=1, sticky="we", padx=(14, 14))

        btn_row = ctk.CTkFrame(inner, fg_color="transparent")
        btn_row.grid(row=0, column=2, sticky="e")
        ctk.CTkButton(
            btn_row, text="✅ Tasdiqlash", width=120, height=32, corner_radius=8,
            fg_color=C["success"], hover_color="#17813F", font=ctk.CTkFont(size=12, weight="bold"),
            command=lambda: self._approve(kind, obj_id),
        ).pack(side="left")
        ctk.CTkButton(
            btn_row, text="❌ Rad etish", width=110, height=32, corner_radius=8,
            fg_color="transparent", hover_color=C["danger_bg"], text_color=C["danger"],
            border_width=1, border_color=C["danger"], font=ctk.CTkFont(size=12, weight="bold"),
            command=lambda: self._reject(kind, obj_id),
        ).pack(side="left", padx=(8, 0))

    def _approve(self, kind, obj_id):
        fn = self.app.client.approve_listing if kind == "listing" else self.app.client.approve_subscription

        def done(result):
            self.status.set("✓ Tasdiqlandi.", "success")
            self.refresh()

        def error(e):
            self.status.set(f"✕ {e}", "error")

        run_in_background(lambda: fn(obj_id), done, error)

    def _reject(self, kind, obj_id):
        reason = simpledialog.askstring("Rad etish sababi", "Sababni yozing (foydalanuvchiga yuboriladi):")
        if not reason:
            return
        fn = self.app.client.reject_listing if kind == "listing" else self.app.client.reject_subscription

        def done(result):
            self.status.set("✓ Rad etildi.", "success")
            self.refresh()

        def error(e):
            self.status.set(f"✕ {e}", "error")

        run_in_background(lambda: fn(obj_id, reason), done, error)


STAT_TILES = [
    ("listings_total", "Jami e'lonlar (bugun)", "today"),
    ("listings_approved", "Tasdiqlangan", "today"),
    ("listings_rejected", "Rad etilgan", "today"),
    ("listings_pending", "Kutilmoqda", "today"),
    ("listings_income", "E'londan daromad (so'm)", "today", True),
    ("subs_total", "Yangi obuna so'rovlari", "today"),
    ("subs_approved", "Tasdiqlangan obunalar", "today"),
    ("subs_income", "Obunadan daromad (so'm)", "today", True),
]


class StatsPage(ctk.CTkFrame):
    def __init__(self, parent, app: App):
        super().__init__(parent, fg_color=C["bg_soft"])
        self.app = app
        header = section_header(self, "Statistika", "Bugungi va umumiy ko'rsatkichlar.")
        secondary_button(header, "\U0001F504  Yangilash", self.refresh, width=130).pack(anchor="w", pady=(10, 0))

        self.grid_frame = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.grid_frame.pack(fill="both", expand=True, padx=28, pady=(8, 20))
        for col in range(4):
            self.grid_frame.grid_columnconfigure(col, weight=1, uniform="stat")

        self._tiles = {}

    def _tile(self, parent, label, accent=C["brand"]):
        c = card(parent)
        inner = ctk.CTkFrame(c, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=18, pady=16)
        bar = ctk.CTkFrame(inner, width=4, height=20, fg_color=accent, corner_radius=2)
        bar.pack(anchor="w")
        value_lbl = ctk.CTkLabel(inner, text="—", font=ctk.CTkFont(size=24, weight="bold"), text_color=C["ink"])
        value_lbl.pack(anchor="w", pady=(10, 2))
        ctk.CTkLabel(inner, text=label, font=ctk.CTkFont(size=12), text_color=C["muted"], wraplength=200, justify="left").pack(anchor="w")
        return c, value_lbl

    def refresh(self):
        def done(data):
            for w in self.grid_frame.winfo_children():
                w.destroy()
            today = data.get("today", {})

            section = ctk.CTkLabel(self.grid_frame, text="BUGUNGI KO'RSATKICHLAR", font=ctk.CTkFont(size=12, weight="bold"), text_color=C["muted"])
            section.grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 10))

            values = {
                "listings_total": today.get("listings_total", 0),
                "listings_approved": today.get("listings_approved", 0),
                "listings_rejected": today.get("listings_rejected", 0),
                "listings_pending": today.get("listings_pending", 0),
                "listings_income": today.get("listings_income", 0),
                "subs_total": today.get("subs_total", 0),
                "subs_approved": today.get("subs_approved", 0),
                "subs_income": today.get("subs_income", 0),
            }
            labels = {
                "listings_total": "Jami e'lonlar", "listings_approved": "Tasdiqlangan",
                "listings_rejected": "Rad etilgan", "listings_pending": "Kutilmoqda",
                "listings_income": "E'londan daromad", "subs_total": "Yangi obuna so'rovlari",
                "subs_approved": "Tasdiqlangan obunalar", "subs_income": "Obunadan daromad",
            }
            accents = [C["brand"], C["success"], C["danger"], C["gold"]] * 2
            row, col = 1, 0
            for i, key in enumerate(values):
                tile, value_lbl = self._tile(self.grid_frame, labels[key], accents[i % len(accents)])
                tile.grid(row=row, column=col, sticky="nsew", padx=6, pady=6)
                val = values[key]
                value_lbl.configure(text=f"{val:,}" if isinstance(val, (int, float)) else str(val))
                col += 1
                if col == 4:
                    col = 0
                    row += 1

            row += 1
            section2 = ctk.CTkLabel(self.grid_frame, text="UMUMIY", font=ctk.CTkFont(size=12, weight="bold"), text_color=C["muted"])
            section2.grid(row=row, column=0, columnspan=4, sticky="w", pady=(16, 10))
            row += 1

            general = [
                ("Faol e'lonlar", data.get("active_listings", 0)),
                ("Faol obunachilar", data.get("active_subscribers", 0)),
                ("Jami foydalanuvchilar", today.get("users_total", 0)),
                ("E'lon narxi (so'm)", data.get("listing_price", 0)),
            ]
            col = 0
            for label, val in general:
                tile, value_lbl = self._tile(self.grid_frame, label, C["ink_soft"])
                tile.grid(row=row, column=col, sticky="nsew", padx=6, pady=6)
                value_lbl.configure(text=f"{val:,}" if isinstance(val, (int, float)) else str(val))
                col += 1
                if col == 4:
                    col = 0
                    row += 1

        def error(e):
            messagebox.showerror("Xatolik", str(e))

        run_in_background(self.app.client.stats, done, error)


if __name__ == "__main__":
    app = App()
    app.mainloop()
