from flask import Blueprint, current_app, request, Response, redirect, session
import requests, re
from urllib.parse import urljoin

proxy_bp = Blueprint("proxy", __name__)

def _passthrough(upstream):
    def generate():
        for chunk in upstream.iter_content(chunk_size=8192):
            if chunk: yield chunk
    resp = Response(generate(), status=upstream.status_code)
    for h in ("Content-Type","Cache-Control","Last-Modified","ETag"):
        if h in upstream.headers: resp.headers[h] = upstream.headers[h]
    return resp

@proxy_bp.route("/")
def root_redirect():
    return redirect("/proxy/ui/")

@proxy_bp.route("/ui/", defaults={"path": ""}, methods=["GET","POST","PUT","PATCH","DELETE"])
@proxy_bp.route("/ui/<path:path>", methods=["GET","POST","PUT","PATCH","DELETE"])
def proxy_ui(path):
    # Get host from query param, or fall back to session
    target_host = request.args.get('host')
    if target_host:
        # Store in session for subsequent requests (CSS, JS, etc.)
        session['proxy_host'] = target_host
    else:
        target_host = session.get('proxy_host') or current_app.config.get('TARGET_HOST', '')

    if not target_host:
        return '<div style="padding:20px;font-family:sans-serif;"><p>No target host specified. Use ?host=&lt;ip&gt;</p><a href="/" style="display:inline-block;margin-top:16px;padding:12px 20px;background:#4a90e2;color:white;text-decoration:none;border-radius:8px;">Back to PoolAIssistant</a></div>', 400

    device_base = f"http://{target_host}"
    target_url = urljoin(device_base + "/", path)
    # Filter out 'host' param - don't pass it to upstream
    upstream_params = {k: v for k, v in request.args.items() if k != 'host'}
    try:
        upstream = requests.request(
            method=request.method, url=target_url, params=upstream_params if upstream_params else None,
            headers={k:v for k,v in request.headers if k.lower() not in ("host","content-length","transfer-encoding","connection","accept-encoding")},
            data=request.get_data() if request.method in ("POST","PUT","PATCH") else None,
            stream=True, timeout=10)
    except requests.RequestException as e:
        return f'<div style="padding:20px;font-family:sans-serif;"><p>Proxy error to {target_url}: {e}</p><a href="/" style="display:inline-block;margin-top:16px;padding:12px 20px;background:#4a90e2;color:white;text-decoration:none;border-radius:8px;">Back to PoolAIssistant</a></div>', 502

    ctype = upstream.headers.get("Content-Type", "").lower()
    if "text/html" in ctype:
        # Get raw bytes and decode, stripping BOM
        raw = upstream.content
        if raw.startswith(b'\xef\xbb\xbf'):
            raw = raw[3:]
        html = raw.decode('utf-8', errors='replace')
        # Insert base tag for relative URLs
        if re.search(r"<head[^>]*>", html, flags=re.I):
            html = re.sub(r"(<head[^>]*>)", rf'\1<base href="/proxy/ui/">', html, count=1, flags=re.I)
        else:
            html = f'<head><base href="/proxy/ui/"></head>{html}'
        # JavaScript shim to rewrite URLs for AJAX/fetch calls + back button (only on top window)
        shim_code = f"""(function(){{try{{var H="{target_host}";var P="/proxy/ui/";function fix(u){{try{{if(typeof u==="string"&&u.startsWith("/"))return P+u.slice(1);if(typeof u==="string"&&!u.startsWith("http")&&!u.startsWith("/proxy")&&!u.startsWith("data:"))return P+u}}catch(e){{}};return u}}var of=window.fetch;if(of){{window.fetch=function(i,n){{if(typeof i==="string"){{i=fix(i)}}return of(i,n)}}}}var OX=window.XMLHttpRequest;if(OX&&OX.prototype&&OX.prototype.open){{var o=OX.prototype.open;OX.prototype.open=function(m,u){{try{{u=fix(u)}}catch(e){{}};return o.apply(this,arguments)}}}}if(window===window.top&&!document.getElementById('poolai-back-btn')){{var d=document.createElement('div');d.id='poolai-back-btn';d.innerHTML='<a href="/" target="_top" style="display:flex;align-items:center;gap:8px;background:#4a90e2;color:white;padding:12px 20px;border-radius:8px;text-decoration:none;font-family:system-ui,sans-serif;font-weight:600;box-shadow:0 4px 12px rgba(0,0,0,0.3);">&#8592; Back to PoolAIssistant</a>';d.style.cssText='position:fixed;bottom:20px;right:20px;z-index:99999;';document.body.appendChild(d)}}}}catch(e){{}}}})();"""
        shim = f"<script>{shim_code}</script>"
        html = html.replace("</body>", shim + "</body>", 1)
        html = html.replace("</BODY>", shim + "</BODY>", 1)
        return html
    return _passthrough(upstream)
