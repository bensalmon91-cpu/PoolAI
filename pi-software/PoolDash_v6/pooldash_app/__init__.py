import os
from flask import Flask, Response, redirect, request, g
from .config import Settings
from .blueprints.alarms import alarms_bp
from .blueprints.health import health_bp
from .translations import get_translator, SUPPORTED_LANGUAGES

def create_app():
    """Application factory so config/blueprints stay tidy."""
    app = Flask(__name__, template_folder="templates", static_folder="static")

    # Load settings (env overrides config.py)
    cfg = Settings.from_env()
    app.config.from_mapping(cfg.to_dict())
    # Read version from VERSION file
    version_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "VERSION")
    try:
        with open(version_file) as f:
            version = f.read().strip()
    except:
        version = "unknown"
    app.config["APP_VERSION"] = f"PoolAIssistant v{version}"
    app.secret_key = app.config.get("SECRET_KEY", "change-me")

    # ---- Persisted PoolAIssistant settings (editable in UI) ----
    from .persist import load as _load_persisted, save as _save_persisted, settings_path as _settings_path, unique_names as _unique_names

    def _distinct_hosts_from_pool_db(db_path: str):
        """Return distinct controller IPs from the readings DB.

        Supports both table names used across PoolAIssistant logger versions: `readings` and `pool_readings`.
        """
        import sqlite3
        if not db_path or not os.path.exists(db_path):
            return []
        try:
            con = sqlite3.connect(db_path)
            con.row_factory = sqlite3.Row
            # Determine which table exists
            tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            table = "readings" if "readings" in tables else ("pool_readings" if "pool_readings" in tables else None)
            if not table:
                con.close()
                return []
            rows = con.execute(
                f"SELECT DISTINCT host FROM {table} WHERE host IS NOT NULL AND host != '' ORDER BY host"
            ).fetchall()
            con.close()
            return [r["host"] for r in rows if r["host"]]
        except Exception:
            return []

    def _apply_persisted(persisted: dict):
        """Apply persisted settings to app.config and rebuild tabs."""
        app.config["MAINTENANCE_ACTIONS"] = persisted.get("maintenance_actions", [])
        app.config["HOST_NAMES"] = persisted.get("host_names", {})
        app.config["CONTROLLERS"] = persisted.get("controllers", [])

        # Prefer explicit controllers list (enabled only)
        controllers = [c for c in (app.config.get("CONTROLLERS") or []) if c.get("enabled")]
        if controllers:
            # ensure unique names
            hosts = [c.get("host") for c in controllers if c.get("host")]
            host_names = {c["host"]: c.get("name") or c["host"] for c in controllers if c.get("host")}
            host_to_name = _unique_names(hosts, host_names)
            app.config["POOL_IPS"] = {name: host for host, name in host_to_name.items()}
            app.config["POOLS"] = list(app.config["POOL_IPS"].keys())
            return

        # If nothing explicitly enabled, fall back to whatever is in the readings DB
        hosts = _distinct_hosts_from_pool_db(app.config.get("POOL_DB_PATH", ""))
        if hosts:
            host_to_name = _unique_names(hosts, app.config.get("HOST_NAMES", {}))
            app.config["POOL_IPS"] = {name: host for host, name in host_to_name.items()}
            app.config["POOLS"] = list(app.config["POOL_IPS"].keys())

    persisted = _load_persisted(app.instance_path)
    _apply_persisted(persisted)

    # track settings file mtime for hot-reload
    try:
        app.config["_PERSIST_PATH"] = str(_settings_path(app.instance_path))
        app.config["_PERSIST_MTIME"] = os.path.getmtime(app.config["_PERSIST_PATH"]) if os.path.exists(app.config["_PERSIST_PATH"]) else 0.0
    except Exception:
        app.config["_PERSIST_PATH"] = ""
        app.config["_PERSIST_MTIME"] = 0.0

    @app.before_request
    def _hot_reload_settings():
        """Hot-reload pool/controllers settings if the JSON file changed.

        This lets you enable/disable tabs and change IPs without restarting Flask.
        """
        p = app.config.get("_PERSIST_PATH")
        if not p:
            return
        try:
            mtime = os.path.getmtime(p) if os.path.exists(p) else 0.0
        except Exception:
            return
        if mtime and mtime != app.config.get("_PERSIST_MTIME"):
            app.config["_PERSIST_MTIME"] = mtime
            persisted = _load_persisted(app.instance_path)
            _apply_persisted(persisted)

    # ---- Translation System ----
    @app.before_request
    def _setup_language():
        """Set up language for the current request."""
        persisted = _load_persisted(app.instance_path)
        g.language = persisted.get("language", "en")
        g.translate = get_translator(g.language)

    @app.context_processor
    def inject_translation():
        """Make translation function and language info available in templates."""
        lang = getattr(g, 'language', 'en')
        return {
            '_': getattr(g, 'translate', get_translator('en')),
            'current_language': lang,
            'supported_languages': SUPPORTED_LANGUAGES,
        }

    # ---- IP View defaults (can be overridden by Settings/env) ----
    # Default target if none provided
    app.config.setdefault("TARGET_HOST", "")

    # Default pool -> IP mapping (only if not already provided or empty)
    # NOTE: if controllers are configured, they will override this.
    if not isinstance(app.config.get("POOL_IPS"), dict) or not app.config.get("POOL_IPS"):
        app.config["POOL_IPS"] = {}
        app.config["POOLS"] = []

    # Register blueprints
    from .blueprints.main_ui import main_bp
    from .blueprints.charts import charts_bp
    from .blueprints.proxy import proxy_bp
    from .blueprints.pump_selector import pump_bp
    # IP View disabled - replaced with direct links in Settings
    # from .blueprints.ip_view import ip_view_bp

    # app.register_blueprint(ip_view_bp)  # Disabled - use Settings > Controller Web Access instead
    app.register_blueprint(main_bp)
    app.register_blueprint(charts_bp)
    app.register_blueprint(proxy_bp, url_prefix="/proxy")
    app.register_blueprint(pump_bp, url_prefix="/pump")
    app.register_blueprint(alarms_bp)
    app.register_blueprint(health_bp)

    # AI Assistant blueprint
    try:
        from .blueprints.ai_assistant import ai_bp, init_local_db
        app.register_blueprint(ai_bp)
        # Initialize AI local database
        with app.app_context():
            init_local_db()
    except Exception as e:
        import sys
        print(f"Warning: Failed to load AI Assistant blueprint: {e}", file=sys.stderr)

    # ---- Captive Portal Detection Handlers ----
    # These routes handle connectivity checks from iOS/Android devices
    # When the AP redirects captive.apple.com etc. to our IP, we respond appropriately
    #
    # Key insight: To make iOS show the captive portal sheet (allowing users to access
    # our setup wizard), we must NOT return "Success" - we redirect to our setup page instead.
    # This makes iOS recognize it as a captive portal and display our page in its WebView.

    @app.route('/hotspot-detect.html')
    def apple_captive_portal():
        """Apple iOS captive portal detection - redirect to setup wizard.

        iOS checks this URL to detect captive portals. By redirecting instead of
        returning 'Success', iOS will show the captive portal WebView with our setup page.
        """
        # Redirect to setup wizard - this triggers iOS captive portal sheet
        return redirect('http://192.168.4.1/setup/wizard', code=302)

    @app.route('/library/test/success.html')
    def apple_captive_portal_alt():
        """Alternative Apple captive portal check - redirect to setup wizard."""
        return redirect('http://192.168.4.1/setup/wizard', code=302)

    @app.route('/generate_204')
    def android_captive_portal():
        """Android captive portal detection - redirect to setup wizard.

        Android expects 204 for 'no captive portal'. By redirecting, we trigger
        the captive portal login page to appear.
        """
        return redirect('http://192.168.4.1/setup/wizard', code=302)

    @app.route('/gen_204')
    def android_captive_portal_alt():
        """Alternative Android captive portal check - redirect to setup wizard."""
        return redirect('http://192.168.4.1/setup/wizard', code=302)

    @app.route('/connectivitycheck.gstatic.com')
    def google_connectivity_check():
        """Google connectivity check - redirect to setup wizard."""
        return redirect('http://192.168.4.1/setup/wizard', code=302)

    @app.route('/success.txt')
    def firefox_captive_portal():
        """Firefox captive portal check - redirect to setup wizard."""
        return redirect('http://192.168.4.1/setup/wizard', code=302)

    @app.route('/canonical.html')
    def firefox_captive_portal_alt():
        """Firefox alternative captive portal check."""
        return redirect('http://192.168.4.1/setup/wizard', code=302)

    # Catch-all for any other captive portal detection domains
    @app.route('/ncsi.txt')
    def windows_captive_portal():
        """Windows NCSI captive portal check."""
        return redirect('http://192.168.4.1/setup/wizard', code=302)

    # ---- Performance: Add cache headers for static assets ----
    @app.after_request
    def add_cache_headers(response):
        from flask import request as flask_request
        # Cache static assets (CSS, JS, images) for 1 hour
        if '/static/' in flask_request.path:
            response.cache_control.max_age = 3600
            response.cache_control.public = True
        # Cache JS/CSS content types
        content_type = response.content_type or ''
        if 'javascript' in content_type or 'css' in content_type:
            response.cache_control.max_age = 3600
        return response

    return app
