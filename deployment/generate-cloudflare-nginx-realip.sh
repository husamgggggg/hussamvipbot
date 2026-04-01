#!/usr/bin/env bash
# يولّد ملفاً لـ Nginx يثق بعناوين Cloudflare ويستخدم CF-Connecting-IP كـ IP الزائر.
# التشغيل على السيرفر (مثلاً):
#   sudo bash deployment/generate-cloudflare-nginx-realip.sh /etc/nginx/conf.d/cloudflare-realip.conf
# ثم داخل كتلة http { } في nginx.conf أضف:
#   include /etc/nginx/conf.d/cloudflare-realip.conf;
# أو ضمّن نفس الأسطر داخل server { } للموقع فقط.
# حدّث الملف عند تغيّر نطاقات Cloudflare: https://www.cloudflare.com/ips/

set -euo pipefail
OUT="${1:-/etc/nginx/conf.d/cloudflare-realip.conf}"

tmp="$(mktemp)"
{
  echo "# تلقائي من https://www.cloudflare.com/ips/ — أعد التوليد دورياً"
  curl -fsSL https://www.cloudflare.com/ips-v4 | sed 's/^/set_real_ip_from /;s/$/;/'
  curl -fsSL https://www.cloudflare.com/ips-v6 | sed 's/^/set_real_ip_from /;s/$/;/'
  echo "real_ip_header CF-Connecting-IP;"
  echo "real_ip_recursive on;"
} >"$tmp"

install -m 0644 "$tmp" "$OUT"
rm -f "$tmp"
echo "تم الكتابة: $OUT"
echo "ثم: sudo nginx -t && sudo systemctl reload nginx"
