from flask import Blueprint, request, render_template, url_for, current_app, jsonify
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple, List
from markupsafe import Markup
import os
import sqlite3
import math
import time

charts_bp = Blueprint("charts", __name__, url_prefix="/charts")

# ---- Query cache with time-based invalidation ----
_query_cache = {}
_cache_ttl = 60  # Cache results for 60 seconds

def _get_cached_or_query(cache_key: str, query_fn):
    """Simple time-based cache for query results."""
    now = time.time()
    if cache_key in _query_cache:
        cached_time, cached_result = _query_cache[cache_key]
        if now - cached_time < _cache_ttl:
            return cached_result
    result = query_fn()
    _query_cache[cache_key] = (now, result)
    # Limit cache size to prevent memory issues
    if len(_query_cache) > 100:
        oldest_keys = sorted(_query_cache.keys(), key=lambda k: _query_cache[k][0])[:50]
        for k in oldest_keys:
            del _query_cache[k]
    return result

# Plot styling
PLOT_HEIGHT = 560
LINE_WIDTH = 2.6
MARKER_SIZE = 4
HOVERMODE = "x unified"

# URL params -> DB label & axis title (primary axis)
METRIC_TO_DB = {
    "chlorine": ("Chlorine_MeasuredValue", "Free Chlorine"),
    "ph": ("pH_MeasuredValue", "pH"),
    "orp": ("ORP_MeasuredValue", "ORP (mV)"),
    "temp": ("Temp_MeasuredValue", "Temperature (C)"),
}

# Secondary Yout label to overlay for certain metrics
YOUT_FOR_METRIC = {
    "chlorine": "Chlorine_Yout",
    "ph": "pH_Yout",
}

# Quick access ranges (shown as prominent buttons)
QUICK_RANGE_CHOICES = [
    ("1h", timedelta(hours=1)),
    ("3h", timedelta(hours=3)),
    ("6h", timedelta(hours=6)),
]

# Extended ranges (shown in dropdown)
EXTENDED_RANGE_CHOICES = [
    ("12h", timedelta(hours=12)),
    ("24h", timedelta(hours=24)),
    ("72h", timedelta(hours=72)),
    ("1w", timedelta(days=7)),
    ("2w", timedelta(days=14)),
    ("1m", timedelta(days=30)),
    ("3m", timedelta(days=90)),
    ("6m", timedelta(days=180)),
    ("1y", timedelta(days=365)),
    ("all", None),
]

# Combined for backward compatibility
RANGE_CHOICES = QUICK_RANGE_CHOICES + EXTENDED_RANGE_CHOICES


def _range_delta(key: str) -> Optional[timedelta]:
    for k, td in RANGE_CHOICES:
        if k == key:
            return td
    return timedelta(days=14)


def _fallback_db_path() -> str:
    preferred = "/opt/PoolAIssistant/data/pool_readings.sqlite3"
    if os.path.isdir("/opt/PoolAIssistant"):
        return preferred
    return os.path.join(os.getcwd(), "pool_readings.sqlite3")


def _get_db_path() -> str:
    path = current_app.config.get("POOL_DB_PATH") or os.getenv("POOL_DB_PATH") or os.getenv("POOLDB")
    return path or _fallback_db_path()


def _connect(db_path: str):
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    return con


def _get_bounds(
    con: sqlite3.Connection, pool: str, label: str, since_iso: Optional[str]
) -> Optional[Tuple[int, int, int]]:
    base_where = "pool = ? AND point_label = ?"
    params = [pool, label]
    if since_iso:
        base_where += " AND ts >= ?"
        params.append(since_iso)
    sql = f"""
        SELECT
          MIN(CAST(strftime('%s', ts) AS INTEGER)) AS start_epoch,
          MAX(CAST(strftime('%s', ts) AS INTEGER)) AS end_epoch,
          COUNT(*) AS row_count
        FROM readings
        WHERE {base_where}
    """
    row = con.execute(sql, params).fetchone()
    if not row or row["row_count"] is None or row["row_count"] == 0:
        return None
    return row["start_epoch"], row["end_epoch"], row["row_count"]


def _query_readings_windowed(
    pool: str, label: str, since_iso: Optional[str], max_points: int, downsample: bool
) -> Tuple[List[str], List[float]]:
    # Use caching for repeated queries with same parameters
    cache_key = f"readings:{pool}:{label}:{since_iso}:{max_points}:{downsample}"

    def _do_query():
        return _query_readings_windowed_uncached(pool, label, since_iso, max_points, downsample)

    return _get_cached_or_query(cache_key, _do_query)


