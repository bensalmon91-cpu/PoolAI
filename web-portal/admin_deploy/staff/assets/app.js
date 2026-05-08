/**
 * PoolAI Staff PWA - client app.
 *
 * Thin SPA that wraps admin endpoints for on-the-go AI governance and check-ins.
 * Views: #/home, #/ai, #/checkin, #/devices
 */
(() => {
    'use strict';

    const $view = document.getElementById('view');
    const $toast = document.getElementById('toast');
    const $aiBadge = document.getElementById('aiBadge');
    const $refresh = document.getElementById('refreshBtn');

    const state = {
        aiFilter: 'pending',      // status filter for AI queue
        aiMode: 'suggestions',    // 'suggestions' | 'flagged' (responses)
    };

    // ---------- helpers ----------
    function h(tag, attrs = {}, children = []) {
        const el = document.createElement(tag);
        for (const [k, v] of Object.entries(attrs || {})) {
            if (v === null || v === undefined || v === false) continue;
            if (k === 'class') el.className = v;
            else if (k === 'dataset') Object.assign(el.dataset, v);
            else if (k === 'html') el.innerHTML = v;
            else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2), v);
            else el.setAttribute(k, v);
        }
        if (!Array.isArray(children)) children = [children];
        for (const c of children) {
            if (c === null || c === undefined || c === false) continue;
            el.append(c.nodeType ? c : document.createTextNode(String(c)));
        }
        return el;
    }

    function escapeHtml(s) {
        return String(s ?? '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function relTime(iso) {
        if (!iso) return '';
        const t = new Date(iso.replace(' ', 'T')).getTime();
        if (isNaN(t)) return iso;
        const diff = Date.now() - t;
        const m = Math.round(diff / 60000);
        if (m < 1) return 'just now';
        if (m < 60) return m + 'm ago';
        const hrs = Math.round(m / 60);
        if (hrs < 24) return hrs + 'h ago';
        return Math.round(hrs / 24) + 'd ago';
    }

    function toast(msg, kind = '') {
        $toast.className = 'toast ' + kind;
        $toast.textContent = msg;
        $toast.hidden = false;
        clearTimeout(toast._t);
        toast._t = setTimeout(() => { $toast.hidden = true; }, 2600);
    }

    async function api(url, opts = {}) {
        const res = await fetch(url, {
            credentials: 'same-origin',
            headers: { 'Accept': 'application/json', ...(opts.headers || {}) },
            ...opts,
        });
        // The admin auth layer sometimes 302s to /admin/login.php instead of
        // returning 401 JSON (host-dependent). Treat redirected or non-JSON
        // responses as a lost session and bounce to the staff login.
        const ct = res.headers.get('content-type') || '';
        if (res.status === 401 || res.redirected || !ct.includes('application/json')) {
            window.location.href = '/staff/login.php';
            throw new Error('Session expired');
        }
        let body;
        try { body = await res.json(); }
        catch (e) { throw new Error('Invalid JSON response'); }
        if (!res.ok || body.ok === false) {
            throw new Error(body.error || ('HTTP ' + res.status));
        }
        return body;
    }

    function setLoading(label = 'Loading…') {
        $view.innerHTML = '';
        $view.append(h('div', { class: 'loading' }, label));
    }

    function modal(titleText, bodyNode, actions) {
        const bd = h('div', { class: 'modal-backdrop' });
        const close = () => bd.remove();
        bd.addEventListener('click', (e) => { if (e.target === bd) close(); });
        const m = h('div', { class: 'modal' }, [
            h('h3', {}, titleText),
            bodyNode,
            h('div', { class: 'actions' }, (actions || []).map(a => h('button', {
                class: 'btn ' + (a.class || 'btn-secondary'),
                onclick: async () => {
                    try {
                        const keep = await a.onClick?.();
                        if (keep !== true) close();
                    } catch (e) { toast(e.message || 'Error', 'err'); }
                }
            }, a.label))),
        ]);
        bd.append(m);
        document.body.append(bd);
        return { close };
    }

    function confirmDialog(title, message) {
        return new Promise((resolve) => {
            modal(title, h('p', { class: 'muted' }, message), [
                { label: 'Cancel', class: 'btn-ghost', onClick: () => resolve(false) },
                { label: 'Confirm', class: 'btn-primary', onClick: () => resolve(true) },
            ]);
        });
    }

    // ---------- HOME ----------
    async function renderHome() {
        setLoading();
        const data = await api('/staff/api/dashboard.php');
        updateBadge(data.ai.review_queue);

        const fleet = data.fleet, ai = data.ai;
        $view.innerHTML = '';

        $view.append(
            h('div', { class: 'section-title' }, `Hello, ${data.staff.username}`),
            h('div', { class: 'stat-grid' }, [
                statTile(fleet.total, 'Devices'),
                statTile(fleet.online, 'Online', 'ok'),
                statTile(fleet.offline, 'Offline', fleet.offline > 0 ? 'bad' : 'ok'),
                statTile(fleet.with_issues, 'Issues', fleet.with_issues > 0 ? 'warn' : 'ok'),
            ])
        );

        $view.append(
            h('div', { class: 'section-title' }, 'AI review queue'),
            h('div', { class: 'stat-grid' }, [
                statTile(ai.suggestions.pending || 0, 'Pending', ai.suggestions.pending ? 'warn' : 'ok'),
                statTile(ai.suggestions.delivered || 0, 'Delivered'),
                statTile(ai.suggestions.read || 0, 'Read'),
                statTile(ai.flagged_responses || 0, 'Flagged', ai.flagged_responses ? 'bad' : 'ok'),
            ])
        );

        // Last check-in card
        $view.append(h('div', { class: 'section-title' }, 'Last check-in'));
        if (data.last_checkin) {
            const c = data.last_checkin;
            $view.append(h('div', { class: 'card' }, [
                h('div', { class: 'title-row' }, [
                    h('h3', {}, `${c.admin_username}`),
                    h('span', { class: 'badge ' + c.status }, c.status),
                ]),
                c.note ? h('div', { class: 'body-text' }, c.note) : null,
                h('div', { class: 'meta' }, [h('span', {}, relTime(c.created_at))]),
            ]));
        } else {
            $view.append(h('div', { class: 'card muted' }, 'No check-ins yet. Use the Check-in tab to record one.'));
        }

        // Quick actions
        $view.append(
            h('div', { class: 'section-title' }, 'Quick actions'),
            h('div', { class: 'card' }, [
                h('div', { class: 'actions' }, [
                    h('a', { class: 'btn btn-success btn-sm', href: '#/checkin' }, 'Record check-in'),
                    h('a', { class: 'btn btn-primary btn-sm', href: '#/ai' }, 'Review AI queue'),
                    h('a', { class: 'btn btn-secondary btn-sm', href: '#/devices' }, 'Devices'),
                ]),
            ])
        );

        // Recent suggestions preview
        if ((data.recent_suggestions || []).length) {
            $view.append(h('div', { class: 'section-title' }, 'Recent AI suggestions'));
            data.recent_suggestions.forEach(s => $view.append(suggestionCard(s, false)));
        }
    }

    function statTile(value, label, cls = '') {
        return h('div', { class: 'stat ' + cls }, [
            h('div', { class: 'value' }, String(value ?? 0)),
            h('div', { class: 'label' }, label),
        ]);
    }

    // ---------- AI GOVERNANCE ----------
    async function renderAi() {
        setLoading();
        // Load counts so chips show numbers.
        const dash = await api('/staff/api/dashboard.php').catch(() => null);
        const counts = dash?.ai?.suggestions || {};
        const flaggedCount = dash?.ai?.flagged_responses || 0;
        if (dash) updateBadge(dash.ai.review_queue);

        $view.innerHTML = '';
        $view.append(
            h('div', { class: 'filter-chips' }, [
                modeChip('suggestions', 'Suggestions',
                    (counts.pending || 0) + (counts.delivered || 0) + (counts.read || 0)),
                modeChip('flagged', 'Flagged answers', flaggedCount),
            ]),
        );

        if (state.aiMode === 'suggestions') {
            $view.append(
                h('div', { class: 'filter-chips' }, [
                    statusChip('pending', 'Pending', counts.pending || 0),
                    statusChip('delivered', 'Delivered', counts.delivered || 0),
                    statusChip('read', 'Read', counts.read || 0),
                    statusChip('acted_upon', 'Acted', counts.acted_upon || 0),
                    statusChip('dismissed', 'Dismissed', counts.dismissed || 0),
                    statusChip('retracted', 'Retracted', counts.retracted || 0),
                ]),
            );
            await renderSuggestionList();
        } else {
            await renderFlaggedList();
        }
    }

    function modeChip(mode, label, count) {
        return h('button', {
            class: 'chip ' + (state.aiMode === mode ? 'active' : ''),
            onclick: () => { state.aiMode = mode; renderAi(); },
        }, [label, h('span', { class: 'count' }, String(count))]);
    }

    function statusChip(status, label, count) {
        return h('button', {
            class: 'chip ' + (state.aiFilter === status ? 'active' : ''),
            onclick: () => { state.aiFilter = status; renderSuggestionList(); refreshChipsActive(); },
        }, [label, h('span', { class: 'count' }, String(count))]);
    }

    function refreshChipsActive() {
        // Re-render just the suggestion chips active state.
        document.querySelectorAll('.filter-chips .chip').forEach(c => c.classList.remove('active'));
        // Simpler: re-render the whole AI view.
        renderAi();
    }

    async function renderSuggestionList() {
        // Clear existing list (keep chips).
        const existing = $view.querySelectorAll('.sugg-list');
        existing.forEach(n => n.remove());
        const list = h('div', { class: 'sugg-list' }, [h('div', { class: 'loading' }, 'Loading…')]);
        $view.append(list);

        try {
            const data = await api('/api/ai/suggestions.php?status=' + encodeURIComponent(state.aiFilter) + '&limit=50');
            list.innerHTML = '';
            const rows = data.suggestions || [];
            if (!rows.length) {
                list.append(h('div', { class: 'empty' }, [
                    h('h3', {}, 'Nothing here'),
                    h('p', {}, `No ${state.aiFilter.replace('_', ' ')} suggestions.`),
                ]));
                return;
            }
            rows.forEach(s => list.append(suggestionCard(s, true)));
        } catch (e) {
            list.innerHTML = '';
            list.append(h('div', { class: 'empty' }, [
                h('h3', {}, 'Could not load'),
                h('p', {}, e.message),
            ]));
        }
    }

    function suggestionCard(s, withActions) {
        const priorityDots = Array.from({ length: 5 }, (_, i) =>
            h('span', { class: 'status-dot', style: `background: ${i < s.priority ? 'var(--warning)' : 'var(--surface-2)'}; box-shadow: none; width: 8px; height: 8px; margin-right: 2px;` }));
        const card = h('div', { class: 'card ai-output-card' }, [
            h('div', { class: 'ai-advisory-banner', title: 'Verify dosing and safety before acting.' },
                'Advisory only - staff must verify before any action'),
            h('div', { class: 'title-row' }, [
                h('h3', {}, s.title),
                h('span', { class: 'badge ' + s.status }, (s.status || '').replace('_', ' ')),
            ]),
            h('div', { class: 'meta' }, [
                h('span', {}, [h('strong', {}, s.device_alias || s.device_name || ('Device ' + s.device_id))]),
                s.suggestion_type ? h('span', {}, s.suggestion_type) : null,
                h('span', {}, ['P: ', ...priorityDots]),
                s.confidence ? h('span', {}, `${Math.round(s.confidence * 100)}%`) : null,
                h('span', {}, relTime(s.created_at)),
            ]),
            h('div', { class: 'body-text' }, s.body || ''),
        ]);
        if (withActions && s.status !== 'retracted') {
            card.append(h('div', { class: 'actions' }, [
                h('button', { class: 'btn btn-ghost btn-sm', onclick: () => editNotes(s, card) }, 'Notes'),
                h('button', { class: 'btn btn-warning btn-sm', onclick: () => dismissSuggestion(s) }, 'Dismiss'),
                h('button', { class: 'btn btn-danger btn-sm', onclick: () => retractSuggestion(s) }, 'Retract'),
            ]));
        }
        if (s.status === 'retracted' && s.retracted_reason) {
            card.append(h('div', { class: 'meta', style: 'color: var(--danger);' }, `Retracted: ${s.retracted_reason}`));
        }
        if (s.admin_notes) {
            card.append(h('div', { class: 'meta' }, `Notes: ${s.admin_notes}`));
        }
        return card;
    }

    async function retractSuggestion(s) {
        const ta = h('textarea', { placeholder: 'Reason (optional)…', rows: 3 });
        const field = h('label', { class: 'field' }, [h('span', {}, 'Reason'), ta]);
        modal('Retract suggestion', field, [
            { label: 'Cancel', class: 'btn-ghost' },
            { label: 'Retract', class: 'btn-danger', onClick: async () => {
                await api('/api/ai/suggestions.php?id=' + s.id, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ retract: true, retracted_reason: ta.value || '' }),
                });
                toast('Retracted', 'ok');
                renderAi();
            } },
        ]);
    }

    async function dismissSuggestion(s) {
        const ok = await confirmDialog('Mark as dismissed?', 'This signals the suggestion was reviewed but not actioned.');
        if (!ok) return;
        await api('/api/ai/suggestions.php?id=' + s.id, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status: 'dismissed' }),
        });
        toast('Dismissed', 'ok');
        renderAi();
    }

    function editNotes(s, card) {
        const ta = h('textarea', { rows: 4 }, []);
        ta.value = s.admin_notes || '';
        const field = h('label', { class: 'field' }, [h('span', {}, 'Admin notes'), ta]);
        modal('Edit notes', field, [
            { label: 'Cancel', class: 'btn-ghost' },
            { label: 'Save', class: 'btn-primary', onClick: async () => {
                await api('/api/ai/suggestions.php?id=' + s.id, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ admin_notes: ta.value }),
                });
                toast('Saved', 'ok');
                renderAi();
            } },
        ]);
    }

    async function renderFlaggedList() {
        const existing = $view.querySelectorAll('.resp-list');
        existing.forEach(n => n.remove());
        const list = h('div', { class: 'resp-list' }, [h('div', { class: 'loading' }, 'Loading…')]);
        $view.append(list);
        try {
            const data = await api('/api/ai/responses.php?flagged=1&limit=50');
            list.innerHTML = '';
            const rows = data.responses || [];
            if (!rows.length) {
                list.append(h('div', { class: 'empty' }, [
                    h('h3', {}, 'Nothing flagged'),
                    h('p', {}, 'Flagged answers will appear here.'),
                ]));
                return;
            }
            rows.forEach(r => list.append(responseCard(r)));
        } catch (e) {
            list.innerHTML = '';
            list.append(h('div', { class: 'empty' }, [h('h3', {}, 'Could not load'), h('p', {}, e.message)]));
        }
    }

    function responseCard(r) {
        const card = h('div', { class: 'card' }, [
            h('div', { class: 'title-row' }, [
                h('h3', {}, r.question_text || 'Question'),
                h('span', { class: 'badge flagged' }, 'flagged'),
            ]),
            h('div', { class: 'meta' }, [
                h('span', {}, [h('strong', {}, r.device_alias || r.device_name || ('Device ' + r.device_id))]),
                r.question_category ? h('span', {}, r.question_category) : null,
                r.pool ? h('span', {}, 'Pool: ' + r.pool) : null,
                h('span', {}, relTime(r.answered_at)),
            ]),
            h('div', { class: 'body-text' }, r.answer || ''),
            r.admin_notes ? h('div', { class: 'meta' }, 'Notes: ' + r.admin_notes) : null,
            h('div', { class: 'actions' }, [
                h('button', { class: 'btn btn-ghost btn-sm', onclick: () => editResponseNotes(r) }, 'Notes'),
                h('button', { class: 'btn btn-success btn-sm', onclick: () => unflagResponse(r) }, 'Unflag'),
            ]),
        ]);
        return card;
    }

    async function unflagResponse(r) {
        await api('/api/ai/responses.php?id=' + r.id, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ flagged: false }),
        });
        toast('Unflagged', 'ok');
        renderAi();
    }

    function editResponseNotes(r) {
        const ta = h('textarea', { rows: 4 }, []);
        ta.value = r.admin_notes || '';
        const field = h('label', { class: 'field' }, [h('span', {}, 'Admin notes'), ta]);
        modal('Edit notes', field, [
            { label: 'Cancel', class: 'btn-ghost' },
            { label: 'Save', class: 'btn-primary', onClick: async () => {
                await api('/api/ai/responses.php?id=' + r.id, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ admin_notes: ta.value }),
                });
                toast('Saved', 'ok');
                renderAi();
            } },
        ]);
    }

    // ---------- CHECK-IN ----------
    async function renderCheckin() {
        setLoading();

        // Load fleet summary and recent check-ins in parallel.
        const [dash, list] = await Promise.all([
            api('/staff/api/dashboard.php'),
            api('/staff/api/checkin.php?limit=20'),
        ]);
        updateBadge(dash.ai.review_queue);

        let selected = dash.fleet.offline > 0 || dash.fleet.with_issues > 0 ? 'attention' : 'ok';
        const noteInput = h('textarea', { rows: 3, placeholder: 'Notes (optional) — what did you verify? any anomalies?' });

        $view.innerHTML = '';
        $view.append(h('div', { class: 'section-title' }, 'Status snapshot'));
        $view.append(h('div', { class: 'stat-grid' }, [
            statTile(dash.fleet.online, 'Online', 'ok'),
            statTile(dash.fleet.offline, 'Offline', dash.fleet.offline ? 'bad' : 'ok'),
            statTile(dash.fleet.with_issues, 'Issues', dash.fleet.with_issues ? 'warn' : 'ok'),
            statTile(dash.ai.review_queue, 'AI queue', dash.ai.review_queue ? 'warn' : 'ok'),
        ]));

        $view.append(h('div', { class: 'section-title' }, 'How are things?'));
        const choicesEl = h('div', { class: 'checkin-choices' });
        const choices = [
            { v: 'ok',        ic: '\u2713', label: 'All clear',  sub: 'no action needed' },
            { v: 'attention', ic: '!',       label: 'Attention',  sub: 'worth watching' },
            { v: 'issue',     ic: '\u26A0',  label: 'Issue',      sub: 'needs follow-up' },
        ];
        function renderChoices() {
            choicesEl.innerHTML = '';
            choices.forEach(c => {
                const btn = h('button', {
                    class: 'checkin-choice ' + c.v + (selected === c.v ? ' selected ' + c.v : ''),
                    onclick: () => { selected = c.v; renderChoices(); },
                }, [
                    h('span', { class: 'ic' }, c.ic),
                    h('span', {}, c.label),
                    h('span', { class: 'sub' }, c.sub),
                ]);
                choicesEl.append(btn);
            });
        }
        renderChoices();

        const submitBtn = h('button', {
            class: 'btn btn-primary btn-block',
            onclick: async () => {
                submitBtn.disabled = true;
                submitBtn.textContent = 'Recording…';
                try {
                    await api('/staff/api/checkin.php', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ status: selected, note: noteInput.value }),
                    });
                    toast('Check-in recorded', 'ok');
                    renderCheckin();
                } catch (e) {
                    toast(e.message, 'err');
                    submitBtn.disabled = false;
                    submitBtn.textContent = 'Record check-in';
                }
            },
        }, 'Record check-in');

        $view.append(
            choicesEl,
            h('label', { class: 'field' }, [h('span', {}, 'Notes'), noteInput]),
            submitBtn,
        );

        $view.append(h('div', { class: 'section-title' }, 'Recent check-ins'));
        const rows = list.checkins || [];
        if (!rows.length) {
            $view.append(h('div', { class: 'card muted' }, 'No check-ins yet.'));
        } else {
            rows.forEach(c => $view.append(checkinCard(c)));
        }
    }

    function checkinCard(c) {
        return h('div', { class: 'card' }, [
            h('div', { class: 'title-row' }, [
                h('h3', {}, c.admin_username),
                h('span', { class: 'badge ' + c.status }, c.status),
            ]),
            c.note ? h('div', { class: 'body-text' }, c.note) : null,
            h('div', { class: 'meta' }, [
                h('span', {}, relTime(c.created_at)),
                c.devices_online !== null ? h('span', {}, `online ${c.devices_online}`) : null,
                c.devices_offline !== null ? h('span', {}, `offline ${c.devices_offline}`) : null,
                c.devices_with_issues !== null ? h('span', {}, `issues ${c.devices_with_issues}`) : null,
                c.pending_suggestions !== null ? h('span', {}, `ai queue ${c.pending_suggestions}`) : null,
            ]),
        ]);
    }

    // ---------- DEVICES ----------
    async function renderDevices() {
        setLoading();
        const data = await api('/staff/api/dashboard.php');
        updateBadge(data.ai.review_queue);

        $view.innerHTML = '';
        $view.append(h('div', { class: 'section-title' }, `${data.devices.length} device${data.devices.length === 1 ? '' : 's'}`));

        if (!data.devices.length) {
            $view.append(h('div', { class: 'empty' }, [h('h3', {}, 'No devices registered')]));
            return;
        }

        data.devices.forEach(d => {
            const dotClass = d.is_online
                ? (d.has_issues || d.alarms_critical ? 'warn' : 'online')
                : 'offline';
            const status = d.is_online
                ? (d.has_issues || d.alarms_critical ? 'issue' : 'ok')
                : 'issue';
            const summary = [];
            if (d.alarms_critical) summary.push(`${d.alarms_critical} critical`);
            else if (d.alarms_total) summary.push(`${d.alarms_total} alarms`);
            if (d.controllers_offline) summary.push(`${d.controllers_offline} ctrl off`);
            if (!d.is_online) summary.push(d.minutes_ago != null ? `${d.minutes_ago}m since seen` : 'never seen');

            $view.append(h('div', { class: 'card' }, [
                h('div', { class: 'title-row' }, [
                    h('h3', {}, [h('span', { class: 'status-dot ' + dotClass }), d.name]),
                    h('span', { class: 'badge ' + status }, d.is_online ? 'online' : 'offline'),
                ]),
                h('div', { class: 'meta' }, [
                    h('span', {}, d.uuid_short || ''),
                    d.software_version ? h('span', {}, 'v' + d.software_version) : null,
                    ...summary.map(s => h('span', {}, s)),
                ]),
            ]));
        });
    }

    // ---------- router ----------
    const routes = {
        '#/home':    { tab: 'home',    render: renderHome },
        '#/ai':      { tab: 'ai',      render: renderAi },
        '#/checkin': { tab: 'checkin', render: renderCheckin },
        '#/devices': { tab: 'devices', render: renderDevices },
    };

    async function router() {
        const hash = routes[window.location.hash] ? window.location.hash : '#/home';
        if (window.location.hash !== hash) window.location.hash = hash;
        document.querySelectorAll('.tab').forEach(t => {
            t.classList.toggle('active', '#/' + t.dataset.tab === hash);
        });
        try {
            await routes[hash].render();
        } catch (e) {
            $view.innerHTML = '';
            $view.append(h('div', { class: 'empty' }, [
                h('h3', {}, 'Something went wrong'),
                h('p', {}, e.message),
                h('button', { class: 'btn btn-primary btn-sm', onclick: router }, 'Retry'),
            ]));
        }
    }

    function updateBadge(n) {
        if (!$aiBadge) return;
        if (n > 0) { $aiBadge.hidden = false; $aiBadge.textContent = n > 99 ? '99+' : String(n); }
        else { $aiBadge.hidden = true; }
    }

    window.addEventListener('hashchange', router);
    $refresh.addEventListener('click', router);

    // Auto-refresh when tab becomes visible after >30s away.
    let hiddenAt = null;
    document.addEventListener('visibilitychange', () => {
        if (document.hidden) { hiddenAt = Date.now(); return; }
        if (hiddenAt && Date.now() - hiddenAt > 30000) router();
        hiddenAt = null;
    });

    // Initial load
    if (!window.location.hash) window.location.hash = '#/home';
    router();
})();
