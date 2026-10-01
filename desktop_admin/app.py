"""
Ijaraga Uylar - Windows desktop admin dasturi.

Imkoniyatlar:
  - Yangi e'lon joylash (mahalliy rasmlar yoki OLX havolasidan)
  - Kutilayotgan e'lon/obuna so'rovlarini tasdiqlash/rad etish
  - Asosiy statistikani ko'rish

Server bilan /api/desktop/* orqali (web/api_desktop.py) ishlaydi - token
botdan /desktop_token buyrug'i bilan olinadi.
"""
import io
import os
import tempfile
import threading
import tkinter as tk
import urllib.request
from tkinter import filedialog, messagebox, simpledialog, ttk

from api_client import ApiClient, ApiError, load_config, save_config

RENTAL_TYPES = [
    ("uzoq_muddat", "Uzoq muddatli ijara"),
    ("kunlik", "Kunlik ijara"),
    ("dacha", "Dacha"),
    ("mehmonxona", "Mehmonxona"),
]


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


root_ref = None  # ildiz oyna - run_in_background() uchun (modul darajasida, bitta oyna bo'lgani uchun)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        global root_ref
        root_ref = self

        self.title("Ijaraga Uylar - Admin")
        self.geometry("880x640")

        cfg = load_config()
        self.client = ApiClient(cfg.get("server_url", ""), cfg.get("token", ""))
        self.photo_paths: list[str] = []

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=8, pady=8)

        self.settings_tab = SettingsTab(notebook, self)
        self.new_listing_tab = NewListingTab(notebook, self)
        self.pending_tab = PendingTab(notebook, self)
        self.stats_tab = StatsTab(notebook, self)

        notebook.add(self.settings_tab, text="⚙ Sozlamalar")
        notebook.add(self.new_listing_tab, text="➕ Yangi e'lon")
        notebook.add(self.pending_tab, text="\U0001F4CB Kutilayotganlar")
        notebook.add(self.stats_tab, text="\U0001F4CA Statistika")

        if not cfg.get("token"):
            notebook.select(self.settings_tab)


class SettingsTab(ttk.Frame):
    def __init__(self, parent, app: App):
        super().__init__(parent, padding=16)
        self.app = app

        ttk.Label(self, text="Server manzili (masalan: https://ijaragauylar.uz):", font=("", 10)).pack(anchor="w", pady=(0, 4))
        self.server_var = tk.StringVar(value=app.client.server_url)
        ttk.Entry(self, textvariable=self.server_var, width=60).pack(anchor="w", pady=(0, 16))

        ttk.Label(self, text="Token (botdan /desktop_token buyrug'i bilan oling):", font=("", 10)).pack(anchor="w", pady=(0, 4))
        self.token_var = tk.StringVar(value=app.client.token)
        ttk.Entry(self, textvariable=self.token_var, width=60, show="*").pack(anchor="w", pady=(0, 16))

        ttk.Button(self, text="\U0001F4BE Saqlash va tekshirish", command=self.save_and_test).pack(anchor="w")

        self.status_label = ttk.Label(self, text="", foreground="green")
        self.status_label.pack(anchor="w", pady=(12, 0))

        ttk.Label(
            self,
            text=(
                "Eslatma: Telegram botda admin sifatida /desktop_token buyrug'ini yuboring - "
                "bot sizga shaxsiy xabarda token yuboradi. Uni hech kimga ko'rsatmang."
            ),
            foreground="gray", wraplength=600, justify="left",
        ).pack(anchor="w", pady=(20, 0))

    def save_and_test(self):
        server_url = self.server_var.get().strip()
        token = self.token_var.get().strip()
        if not server_url or not token:
            messagebox.showwarning("Diqqat", "Server manzili va tokenni to'ldiring.")
            return
        save_config(server_url, token)
        self.app.client = ApiClient(server_url, token)
        self.status_label.config(text="Tekshirilmoqda...", foreground="gray")

        def done(result):
            name = result.get("full_name") or result.get("username") or "Admin"
            self.status_label.config(text=f"✅ Ulandi: {name}", foreground="green")

        def error(e):
            self.status_label.config(text=f"❌ {e}", foreground="red")

        run_in_background(self.app.client.me, done, error)


