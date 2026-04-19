#!/usr/bin/env python3
"""
cookie_bridge.py — حفظ/استعادة كوكيز Cloudflare لجسر Playwright.

pyquotex يستخدم requests.Session داخلياً (browser = requests.Session).
الكوكيز متاحة في:
  1. self_api.browser.cookies  → RequestsCookieJar (المصدر الرئيسي)
  2. self_api.session_data["cookies"] → "name=val; name2=val2" (header string)

نقرأ المصدر الأول أولاً، ثم نكمل من الثاني إن نقص cf_clearance.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

log = logging.getLogger(__name__)

_BASE = os.path.dirname(os.path.abspath(__file__))
_COOKIES_DIR = os.path.join(_BASE, "data", "bridge_cookies")
_MAX_AGE_SEC = 5 * 3600


def _slug(email: str) -> str:
    return email.replace("@", "_at_").replace(".", "_").replace("+", "_plus_")


def _cookie_path(email: str) -> str:
    os.makedirs(_COOKIES_DIR, exist_ok=True)
    return os.path.join(_COOKIES_DIR, f"bridge_{_slug(email)}.json")


def _build_and_save(email: str, raw_dict: dict) -> bool:
    """يبني قائمة Playwright cookies من {name:value} ويحفظها."""
    if not raw_dict:
        return False
    expires = int(time.time()) + _MAX_AGE_SEC
    cookies: list[dict] = []
    for name, value in raw_dict.items():
        if not name or value is None:
            continue
        cookies.append({
            "name": str(name),
            "value": str(value),
            "domain": ".qxbroker.com",
            "path": "/",
            "httpOnly": any(k in str(name).lower() for k in ("cf", "session", "token")),
            "secure": True,
            "sameSite": "None",
            "expires": expires,
        })
    if not cookies:
        return False
    cf_count = sum(1 for c in cookies if "cf_clearance" in c["name"].lower())
    out = {
        "email": email,
        "saved_at": time.time(),
        "cf_count": cf_count,
        "total": len(cookies),
        "cookies": cookies,
    }
    try:
        dest = _cookie_path(email)
        with open(dest, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        log.info(
            "[cookie_bridge] ✅ حُفظت %d cookies (%d cf_clearance) → %s",
            len(cookies), cf_count, os.path.basename(dest),
        )
        return True
    except Exception as e:
        log.warning("[cookie_bridge] فشل الكتابة: %s", e)
        return False


# ─────────────────────────────────────────────────────────────
# المصدر الأساسي: requests.Session.cookies (RequestsCookieJar)
# ─────────────────────────────────────────────────────────────

def save_cf_cookies_from_client(email: str, api_obj: Any) -> bool:
    """
    يقرأ cookies من:
      1. api_obj.browser.cookies  → requests.RequestsCookieJar
      2. api_obj.session_data["cookies"] → "k=v; k2=v2" string
    """
    raw: dict[str, str] = {}

    # ── المصدر 1: browser.cookies (RequestsCookieJar) ──
    try:
        browser = getattr(api_obj, "browser", None)
        if browser is not None:
            jar = getattr(browser, "cookies", None)
            if jar is not None:
                # RequestsCookieJar يدعم .items()
                if hasattr(jar, "items"):
                    for name, value in jar.items():
                        if name and value:
                            raw[str(name)] = str(value)
                # fallback: iterate كـ dict
                elif hasattr(jar, "__iter__"):
                    for cookie in jar:
                        n = getattr(cookie, "name", None) or str(cookie)
                        v = getattr(cookie, "value", "")
                        if n and v:
                            raw[n] = v
                if raw:
                    log.info(
                        "[cookie_bridge] browser.cookies: %d keys، CF: %s",
                        len(raw),
                        [k for k in raw if "cf" in k.lower()] or "none",
                    )
    except Exception as e:
        log.debug("[cookie_bridge] browser.cookies read error: %s", e)

    # ── المصدر 2: session_data["cookies"] كـ header string ──
    try:
        sd = getattr(api_obj, "session_data", None)
        if isinstance(sd, dict):
            cookie_str = sd.get("cookies") or ""
            if isinstance(cookie_str, str) and cookie_str.strip():
                for part in cookie_str.split(";"):
                    part = part.strip()
                    if "=" in part:
                        k, _, v = part.partition("=")
                        k, v = k.strip(), v.strip()
                        if k and v and k not in raw:
                            raw[k] = v
                log.info(
                    "[cookie_bridge] session_data.cookies: %d keys (after merge)",
                    len(raw),
                )
    except Exception as e:
        log.debug("[cookie_bridge] session_data.cookies read error: %s", e)

    if not raw:
        log.warning("[cookie_bridge] لا cookies متاحة من browser أو session_data")
        return False

    cf_keys = [k for k in raw if "cf_clearance" in k.lower()]
    if not cf_keys:
        log.warning(
            "[cookie_bridge] ⚠️ cf_clearance غير موجود في cookies (%s) — "
            "CF لم تمنح clearance بعد. الـ WS سيفشل بـ 403.",
            list(raw.keys()),
        )

    return _build_and_save(email, raw)


# ─────────────────────────────────────────────────────────────
# المصدر الاحتياطي: session.json (بعد WS ناجح)
# ─────────────────────────────────────────────────────────────

def save_cf_cookies_from_session(
    email: str,
    session_json_path: str | None = None,
) -> bool:
    """يقرأ cookies من session.json — يُستدعى في Fix A/B."""
    path = session_json_path or os.path.join(os.getcwd(), "session.json")
    if not os.path.isfile(path):
        return False
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        log.warning("[cookie_bridge] فشل قراءة session.json: %s", e)
        return False

    entry = data.get(email) if isinstance(data, dict) else None
    if not isinstance(entry, dict):
        return False

    raw_cookies: Any = entry.get("cookies") or {}

    if isinstance(raw_cookies, str):
        if not raw_cookies.strip():
            return False
        # قد يكون JSON أو header string
        try:
            raw_cookies = json.loads(raw_cookies)
        except Exception:
            # header string: "k=v; k2=v2"
            raw_dict: dict = {}
            for part in raw_cookies.split(";"):
                part = part.strip()
                if "=" in part:
                    k, _, v = part.partition("=")
                    raw_dict[k.strip()] = v.strip()
            return _build_and_save(email, raw_dict) if raw_dict else False

    if isinstance(raw_cookies, list):
        raw_dict = {}
        for item in raw_cookies:
            if isinstance(item, dict) and "name" in item:
                raw_dict[item["name"]] = item.get("value", "")
            elif isinstance(item, (list, tuple)) and len(item) >= 2:
                raw_dict[str(item[0])] = str(item[1])
        raw_cookies = raw_dict
    elif not isinstance(raw_cookies, dict):
        return False

    return _build_and_save(email, raw_cookies) if raw_cookies else False


# ─────────────────────────────────────────────────────────────
# واجهة القراءة
# ─────────────────────────────────────────────────────────────

def load_cf_cookies_for_bridge(email: str) -> list[dict]:
    """يُعيد cookies جاهزة لـ playwright context.add_cookies()."""
    p = _cookie_path(email)
    if not os.path.isfile(p):
        return []
    try:
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
        cookies: list[dict] = data.get("cookies") or []
        age_min = (time.time() - data.get("saved_at", 0)) / 60
        if age_min > _MAX_AGE_SEC / 60:
            log.warning("[cookie_bridge] cookies قديمة (%.0f دقيقة) — أعد Login", age_min)
        return cookies
    except Exception as e:
        log.warning("[cookie_bridge] فشل التحميل: %s", e)
        return []


def get_cookies_file_path(email: str) -> str | None:
    p = _cookie_path(email)
    return p if os.path.isfile(p) else None


def has_cf_clearance(email: str) -> bool:
    return any(c.get("name") == "cf_clearance" for c in load_cf_cookies_for_bridge(email))