def _query_readings_windowed_uncached(
    pool: str, label: str, since_iso: Optional[str], max_points: int, downsample: bool
) -> Tuple[List[str], List[float]]:
    db_path = _get_db_path()
    xs, ys = [], []
    try:
        with _connect(db_path) as con:
            bounds = _get_bounds(con, pool, label, since_iso)
            if not bounds:
                return xs, ys

            start_epoch, end_epoch, row_count = bounds

            # If downsampling is disabled, always pull all rows.
            if not downsample:
                base_where = "pool = ? AND point_label = ?"
                params = [pool, label]
                if since_iso:
                    base_where += " AND ts >= ?"
                    params.append(since_iso)
                sql_all = f"""
                    SELECT ts, value
                    FROM readings
                    WHERE {base_where}
                    ORDER BY ts
                """
                for r in con.execute(sql_all, params):
                    xs.append(r["ts"])
                    ys.append(r["value"])
                return xs, ys

            # Small result: pull all rows
            if row_count <= max_points:
                base_where = "pool = ? AND point_label = ?"
                params = [pool, label]
                if since_iso:
                    base_where += " AND ts >= ?"
                    params.append(since_iso)
                sql_all = f"""
                    SELECT ts, value
                    FROM readings
                    WHERE {base_where}
                    ORDER BY ts
                """
                for r in con.execute(sql_all, params):
                    xs.append(r["ts"])
                    ys.append(r["value"])
                return xs, ys

            # Otherwise bucket to <= max_points
            span = max(1, end_epoch - start_epoch)
            bucket_sec = max(1, math.ceil(span / max_points))

            base_where = "pool = ? AND point_label = ?"
            params = [pool, label]
            if since_iso:
                base_where += " AND ts >= ?"
                params.append(since_iso)

            sql_bucket_ids = f"""
                WITH base AS (
                  SELECT
                    rowid AS rid,
                    CAST((CAST(strftime('%s', ts) AS INTEGER) - ?) / ? AS INTEGER) AS bkt
                  FROM readings
                  WHERE {base_where}
                ),
                picked AS (
                  SELECT MIN(rid) AS rid
                  FROM base
                  GROUP BY bkt
                )
                SELECT r.ts, r.value
                FROM readings r
                JOIN picked p ON p.rid = r.rowid
                ORDER BY r.ts
            """
            all_params = [start_epoch, bucket_sec] + params
            for r in con.execute(sql_bucket_ids, all_params):
                xs.append(r["ts"])
                ys.append(r["value"])
    except sqlite3.OperationalError as e:
        raise RuntimeError(f"DB error: {e}. Using DB at: {db_path}")
    return xs, ys


def _as_percent(vals: List[float]) -> List[float]:
    """If series looks like 0..1, scale to 0..100. Otherwise return as-is."""
    if not vals:
        return vals
    try:
        finite = [v for v in vals if v is not None]
        if not finite:
            return vals
        vmax = max(finite)
        if vmax <= 1.5:
            return [v * 100 if v is not None else None for v in vals]
        return vals
    except (TypeError, ValueError):
        # Handle non-numeric values gracefully
        return vals


@charts_bp.route("/api/<pool>/<metric>/data")
def chart_data_api(pool: str, metric: str):
    """
    JSON API endpoint for chart data - enables async loading.
    Returns data for client-side Plotly rendering.
    """
    metric = metric.lower()
    if metric not in METRIC_TO_DB:
        return jsonify({"error": f"Unknown metric: {metric}"}), 400

    db_label, axis_title = METRIC_TO_DB[metric]

    range_key = request.args.get("range", "2w")
    td = _range_delta(range_key)
    since_iso = None
    if td is not None:
        cutoff = datetime.now(timezone.utc) - td
        since_iso = cutoff.strftime("%Y-%m-%dT%H:%M:%S")

    try:
        max_points = int(request.args.get("max_points", "500"))
        max_points = max(100, min(5000, max_points))
    except ValueError:
        max_points = 500

    downsample = bool(current_app.config.get("CHART_DOWNSAMPLE", True))

    try:
        xs, ys = _query_readings_windowed(pool, db_label, since_iso, max_points, downsample)
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 500

    # Get secondary Y axis data if applicable
    yout_label = YOUT_FOR_METRIC.get(metric)
    xs_yout: List[str] = []
    ys_yout: List[float] = []
    if yout_label:
        try:
            xs_yout, ys_yout = _query_readings_windowed(pool, yout_label, since_iso, max_points, downsample)
            ys_yout = _as_percent(ys_yout)
        except RuntimeError:
            xs_yout, ys_yout = [], []

    return jsonify({
        "pool": pool,
        "metric": metric,
        "axis_title": axis_title,
        "range_key": range_key,
        "max_points": max_points,
        "primary": {"x": xs, "y": ys},
        "secondary": {"x": xs_yout, "y": ys_yout} if xs_yout else None,
    })