class NewListingTab(ttk.Frame):
    def __init__(self, parent, app: App):
        super().__init__(parent, padding=16)
        self.app = app

        form = ttk.Frame(self)
        form.pack(fill="x")

        self.fields = {}
        rows = [
            ("manzil", "Manzil *"), ("narx", "Narxi *"), ("xona", "Xonalar soni"),
            ("moljal", "Mo'ljal"), ("kimlarga", "Kimlarga"), ("qulaylik", "Qulayliklar"),
            ("telefon", "Telefon *"),
        ]
        for i, (key, label) in enumerate(rows):
            ttk.Label(form, text=label).grid(row=i, column=0, sticky="w", pady=4)
            var = tk.StringVar()
            ttk.Entry(form, textvariable=var, width=55).grid(row=i, column=1, sticky="w", pady=4, padx=(8, 0))
            self.fields[key] = var

        ttk.Label(form, text="Ijara turi").grid(row=len(rows), column=0, sticky="w", pady=4)
        self.rental_type_var = tk.StringVar(value=RENTAL_TYPES[0][0])
        rt_combo = ttk.Combobox(form, values=[label for _, label in RENTAL_TYPES], state="readonly", width=52)
        rt_combo.current(0)
        rt_combo.grid(row=len(rows), column=1, sticky="w", pady=4, padx=(8, 0))
        rt_combo.bind("<<ComboboxSelected>>", lambda e: self.rental_type_var.set(RENTAL_TYPES[rt_combo.current()][0]))

        # ---- Rasmlar ----
        photo_frame = ttk.LabelFrame(self, text="Rasmlar", padding=12)
        photo_frame.pack(fill="x", pady=(16, 0))

        btn_row = ttk.Frame(photo_frame)
        btn_row.pack(fill="x")
        ttk.Button(btn_row, text="\U0001F4C1 Kompyuterdan rasm qo'shish", command=self.add_local_photos).pack(side="left")
        ttk.Button(btn_row, text="\U0001F5D1 Tozalash", command=self.clear_photos).pack(side="left", padx=(8, 0))

        olx_row = ttk.Frame(photo_frame)
        olx_row.pack(fill="x", pady=(10, 0))
        ttk.Label(olx_row, text="OLX e'lon havolasi:").pack(side="left")
        self.olx_url_var = tk.StringVar()
        ttk.Entry(olx_row, textvariable=self.olx_url_var, width=45).pack(side="left", padx=(8, 8))
        ttk.Button(olx_row, text="\U0001F310 OLX'dan rasm olish", command=self.fetch_olx_photos).pack(side="left")

        self.photo_listbox = tk.Listbox(photo_frame, height=6)
        self.photo_listbox.pack(fill="x", pady=(10, 0))

        self.status_label = ttk.Label(self, text="", foreground="gray")
        self.status_label.pack(anchor="w", pady=(12, 4))

        ttk.Button(self, text="✅ Kanalga joylash", command=self.submit).pack(anchor="w")

    def add_local_photos(self):
        paths = filedialog.askopenfilenames(
            title="Rasmlarni tanlang", filetypes=[("Rasmlar", "*.jpg *.jpeg *.png *.webp")],
        )
        for p in paths:
            self.app.photo_paths.append(p)
            self.photo_listbox.insert("end", os.path.basename(p))

    def clear_photos(self):
        self.app.photo_paths.clear()
        self.photo_listbox.delete(0, "end")

    def fetch_olx_photos(self):
        url = self.olx_url_var.get().strip()
        if not url:
            messagebox.showwarning("Diqqat", "OLX havolasini kiriting.")
            return
        self.status_label.config(text="OLX'dan rasmlar qidirilmoqda...", foreground="gray")

        def done(photo_urls):
            if not photo_urls:
                self.status_label.config(text="Rasm topilmadi - rasmlarni qo'lda yuklang.", foreground="orange")
                return
            self.status_label.config(text=f"{len(photo_urls)} ta rasm topildi, yuklab olinmoqda...", foreground="gray")
            run_in_background(lambda: self._download_olx_photos(photo_urls), self._olx_download_done, self._olx_error)

        def error(e):
            self.status_label.config(
                text=f"⚠️ OLX'dan rasm topib bo'lmadi ({e}). Rasmlarni qo'lda yuklang - OLX sahifa "
                     "tuzilishi vaqti-vaqti bilan o'zgarib turadi, bu funksiya 100% kafolat bermaydi.",
                foreground="orange",
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
        for p in paths:
            self.app.photo_paths.append(p)
            self.photo_listbox.insert("end", f"OLX: {os.path.basename(p)}")
        self.status_label.config(text=f"✅ {len(paths)} ta rasm qo'shildi. Tekshirib, keraksizlarini ro'yxatdan olib tashlang.", foreground="green")

    def _olx_error(self, e):
        self.status_label.config(text=f"⚠️ Rasmlarni yuklab olishda xatolik: {e}", foreground="orange")

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
        self.status_label.config(text="Joylanmoqda...", foreground="gray")

        def done(result):
            if result.get("posted"):
                self.status_label.config(text=f"✅ E'lon #{result['listing_id']} kanalga joylandi!", foreground="green")
            else:
                self.status_label.config(text=f"⚠️ E'lon #{result['listing_id']} saqlandi, lekin kanalga joylanmadi.", foreground="orange")
            self.clear_photos()
            for var in self.fields.values():
                var.set("")

        def error(e):
            self.status_label.config(text=f"❌ {e}", foreground="red")

        run_in_background(lambda: self.app.client.create_listing(fields, photo_paths), done, error)


class PendingTab(ttk.Frame):
    def __init__(self, parent, app: App):
        super().__init__(parent, padding=16)
        self.app = app

        ttk.Button(self, text="\U0001F504 Yangilash", command=self.refresh).pack(anchor="w", pady=(0, 8))

        columns = ("type", "id", "info")
        self.tree = ttk.Treeview(self, columns=columns, show="headings", height=18)
        self.tree.heading("type", text="Turi")
        self.tree.heading("id", text="ID")
        self.tree.heading("info", text="Ma'lumot")
        self.tree.column("type", width=100)
        self.tree.column("id", width=60)
        self.tree.column("info", width=600)
        self.tree.pack(fill="both", expand=True)

        btn_row = ttk.Frame(self)
        btn_row.pack(fill="x", pady=(8, 0))
        ttk.Button(btn_row, text="✅ Tasdiqlash", command=self.approve_selected).pack(side="left")
        ttk.Button(btn_row, text="❌ Rad etish", command=self.reject_selected).pack(side="left", padx=(8, 0))

        self.status_label = ttk.Label(self, text="", foreground="gray")
        self.status_label.pack(anchor="w", pady=(8, 0))

        self._rows: dict[str, tuple] = {}

    def refresh(self):
        self.status_label.config(text="Yuklanmoqda...", foreground="gray")

        def done(data):
            self.tree.delete(*self.tree.get_children())
            self._rows.clear()
            for listing in data.get("listings", []):
                info = f"{listing.get('manzil', '')} — {listing.get('narx', '')} — {listing.get('telefon', '')}"
                item = self.tree.insert("", "end", values=("E'lon", listing["id"], info))
                self._rows[item] = ("listing", listing["id"])
            for sub in data.get("subscriptions", []):
                info = f"user_id: {sub.get('user_id')} — {sub.get('price_charged', 0):,} so'm"
                item = self.tree.insert("", "end", values=("Obuna", sub["id"], info))
                self._rows[item] = ("subscription", sub["id"])
            self.status_label.config(text=f"{len(self._rows)} ta kutilayotgan so'rov.", foreground="gray")

        def error(e):
            self.status_label.config(text=f"❌ {e}", foreground="red")

        run_in_background(self.app.client.pending, done, error)

    def _selected(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Diqqat", "Avval ro'yxatdan bitta qatorni tanlang.")
            return None
        return self._rows.get(sel[0])

    def approve_selected(self):
        target = self._selected()
        if not target:
            return
        kind, obj_id = target
        fn = self.app.client.approve_listing if kind == "listing" else self.app.client.approve_subscription

        def done(result):
            self.status_label.config(text="✅ Tasdiqlandi.", foreground="green")
            self.refresh()

        def error(e):
            self.status_label.config(text=f"❌ {e}", foreground="red")

        run_in_background(lambda: fn(obj_id), done, error)

    def reject_selected(self):
        target = self._selected()
        if not target:
            return
        kind, obj_id = target
        reason = simpledialog.askstring("Rad etish sababi", "Sababni yozing (foydalanuvchiga yuboriladi):")
        if not reason:
            return
        fn = self.app.client.reject_listing if kind == "listing" else self.app.client.reject_subscription

        def done(result):
            self.status_label.config(text="✅ Rad etildi.", foreground="green")
            self.refresh()

        def error(e):
            self.status_label.config(text=f"❌ {e}", foreground="red")

        run_in_background(lambda: fn(obj_id, reason), done, error)


class StatsTab(ttk.Frame):
    def __init__(self, parent, app: App):
        super().__init__(parent, padding=16)
        self.app = app

        ttk.Button(self, text="\U0001F504 Yangilash", command=self.refresh).pack(anchor="w", pady=(0, 12))
        self.text = tk.Text(self, height=20, width=70, state="disabled")
        self.text.pack(fill="both", expand=True)

    def refresh(self):
        def done(data):
            today = data.get("today", {})
            lines = [
                "=== BUGUNGI KO'RSATKICHLAR ===", "",
                f"Jami e'lonlar: {today.get('listings_total', 0)}",
                f"Tasdiqlangan: {today.get('listings_approved', 0)}",
                f"Rad etilgan: {today.get('listings_rejected', 0)}",
                f"Kutilmoqda: {today.get('listings_pending', 0)}",
                f"E'londan daromad: {today.get('listings_income', 0):,} so'm",
                f"Yangi obuna so'rovlari: {today.get('subs_total', 0)}",
                f"Tasdiqlangan obunalar: {today.get('subs_approved', 0)}",
                f"Obunadan daromad: {today.get('subs_income', 0):,} so'm",
                "",
                "=== UMUMIY ===", "",
                f"Faol e'lonlar: {data.get('active_listings', 0)}",
                f"Faol obunachilar: {data.get('active_subscribers', 0)}",
                f"Jami foydalanuvchilar: {today.get('users_total', 0)}",
                f"E'lon narxi: {data.get('listing_price', 0):,} so'm",
            ]
            self.text.config(state="normal")
            self.text.delete("1.0", "end")
            self.text.insert("1.0", "\n".join(lines))
            self.text.config(state="disabled")

        def error(e):
            messagebox.showerror("Xatolik", str(e))

        run_in_background(self.app.client.stats, done, error)


if __name__ == "__main__":
    app = App()
    app.mainloop()
