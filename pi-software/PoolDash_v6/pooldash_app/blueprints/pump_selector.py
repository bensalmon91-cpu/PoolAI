from flask import Blueprint, render_template_string

pump_bp = Blueprint("pump", __name__)

@pump_bp.route("/")
def index():
    # Placeholder UI so the iframe in Maintenance page always loads
    return render_template_string("""    <html><head><meta name=viewport content="width=device-width,initial-scale=1"></head>
    <body style="font-family:system-ui; margin:0; padding:12px">
      <h3>Pump selector</h3>
      <p>This is a placeholder panel. Replace with your real pump control UI.</p>
      <p>You can find it in <code>pooldash_app/blueprints/pump_selector.py</code>.</p>
    </body></html>""")
