(function () {
  function byId(id) {
    return document.getElementById(id);
  }

  function setStatus(id, message, isError) {
    var node = byId(id);
    if (!node) {
      return;
    }
    node.textContent = message;
    node.style.color = isError ? "#b42318" : "#2e7d32";
  }

  var cache = {
    accounts: [],
    pools: [],
    devices: [],
  };

  function fetchJson(url) {
    return fetch(url).then(function (res) {
      if (!res.ok) {
        throw new Error("Request failed");
      }
      return res.json();
    });
  }

  function populateSelect(select, items, labelKey, valueKey, includeBlank) {
    select.innerHTML = "";
    if (includeBlank) {
      var blank = document.createElement("option");
      blank.value = "";
      blank.textContent = "Unassigned";
      select.appendChild(blank);
    }
    items.forEach(function (item) {
      var opt = document.createElement("option");
      opt.value = item[valueKey];
      opt.textContent = item[labelKey];
      select.appendChild(opt);
    });
  }

  function renderAccounts() {
    var tbody = byId("accounts-table").querySelector("tbody");
    tbody.innerHTML = "";
    cache.accounts.forEach(function (a) {
      var tr = document.createElement("tr");
      tr.innerHTML =
        "<td>" + a.name + "</td>" +
        "<td>" + (a.contact_name || "-") + "</td>" +
        "<td>" + (a.contact_email || "-") + "</td>" +
        "<td>" + (a.contact_phone || "-") + "</td>" +
        "<td>" + (a.address || "-") + "</td>";
      tbody.appendChild(tr);
    });
  }

  function populateAccountEdit(account) {
    byId("account-edit-name").value = account.name || "";
    byId("account-edit-contact").value = account.contact_name || "";
    byId("account-edit-email").value = account.contact_email || "";
    byId("account-edit-phone").value = account.contact_phone || "";
    byId("account-edit-address").value = account.address || "";
  }

  function renderPools() {
    var tbody = byId("pools-table").querySelector("tbody");
    tbody.innerHTML = "";
    cache.pools.forEach(function (p) {
      var tr = document.createElement("tr");
      tr.innerHTML =
        "<td>" + p.name + "</td>" +
        "<td>" + p.account_name + "</td>" +
        "<td>" + (p.location || "-") + "</td>" +
        "<td>" + (p.notes || "-") + "</td>";
      tbody.appendChild(tr);
    });
  }

  function renderUsers(users) {
    var tbody = byId("users-table").querySelector("tbody");
    tbody.innerHTML = "";
    users.forEach(function (u) {
      var tr = document.createElement("tr");
      tr.innerHTML =
        "<td>" + u.email + "</td>" +
        "<td>" + (u.account_name || "-") + "</td>" +
        "<td>" + (u.is_admin ? "Yes" : "No") + "</td>" +
        "<td>" + new Date(u.created_at).toLocaleString() + "</td>";
      tbody.appendChild(tr);
    });
  }

  function renderDevices() {
    var tbody = byId("devices-table").querySelector("tbody");
    tbody.innerHTML = "";
    cache.devices.forEach(function (d) {
      var tr = document.createElement("tr");
      tr.innerHTML =
        "<td class=\"mono\">" + d.device_id + "</td>" +
        "<td>" + (d.model || "-") + "</td>" +
        "<td>" + (d.hostname || "-") + "</td>" +
        "<td>" + (d.account_name || "-") + "</td>" +
        "<td>" + (d.pool_name || "-") + "</td>" +
        "<td>" + (d.last_seen_at ? new Date(d.last_seen_at).toLocaleString() : "-") + "</td>";
      tbody.appendChild(tr);
    });
  }

  function renderClientOverview() {
    var select = byId("client-filter");
    var poolList = byId("client-pools");
    var deviceList = byId("client-devices");
    if (!select || !poolList || !deviceList) {
      return;
    }
    populateSelect(select, cache.accounts, "name", "id");
    function updateLists() {
      var accountId = Number(select.value);
      poolList.innerHTML = "";
      deviceList.innerHTML = "";
      cache.pools.filter(function (p) {
        return p.account_id === accountId;
      }).forEach(function (p) {
        var li = document.createElement("li");
        li.textContent = p.name + (p.location ? " (" + p.location + ")" : "");
        poolList.appendChild(li);
      });
      cache.devices.filter(function (d) {
        return d.account_id === accountId;
      }).forEach(function (d) {
        var li = document.createElement("li");
        li.textContent = d.device_id + (d.pool_name ? " → " + d.pool_name : "");
        deviceList.appendChild(li);
      });
      if (!poolList.children.length) {
        poolList.innerHTML = "<li class=\"muted\">No pools assigned.</li>";
      }
      if (!deviceList.children.length) {
        deviceList.innerHTML = "<li class=\"muted\">No devices assigned.</li>";
      }
    }
    select.addEventListener("change", updateLists);
    if (cache.accounts.length) {
      select.value = cache.accounts[0].id;
    }
    updateLists();
  }

  function refreshData() {
    Promise.all([
      fetchJson("/api/admin/accounts"),
      fetchJson("/api/admin/pools"),
      fetchJson("/api/admin/devices"),
      fetchJson("/api/admin/users"),
    ])
      .then(function (data) {
        cache.accounts = data[0] || [];
        cache.pools = data[1] || [];
        cache.devices = data[2] || [];
        renderAccounts();
        renderPools();
        renderDevices();
        renderUsers(data[3] || []);

        populateSelect(byId("pool-account"), cache.accounts, "name", "id");
        populateSelect(byId("user-account"), cache.accounts, "name", "id", true);
        populateSelect(byId("device-account"), cache.accounts, "name", "id", true);

        var editSelect = byId("account-edit-select");
        if (editSelect) {
          populateSelect(editSelect, cache.accounts, "name", "id");
          if (cache.accounts.length) {
            editSelect.value = cache.accounts[0].id;
            populateAccountEdit(cache.accounts[0]);
          }
          editSelect.addEventListener("change", function () {
            var selected = cache.accounts.find(function (a) {
              return a.id === Number(editSelect.value);
            });
            if (selected) {
              populateAccountEdit(selected);
            }
          });
        }

        var poolSelect = byId("device-pool");
        populateSelect(poolSelect, cache.pools, "name", "id", true);

        var deviceSelect = byId("device-select");
        populateSelect(
          deviceSelect,
          cache.devices,
          "device_id",
          "device_id"
        );
        renderClientOverview();
      })
      .catch(function () {
        setStatus("account-status", "Failed to load admin data.", true);
      });
  }

  var accountForm = byId("account-form");
  if (accountForm) {
    accountForm.addEventListener("submit", function (event) {
      event.preventDefault();
      var payload = {
        name: byId("account-name").value.trim(),
        contact_name: byId("account-contact").value.trim(),
        contact_email: byId("account-email").value.trim(),
        contact_phone: byId("account-phone").value.trim(),
        address: byId("account-address").value.trim(),
      };
      if (!payload.name) {
        return;
      }
      fetch("/api/admin/accounts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      })
        .then(function (res) {
          if (!res.ok) {
            throw new Error("Failed");
          }
          return res.json();
        })
        .then(function () {
          setStatus("account-status", "Client created.", false);
          accountForm.reset();
          refreshData();
        })
        .catch(function () {
          setStatus("account-status", "Failed to create client.", true);
        });
    });
  }

  var accountEditForm = byId("account-edit-form");
  if (accountEditForm) {
    accountEditForm.addEventListener("submit", function (event) {
      event.preventDefault();
      var accountId = byId("account-edit-select").value;
      var payload = {
        name: byId("account-edit-name").value.trim(),
        contact_name: byId("account-edit-contact").value.trim(),
        contact_email: byId("account-edit-email").value.trim(),
        contact_phone: byId("account-edit-phone").value.trim(),
        address: byId("account-edit-address").value.trim(),
      };
      if (!accountId || !payload.name) {
        return;
      }
      fetch("/api/admin/accounts/" + accountId, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      })
        .then(function (res) {
          if (!res.ok) {
            throw new Error("Failed");
          }
          return res.json();
        })
        .then(function () {
          setStatus("account-edit-status", "Client updated.", false);
          refreshData();
        })
        .catch(function () {
          setStatus("account-edit-status", "Failed to update client.", true);
        });
    });
  }

  var poolForm = byId("pool-form");
  if (poolForm) {
    poolForm.addEventListener("submit", function (event) {
      event.preventDefault();
      var payload = {
        account_id: byId("pool-account").value,
        name: byId("pool-name").value.trim(),
        location: byId("pool-location").value.trim(),
        notes: byId("pool-notes").value.trim(),
      };
      if (!payload.account_id || !payload.name) {
        return;
      }
      fetch("/api/admin/pools", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      })
        .then(function (res) {
          if (!res.ok) {
            throw new Error("Failed");
          }
          return res.json();
        })
        .then(function () {
          setStatus("pool-status", "Pool created.", false);
          poolForm.reset();
          refreshData();
        })
        .catch(function () {
          setStatus("pool-status", "Failed to create pool.", true);
        });
    });
  }

  var userForm = byId("user-form");
  if (userForm) {
    userForm.addEventListener("submit", function (event) {
      event.preventDefault();
      var payload = {
        email: byId("user-email").value.trim(),
        password: byId("user-password").value.trim(),
        accountId: byId("user-account").value,
        isAdmin: byId("user-admin").value,
      };
      if (!payload.email || !payload.password) {
        return;
      }
      fetch("/api/admin/users", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      })
        .then(function (res) {
          if (!res.ok) {
            throw new Error("Failed");
          }
          return res.json();
        })
        .then(function () {
          setStatus("user-status", "User created.", false);
          userForm.reset();
          refreshData();
        })
        .catch(function () {
          setStatus("user-status", "Failed to create user.", true);
        });
    });
  }

  var deviceForm = byId("device-form");
  if (deviceForm) {
    deviceForm.addEventListener("submit", function (event) {
      event.preventDefault();
      var deviceId = byId("device-select").value;
      var payload = {
        account_id: byId("device-account").value || null,
        pool_id: byId("device-pool").value || null,
      };
      if (!deviceId) {
        return;
      }
      fetch("/api/admin/devices/" + deviceId, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      })
        .then(function (res) {
          if (!res.ok) {
            throw new Error("Failed");
          }
          return res.json();
        })
        .then(function () {
          setStatus("device-status", "Device updated.", false);
          refreshData();
        })
        .catch(function () {
          setStatus("device-status", "Failed to update device.", true);
        });
    });
  }

  refreshData();

  // Device Health Monitor
  function formatUptime(seconds) {
    if (!seconds) return "-";
    var days = Math.floor(seconds / 86400);
    var hours = Math.floor((seconds % 86400) / 3600);
    var mins = Math.floor((seconds % 3600) / 60);
    if (days > 0) return days + "d " + hours + "h";
    if (hours > 0) return hours + "h " + mins + "m";
    return mins + "m";
  }

  function formatTimeAgo(dateStr) {
    if (!dateStr) return "Never";
    var date = new Date(dateStr);
    var now = new Date();
    var mins = Math.round((now - date) / 60000);
    if (mins < 1) return "Just now";
    if (mins < 60) return mins + "m ago";
    var hours = Math.round(mins / 60);
    if (hours < 24) return hours + "h ago";
    var days = Math.round(hours / 24);
    return days + "d ago";
  }

  function renderHealthTable(devices) {
    var tbody = byId("health-table").querySelector("tbody");
    var banner = byId("issues-banner");
    tbody.innerHTML = "";

    if (!devices.length) {
      var tr = document.createElement("tr");
      tr.innerHTML = '<td colspan="8" class="muted">No device health data yet. Devices will appear after their first heartbeat.</td>';
      tbody.appendChild(tr);
      if (banner) banner.style.display = "none";
      return;
    }

    // Collect all issues across devices for the banner
    var allIssues = [];
    devices.forEach(function (d) {
      if (d.has_issues && d.issues && d.issues.length) {
        d.issues.forEach(function (issue) {
          allIssues.push({ device: d.device_name || d.device_id, issue: issue });
        });
      }
    });

    // Show issues banner if there are any
    if (banner) {
      if (allIssues.length > 0) {
        var html = '<strong>Issues Detected:</strong><ul>';
        allIssues.forEach(function (item) {
          html += '<li><strong>' + item.device + ':</strong> ' + item.issue + '</li>';
        });
        html += '</ul>';
        banner.innerHTML = html;
        banner.style.display = "block";
        banner.className = "issues-banner issues-warning";
      } else {
        banner.innerHTML = '<strong>All Systems OK</strong> - No issues detected';
        banner.style.display = "block";
        banner.className = "issues-banner issues-ok";
      }
    }

    devices.forEach(function (d) {
      var tr = document.createElement("tr");
      var statusClass = d.is_online ? "status-online" : "status-offline";
      var statusText = d.is_online ? "Online" : "Offline";
      var diskClass = d.disk_used_pct > 80 ? "text-warning" : "";
      var memClass = d.memory_used_pct > 85 ? "text-warning" : "";
      var failedClass = d.failed_uploads > 0 ? "text-error" : "";

      // Controllers summary
      var controllersOnline = d.controllers_online || 0;
      var controllersOffline = d.controllers_offline || 0;
      var controllersHtml = '';
      if (controllersOnline > 0 || controllersOffline > 0) {
        controllersHtml = '<span class="status-ok">' + controllersOnline + ' online</span>';
        if (controllersOffline > 0) {
          controllersHtml += '<br><span class="status-error">' + controllersOffline + ' offline</span>';
        }
      } else {
        controllersHtml = '-';
      }

      // Alarms summary
      var alarmsTotal = d.alarms_total || 0;
      var alarmsCritical = d.alarms_critical || 0;
      var alarmsWarning = d.alarms_warning || 0;
      var alarmsHtml = '';
      if (alarmsTotal > 0) {
        if (alarmsCritical > 0) {
          alarmsHtml = '<span class="status-error">' + alarmsCritical + ' critical</span>';
        }
        if (alarmsWarning > 0) {
          alarmsHtml += (alarmsHtml ? '<br>' : '') + '<span class="status-warning">' + alarmsWarning + ' warning</span>';
        }
        if (!alarmsHtml) {
          alarmsHtml = alarmsTotal + ' active';
        }
      } else {
        alarmsHtml = '<span class="status-ok">None</span>';
      }

      // System info (disk, memory, temp combined)
      var systemHtml = '<span class="' + diskClass + '">Disk: ' + (d.disk_used_pct ? d.disk_used_pct.toFixed(0) + '%' : '-') + '</span>' +
        '<br><span class="' + memClass + '">Mem: ' + (d.memory_used_pct ? d.memory_used_pct.toFixed(0) + '%' : '-') + '</span>' +
        '<br>Up: ' + formatUptime(d.uptime_seconds);

      // Uploads info
      var uploadsHtml = 'Pending: ' + (d.pending_chunks || 0) +
        '<br><span class="' + failedClass + '">Failed: ' + (d.failed_uploads || 0) + '</span>' +
        '<br>Last: ' + formatTimeAgo(d.last_upload_success);

      tr.innerHTML =
        '<td><span class="status-badge ' + statusClass + '">' + statusText + '</span>' +
          (d.has_issues ? '<br><span class="status-badge status-warning">Issues</span>' : '') + '</td>' +
        '<td class="mono">' + (d.device_name || d.device_id) + '</td>' +
        '<td>' + controllersHtml + '</td>' +
        '<td>' + alarmsHtml + '</td>' +
        '<td>' + formatTimeAgo(d.health_ts) + '</td>' +
        '<td>' + systemHtml + '</td>' +
        '<td>' + uploadsHtml + '</td>' +
        '<td><button type="button" class="btn-small" data-device="' + d.device_id + '">Request Upload</button></td>';
      tbody.appendChild(tr);
    });

    // Add click handlers for upload buttons
    tbody.querySelectorAll("button[data-device]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var deviceId = btn.getAttribute("data-device");
        requestUpload(deviceId, btn);
      });
    });
  }

  function requestUpload(deviceId, btn) {
    btn.disabled = true;
    btn.textContent = "Requesting...";

    fetch("/api/admin_request_upload.php?device_id=" + deviceId, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
    })
      .then(function (res) {
        return res.json();
      })
      .then(function (data) {
        if (data.ok) {
          btn.textContent = "Requested!";
          setStatus("health-status", "Upload requested for device. It will upload on next heartbeat.", false);
        } else {
          btn.textContent = "Request Upload";
          btn.disabled = false;
          setStatus("health-status", data.error || "Failed to request upload.", true);
        }
      })
      .catch(function () {
        btn.textContent = "Request Upload";
        btn.disabled = false;
        setStatus("health-status", "Failed to request upload.", true);
      });
  }

  function refreshHealth() {
    fetchJson("/api/admin_health.php")
      .then(function (devices) {
        renderHealthTable(devices);
      })
      .catch(function () {
        setStatus("health-status", "Failed to load device health data.", true);
      });
  }

  var refreshBtn = byId("refresh-health");
  if (refreshBtn) {
    refreshBtn.addEventListener("click", refreshHealth);
  }

  // Initial health load and auto-refresh every 60 seconds
  refreshHealth();
  setInterval(refreshHealth, 60000);
})();
