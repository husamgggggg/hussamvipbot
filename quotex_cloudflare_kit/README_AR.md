# حزمة Quotex + Cloudflare / WebSocket

مجلد منفصل يضم **الملفات القابلة للنقل** المستخدمة للربط مع Quotex عبر `pyquotex`، وتمرير **البروكسي** إلى WebSocket، وتشغيل **جسر Playwright** المحلي لتقليل فشل الاتصال بسبب Cloudflare (403 / cf-mitigated / challenge).

## محتويات المجلد

| الملف | الدور |
|--------|--------|
| `ws_bridge.py` | عملية مستقلة: Chromium (Playwright) ↔ `websockets` على `127.0.0.1` ↔ عميل `pyquotex`. يجب أن يمر **نفس بروكسي تسجيل الدخول** إلى Chromium (`--proxy-url` من `bot.py` أو متغيرات البيئة في الملف). |
| `zenrows_pyquotex.py` | بناء قاموس `proxies` لـ HTTP/HTTPS من `ZENROWS_*` / `QUOTEX_PROXY_*` / `HTTPS_PROXY`. |
| `nexora_pyquotex_ws_on_message.py` | استبدال `WebsocketClient.on_message` في pyquotex لمعالجة رسائل نصية/ثنائية وSocket.IO دون خطأ `str has no attribute get`. |
| `requirements-quotex-cloudflare-kit.txt` | التبعيات الضرورية لهذه الطبقة. |
| `env.example` | أهم متغيرات البيئة (`QUOTEX_USE_PLAYWRIGHT_BRIDGE`, بروكسي، إلخ). |

## ما الذي لا يزال داخل `bot.py`؟

منطق الدمج (patch على `QuotexAPI.start_websocket`، تهيئة ZenRows، `create_stealth_websocket`، تشغيل `ws_bridge.py` كـ subprocess، إلخ) موجود في المشروع الرئيسي:

- **`husaam_trader/aboodtraderFINAL/bot.py`** تقريبًا من السطر **57** (`_HUSAAM_WS_LAST`) حتى **666** (`_install_pyquotex_ws_proxy_patch` + `QX_HTTP_PROXIES`).

قبل هذا القسم يجب أن يكون متوفرًا في `bot.py`: استيراد `pyquotex` والمتغير **`QX`**، ووحدات مثل `asyncio`, `socket`, `ssl`, `subprocess`, `urllib.parse`, `threading.Thread`, واختياريًا `websocket` و`curl_cffi.requests`، بالإضافة إلى **`log`** بعد `logging.basicConfig` (جزء من الدوال يُنفَّذ لاحقًا عند وصول رسائل WS ويستخدم `log`).

## الاستخدام

1. انسخ مجلد `quotex_cloudflare_kit` إلى مشروعك أو اتركه بجانب `bot.py` كما في المشروع الحالي.
2. ثبّت التبعيات من `requirements-quotex-cloudflare-kit.txt`.
3. ثبّت متصفح Playwright: `playwright install chromium`
4. عيّن المتغيرات من `env.example` (خاصة `QUOTEX_USE_PLAYWRIGHT_BRIDGE=1` والبروكسي إن وُجد).
5. تأكد أن مسار `ws_bridge.py` الذي يمرّر إليه `bot.py` يشير إلى نسخة الحزمة (الكود يستخدم `os.path.dirname(__file__)` بجانب `bot.py`).

## ملاحظة

هذه الحزمة **لا تضمن** تجاوز Cloudflare في كل الحالات؛ الهدف هو **مواءمة IP الجلسة** (HTTP عبر البروكسي + WS عبر نفس البروكسي أو عبر متصفح حقيقي في الجسر) وتصحيح سلوك المكتبة مع أنواع الرسائل.
