"""
طلب صفحة عبر FlareSolverr (Cloudflare challenge) ثم تمرير الكوكيز + User-Agent إلى pyquotex عبر session.json.

تشغيل FlareSolverr محلياً (مثال Docker):
  docker run -d --name flaresolverr -p 8191:8191 ghcr.io/flaresolverr/flaresolverr:latest

المتغيرات البيئية:
  FLARESOLVERR_ENABLED=1
  FLARESOLVERR_URL=http://127.0.0.1:8191/v1
  FLARESOLVERR_TARGET_URL=https://qxbroker.com/en/sign-in
  FLARESOLVERR_MAX_TIMEOUT_MS=120000
  FLARESOLVERR_WAIT_SEC=2   (اختياري؛ انتظار بعد حل التحدي قبل إرجاع الكوكيز)
  FLARESOLVERR_PROXY_URL=   (اختياري؛ إن وُجد يُمرَّر لطلب FlareSolverr — بدون جلسة)
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import socket
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

log = logging.getLogger("NexoraTrade.flaresolverr")


def _enabled() -> bool:
    return os.getenv("FLARESOLVERR_ENABLED", "").strip().lower() in ("1", "true", "yes", "on")


def _api_v1_url() -> str:
    raw = (os.getenv("FLARESOLVERR_URL") or "http://127.0.0.1:8191/v1").strip().rstrip("/")
    if raw.endswith("/v1"):
        return raw
    return raw + "/v1"


def flaresolverr_listen_tcp_reachable(timeout_sec: float = 0.4) -> bool:
    """
    فحص سريع (TCP) أن منفذ FlareSolverr يقبل اتصالاً — دون استدعاء /v1.
    يُستخدم لتجنّب تفعيل جسر WebSocket تلقائياً عندما FLARESOLVERR_ENABLED=1
    لكن الحاوية متوقفة (فيُفتح الجسر بلا cf_clearance ويُضيع الوقت في المهلة).
    """
    if not _enabled():
        return False
    try:
        u = urlparse((os.getenv("FLARESOLVERR_URL") or "http://127.0.0.1:8191/v1").strip())
    except Exception:
        return False
    host = (u.hostname or "127.0.0.1").strip() or "127.0.0.1"
    port = int(u.port or 8191)
    t = max(0.1, min(float(timeout_sec or 0.4), 2.0))
    try:
        with socket.create_connection((host, port), timeout=t):
            return True
    except OSError:
        return False


def _target_url() -> str:
    return (
        os.getenv("FLARESOLVERR_TARGET_URL", "").strip()
        or "https://qxbroker.com/en/sign-in"
    )


def _max_timeout_ms() -> int:
    try:
        v = int(os.getenv("FLARESOLVERR_MAX_TIMEOUT_MS", "120000") or 120000)
        return max(10000, min(v, 300000))
    except Exception:
        return 120000


def _optional_proxy_payload() -> dict[str, Any] | None:
    u = (os.getenv("FLARESOLVERR_PROXY_URL") or os.getenv("QUOTEX_PROXY_URL") or "").strip()
    if not u:
        return None
    if "@" in u:
        log.warning(
            "FlareSolverr: طلب request.get مع بروكسي يحتوي @ قد لا يدعمه FlareSolverr — "
            "عيّن PROXY_URL على حاوية FlareSolverr أو FLARESOLVERR_PROXY_URL بدون مصادقة"
        )
    return {"url": u}


def _cookies_to_header(cookies: list[Any]) -> str:
    parts: list[str] = []
    for c in cookies or []:
        if not isinstance(c, dict):
            continue
        n = str(c.get("name") or "").strip()
        v = c.get("value")
        if not n or v is None:
            continue
        parts.append(f"{n}={v}")
    return "; ".join(parts)


def flare_snapshot_path(email: str) -> Path:
    """ملف جانبي: كوكيز Flare كاملة (قائمة) — لا يستبدلها pyquotex بعد login."""
    h = hashlib.sha256((email or "").strip().lower().encode("utf-8")).hexdigest()[:20]
    return Path(os.getcwd()) / "data" / f"nexora_flare_{h}.json"


def solve_flaresolverr() -> dict[str, Any] | None:
    """
    يستدعي FlareSolverr request.get على FLARESOLVERR_TARGET_URL.
    يُرجع dict: cookie_header, user_agent, cookies (قائمة خام من Flare) أو None.
    """
    if not _enabled():
        return None
    api = _api_v1_url()
    page = _target_url()
    max_ms = _max_timeout_ms()
    body: dict[str, Any] = {
        "cmd": "request.get",
        "url": page,
        "maxTimeout": max_ms,
        "returnOnlyCookies": True,
    }
    try:
        w = float(os.getenv("FLARESOLVERR_WAIT_SEC", "0") or 0)
        if w > 0:
            body["waitInSeconds"] = min(max(w, 0.5), 30.0)
    except Exception:
        pass
    px = _optional_proxy_payload()
    if px:
        body["proxy"] = px
    raw_b = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        api,
        data=raw_b,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    timeout_sec = max(35.0, min(max_ms / 1000.0 + 45.0, 360.0))
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            raw = json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as e:
        log.warning("FlareSolverr HTTP %s: %s", e.code, e.reason)
        return None
    except urllib.error.URLError as e:
        log.warning("FlareSolverr اتصال فشل (%s) — هل الحاوية تعمل على %s؟", e.reason, api)
        return None
    except Exception as e:
        log.warning("FlareSolverr: %s", e)
        return None

    if raw.get("status") != "ok":
        log.warning(
            "FlareSolverr status=%s message=%s",
            raw.get("status"),
            raw.get("message"),
        )
        return None

    sol = raw.get("solution") or {}
    cookies = sol.get("cookies") or []
    hdr = _cookies_to_header(cookies)
    ua = (
        str(sol.get("userAgent") or sol.get("user_agent") or "").strip()
    )
    if not hdr:
        log.warning("FlareSolverr: لا كوكيز في الرد لـ %s", page)
        return None
    log.info(
        "FlareSolverr: تم جلب %s كوكي لـ %s",
        len(cookies),
        urlparse(page).netloc or page,
    )
    return {
        "cookie_header": hdr,
        "user_agent": ua or None,
        "cookies": list(cookies) if isinstance(cookies, list) else [],
    }


def apply_to_pyquotex_disk(email: str) -> tuple[str | None, str | None]:
    """
    يحل التحدي (إن مفعّلاً) ويكتب session.json لنفس البريد قبل Quotex(...).
    يُرجع (cookie_header, user_agent) لاستخدامهما في Quotex(user_agent=...).
    """
    sol = solve_flaresolverr()
    if not sol:
        return None, None
    ck = sol.get("cookie_header") or ""
    ua = sol.get("user_agent")
    raw_cookies = sol.get("cookies") or []
    _ua_final = ua or (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )
    try:
        snap = flare_snapshot_path(email)
        snap.parent.mkdir(parents=True, exist_ok=True)
        snap.write_text(
            json.dumps(
                {
                    "email": email,
                    "saved_at": time.time(),
                    "user_agent": _ua_final,
                    "cookies": raw_cookies,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        log.info("FlareSolverr: لقطة كوكيز للجسر — %s", snap.name)
    except Exception as e:
        log.warning("FlareSolverr: تعذر كتابة لقطة الجسر — %s", e)
    try:
        from pyquotex.config import update_session
    except Exception as e:
        log.warning("FlareSolverr: تعذر استيراد pyquotex.config — %s", e)
        return ck or None, ua
    try:
        update_session(
            email,
            {
                "cookies": ck,
                "token": None,
                "user_agent": _ua_final,
            },
        )
    except Exception as e:
        log.warning("FlareSolverr: تعذر كتابة session.json — %s", e)
        return ck or None, ua
    return ck or None, ua
