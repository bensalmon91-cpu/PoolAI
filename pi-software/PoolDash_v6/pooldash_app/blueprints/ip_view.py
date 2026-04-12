from flask import Blueprint, current_app, render_template, request, Response
from urllib.parse import urlparse, urljoin, quote
import re
import requests

ip_view_bp = Blueprint("ip_view", __name__, url_prefix="")

@ip_view_bp.app_context_processor
def inject_defaults():
    return {
        "pools": current_app.config.get("POOLS", []),
        "pool_ips": current_app.config.get("POOL_IPS", {}),
    }

def _normalize_target(raw: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        return ""
    if not raw.startswith("http://") and not raw.startswith("https://"):
        raw = "http://" + raw
    u = urlparse(raw)
    host = u.hostname or ""
    port = u.port
    scheme = u.scheme or "http"
    if not host:
        return ""
    # default port
    if port:
        netloc = f"{host}:{port}"
    else:
        netloc = host
    return f"{scheme}://{netloc}"

@ip_view_bp.route("/ip_view")
def ip_view_index():
    pool = request.args.get("pool", "")
    host = request.args.get("host", "")
    pool_ips = current_app.config.get("POOL_IPS", {}) or {}

    target = ""
    if pool and pool in pool_ips:
        target = _normalize_target(pool_ips[pool])
    elif host:
        target = _normalize_target(host)
    else:
        # fallback to configured target
        target = _normalize_target(current_app.config.get("TARGET_HOST", ""))

    if not target:
        target = "http://127.0.0.1"

    ip_raw_url = target
    ip_proxied_src = "/ip_proxy?target=" + quote(target, safe="")
    return render_template(
        "ip_view.html",
        active_tab="IP View",
        selected_pool=pool,
        ip_raw_url=ip_raw_url,
        ip_proxied_src=ip_proxied_src,
    )

@ip_view_bp.route("/ip_proxy")
def ip_proxy():
    target = request.args.get("target", "")
    target = _normalize_target(target)
    if not target:
        return Response("Missing target", status=400)

    # pass-through path and query
    path = request.args.get("path", "")
    upstream = urljoin(target + "/", path.lstrip("/"))
    # Forward the browser path if it exists
    # (If the iframe navigates, it stays under our proxy thanks to <base>)
    try:
        r = requests.get(upstream, timeout=10)
    except Exception as e:
        return Response(f"Proxy error: {e}", status=502)

    content_type = r.headers.get("Content-Type", "")
    body = r.content

    if content_type.startswith("text/html"):
        # Handle UTF-8 BOM by decoding from raw bytes
        raw_bytes = r.content
        # Remove UTF-8 BOM (EF BB BF) if present
        if raw_bytes.startswith(b'\xef\xbb\xbf'):
            raw_bytes = raw_bytes[3:]

        try:
            text = raw_bytes.decode('utf-8')
        except UnicodeDecodeError:
            text = raw_bytes.decode('latin-1')

        # ensure relative links keep working via base tag
        if "<head" in text.lower():
            text = re.sub(r"(?is)<head([^>]*)>", rf"<head\1><base href=\"{target}/\">", text, count=1)
        else:
            text = f'<head><base href="{target}/"></head>' + text
        # remove common frame busters
        text = re.sub(r"(?is)if\s*\(\s*top\s*!=\s*self\s*\)\s*\{[^}]*\}", "", text)
        body = text.encode("utf-8")
        content_type = "text/html; charset=utf-8"

    resp = Response(body, status=r.status_code)
    resp.headers["Content-Type"] = content_type or "application/octet-stream"
    resp.headers["X-Frame-Options"] = "ALLOWALL"
    return resp
