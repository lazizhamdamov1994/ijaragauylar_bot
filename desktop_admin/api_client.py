"""
Ijaraga Uylar - desktop admin dasturi uchun server bilan muloqot qatlami.
GUI'dan (app.py) MUSTAQIL - shuning uchun oyna ochmasdan ham sinovdan
o'tkazish mumkin.
"""
import json
import os

import requests

CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".ijaragauylar_admin_config.json")
DEFAULT_TIMEOUT = 25


class ApiError(Exception):
    def __init__(self, message: str, status_code: int = None):
        super().__init__(message)
        self.status_code = status_code


def load_config() -> dict:
    if not os.path.exists(CONFIG_PATH):
        return {"server_url": "", "token": ""}
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"server_url": "", "token": ""}


def save_config(server_url: str, token: str) -> None:
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump({"server_url": server_url.rstrip("/"), "token": token}, f, ensure_ascii=False, indent=2)


class ApiClient:
    """Serverdagi /api/desktop/* endpointlariga so'rov yuboradi. Har bir
    metod javobni dict qilib qaytaradi yoki ApiError ko'taradi (aniq xato
    matni bilan - GUI buni to'g'ridan-to'g'ri foydalanuvchiga ko'rsatadi)."""

    def __init__(self, server_url: str, token: str):
        self.server_url = (server_url or "").rstrip("/")
        self.token = token or ""

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"}

    def _handle(self, resp: requests.Response) -> dict:
        if resp.status_code == 401:
            raise ApiError("Token yaroqsiz yoki eskirgan. Botdan /desktop_token bilan yangisini oling.", 401)
        if not resp.ok:
            try:
                detail = resp.json().get("detail", resp.text)
            except Exception:
                detail = resp.text
            raise ApiError(f"Server xatosi ({resp.status_code}): {detail}", resp.status_code)
        try:
            return resp.json()
        except Exception:
            raise ApiError("Serverdan noto'g'ri javob keldi.")

    def _get(self, path: str, **kwargs) -> dict:
        if not self.server_url:
            raise ApiError("Avval Sozlamalar'da server manzilini kiriting.")
        try:
            resp = requests.get(f"{self.server_url}{path}", headers=self._headers(), timeout=DEFAULT_TIMEOUT, **kwargs)
        except requests.RequestException as e:
            raise ApiError(f"Serverga ulanib bo'lmadi: {e}")
        return self._handle(resp)

    def _post(self, path: str, **kwargs) -> dict:
        if not self.server_url:
            raise ApiError("Avval Sozlamalar'da server manzilini kiriting.")
        try:
            resp = requests.post(f"{self.server_url}{path}", headers=self._headers(), timeout=DEFAULT_TIMEOUT, **kwargs)
        except requests.RequestException as e:
            raise ApiError(f"Serverga ulanib bo'lmadi: {e}")
        return self._handle(resp)

    def me(self) -> dict:
        return self._get("/api/desktop/me")

    def stats(self) -> dict:
        return self._get("/api/desktop/stats")

    def pending(self) -> dict:
        return self._get("/api/desktop/pending")

    def approve_listing(self, listing_id: int) -> dict:
        return self._post(f"/api/desktop/pending/listing/{listing_id}/approve")

    def reject_listing(self, listing_id: int, reason: str) -> dict:
        return self._post(f"/api/desktop/pending/listing/{listing_id}/reject", data={"reason": reason})

    def approve_subscription(self, sub_id: int) -> dict:
        return self._post(f"/api/desktop/pending/subscription/{sub_id}/approve")

    def reject_subscription(self, sub_id: int, reason: str) -> dict:
        return self._post(f"/api/desktop/pending/subscription/{sub_id}/reject", data={"reason": reason})

    def create_listing(self, fields: dict, photo_paths: list) -> dict:
        files = []
        opened = []
        try:
            for path in photo_paths:
                fh = open(path, "rb")
                opened.append(fh)
                files.append(("photos", (os.path.basename(path), fh, "image/jpeg")))
            return self._post("/api/desktop/listings", data=fields, files=files)
        finally:
            for fh in opened:
                fh.close()

    def olx_photos(self, url: str) -> list:
        data = self._post("/api/desktop/olx-photos", data={"url": url})
        return data.get("photo_urls", [])