@charts_bp.route("/<pool>/<metric>")
def chart_page(pool: str, metric: str):
    """
    Async chart page - loads instantly, fetches data via JavaScript.
    Includes Fast Mode toggle that persists via localStorage.
    """
    metric = metric.lower()
    if metric not in METRIC_TO_DB:
        metric = "chlorine"
    db_label, axis_title = METRIC_TO_DB[metric]

    range_key = request.args.get("range", "2w")

    # API URL for async data fetch (max_points will be set by JS based on fast mode)
    api_url = url_for("charts.chart_data_api", pool=pool, metric=metric)
    base_page_url = url_for("charts.chart_page", pool=pool, metric=metric)

    # Page HTML with loading spinner - renders IMMEDIATELY
    inner = f"""
      <div class="chart-header">
        <div>
          <h2>{pool} - {axis_title}</h2>
          <div class="btn-row" id="range-buttons">
            <!-- Range buttons will be populated by JS to include current max_points -->
          </div>
        </div>
        <div class="chart-controls">
          <button id="fast-mode-btn" class="btn" onclick="toggleFastMode()" title="Fast mode uses fewer data points for quicker loading">
            Loading...
          </button>
          <button id="download-chart-btn" class="btn btn--secondary" onclick="downloadChart()" title="Download chart as PNG image" style="display:none;">
            Download PNG
          </button>
          <span id="points-display" class="muted" style="font-size: 12px; margin-left: 8px;"></span>
        </div>
      </div>

      <div id="chart-container" style="min-height: 400px; position: relative;">
        <div id="chart-loading" style="display: flex; flex-direction: column; align-items: center; justify-content: center; height: 400px; color: #888;">
          <div class="spinner"></div>
          <p style="margin-top: 16px;">Loading chart data...</p>
        </div>
        <div id="chart" style="display: none;"></div>
        <div id="chart-error" style="display: none; color: #b00; padding: 20px;"></div>
      </div>

      <style>
        @keyframes spin {{ 0% {{ transform: rotate(0deg); }} 100% {{ transform: rotate(360deg); }} }}
        .spinner {{ width: 40px; height: 40px; border: 4px solid #f3f3f3; border-top: 4px solid #3498db; border-radius: 50%; animation: spin 1s linear infinite; }}
        .chart-header {{ display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 12px; margin-bottom: 12px; }}
        .chart-controls {{ display: flex; align-items: center; gap: 8px; }}
        .btn.fast-on {{ background: #4caf50; color: white; }}
        .btn.fast-off {{ background: #ff9800; color: white; }}
        .range-dropdown {{
          padding: 8px 12px;
          border: 2px solid var(--color-border, #ddd);
          border-radius: 8px;
          background: var(--color-surface, #fff);
          color: var(--color-text, #333);
          font-size: 14px;
          font-weight: 500;
          cursor: pointer;
          min-width: 80px;
        }}
        .range-dropdown:focus {{
          outline: none;
          border-color: var(--color-accent, #4a90e2);
        }}
        .range-dropdown.active {{
          background: var(--color-accent, #4a90e2);
          color: white;
          border-color: var(--color-accent, #4a90e2);
        }}
      </style>

      <script>
        (function() {{
          const FAST_POINTS = 150;
          const NORMAL_POINTS = 500;
          const STORAGE_KEY = 'pooldash_chart_fast_mode';
          const rangeKey = '{range_key}';
          const apiUrlBase = '{api_url}';
          const pageUrlBase = '{base_page_url}';
          const quickRanges = {[rk for rk, _ in QUICK_RANGE_CHOICES]};
          const extendedRanges = {[rk for rk, _ in EXTENDED_RANGE_CHOICES]};

          // Get fast mode preference from localStorage
          function isFastMode() {{
            return localStorage.getItem(STORAGE_KEY) === 'true';
          }}

          function setFastMode(enabled) {{
            localStorage.setItem(STORAGE_KEY, enabled ? 'true' : 'false');
          }}

          function getMaxPoints() {{
            return isFastMode() ? FAST_POINTS : NORMAL_POINTS;
          }}

          // Update the fast mode button appearance
          function updateFastModeButton() {{
            const btn = document.getElementById('fast-mode-btn');
            const pointsDisplay = document.getElementById('points-display');
            const fast = isFastMode();
            btn.textContent = fast ? '⚡ Fast Mode' : '📊 Full Detail';
            btn.className = 'btn ' + (fast ? 'fast-on' : 'fast-off');
            pointsDisplay.textContent = getMaxPoints() + ' pts';
          }}

          // Build range buttons with quick buttons + dropdown for extended ranges
          function buildRangeButtons() {{
            const container = document.getElementById('range-buttons');
            let html = '';

            // Quick range buttons (1h, 3h, 6h)
            for (const rk of quickRanges) {{
              const active = rk === rangeKey ? '' : 'secondary';
              const href = pageUrlBase + '?range=' + rk;
              html += '<a class="btn ' + active + '" href="' + href + '">' + rk + '</a>';
            }}

            // Extended range dropdown
            const isExtendedActive = extendedRanges.includes(rangeKey);
            html += '<select class="range-dropdown' + (isExtendedActive ? ' active' : '') + '" onchange="if(this.value) window.location.href=this.value">';
            html += '<option value="">' + (isExtendedActive ? rangeKey : 'More...') + '</option>';
            for (const rk of extendedRanges) {{
              if (rk !== rangeKey) {{
                const href = pageUrlBase + '?range=' + rk;
                html += '<option value="' + href + '">' + rk + '</option>';
              }}
            }}
            html += '</select>';

            container.innerHTML = html;
          }}

          // Toggle fast mode and reload chart
          window.toggleFastMode = function() {{
            setFastMode(!isFastMode());
            updateFastModeButton();
            buildRangeButtons();
            loadChart();
          }};

          // Download chart as PNG image
          window.downloadChart = function() {{
            const chartDiv = document.getElementById('chart');
            if (!chartDiv) return;

            const filename = '{pool}_{metric}_' + rangeKey + '_' + new Date().toISOString().slice(0,10) + '.png';

            Plotly.downloadImage(chartDiv, {{
              format: 'png',
              width: 1200,
              height: 600,
              filename: filename.replace('.png', '')
            }});
          }};

          // Load chart data
          function loadChart() {{
            const chartDiv = document.getElementById('chart');
            const loadingDiv = document.getElementById('chart-loading');
            const errorDiv = document.getElementById('chart-error');
            const maxPoints = getMaxPoints();

            // Show loading
            loadingDiv.style.display = 'flex';
            chartDiv.style.display = 'none';
            errorDiv.style.display = 'none';

            const apiUrl = apiUrlBase + '?range=' + rangeKey + '&max_points=' + maxPoints;

            fetch(apiUrl)
              .then(response => {{
                if (!response.ok) throw new Error('Network response was not ok');
                return response.json();
              }})
              .then(data => {{
                if (data.error) throw new Error(data.error);

                loadingDiv.style.display = 'none';

                if (!data.primary.x || data.primary.x.length === 0) {{
                  errorDiv.textContent = 'No data found for this selection.';
                  errorDiv.style.display = 'block';
                  return;
                }}

                chartDiv.style.display = 'block';

                // Build traces
                const traces = [];
                traces.push({{
                  x: data.primary.x,
                  y: data.primary.y,
                  mode: 'lines+markers',
                  name: data.axis_title,
                  line: {{ width: {LINE_WIDTH} }},
                  marker: {{ size: {MARKER_SIZE} }},
                  yaxis: 'y'
                }});

                if (data.secondary && data.secondary.x && data.secondary.x.length > 0) {{
                  traces.push({{
                    x: data.secondary.x,
                    y: data.secondary.y,
                    mode: 'lines',
                    name: 'Controller Output (%)',
                    line: {{ width: 1.8, dash: 'dot' }},
                    yaxis: 'y2'
                  }});
                }}

                const modeLabel = isFastMode() ? 'Fast' : 'Full';
                const layout = {{
                  height: {PLOT_HEIGHT},
                  hovermode: '{HOVERMODE}',
                  margin: {{ l: 50, r: 60, t: 40, b: 100 }},
                  xaxis: {{ title: 'Timestamp' }},
                  yaxis: {{ title: data.axis_title }},
                  title: data.pool + ' - ' + data.axis_title + ' (' + data.range_key + ', ' + modeLabel + ')',
                  legend: {{
                    orientation: 'h',
                    yanchor: 'top',
                    y: -0.15,
                    xanchor: 'center',
                    x: 0.5
                  }}
                }};

                if (data.secondary && data.secondary.y && data.secondary.y.length > 0) {{
                  const ys = data.secondary.y.filter(v => v !== null);
                  if (ys.length > 0) {{
                    const ymin = Math.max(0, Math.min(...ys, 0));
                    const ymax = Math.max(...ys, 100);
                    const pad = Math.max(2, 0.05 * (ymax - ymin || 100));
                    layout.yaxis2 = {{
                      title: 'Controller Output (%)',
                      overlaying: 'y',
                      side: 'right',
                      showgrid: false,
                      rangemode: 'tozero',
                      range: [Math.max(0, ymin - pad), Math.min(100, ymax + pad)]
                    }};
                  }}
                }}

                Plotly.newPlot('chart', traces, layout, {{ responsive: true }});

                // Update points display with actual count
                document.getElementById('points-display').textContent = data.primary.x.length + ' pts loaded';

                // Show download button now that chart is loaded
                document.getElementById('download-chart-btn').style.display = 'inline-block';
              }})
              .catch(error => {{
                loadingDiv.style.display = 'none';
                errorDiv.textContent = 'Error loading chart: ' + error.message;
                errorDiv.style.display = 'block';
              }});
          }}

          // Wait for Plotly to be available before loading chart
          function waitForPlotly(callback, maxWait) {{
            const start = Date.now();
            const check = function() {{
              if (typeof Plotly !== 'undefined') {{
                callback();
              }} else if (Date.now() - start < maxWait) {{
                setTimeout(check, 100);
              }} else {{
                document.getElementById('chart-loading').style.display = 'none';
                document.getElementById('chart-error').textContent = 'Chart library failed to load. Please refresh the page.';
                document.getElementById('chart-error').style.display = 'block';
              }}
            }};
            check();
          }}

          // Initialize
          updateFastModeButton();
          buildRangeButtons();
          waitForPlotly(loadChart, 10000);  // Wait up to 10 seconds for Plotly
        }})();
      </script>
    """

    # Load Plotly - try local first (faster for Pi), then CDN as fallback
    plotly_script = '''<script>
(function() {
  var loaded = false;
  function tryLoad(src, next) {
    var s = document.createElement('script');
    s.src = src;
    s.onload = function() { loaded = true; };
    s.onerror = function() { if (next && !loaded) next(); };
    document.head.appendChild(s);
  }
  tryLoad('/static/js/plotly-basic-2.27.0.min.js', function() {
    tryLoad('https://cdn.plot.ly/plotly-basic-2.27.0.min.js');
  });
})();
</script>'''

    return render_template(
        "base.html",
        active_tab=pool,
        head_extra=plotly_script,
        content_html=Markup(inner),
    )


