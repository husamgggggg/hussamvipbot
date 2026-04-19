#!/usr/bin/env python3
"""
flare_cf.py — جلب cf_clearance من FlareSolverr وحفظها للجسر.

FlareSolverr يشغّل Chrome حقيقي يحل CF JS Challenge
ويعيد cf_clearance الصالحة لـ ws2.qxbroker.com.

الاستخدام:
  from flare_cf import fetch_and_save_cf_clearance
  ok = await fetch_and_save_cf_clearance(email)
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Optional

log = logging.getLogger(__name__)

_FLARE_URL = ""
_FLARE_SESSION = "nexora"


def _get_flare_url() -> str:
    global _FLARE_URL
    if not _FLARE_URL:
        _FLARE_URL = (
            os.environ.get("FLARESOLVERR_URL", "").strip()
            or "http://localhost:8191/v1"
        )
    return _FLARE_URL


def _get_session_id() -> str:
    return (
        os.environ.get("FLARESOLVERR_SESSION", "").strip()
        or _FLARE_SESSION
    )


def _flare_post(payload: dict, timeout: int = 60) -> Optional[dict]:
    """POST إلى FlareSolverr — يستخدم requests العادي (sync)."""
    url = _get_flare_url()
    try:
        import requests as _req
        resp = _req.post(url, json=payload, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        log.warning("[flare_cf] FlareSolverr request failed: %s", e)
        return None


def is_flaresolverr_running() -> bool:
    """يتحقق أن FlareSolverr شغّال."""
    try:
        import requests as _req
        r = _req.get(_get_flare_url().replace("/v1", ""), timeout=3)
        return r.status_code < 500
    except Exception:
        return False


def ensure_session() -> bool:
    """ينشئ session في FlareSolverr إن لم تكن موجودة."""
    sid = _get_session_id()
    # تحقق هل الـ session موجودة
    resp = _flare_post({"cmd": "sessions.list"})
    if resp and sid in (resp.get("sessions") or []):
        log.debug("[flare_cf] session %r موجودة", sid)
        return True
    # أنشئها
    resp = _flare_post({"cmd": "sessions.create", "session": sid})
    ok = resp and resp.get("status") == "ok"
    if ok:
        log.info("[flare_cf] session %r أُنشئت", sid)
    else:
        log.warning("[flare_cf] فشل إنشاء session: %s", resp)
    return ok


def get_cf_clearance(url: str = "https://qxbroker.com") -> Optional[dict]:
    """
    يجلب cf_clearance لـ url عبر FlareSolverr.
    يُعيد dict يحتوي cf_clearance و__cf_bm وغيرها، أو None.
    """
    if not is_flaresolverr_running():
        log.error(
            "[flare_cf] FlareSolverr غير شغّال على %s — "
            "شغّله: docker run -p 8191:8191 ghcr.io/flaresolverr/flaresolverr:latest",
            _get_flare_url(),
        )
        return None

    ensure_session()

    log.info("[flare_cf] جلب cf_clearance لـ %s ...", url)
    resp = _flare_post(
        {
            "cmd": "request.get",
            "url": url,
            "session": _get_session_id(),
            "maxTimeout": 55000,
        },
        timeout=65,
    )

    if not resp or resp.get("status") != "ok":
        log.warning("[flare_cf] FlareSolverr رد بخطأ: %s", resp)
        return None

    solution = resp.get("solution") or {}
    raw_cookies: list = solution.get("cookies") or []

    # تحويل إلى dict {name: value}
    cookie_dict: dict[str, str] = {}
    for c in raw_cookies:
        if isinstance(c, dict) and c.get("name"):
            cookie_dict[c["name"]] = c.get("value", "")

    if not cookie_dict.get("cf_clearance"):
        log.warning(
            "[flare_cf] cf_clearance غير موجود في رد FlareSolverr — "
            "cookies: %s",
            list(cookie_dict.keys()),
        )
        return None

    log.info(
        "[flare_cf] ✅ cf_clearance مُستَلَم — user_agent: %s",
        solution.get("userAgent", "")[:60],
    )
    return {
        "cookies": cookie_dict,
        "user_agent": solution.get("userAgent", ""),
    }


def fetch_and_save_cf_clearance(email: str, url: str = "https://qxbroker.com") -> bool:
    """
    يجلب cf_clearance ويحفظه في data/bridge_cookies/ للجسر.
    يُستدعى من bot.py قبل أو بعد authenticate() إن لم تُوجد cf_clearance.
    """
    result = get_cf_clearance(url)
    if not result:
        return False

    try:
        from cookie_bridge import _build_and_save
        saved = _build_and_save(email, result["cookies"])
        if saved:
            log.info("[flare_cf] ✅ cf_clearance حُفظ للجسر (email=%s)", email)
        return saved
    except Exception as e:
        log.warning("[flare_cf] فشل حفظ cf_clearance: %s", e)
        return False
