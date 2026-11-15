"""Nihola Estate web sayti.  Ishga tushirish:  python web.py   ->  http://localhost:8000"""
import os

import uvicorn

if __name__ == "__main__":
    host = os.getenv("WEB_HOST", "0.0.0.0")
    port = int(os.getenv("WEB_PORT", "8000"))
    print(f"\n  Sayt ishga tushdi:  http://localhost:{port}\n  (To'xtatish: Ctrl + C)\n")
    uvicorn.run("web.app:app", host=host, port=port, log_level="warning")