@charts_bp.route("/api/<pool>/trends/data")
def trends_data_api(pool: str):
    """
    JSON API endpoint for trends chart data - enables async loading.
    """
    range_key = request.args.get("range", "24h")
    td = _range_delta(range_key)
    since_iso = None
    if td is not None:
        cutoff = datetime.now(timezone.utc) - td
        since_iso = cutoff.strftime("%Y-%m-%dT%H:%M:%S")

    try:
        max_points = int(request.args.get("max_points", "500"))
        max_points = max(100, min(2000, max_points))
    except ValueError:
        max_points = 500

    downsample = bool(current_app.config.get("CHART_DOWNSAMPLE", True))

    # Fetch all metrics
    metrics_data = {}
    for metric_key, (db_label, display_name) in METRIC_TO_DB.items():
        try:
            xs, ys = _query_readings_windowed(pool, db_label, since_iso, max_points, downsample)
            if xs and ys:
                metrics_data[metric_key] = {"x": xs, "y": ys, "name": display_name}
        except RuntimeError:
            pass

    return jsonify({
        "pool": pool,
        "range_key": range_key,
        "max_points": max_points,
        "metrics": metrics_data,
    })


@charts_bp.route("/<pool>/trends")
def trends_page(pool: str):
    """Async trends page - loads instantly, fetches data via JavaScript."""
    range_key = request.args.get("range", "24h")

    # API URL for async data fetch
    api_url = url_for("charts.trends_data_api", pool=pool)
    base_page_url = url_for("charts.trends_page", pool=pool)

    # Metric colors
    metric_colors = {
        "chlorine": "#00bcd4",
        "ph": "#ff9800",
        "orp": "#4caf50",
        "temp": "#e91e63",
    }

    inner = f"""
      <div class="chart-header">
        <div>
          <h2>{pool} - All Trends</h2>
          <p class="muted" style="margin:4px 0 8px;">All metrics normalized to 0-100% for trend comparison</p>
          <div class="btn-row" id="range-buttons">
            <!-- Range buttons populated by JS -->
          </div>
        </div>
        <div class="chart-controls">
          <button id="fast-mode-btn" class="btn" onclick="toggleFastMode()" title="Fast mode uses fewer data points for quicker loading">
            Loading...
          </button>
          <button id="download-chart-btn" class="btn btn--secondary" onclick="downloadChart()" title="Download chart as PNG image" style="display:none;">
            Download PNG
          </button>
          <span id="points-display" class="muted" style="font-size: 12px; margin-left: 8px;"></span>
        </div>
      </div>

      <div id="chart-container" style="min-height: 400px; position: relative;">
        <div id="chart-loading" style="display: flex; flex-direction: column; align-items: center; justify-content: center; height: 400px; color: #888;">
          <div class="spinner"></div>
          <p style="margin-top: 16px;">Loading trends data...</p>
        </div>
        <div id="chart" style="display: none;"></div>
        <div id="chart-error" style="display: none; color: #b00; padding: 20px;"></div>
      </div>

      <style>
        @keyframes spin {{ 0% {{ transform: rotate(0deg); }} 100% {{ transform: rotate(360deg); }} }}
        .spinner {{ width: 40px; height: 40px; border: 4px solid #f3f3f3; border-top: 4px solid #3498db; border-radius: 50%; animation: spin 1s linear infinite; }}
        .chart-header {{ display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 12px; margin-bottom: 12px; }}
        .chart-controls {{ display: flex; align-items: center; gap: 8px; }}
        .btn.fast-on {{ background: #4caf50; color: white; }}
        .btn.fast-off {{ background: #ff9800; color: white; }}
        .range-dropdown {{
          padding: 8px 12px;
          border: 2px solid var(--color-border, #ddd);
          border-radius: 8px;
          background: var(--color-surface, #fff);
          color: var(--color-text, #333);
          font-size: 14px;
          font-weight: 500;
          cursor: pointer;
          min-width: 80px;
        }}
        .range-dropdown:focus {{
          outline: none;
          border-color: var(--color-accent, #4a90e2);
        }}
        .range-dropdown.active {{
          background: var(--color-accent, #4a90e2);
          color: white;
          border-color: var(--color-accent, #4a90e2);
        }}
      </style>

      <script>
        (function() {{
          const FAST_POINTS = 150;
          const NORMAL_POINTS = 500;
          const STORAGE_KEY = 'pooldash_chart_fast_mode';
          const rangeKey = '{range_key}';
          const apiUrlBase = '{api_url}';
          const pageUrlBase = '{base_page_url}';
          const quickRanges = {[rk for rk, _ in QUICK_RANGE_CHOICES]};
          const extendedRanges = {[rk for rk, _ in EXTENDED_RANGE_CHOICES]};
          const metricColors = {str(metric_colors).replace("'", '"')};

          function isFastMode() {{
            return localStorage.getItem(STORAGE_KEY) === 'true';
          }}

          function setFastMode(enabled) {{
            localStorage.setItem(STORAGE_KEY, enabled ? 'true' : 'false');
          }}

          function getMaxPoints() {{
            return isFastMode() ? FAST_POINTS : NORMAL_POINTS;
          }}

          function updateFastModeButton() {{
            const btn = document.getElementById('fast-mode-btn');
            const pointsDisplay = document.getElementById('points-display');
            const fast = isFastMode();
            btn.textContent = fast ? '⚡ Fast Mode' : '📊 Full Detail';
            btn.className = 'btn ' + (fast ? 'fast-on' : 'fast-off');
            pointsDisplay.textContent = getMaxPoints() + ' pts';
          }}

          function buildRangeButtons() {{
            const container = document.getElementById('range-buttons');
            let html = '';

            // Quick range buttons (1h, 3h, 6h)
            for (const rk of quickRanges) {{
              const active = rk === rangeKey ? '' : 'secondary';
              const href = pageUrlBase + '?range=' + rk;
              html += '<a class="btn ' + active + '" href="' + href + '">' + rk + '</a>';
            }}

            // Extended range dropdown
            const isExtendedActive = extendedRanges.includes(rangeKey);
            html += '<select class="range-dropdown' + (isExtendedActive ? ' active' : '') + '" onchange="if(this.value) window.location.href=this.value">';
            html += '<option value="">' + (isExtendedActive ? rangeKey : 'More...') + '</option>';
            for (const rk of extendedRanges) {{
              if (rk !== rangeKey) {{
                const href = pageUrlBase + '?range=' + rk;
                html += '<option value="' + href + '">' + rk + '</option>';
              }}
            }}
            html += '</select>';

            container.innerHTML = html;
          }}

          window.toggleFastMode = function() {{
            setFastMode(!isFastMode());
            updateFastModeButton();
            buildRangeButtons();
            loadChart();
          }};

          window.downloadChart = function() {{
            const chartDiv = document.getElementById('chart');
            if (!chartDiv) return;

            const filename = '{pool}_trends_' + rangeKey + '_' + new Date().toISOString().slice(0,10) + '.png';

            Plotly.downloadImage(chartDiv, {{
              format: 'png',
              width: 1200,
              height: 600,
              filename: filename.replace('.png', '')
            }});
          }};

          function normalize(values) {{
            const finite = values.filter(v => v !== null && v !== undefined);
            if (finite.length === 0) return values.map(() => null);
            const vmin = Math.min(...finite);
            const vmax = Math.max(...finite);
            if (vmax === vmin) return values.map(v => v !== null ? 50 : null);
            return values.map(v => v !== null ? ((v - vmin) / (vmax - vmin)) * 100 : null);
          }}

          function loadChart() {{
            const chartDiv = document.getElementById('chart');
            const loadingDiv = document.getElementById('chart-loading');
            const errorDiv = document.getElementById('chart-error');
            const maxPoints = getMaxPoints();

            loadingDiv.style.display = 'flex';
            chartDiv.style.display = 'none';
            errorDiv.style.display = 'none';

            const apiUrl = apiUrlBase + '?range=' + rangeKey + '&max_points=' + maxPoints;

            fetch(apiUrl)
              .then(response => {{
                if (!response.ok) throw new Error('Network response was not ok');
                return response.json();
              }})
              .then(data => {{
                loadingDiv.style.display = 'none';

                const metricKeys = Object.keys(data.metrics || {{}});
                if (metricKeys.length === 0) {{
                  errorDiv.textContent = 'No data found for any metric.';
                  errorDiv.style.display = 'block';
                  return;
                }}

                chartDiv.style.display = 'block';

                const traces = [];
                let totalPoints = 0;
                for (const key of metricKeys) {{
                  const m = data.metrics[key];
                  totalPoints += m.x.length;
                  const normalized = normalize(m.y);
                  traces.push({{
                    x: m.x,
                    y: normalized,
                    mode: 'lines',
                    name: m.name,
                    line: {{ width: 2, color: metricColors[key] || '#888' }},
                    customdata: m.y,
                    hovertemplate: m.name + ': %{{y:.1f}}%<br>Raw: %{{customdata:.2f}}<extra></extra>'
                  }});
                }}

                const modeLabel = isFastMode() ? 'Fast' : 'Full';
                const layout = {{
                  height: {PLOT_HEIGHT},
                  hovermode: 'x unified',
                  margin: {{ l: 50, r: 30, t: 50, b: 100 }},
                  xaxis: {{ title: 'Time' }},
                  yaxis: {{
                    title: 'Normalized (%)',
                    range: [-5, 105],
                    ticksuffix: '%'
                  }},
                  title: data.pool + ' - All Trends (' + data.range_key + ', ' + modeLabel + ')',
                  legend: {{
                    orientation: 'h',
                    yanchor: 'top',
                    y: -0.15,
                    xanchor: 'center',
                    x: 0.5
                  }}
                }};

                Plotly.newPlot('chart', traces, layout, {{ responsive: true }});
                document.getElementById('points-display').textContent = totalPoints + ' pts loaded';

                // Show download button now that chart is loaded
                document.getElementById('download-chart-btn').style.display = 'inline-block';
              }})
              .catch(error => {{
                loadingDiv.style.display = 'none';
                errorDiv.textContent = 'Error loading chart: ' + error.message;
                errorDiv.style.display = 'block';
              }});
          }}

          // Wait for Plotly to be available before loading chart
          function waitForPlotly(callback, maxWait) {{
            const start = Date.now();
            const check = function() {{
              if (typeof Plotly !== 'undefined') {{
                callback();
              }} else if (Date.now() - start < maxWait) {{
                setTimeout(check, 100);
              }} else {{
                document.getElementById('chart-loading').style.display = 'none';
                document.getElementById('chart-error').textContent = 'Chart library failed to load. Please refresh the page.';
                document.getElementById('chart-error').style.display = 'block';
              }}
            }};
            check();
          }}

          // Initialize
          updateFastModeButton();
          buildRangeButtons();
          waitForPlotly(loadChart, 10000);  // Wait up to 10 seconds for Plotly
        }})();
      </script>
    """

    # Load Plotly - try local first (faster for Pi), then CDN as fallback
    plotly_script = '''<script>
(function() {
  var loaded = false;
  function tryLoad(src, next) {
    var s = document.createElement('script');
    s.src = src;
    s.onload = function() { loaded = true; };
    s.onerror = function() { if (next && !loaded) next(); };
    document.head.appendChild(s);
  }
  tryLoad('/static/js/plotly-basic-2.27.0.min.js', function() {
    tryLoad('https://cdn.plot.ly/plotly-basic-2.27.0.min.js');
  });
})();
</script>'''

    return render_template(
        "base.html",
        active_tab=pool,
        head_extra=plotly_script,
        content_html=Markup(inner),
    )


