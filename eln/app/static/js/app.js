/* ELN – Oberflächenlogik (ohne Inline-Skripte, CSP-konform). */
(function () {
  'use strict';
  const $ = (sel, root) => (root || document).querySelector(sel);
  const $$ = (sel, root) => Array.from((root || document).querySelectorAll(sel));
  const csrf = () => ($('meta[name="csrf-token"]') || {}).content || '';
  const json = (el) => { try { return JSON.parse(el.textContent || 'null'); } catch (e) { return null; } };
  const deNum = (v, d) => (v === null || v === undefined || v === '' || isNaN(v)) ? '' :
    Number(v).toLocaleString('de-DE', d === undefined ? { maximumFractionDigits: 6 } : { minimumFractionDigits: d, maximumFractionDigits: d });
  const parseNum = (s) => {
    if (s === null || s === undefined) return null;
    s = String(s).trim().replace(/\s/g, '');
    if (!s) return null;
    if (s.includes(',') && s.includes('.')) s = s.lastIndexOf(',') > s.lastIndexOf('.') ? s.replace(/\./g, '').replace(',', '.') : s.replace(/,/g, '');
    else s = s.replace(',', '.');
    const n = Number(s);
    return isNaN(n) ? NaN : n;
  };

  /* --- Toasts ------------------------------------------------------------ */
  function toast(message, kind) {
    const box = $('#toasts');
    if (!box) return;
    const el = document.createElement('div');
    el.className = 'toast toast-' + (kind || 'info');
    el.textContent = message;
    box.appendChild(el);
    setTimeout(() => el.remove(), kind === 'error' || kind === 'warning' ? 12000 : 6000);
  }
  $$('.toast').forEach((t) => {
    const err = t.classList.contains('toast-error') || t.classList.contains('toast-warning');
    setTimeout(() => t.remove(), err ? 14000 : 6000);
  });
  document.addEventListener('click', (e) => { if (e.target.classList.contains('toast')) e.target.remove(); });

  /* --- Theme --------------------------------------------------------------- */
  $$('[data-theme-toggle]').forEach((b) => b.addEventListener('click', () => {
    const next = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    try { localStorage.setItem('eln-theme', next); } catch (e) { /* ignorieren */ }
    $$('canvas').forEach((c) => { const ch = window.Chart && Chart.getChart(c); if (ch) { applyChartTheme(); ch.update(); } });
  }));

  /* --- Navigation, Dropdowns, Tabs --------------------------------------- */
  $$('[data-toggle-sidebar]').forEach((b) => b.addEventListener('click', () => $('#sidebar').classList.toggle('open')));
  document.addEventListener('click', (e) => {
    const trigger = e.target.closest('[data-dropdown]');
    $$('.dropdown.open').forEach((d) => { if (!trigger || d !== trigger.parentElement) d.classList.remove('open'); });
    if (trigger) { trigger.parentElement.classList.toggle('open'); e.preventDefault(); }
  });
  $$('[data-tabs]').forEach((tabs) => {
    const activate = (name) => {
      $$('.tab', tabs).forEach((t) => t.classList.toggle('active', t.dataset.tab === name));
      $$('.tab-panel', tabs).forEach((p) => p.classList.toggle('active', p.dataset.panel === name));
    };
    $$('.tab', tabs).forEach((t) => t.addEventListener('click', () => { activate(t.dataset.tab); history.replaceState(null, '', '#' + t.dataset.tab); }));
    const h = location.hash.replace('#', '');
    if (h && $(`[data-tab="${h}"]`, tabs)) activate(h);
  });
  $$('[data-autosubmit]').forEach((el) => el.addEventListener('change', () => el.form.submit()));

  /* --- Dialoge und Bestätigungen ----------------------------------------- */
  document.addEventListener('click', (e) => {
    const opener = e.target.closest('[data-open-dialog]');
    if (opener) {
      const dlg = document.getElementById(opener.dataset.openDialog);
      if (dlg) {
        if (opener.dataset.setField) {
          $$(`[data-field="${opener.dataset.setField}"]`, dlg).forEach((i) => { i.value = opener.dataset.setValue; });
          $$(`[data-show="${opener.dataset.setField}"]`, dlg).forEach((i) => { i.textContent = opener.dataset.setValue; });
        }
        $$('.dropdown.open').forEach((d) => d.classList.remove('open'));
        dlg.showModal();
      }
    }
    const closer = e.target.closest('[data-close-dialog]');
    if (closer) closer.closest('dialog').close();
  });
  const confirmDlg = $('#confirm-dialog');
  document.addEventListener('submit', (e) => {
    const form = e.target;
    if (form.dataset.confirm && !form.dataset.confirmed && confirmDlg) {
      e.preventDefault();
      $('[data-confirm-text]', confirmDlg).textContent = form.dataset.confirm;
      confirmDlg.returnValue = '';
      confirmDlg.showModal();
      confirmDlg.addEventListener('close', function handler() {
        confirmDlg.removeEventListener('close', handler);
        if (confirmDlg.returnValue === 'ok') { form.dataset.confirmed = '1'; form.requestSubmit ? form.requestSubmit() : form.submit(); }
      });
    }
  }, true);

  /* Warnung beim Verlassen ungespeicherter Formulare */
  $$('form[data-dirty-check]').forEach((form) => {
    let dirty = false;
    form.addEventListener('input', () => { dirty = true; });
    form.addEventListener('submit', () => { dirty = false; });
    window.addEventListener('beforeunload', (e) => { if (dirty) { e.preventDefault(); e.returnValue = ''; } });
  });

  /* --- Mehrfachauswahl mit Filterfeld --------------------------------------- */
  $$('select[data-multi]').forEach((sel) => {
    const filter = document.createElement('input');
    filter.type = 'search';
    filter.placeholder = 'Liste filtern …';
    filter.className = 'multi-filter';
    sel.parentNode.insertBefore(filter, sel);
    filter.addEventListener('input', () => {
      const q = filter.value.toLowerCase();
      Array.from(sel.options).forEach((o) => { o.hidden = q && !o.text.toLowerCase().includes(q) && !o.selected; });
    });
    sel.addEventListener('mousedown', (e) => {   // Klick schaltet um, ohne andere Auswahl zu verlieren
      if (e.target.tagName === 'OPTION' && !e.ctrlKey && !e.shiftKey) {
        e.preventDefault();
        e.target.selected = !e.target.selected;
        sel.dispatchEvent(new Event('change', { bubbles: true }));
      }
    });
  });

  /* --- Dynamische Tabellenzeilen ------------------------------------------ */
  function nextIndex(table, prefix) {
    let max = -1;
    $$('[name^="' + prefix + '-"]', table).forEach((i) => { const n = parseInt(i.name.split('-')[1], 10); if (n > max) max = n; });
    return max + 1;
  }
  function addRow(prefix) {
    const table = $(`table[data-rows="${prefix}"]`);
    if (!table) return null;
    const tpl = $('template', table);
    const html = tpl.innerHTML.replace(/__i__/g, nextIndex(table, prefix));
    const tbody = $('tbody', table);
    tbody.insertAdjacentHTML('beforeend', html);
    const row = tbody.lastElementChild;
    document.dispatchEvent(new CustomEvent('eln:row-added', { detail: { prefix, row } }));
    return row;
  }
  document.addEventListener('click', (e) => {
    const add = e.target.closest('[data-add-row]');
    if (add) { const r = addRow(add.dataset.addRow); if (r) { const f = $('input,select', r); if (f) f.focus(); } }
    const rm = e.target.closest('[data-remove-row]');
    if (rm) { const tr = rm.closest('[data-row]'); const table = tr.closest('table'); tr.remove(); table.dispatchEvent(new Event('input', { bubbles: true })); }
  });

  /* --- Rezepturpositionen: Chargenfilter und Live-Summe ------------------------ */
  const editor = $('[data-recipe-editor]');
  if (editor) {
    const batches = json($('[data-batch-map]', editor)) || [];
    const fillBatches = (row) => {
      const mat = $('[data-material]', row), bsel = $('[data-batch]', row);
      if (!mat || !bsel) return;
      const current = bsel.value || bsel.dataset.selected || '';
      bsel.innerHTML = '<option value="">–</option>';
      batches.filter((b) => String(b.material_id) === mat.value).forEach((b) => {
        const o = new Option(b.label, b.id); if (String(b.id) === String(current)) o.selected = true; bsel.add(o);
      });
    };
    const updateSum = () => {
      let sum = 0, missing = false;
      $$('[data-percent]', editor).forEach((i) => { const v = parseNum(i.value); if (v === null || isNaN(v)) missing = true; else sum += v; });
      $('[data-percent-sum]', editor).textContent = deNum(sum, 3);
      const hint = $('[data-sum-hint]', editor);
      const ok = Math.abs(sum - 100) <= 0.01;
      hint.textContent = missing ? 'Nicht alle Anteile erfasst' : (ok ? '✓ 100 %' : `Abweichung ${deNum(sum - 100, 3)} %`);
      hint.className = ok && !missing ? 'sum-indicator sum-ok' : 'sum-indicator sum-warning';
    };
    $$('[data-row]', editor).forEach(fillBatches);
    editor.addEventListener('change', (e) => { if (e.target.matches('[data-material]')) fillBatches(e.target.closest('[data-row]')); });
    editor.addEventListener('input', updateSum);
    document.addEventListener('eln:row-added', (e) => { if (e.detail.prefix === 'item') fillBatches(e.detail.row); updateSum(); });
    updateSum();
  }

  /* --- Gerätewarnungen im Versuchsformular -------------------------------- */
  const devWarn = $('#device-warnings');
  if (devWarn) {
    const map = json(devWarn) || {};
    const box = $('[data-device-warning-box]');
    const sel = $('select[name="devices"]');
    const update = () => {
      const msgs = [];
      Array.from(sel.selectedOptions).forEach((o) => (map[o.value] || []).forEach((m) => msgs.push(m)));
      box.hidden = !msgs.length;
      box.textContent = msgs.length ? '⚠ ' + msgs.join(' ') : '';
    };
    if (sel) { sel.addEventListener('change', update); update(); }
  }

  /* --- Compoundierung: Zonenvorlagen --------------------------------------- */
  const zoneBtn = $('[data-load-zones]');
  if (zoneBtn) {
    const templates = json($('[data-zone-templates]')) || {};
    const defaults = json($('[data-default-zones]')) || [];
    zoneBtn.addEventListener('click', () => {
      const dev = $('select[name="device_id"]');
      const label = dev && dev.selectedOptions[0] ? dev.selectedOptions[0].text : '';
      let names = defaults;
      Object.keys(templates).forEach((k) => { if (label.includes(k)) names = templates[k]; });
      const tbody = $('table[data-rows="zone"] tbody');
      if ($$('tr', tbody).length && !window.confirm('Vorhandene Zonen durch die Vorlage ersetzen?')) return;
      tbody.innerHTML = '';
      names.forEach((n) => { const r = addRow('zone'); $('input[name$="-name"]', r).value = n; });
    });
    $('[data-fill-set-temp]').addEventListener('click', () => {
      const v = window.prompt('Solltemperatur für alle Zonen (°C):');
      if (v !== null && v !== '') $$('table[data-rows="zone"] input[name$="-set_temp"]').forEach((i) => { i.value = v; });
    });
  }

  /* --- Drag-and-drop-Upload -------------------------------------------- */
  $$('form[data-upload]').forEach((form) => {
    const zone = $('[data-dropzone]', form), input = $('[data-file-input]', form), queue = $('[data-file-queue]', form);
    let files = [];
    const render = () => {
      queue.innerHTML = '';
      files.forEach((f) => { const li = document.createElement('li'); li.textContent = `${f.name} (${deNum(f.size / 1024, 1)} KB)`; queue.appendChild(li); });
    };
    const add = (list) => { Array.from(list).forEach((f) => files.push(f)); render(); };
    ['dragenter', 'dragover'].forEach((ev) => zone.addEventListener(ev, (e) => { e.preventDefault(); zone.classList.add('drag'); }));
    ['dragleave', 'drop'].forEach((ev) => zone.addEventListener(ev, (e) => { e.preventDefault(); zone.classList.remove('drag'); }));
    zone.addEventListener('drop', (e) => add(e.dataTransfer.files));
    input.addEventListener('change', () => { add(input.files); input.value = ''; });
    form.addEventListener('submit', (e) => {
      e.preventDefault();
      if (!files.length) { toast('Bitte zuerst Dateien auswählen oder hineinziehen.', 'warning'); return; }
      const fd = new FormData(form);
      fd.delete('files');
      files.forEach((f) => fd.append('files', f, f.name));
      const bar = $('[data-progress-bar]', form), prog = $('[data-progress]', form);
      prog.hidden = false;
      const xhr = new XMLHttpRequest();
      xhr.open('POST', form.action);
      xhr.setRequestHeader('X-CSRF-Token', csrf());
      xhr.setRequestHeader('X-Requested-With', 'fetch');
      xhr.upload.addEventListener('progress', (ev) => { if (ev.lengthComputable) bar.style.width = (ev.loaded / ev.total * 100) + '%'; });
      xhr.onload = () => {
        let res = {};
        try { res = JSON.parse(xhr.responseText); } catch (err) { res = { ok: false, messages: ['Unerwartete Antwort vom Server.'] }; }
        if (xhr.status === 401) { location.reload(); return; }
        (res.messages || []).forEach((m) => toast(m, 'warning'));
        if (res.ok) { toast(res.summary, 'success'); setTimeout(() => { location.hash = 'anhaenge'; location.reload(); }, 900); }
        else { toast(res.summary || res.detail || 'Upload fehlgeschlagen.', 'error'); prog.hidden = true; }
      };
      xhr.onerror = () => { toast('Netzwerkfehler beim Upload.', 'error'); prog.hidden = true; };
      xhr.send(fd);
    });
  });

  /* --- Bildergalerie (Lightbox) -------------------------------------------- */
  document.addEventListener('click', (e) => {
    const a = e.target.closest('[data-lightbox]');
    const lb = $('#lightbox');
    if (a && lb) {
      e.preventDefault();
      $('[data-lightbox-img]', lb).src = a.href;
      $('[data-lightbox-caption]', lb).textContent = a.dataset.caption || '';
      lb.showModal();
    }
  });

  /* --- Tabellen (Tabulator) -------------------------------------------- */
  $$('[data-table]').forEach((el) => {
    if (!window.Tabulator) return;
    const columns = JSON.parse(el.dataset.columns || '[]');
    const rows = json($(`[data-table-rows="${el.id}"]`)) || [];
    const statusClass = { 'freigegeben': 'success', 'aktiv': 'success', 'gültig': 'success', 'betriebsbereit': 'success', 'vorhanden': 'success', 'erledigt': 'success',
      'zur Prüfung': 'warning', 'pausiert': 'warning', 'in Wartung': 'warning', 'Quarantäne': 'warning', 'in Prüfung': 'warning', 'hoch': 'warning',
      'Korrektur erforderlich': 'danger', 'abgebrochen': 'danger', 'gesperrt': 'danger', 'storniert': 'danger', 'abgelaufen': 'danger', 'dringend': 'danger',
      'in Bearbeitung': 'info', 'geplant': 'info', 'offen': 'info', 'abgeschlossen': 'primary', 'geprüft': 'primary' };
    const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    const dateSorter = (a, b) => { const p = (s) => s ? s.split('.').reverse().join('') : ''; return p(a).localeCompare(p(b)); };
    const cols = columns.map((c, i) => {
      const col = { title: c[1], field: 'c' + i, headerFilter: 'input', headerFilterPlaceholder: 'filtern', minWidth: 80 };
      if (c[2] === 'link') col.formatter = (cell) => `<a href="${esc(cell.getRow().getData()._url)}">${esc(cell.getValue())}</a>`;
      if (c[2] === 'status' || c[2] === 'priority') col.formatter = (cell) => cell.getValue() ? `<span class="badge badge-${statusClass[cell.getValue()] || 'neutral'}">${esc(cell.getValue())}</span>` : '';
      if (c[2] === 'date') col.sorter = dateSorter;
      if (c[2] === 'number' || c[2] === 'int') { col.hozAlign = 'right'; col.sorter = (a, b) => (parseNum(a) || 0) - (parseNum(b) || 0); }
      return col;
    });
    const table = new Tabulator(el, {
      data: rows, columns: cols, layout: 'fitColumns', pagination: 'local', paginationSize: 25, paginationSizeSelector: [25, 50, 100, 500],
      placeholder: 'Keine Einträge', locale: 'de', langs: { de: { pagination: { first: '«', first_title: 'Erste Seite', last: '»', last_title: 'Letzte Seite', prev: '‹', prev_title: 'Vorherige', next: '›', next_title: 'Nächste', page_size: 'Zeilen', counter: { showing: 'Zeige', of: 'von', rows: 'Zeilen', pages: 'Seiten' } } } },
    });
    table.on('rowClick', (e, row) => { if (!e.target.closest('a')) location.href = row.getData()._url; });
    const filter = $(`[data-table-filter="${el.id}"]`);
    if (filter) filter.addEventListener('input', () => {
      const q = filter.value.toLowerCase();
      if (!q) table.clearFilter(); else table.setFilter((d) => Object.keys(d).some((k) => k !== '_url' && String(d[k]).toLowerCase().includes(q)));
    });
  });

  /* --- Diagramme (Chart.js) --------------------------------------------- */
  const palette = ['#1f5f99', '#d9822b', '#2f9e6b', '#b3261e', '#7b4fb0', '#0f8fa8', '#a07b00', '#5c6b7a', '#d14d8c', '#4b8f29'];
  function applyChartTheme() {
    if (!window.Chart) return;
    const cs = getComputedStyle(document.documentElement);
    Chart.defaults.color = cs.getPropertyValue('--muted').trim();
    Chart.defaults.borderColor = cs.getPropertyValue('--border').trim();
    Chart.defaults.font.family = cs.getPropertyValue('--font').trim();
  }
  applyChartTheme();
  const deTick = { callback: (v) => deNum(v) };
  const deTooltip = { callbacks: { label: (ctx) => `${ctx.dataset.label || ''}: ${deNum(ctx.parsed.y !== undefined ? ctx.parsed.y : ctx.parsed)}` } };
  function mkChart(name, config) {
    const c = $(`canvas[data-chart="${name}"]`);
    if (!c || !window.Chart) return null;
    config.options = Object.assign({ responsive: true, maintainAspectRatio: false }, config.options || {});
    return new Chart(c, config);
  }

  const dash = $('[data-dashboard-charts]');
  if (dash) {
    const d = json(dash);
    mkChart('dash-status', { type: 'doughnut', data: { labels: d.status.labels, datasets: [{ data: d.status.data, backgroundColor: palette }] }, options: { plugins: { legend: { position: 'right' } } } });
    mkChart('dash-departments', { type: 'bar', data: { labels: d.departments.labels, datasets: [{ label: 'Versuche', data: d.departments.data, backgroundColor: palette[0] }] }, options: { indexAxis: 'y', plugins: { legend: { display: false } }, scales: { x: { ticks: { precision: 0 } } } } });
    mkChart('dash-monthly', { type: 'line', data: { labels: d.monthly.labels, datasets: [{ label: 'neue Versuche', data: d.monthly.data, borderColor: palette[0], backgroundColor: palette[0] + '33', fill: true, tension: .3 }] }, options: { plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true, ticks: { precision: 0 } } } } });
  }

  const meas = $('[data-chart-data="measurement"]');
  if (meas) {
    const d = json(meas);
    mkChart('measurement', { type: 'scatter', data: { datasets: [{ label: d.y_label, data: d.points, borderColor: palette[0], backgroundColor: palette[0], showLine: true }] },
      options: { plugins: { tooltip: deTooltip, legend: { display: false } }, scales: { x: { title: { display: true, text: d.x_label }, ticks: deTick }, y: { title: { display: true, text: d.y_label }, ticks: deTick } } } });
  }

  const comp = $('[data-compounding-charts]');
  if (comp) {
    const d = json(comp);
    mkChart('zones', { type: 'line', data: { labels: d.zones.labels, datasets: [
      { label: 'Soll °C', data: d.zones.set, borderColor: palette[0], backgroundColor: palette[0], stepped: false, tension: .2 },
      { label: 'Ist °C', data: d.zones.actual, borderColor: palette[1], backgroundColor: palette[1], borderDash: [5, 4], tension: .2 }] },
      options: { plugins: { tooltip: deTooltip }, scales: { y: { ticks: deTick, title: { display: true, text: '°C' } } } } });
    const series = Object.entries(d.readings.series).filter(([, v]) => v.some((x) => x !== null));
    mkChart('readings', { type: 'line', data: { labels: d.readings.minutes.map((m) => deNum(m)), datasets: series.map(([label, values], i) => ({ label, data: values, borderColor: palette[i], backgroundColor: palette[i], yAxisID: 'y' + i, tension: .2 })) },
      options: { interaction: { mode: 'index', intersect: false }, plugins: { tooltip: deTooltip },
        scales: Object.fromEntries([['x', { title: { display: true, text: 'Zeit [min]' } }]].concat(series.map(([label], i) => ['y' + i, { position: i % 2 ? 'right' : 'left', display: i < 2, title: { display: i < 2, text: label }, ticks: deTick, grid: { drawOnChartArea: i === 0 } }]))) } });
  }

  const cmp = $('[data-compare-chart]');
  if (cmp) {
    const d = json(cmp);
    mkChart('compare-zones', { type: 'line', data: { labels: d.zones, datasets: d.runs.map((r, i) => ({ label: r.label, data: r.set, borderColor: palette[i % 10], backgroundColor: palette[i % 10], tension: .2 })) }, options: { plugins: { tooltip: deTooltip }, scales: { y: { ticks: deTick } } } });
    mkChart('compare-params', { type: 'bar', data: { labels: d.params.map((p) => p.label), datasets: d.runs.map((r, i) => ({ label: r.label, data: d.params.map((p) => p.values[i]), backgroundColor: palette[i % 10] })) },
      options: { indexAxis: 'y', plugins: { tooltip: { callbacks: { label: (c) => `${c.dataset.label}: ${deNum(c.parsed.x)}` } } }, scales: { x: { ticks: deTick } } } });
  }

  /* --- Auswertungen ---------------------------------------------------- */
  const af = $('[data-analysis-form]');
  if (af) {
    const meta = json($('[data-analysis-meta]', af)) || {};
    const dsSel = $('[data-ds]', af);
    const fill = () => {
      const ds = meta[dsSel.value];
      if (!ds) return;
      $$('select[data-fields]', af).forEach((sel) => {
        const keep = sel.value || sel.dataset.value || '';
        sel.innerHTML = '';
        if (sel.dataset.empty) sel.add(new Option(sel.dataset.empty, ''));
        const keys = sel.dataset.fields === 'numeric' ? ds.numeric : Object.keys(ds.fields);
        keys.forEach((k) => { const o = new Option(ds.fields[k] || k, k); if (k === keep) o.selected = true; sel.add(o); });
      });
    };
    dsSel.addEventListener('change', () => { $$('select[data-fields]', af).forEach((s) => { s.dataset.value = ''; s.value = ''; }); fill(); });
    fill();
  }
  const ar = $('[data-analysis-result]');
  if (ar) {
    const r = json(ar) || {};
    if (r.chart === 'scatter' && r.series) {
      mkChart('analysis', { type: 'scatter', data: { datasets: Object.entries(r.series).map(([label, pts], i) => ({ label, data: pts, backgroundColor: palette[i % 10], borderColor: palette[i % 10], showLine: false })) },
        options: { plugins: { tooltip: { callbacks: { label: (c) => `${c.dataset.label}: x=${deNum(c.parsed.x)}, y=${deNum(c.parsed.y)}` } } }, scales: { x: { title: { display: true, text: r.x_label }, ticks: deTick }, y: { title: { display: true, text: r.y_label }, ticks: deTick } } } });
    } else if (r.chart === 'boxplot' && r.boxes) {
      // Boxplot aus schwebenden Balken: Whisker (Min–Max), Box (Q1–Q3), Median
      mkChart('analysis', { type: 'bar', data: { labels: r.boxes.map((b) => b.label), datasets: [
        { label: 'Min–Max', data: r.boxes.map((b) => [b.min, b.max]), backgroundColor: palette[7], barPercentage: .08, grouped: false },
        { label: 'Q1–Q3', data: r.boxes.map((b) => [b.q1, b.q3]), backgroundColor: palette[0] + 'aa', borderColor: palette[0], borderWidth: 1, barPercentage: .5, grouped: false },
        { label: 'Median', type: 'scatter', data: r.boxes.map((b, i) => ({ x: b.label, y: b.median })), backgroundColor: palette[1], pointStyle: 'line', pointRadius: 18, borderColor: palette[1], borderWidth: 3 }] },
        options: { plugins: { tooltip: { callbacks: { label: (c) => { const v = c.raw; return Array.isArray(v) ? `${c.dataset.label}: ${deNum(v[0])} – ${deNum(v[1])}` : `Median: ${deNum(c.parsed.y)}`; } } } }, scales: { y: { ticks: deTick } } } });
    } else if (r.datasets && r.chart !== 'none') {
      mkChart('analysis', { type: r.chart === 'line' ? 'line' : 'bar', data: { labels: r.labels, datasets: r.datasets.map((d, i) => ({ label: d.label, data: d.data, backgroundColor: palette[i % 10] + (r.chart === 'line' ? '33' : ''), borderColor: palette[i % 10], tension: .25, spanGaps: true })) },
        options: { plugins: { tooltip: deTooltip }, scales: { y: { beginAtZero: true, ticks: deTick } } } });
    }
  }

  window.ELN = { toast, parseNum, deNum };
})();
