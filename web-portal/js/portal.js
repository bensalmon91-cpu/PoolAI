(function () {
  var tabs = document.getElementById("pool-tabs");
  var summary = document.getElementById("summary-grid");
  var title = document.getElementById("pool-title");
  var meta = document.getElementById("pool-meta");
  var recentBody = document.getElementById("recent-body");
  var aiList = document.getElementById("ai-list");
  var alarmList = document.getElementById("alarm-list");
  var pools = [];

  function formatLabel(label) {
    return label
      .replace("_MeasuredValue", "")
      .replace("_", " ");
  }

  function renderTabs() {
    tabs.innerHTML = "";
    pools.forEach(function (pool, idx) {
      var btn = document.createElement("button");
      btn.className = "tab-button" + (idx === 0 ? " active" : "");
      btn.textContent = pool.name;
      btn.addEventListener("click", function () {
        document.querySelectorAll(".tab-button").forEach(function (el) {
          el.classList.remove("active");
        });
        btn.classList.add("active");
        loadPool(pool);
      });
      tabs.appendChild(btn);
    });
  }

  function renderSummary(values) {
    summary.innerHTML = "";
    if (!values.length) {
      summary.innerHTML = "<p class=\"muted\">No readings available yet.</p>";
      return;
    }
    values.forEach(function (row) {
      var card = document.createElement("div");
      card.className = "summary-card";
      card.innerHTML =
        "<div class=\"summary-label\">" +
        formatLabel(row.point_label) +
        "</div>" +
        "<div class=\"summary-value\">" +
        (row.value === null ? "-" : Number(row.value).toFixed(2)) +
        "</div>" +
        "<div class=\"summary-meta\">" +
        row.ts +
        "</div>";
      summary.appendChild(card);
    });
  }

  function renderRecent(rows) {
    recentBody.innerHTML = "";
    if (!rows.length) {
      recentBody.innerHTML = "<tr><td colspan=\"3\" class=\"muted\">No recent readings.</td></tr>";
      return;
    }
    rows.forEach(function (row) {
      var tr = document.createElement("tr");
      tr.innerHTML =
        "<td class=\"mono\">" +
        row.ts +
        "</td><td>" +
        formatLabel(row.point_label) +
        "</td><td class=\"mono\">" +
        (row.value === null ? "-" : Number(row.value).toFixed(2)) +
        "</td>";
      recentBody.appendChild(tr);
    });
  }

  function loadPool(pool) {
    title.textContent = pool.name;
    if (meta) {
      var metaBits = [];
      if (pool.location) metaBits.push(pool.location);
      if (pool.notes) metaBits.push(pool.notes);
      meta.textContent = metaBits.join(" · ");
    }
    fetch("/api/portal/pool/" + pool.id + "/latest")
      .then(function (res) {
        return res.json();
      })
      .then(function (data) {
        renderSummary(data.values || []);
      });
    fetch("/api/portal/pool/" + pool.id + "/recent")
      .then(function (res) {
        return res.json();
      })
      .then(function (data) {
        renderRecent(data.rows || []);
        renderChart(data.rows || []);
      });
    fetch("/api/portal/pool/" + pool.id + "/ai")
      .then(function (res) {
        return res.json();
      })
      .then(function (data) {
        renderAi(data.findings || []);
      });
    fetch("/api/portal/pool/" + pool.id + "/alarms")
      .then(function (res) {
        return res.json();
      })
      .then(function (data) {
        renderAlarms(data.open || []);
      });
  }

  function renderAi(findings) {
    if (!aiList) {
      return;
    }
    aiList.innerHTML = "";
    if (!findings.length) {
      aiList.innerHTML = "<li class=\"muted\">No AI summaries yet.</li>";
      return;
    }
    findings.slice(0, 5).forEach(function (f) {
      var li = document.createElement("li");
      li.innerHTML =
        "<strong>" + f.summary + "</strong><br>" +
        "<span class=\"muted\">Grade " + (f.water_quality_grade || "-") +
        " · " + f.ts + "</span>";
      aiList.appendChild(li);
    });
  }

  function renderAlarms(alarms) {
    if (!alarmList) {
      return;
    }
    alarmList.innerHTML = "";
    if (!alarms.length) {
      alarmList.innerHTML = "<li class=\"muted\">No active alarms.</li>";
      return;
    }
    alarms.slice(0, 10).forEach(function (a) {
      var li = document.createElement("li");
      li.innerHTML =
        "<strong>" + a.source_label + "</strong> (" + a.bit_name + ")" +
        "<br><span class=\"muted\">Started " + a.started_ts + "</span>";
      alarmList.appendChild(li);
    });
  }

  function renderChart(rows) {
    if (!window.Plotly) {
      return;
    }
    var series = {
      pH_MeasuredValue: { name: "pH", x: [], y: [] },
      Chlorine_MeasuredValue: { name: "Chlorine", x: [], y: [] },
      ORP_MeasuredValue: { name: "ORP", x: [], y: [] },
      Temp_MeasuredValue: { name: "Temp", x: [], y: [] },
    };
    rows.slice().reverse().forEach(function (row) {
      if (!series[row.point_label]) return;
      series[row.point_label].x.push(row.ts);
      series[row.point_label].y.push(row.value);
    });
    var traces = Object.keys(series).map(function (key) {
      return {
        x: series[key].x,
        y: series[key].y,
        mode: "lines",
        name: series[key].name,
      };
    });
    var layout = {
      margin: { t: 30, r: 20, l: 50, b: 40 },
      height: 320,
      legend: { orientation: "h" },
    };
    Plotly.newPlot("chart", traces, layout, { displayModeBar: false });
  }

  fetch("/api/portal/pools")
    .then(function (res) {
      return res.json();
    })
    .then(function (data) {
      pools = data || [];
      if (!pools.length) {
        title.textContent = "No pools assigned";
        summary.innerHTML = "<p class=\"muted\">Ask support to assign your pools.</p>";
        return;
      }
      renderTabs();
      loadPool(pools[0]);
    });
})();