@charts_bp.route("/<pool>/lsi")
def lsi_chart_page(pool: str):
    """LSI history chart page."""
    from ..db.lsi_history import get_lsi_chart_data, get_lsi_history

    days = request.args.get("days", "30", type=str)
    try:
        since_days = int(days)
    except ValueError:
        since_days = 30

    # Get chart data
    timestamps, values = get_lsi_chart_data(pool, since_days=since_days)

    # Get recent history for the table
    history = get_lsi_history(pool, limit=20, since_days=since_days)

    # Build the page content
    inner = f"""
      <div class="chart-header">
        <div>
          <h2>{pool} - LSI History</h2>
          <p class="muted" style="margin:4px 0 8px;">Langelier Saturation Index trend over time</p>
          <div class="btn-row">
            <a class="btn {'secondary' if since_days != 7 else ''}" href="?days=7">7 days</a>
            <a class="btn {'secondary' if since_days != 30 else ''}" href="?days=30">30 days</a>
            <a class="btn {'secondary' if since_days != 90 else ''}" href="?days=90">90 days</a>
            <a class="btn {'secondary' if since_days != 180 else ''}" href="?days=180">6 months</a>
            <a class="btn {'secondary' if since_days != 365 else ''}" href="?days=365">1 year</a>
          </div>
        </div>
        <div class="chart-controls">
          <button id="download-chart-btn" class="btn btn--secondary" onclick="downloadChart()" title="Download chart as PNG image" style="display:none;">
            Download PNG
          </button>
        </div>
      </div>

      <div id="chart-container" style="min-height: 400px; position: relative;">
        <div id="chart"></div>
        <div id="chart-error" style="display: none; color: #b00; padding: 20px;"></div>
      </div>

      <style>
        .chart-header {{ display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 12px; margin-bottom: 12px; }}
        .chart-controls {{ display: flex; align-items: center; gap: 8px; }}
        .lsi-table {{ margin-top: 24px; }}
        .lsi-table table {{ width: 100%; border-collapse: collapse; }}
        .lsi-table th, .lsi-table td {{ padding: 8px 12px; text-align: left; border-bottom: 1px solid #ddd; }}
        .lsi-table th {{ background: #f5f5f5; font-weight: 600; }}
        .lsi-good {{ color: #4caf50; }}
        .lsi-warning {{ color: #ff9800; }}
        .lsi-danger {{ color: #f44336; }}
      </style>

      <script>
        const timestamps = {timestamps};
        const values = {values};

        // Wait for Plotly to be available
        function waitForPlotly(callback, maxWait) {{
          const start = Date.now();
          const check = function() {{
            if (typeof Plotly !== 'undefined') {{
              callback();
            }} else if (Date.now() - start < maxWait) {{
              setTimeout(check, 100);
            }} else {{
              document.getElementById('chart-error').textContent = 'Chart library failed to load. Please refresh the page.';
              document.getElementById('chart-error').style.display = 'block';
            }}
          }};
          check();
        }}

        function renderChart() {{
          if (timestamps.length === 0) {{
            document.getElementById('chart-error').textContent = 'No LSI readings found for this period.';
            document.getElementById('chart-error').style.display = 'block';
            return;
          }}

          // Color points based on LSI value
          const colors = values.map(v => {{
            if (v >= -0.3 && v <= 0.3) return '#4caf50';  // Good (balanced)
            if (v >= -0.5 && v <= 0.5) return '#ff9800';  // Warning
            return '#f44336';  // Danger (corrosive or scaling)
          }});

          const trace = {{
            x: timestamps,
            y: values,
            mode: 'lines+markers',
            name: 'LSI',
            line: {{ width: 2.5, color: '#3498db' }},
            marker: {{ size: 8, color: colors }},
            hovertemplate: 'LSI: %{{y:.2f}}<br>%{{x}}<extra></extra>'
          }};

          // Add reference bands
          const shapes = [
            // Good zone (-0.3 to 0.3)
            {{ type: 'rect', xref: 'paper', x0: 0, x1: 1, yref: 'y', y0: -0.3, y1: 0.3, fillcolor: 'rgba(76, 175, 80, 0.1)', line: {{ width: 0 }} }},
          ];

          const layout = {{
            height: {PLOT_HEIGHT},
            hovermode: 'x unified',
            margin: {{ l: 50, r: 60, t: 40, b: 100 }},
            xaxis: {{ title: 'Date' }},
            yaxis: {{
              title: 'LSI Value',
              zeroline: true,
              zerolinewidth: 2,
              zerolinecolor: '#888'
            }},
            shapes: shapes,
            legend: {{
              orientation: 'h',
              yanchor: 'top',
              y: -0.15,
              xanchor: 'center',
              x: 0.5
            }},
            annotations: [
              {{ x: 1.02, y: 0.3, xref: 'paper', yref: 'y', text: 'Scaling', showarrow: false, font: {{ size: 10, color: '#f44336' }} }},
              {{ x: 1.02, y: 0, xref: 'paper', yref: 'y', text: 'Balanced', showarrow: false, font: {{ size: 10, color: '#4caf50' }} }},
              {{ x: 1.02, y: -0.3, xref: 'paper', yref: 'y', text: 'Corrosive', showarrow: false, font: {{ size: 10, color: '#f44336' }} }}
            ]
          }};

          Plotly.newPlot('chart', [trace], layout, {{ responsive: true }});
          document.getElementById('download-chart-btn').style.display = 'inline-block';
        }}

        function downloadChart() {{
          const chartDiv = document.getElementById('chart');
          if (!chartDiv) return;
          const filename = '{pool}_lsi_' + new Date().toISOString().slice(0,10);
          Plotly.downloadImage(chartDiv, {{ format: 'png', width: 1200, height: 600, filename: filename }});
        }}

        // Initialize - wait for Plotly then render
        waitForPlotly(renderChart, 10000);
      </script>
    """

    # Add recent readings table
    if history:
        inner += """
          <div class="lsi-table">
            <h3>Recent Readings</h3>
            <table>
              <thead>
                <tr>
                  <th>Date</th>
                  <th>LSI</th>
                  <th>pH</th>
                  <th>Temp (°C)</th>
                  <th>Source</th>
                </tr>
              </thead>
              <tbody>
        """
        for row in history:
            lsi_val = row.get('lsi_value', 0)
            if -0.3 <= lsi_val <= 0.3:
                lsi_class = 'lsi-good'
            elif -0.5 <= lsi_val <= 0.5:
                lsi_class = 'lsi-warning'
            else:
                lsi_class = 'lsi-danger'

            ts = row.get('timestamp', '')[:16].replace('T', ' ')
            ph = f"{row.get('ph', '-'):.1f}" if row.get('ph') else '-'
            temp = f"{row.get('temperature_c', '-'):.1f}" if row.get('temperature_c') else '-'
            source = row.get('source', 'manual')

            inner += f"""
                <tr>
                  <td>{ts}</td>
                  <td class="{lsi_class}">{lsi_val:.2f}</td>
                  <td>{ph}</td>
                  <td>{temp}</td>
                  <td>{source}</td>
                </tr>
            """
        inner += """
              </tbody>
            </table>
          </div>
        """

    # Load Plotly - try local first (faster for Pi), then CDN as fallback
    plotly_script = '''<script>
(function() {
  var loaded = false;
  function tryLoad(src, next) {
    var s = document.createElement('script');
    s.src = src;
    s.onload = function() { loaded = true; };
    s.onerror = function() { if (next && !loaded) next(); };
    document.head.appendChild(s);
  }
  tryLoad('/static/js/plotly-basic-2.27.0.min.js', function() {
    tryLoad('https://cdn.plot.ly/plotly-basic-2.27.0.min.js');
  });
})();
</script>'''

    return render_template(
        "base.html",
        active_tab=pool,
        head_extra=plotly_script,
        content_html=Markup(inner),
    )
