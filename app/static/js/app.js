(() => {
  const page = document.body.dataset.page || '';
  const csrf = document.querySelector('meta[name="csrf-token"]')?.content || '';
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const money = value => 'S/ ' + Number(value || 0).toLocaleString('es-PE', {minimumFractionDigits: 2, maximumFractionDigits: 2});
  const number = (value, digits = 3) => Number(value || 0).toLocaleString('es-PE', {minimumFractionDigits: digits, maximumFractionDigits: digits});
  const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  let vesselCatalog = [];
  const normalizeName = value => String(value ?? '').normalize('NFKD').replace(/[\u0300-\u036f]/g, '').trim().toLocaleLowerCase('es').replace(/\s+/g, ' ');

  function toast(message, type = 'success') {
    const area = $('#toastArea');
    if (!area) return;
    const node = document.createElement('div');
    node.className = `app-toast toast-${type}`;
    node.innerHTML = `<i class="bi ${type === 'success' ? 'bi-check-circle-fill' : 'bi-exclamation-triangle-fill'}"></i><span>${escapeHtml(message)}</span>`;
    area.appendChild(node);
    setTimeout(() => node.remove(), 4500);
  }
  async function api(url, options = {}) {
    const headers = {'Content-Type': 'application/json', 'X-CSRFToken': csrf, ...(options.headers || {})};
    const response = await fetch(url, {...options, headers});
    const contentType = response.headers.get('content-type') || '';
    const payload = contentType.includes('application/json') ? await response.json() : null;
    if (!response.ok) throw new Error(payload?.error || `Error HTTP ${response.status}`);
    return payload;
  }
  function setTodayDefaults() {
    const today = new Date();
    const local = new Date(today.getTime() - today.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
    $$('input[type="date"][name]').forEach(el => { if (!el.value) el.value = local; });
  }
  function syncVesselNameField(prefix) {
    const input = $(`#${prefix}Vessel`);
    const hidden = $(`#${prefix}VesselId`);
    const status = $(`#${prefix}VesselStatus`);
    const register = $(`#${prefix}VesselRegister`);
    if (!input || !hidden || !status || !register) return;
    const typed = input.value.trim();
    const normalized = normalizeName(typed);
    const matches = normalized ? vesselCatalog.filter(v => normalizeName(v.nombre) === normalized) : [];
    hidden.value = matches.length === 1 ? matches[0].id : '';
    register.classList.toggle('d-none', !typed || matches.length === 1);
    if (!typed) {
      status.textContent = 'Escribe el nombre para comprobar si está registrada.';
      status.className = 'form-text';
    } else if (matches.length === 1) {
      status.textContent = `Embarcación encontrada: ${matches[0].nombre} (${matches[0].codigo}).`;
      status.className = 'form-text text-success';
    } else if (matches.length > 1) {
      status.textContent = 'Hay registros repetidos con ese nombre. Revisa el catálogo de Embarcaciones.';
      status.className = 'form-text text-danger';
    } else {
      status.textContent = 'No está registrada. Usa “Registrar embarcación” para agregarla antes de guardar.';
      status.className = 'form-text text-danger';
    }
  }
  function bindVesselNameFields() {
    ['fishing', 'ice'].forEach(prefix => {
      const input = $(`#${prefix}Vessel`);
      if (!input || input.dataset.lookupBound === '1') return;
      input.dataset.lookupBound = '1';
      input.addEventListener('input', () => syncVesselNameField(prefix));
      input.addEventListener('change', () => syncVesselNameField(prefix));
    });
  }
  async function loadVessels() {
    const rows = await api('/api/vessels');
    vesselCatalog = rows;
    ['fishing', 'ice'].forEach(prefix => {
      const datalist = $(`#${prefix}VesselOptions`);
      if (datalist) datalist.innerHTML = rows.map(v => `<option value="${escapeHtml(v.nombre)}" label="${escapeHtml(v.codigo)}"></option>`).join('');
      syncVesselNameField(prefix);
    });
    const reportSelect = $('#reportVessel');
    if (reportSelect) {
      const first = reportSelect.querySelector('option')?.outerHTML || '<option value="">Todas las embarcaciones</option>';
      reportSelect.innerHTML = first + rows.map(v => `<option value="${escapeHtml(v.id)}">${escapeHtml(v.nombre)} (${escapeHtml(v.codigo)})</option>`).join('');
    }
    return rows;
  }
  function dateParams(fromId, toId) {
    const params = new URLSearchParams();
    const from = $(fromId)?.value, to = $(toId)?.value;
    if (from) params.set('desde', from);
    if (to) params.set('hasta', to);
    return params.toString();
  }
  function actionButton(id, endpoint, label = 'Anular') {
    return `<button class="btn btn-sm btn-outline-danger js-annul" data-id="${escapeHtml(id)}" data-endpoint="${endpoint}" type="button"><i class="bi bi-x-circle"></i> ${label}</button>`;
  }
  function editButton(row, endpoint) {
    const packed = encodeURIComponent(JSON.stringify(row));
    return `<button class="btn btn-sm btn-outline-primary js-edit me-1" data-endpoint="${endpoint}" data-record="${packed}" type="button"><i class="bi bi-pencil-square"></i> Editar</button>`;
  }
  async function editHandler(event) {
    const button = event.target.closest('.js-edit');
    if (!button) return;
    let row;
    try { row = JSON.parse(decodeURIComponent(button.dataset.record || '')); }
    catch (_) { toast('No se pudo cargar el registro para editar.', 'error'); return; }
    const ask = (label, value, optional = false) => {
      const result = prompt(label, value ?? '');
      if (result === null) return null;
      return optional && result.trim() === '' ? '' : result.trim();
    };
    const field = (label, key, optional = false) => ask(label, row[key] ?? '', optional);
    let payload = {};
    const endpoint = button.dataset.endpoint;
    if (endpoint === '/api/vessels') {
      const nombre = field('Nombre de embarcación:', 'nombre'); if (nombre === null) return;
      const matricula = field('Matrícula (opcional):', 'matricula', true); if (matricula === null) return;
      payload = {nombre, matricula};
    } else if (endpoint === '/api/fishing') {
      const fecha = field('Fecha (AAAA-MM-DD):', 'fecha'); if (fecha === null) return;
      const toneladas_tm = field('Toneladas TM:', 'toneladas_tm'); if (toneladas_tm === null) return;
      const kilos_kg = field('Kilos KG:', 'kilos_kg'); if (kilos_kg === null) return;
      const observaciones = field('Observaciones (opcional):', 'observaciones', true); if (observaciones === null) return;
      payload = {fecha, toneladas_tm, kilos_kg, observaciones};
    } else if (endpoint === '/api/valuations') {
      const isKg = Number(row.kilos_valorizados || 0) > 0;
      const fecha_valorizacion = field('Fecha de valorización (AAAA-MM-DD):', 'fecha_valorizacion'); if (fecha_valorizacion === null) return;
      const quantityKey = isKg ? 'kilos_valorizados' : 'toneladas_valorizadas';
      const priceKey = isKg ? 'precio_por_kg' : 'precio_por_tm';
      const quantity = field(isKg ? 'Cantidad KG:' : 'Cantidad TM:', quantityKey); if (quantity === null) return;
      const price = field(isKg ? 'Precio por KG (S/):' : 'Precio por TM (S/):', priceKey); if (price === null) return;
      const observaciones = field('Observaciones (opcional):', 'observaciones', true); if (observaciones === null) return;
      payload = {fecha_valorizacion, [quantityKey]: quantity, [priceKey]: price, observaciones};
    } else if (endpoint === '/api/ice') {
      const fecha = field('Fecha (AAAA-MM-DD):', 'fecha'); if (fecha === null) return;
      const cantidad = field('Cantidad:', 'cantidad'); if (cantidad === null) return;
      const unidad = ask('Unidad (BLOQUE, BOLSA, KG, TM, UNIDAD u OTRO):', row.unidad); if (unidad === null) return;
      const precio_unitario = field('Precio unitario (S/):', 'precio_unitario'); if (precio_unitario === null) return;
      const observaciones = field('Observaciones (opcional):', 'observaciones', true); if (observaciones === null) return;
      payload = {fecha, cantidad, unidad, precio_unitario, observaciones};
    } else if (endpoint === '/api/stay-expenses') {
      const fecha = field('Fecha (AAAA-MM-DD):', 'fecha'); if (fecha === null) return;
      const descripcion = field('Descripción:', 'descripcion'); if (descripcion === null) return;
      const precio = field('Precio (S/):', 'precio'); if (precio === null) return;
      payload = {fecha, descripcion, precio};
    } else return;
    if (!confirm('¿Guardar los cambios de este registro?')) return;
    try {
      await api(`${endpoint}/${encodeURIComponent(row.id)}`, {method:'PUT', body:JSON.stringify(payload)});
      toast('Registro actualizado correctamente.');
      if (page === 'vessels') await Promise.all([loadVesselTable(), loadNextVesselCode()]);
      if (page === 'fishing') await loadFishing();
      if (page === 'valuation') { await loadValuations(); await loadLandings(); }
      if (page === 'ice') await loadIce();
      if (page === 'stay_expenses') await loadStayExpenses();
    } catch (err) { toast(err.message, 'error'); }
  }

  async function annulHandler(event) {
    const button = event.target.closest('.js-annul');
    if (!button) return;
    if (!confirm('¿Confirmas la anulación? El registro se conservará en el historial de auditoría.')) return;
    try {
      await api(`${button.dataset.endpoint}/${encodeURIComponent(button.dataset.id)}/annul`, {method:'POST', body:'{}'});
      toast('Registro anulado correctamente.');
      if (page === 'fishing') loadFishing();
      if (page === 'valuation') { loadValuations(); loadLandings(); }
      if (page === 'ice') loadIce();
      if (page === 'stay_expenses') loadStayExpenses();
    } catch (err) { toast(err.message, 'error'); }
  }

  async function loadDashboard() {
    const query = dateParams('#dashboardFrom', '#dashboardTo');
    try {
      const data = await api(`/api/dashboard${query ? `?${query}` : ''}`);
      $('#metricTm').innerHTML = `${number(data.toneladas_tm)} <small>TM</small>`;
      $('#metricKg').innerHTML = `${number(data.kilos_kg)} <small>KG</small>`;
      $('#metricVal').textContent = money(data.valor_pesca);
      $('#metricIce').textContent = money(data.valor_hielo);
      $('#metricStayExpenses').textContent = money(data.gastos_estadia);
      $('#metricStayExpenseCount').textContent = data.registros_gastos_estadia ?? 0;
      $('#metricLandings').textContent = data.desembarques;
      $('#metricVessels').textContent = data.embarcaciones_activas;
      $('#metricPending').textContent = `${number(data.pendiente_tm)} TM`;
      $('#metricPendingKg').textContent = `${number(data.pendiente_kg)} KG`;
      $('#metricIceDispatches').textContent = data.despachos_hielo ?? 0;
      const iceBody = $('#iceSummaryBody');
      if (iceBody) {
        iceBody.innerHTML = data.hielo_por_unidad?.length
          ? data.hielo_por_unidad.map(r => `<tr><td><span class="code-chip">${escapeHtml(r.unidad)}</span></td><td class="text-end fw-semibold">${number(r.cantidad)}</td><td class="text-end">${r.despachos}</td></tr>`).join('')
          : '<tr><td colspan="3" class="empty-cell">No hay despachos de hielo para este periodo.</td></tr>';
      }
      const tbody = $('#topVesselsBody');
      tbody.innerHTML = data.top_embarcaciones.length ? data.top_embarcaciones.map(r => `<tr><td><strong>${escapeHtml(r.nombre)}</strong></td><td class="text-end fw-semibold">${number(r.tm)} TM</td></tr>`).join('') : '<tr><td colspan="2" class="empty-cell">Sin movimientos para el periodo.</td></tr>';
      const canvas = $('#fishingChart');
      if (canvas) {
        if (window.fishingChartInstance) window.fishingChartInstance.destroy();
        window.fishingChartInstance = new Chart(canvas, {type:'bar', data:{labels:data.pesca_diaria.map(r=>r.fecha), datasets:[{label:'Toneladas TM',data:data.pesca_diaria.map(r=>r.tm),backgroundColor:'#2B82A9',borderRadius:6,maxBarThickness:34}]}, options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{x:{grid:{display:false}},y:{beginAtZero:true,grid:{color:'#edf1f5'}}}}});
      }
    } catch (err) { toast(err.message, 'error'); }
  }

  async function loadNextVesselCode() {
    const input = $('#vesselNextCode');
    if (!input) return;
    try {
      const result = await api('/api/vessels/next-code');
      input.value = result.codigo || 'Se asignará al guardar';
    } catch (err) {
      input.value = 'Se asignará al guardar';
      toast(err.message, 'error');
    }
  }
  function vesselLabel(name, code) {
    return code ? `${name} (${code})` : (name || 'Embarcación no disponible');
  }
  async function loadVesselTable() {
    try {
      const rows = await api('/api/vessels');
      $('#vesselCount').textContent = `${rows.length} activas`;
      $('#vesselsBody').innerHTML = rows.length ? rows.map(v => `<tr><td><span class="code-chip">${escapeHtml(v.codigo)}</span></td><td><strong>${escapeHtml(v.nombre)}</strong></td><td>${escapeHtml(v.matricula || '—')}</td><td><span class="status-badge">Activa</span></td><td class="text-end">${editButton(v, '/api/vessels')}<button class="btn btn-sm btn-outline-danger js-deactivate" data-id="${escapeHtml(v.id)}"><i class="bi bi-person-dash"></i> Desactivar</button></td></tr>`).join('') : '<tr><td colspan="5" class="empty-cell">Todavía no hay embarcaciones registradas.</td></tr>';
    } catch (err) { toast(err.message, 'error'); }
  }
  async function loadFishing() {
    try {
      const query = dateParams('#fishingFrom', '#fishingTo');
      const rows = await api(`/api/fishing${query ? `?${query}` : ''}`);
      let tm = 0, kg = 0;
      rows.forEach(r => { tm += Number(r.toneladas_tm || 0); kg += Number(r.kilos_kg || 0); });
      $('#fishingTotalTm').textContent = number(tm); $('#fishingTotalKg').textContent = number(kg);
      $('#fishingBody').innerHTML = rows.length ? rows.map(r => `<tr><td>${escapeHtml(r.fecha)}</td><td><strong>${escapeHtml(vesselLabel(r.embarcacion_nombre, r.embarcacion_codigo))}</strong></td><td class="text-end">${number(r.toneladas_tm)}</td><td class="text-end">${number(r.kilos_kg)}</td><td class="text-wrap-cell">${escapeHtml(r.observaciones || '—')}</td><td>${editButton(r, '/api/fishing')}${actionButton(r.id, '/api/fishing')}</td></tr>`).join('') : '<tr><td colspan="6" class="empty-cell">No hay ingresos para este filtro.</td></tr>';
    } catch (err) { toast(err.message, 'error'); }
  }
  async function loadLandings() {
    try {
      const rows = await api('/api/available-landings');
      const tmRows = rows.filter(r => Number(r.pendiente_tm || 0) > 0);
      const kgRows = rows.filter(r => Number(r.pendiente_kg || 0) > 0);
      const optionHtml = (r, type) => {
        const pending = type === 'TM' ? r.pendiente_tm : r.pendiente_kg;
        const unit = type;
        return `<option value="${escapeHtml(r.id)}" data-pending="${escapeHtml(pending)}">${escapeHtml(r.fecha)} · ${escapeHtml(vesselLabel(r.embarcacion_nombre, r.embarcacion_codigo))} · ${number(pending)} ${unit} pendientes</option>`;
      };
      $('#landingTmSelect').innerHTML = '<option value="">Selecciona un desembarque...</option>' + tmRows.map(r => optionHtml(r, 'TM')).join('');
      $('#landingKgSelect').innerHTML = '<option value="">Selecciona un desembarque...</option>' + kgRows.map(r => optionHtml(r, 'KG')).join('');
      if (!tmRows.length) $('#landingTmInfo').textContent = 'No hay desembarques con TM pendientes.';
      if (!kgRows.length) $('#landingKgInfo').textContent = 'No hay desembarques con KG pendientes.';
    } catch (err) { toast(err.message, 'error'); }
  }
  async function loadValuations() {
    try {
      const query = dateParams('#valuationFrom', '#valuationTo');
      const rows = await api(`/api/valuations${query ? `?${query}` : ''}`);
      const tmRows = rows.filter(r => Number(r.toneladas_valorizadas || 0) > 0);
      const kgRows = rows.filter(r => Number(r.kilos_valorizados || 0) > 0);
      const tmTotal = tmRows.reduce((sum, r) => sum + Number(r.importe_tm || 0), 0);
      const kgTotal = kgRows.reduce((sum, r) => sum + Number(r.importe_kg || 0), 0);
      $('#valuationTmTotal').textContent = money(tmTotal);
      $('#valuationKgTotal').textContent = money(kgTotal);
      $('#valuationTmBody').innerHTML = tmRows.length ? tmRows.map(r => `<tr><td>${escapeHtml(r.fecha_valorizacion)}</td><td><strong>${escapeHtml(vesselLabel(r.embarcacion_nombre, r.embarcacion_codigo))}</strong></td><td>${number(r.toneladas_valorizadas)} TM</td><td>${money(r.precio_por_tm)}</td><td class="fw-semibold">${money(r.importe_tm)}</td><td>${editButton(r, '/api/valuations')}${actionButton(r.id, '/api/valuations')}</td></tr>`).join('') : '<tr><td colspan="6" class="empty-cell">No hay valorizaciones TM para este filtro.</td></tr>';
      $('#valuationKgBody').innerHTML = kgRows.length ? kgRows.map(r => `<tr><td>${escapeHtml(r.fecha_valorizacion)}</td><td><strong>${escapeHtml(vesselLabel(r.embarcacion_nombre, r.embarcacion_codigo))}</strong></td><td>${number(r.kilos_valorizados)} KG</td><td>${money(r.precio_por_kg)}</td><td class="fw-semibold">${money(r.importe_kg)}</td><td>${editButton(r, '/api/valuations')}${actionButton(r.id, '/api/valuations')}</td></tr>`).join('') : '<tr><td colspan="6" class="empty-cell">No hay valorizaciones KG para este filtro.</td></tr>';
    } catch (err) { toast(err.message, 'error'); }
  }
  async function loadIce() {
    try {
      const query = dateParams('#iceFrom', '#iceTo');
      const rows = await api(`/api/ice${query ? `?${query}` : ''}`);
      const total = rows.reduce((sum, r) => sum + Number(r.importe_total || 0), 0);
      $('#iceTotal').textContent = money(total);
      $('#iceBody').innerHTML = rows.length ? rows.map(r => `<tr><td>${escapeHtml(r.fecha)}</td><td><strong>${escapeHtml(vesselLabel(r.embarcacion_nombre, r.embarcacion_codigo))}</strong></td><td>${number(r.cantidad)}</td><td><span class="code-chip">${escapeHtml(r.unidad)}</span></td><td>${money(r.precio_unitario)}</td><td class="fw-semibold">${money(r.importe_total)}</td><td>${editButton(r, '/api/ice')}${actionButton(r.id, '/api/ice')}</td></tr>`).join('') : '<tr><td colspan="7" class="empty-cell">No hay despachos para este filtro.</td></tr>';
    } catch (err) { toast(err.message, 'error'); }
  }
  async function loadStayExpenses() {
    try {
      const query = dateParams('#stayExpenseFrom', '#stayExpenseTo');
      const rows = await api(`/api/stay-expenses${query ? `?${query}` : ''}`);
      const total = rows.reduce((sum, row) => sum + Number(row.precio || 0), 0);
      $('#stayExpenseTotal').textContent = money(total);
      $('#stayExpenseFooter').textContent = money(total);
      $('#stayExpenseCount').textContent = rows.length;
      $('#stayExpensesBody').innerHTML = rows.length
        ? rows.map(row => `<tr><td>${escapeHtml(row.fecha)}</td><td><strong>${escapeHtml(row.descripcion)}</strong></td><td class="fw-semibold">${money(row.precio)}</td><td>${editButton(row, '/api/stay-expenses')}${actionButton(row.id, '/api/stay-expenses')}</td></tr>`).join('')
        : '<tr><td colspan="4" class="empty-cell">No hay gastos de estadía para este filtro.</td></tr>';
    } catch (err) { toast(err.message, 'error'); }
  }
  function formData(form) { return Object.fromEntries(new FormData(form).entries()); }
  function bindForm(formId, endpoint, onSuccess) {
    const form = $(formId); if (!form) return;
    form.addEventListener('submit', async event => {
      event.preventDefault();
      const button = form.querySelector('button[type="submit"]');
      button.disabled = true;
      try {
        if (endpoint === '/api/fishing') {
          syncVesselNameField('fishing');
          if (!$('#fishingVesselId')?.value) throw new Error('La embarcación no está registrada. Usa “Registrar embarcación” antes de guardar.');
        }
        if (endpoint === '/api/ice') {
          syncVesselNameField('ice');
          if (!$('#iceVesselId')?.value) throw new Error('La embarcación no está registrada. Usa “Registrar embarcación” antes de guardar.');
        }
        await api(endpoint, {method:'POST', body:JSON.stringify(formData(form))});
        toast('Registro guardado correctamente.');
        form.reset(); setTodayDefaults();
        if (endpoint === '/api/fishing') syncVesselNameField('fishing');
        if (endpoint === '/api/ice') syncVesselNameField('ice');
        if (onSuccess) await onSuccess();
      } catch (err) { toast(err.message, 'error'); }
      finally { button.disabled = false; }
    });
  }
  function bindAnnulDelegation() { document.addEventListener('click', annulHandler); }
  function bindLiveCalculation(formId, qtyName, priceName, outputId) {
    const form = $(formId); if (!form) return;
    const calc = () => { const qty = Number(form.elements[qtyName].value || 0); const price = Number(form.elements[priceName].value || 0); $(outputId).textContent = money(qty * price); };
    form.addEventListener('input', calc);
  }
  async function downloadReport(format) {
    const kind = $('#reportType').value;
    const params = new URLSearchParams();
    const from = $('#reportFrom').value, to = $('#reportTo').value, vessel = $('#reportVessel').value;
    if (from) params.set('desde', from); if (to) params.set('hasta', to); if (vessel) params.set('embarcacion_id', vessel); params.set('formato', format);
    try {
      const response = await fetch(`/api/reports/${kind}?${params.toString()}`, {headers:{'X-CSRFToken':csrf}});
      if (!response.ok) { const err = await response.json().catch(()=>({})); throw new Error(err.error || 'No se pudo generar el reporte.'); }
      const blob = await response.blob();
      const disposition = response.headers.get('content-disposition') || '';
      const match = disposition.match(/filename="?([^";]+)"?/i);
      const filename = match?.[1] || `CONTROL_PESQUERO.${format}`;
      const url = URL.createObjectURL(blob); const link = document.createElement('a');
      link.href = url; link.download = filename; document.body.appendChild(link); link.click(); link.remove(); URL.revokeObjectURL(url);
      toast('Reporte guardado en Google Drive y descargado en tu computadora.');
    } catch (err) { toast(err.message, 'error'); }
  }

  async function previewReport() {
    const kind = $('#reportType').value;
    const params = new URLSearchParams();
    const from = $('#reportFrom').value, to = $('#reportTo').value, vessel = $('#reportVessel').value;
    if (from) params.set('desde', from);
    if (to) params.set('hasta', to);
    if (vessel) params.set('embarcacion_id', vessel);
    try {
      const report = await api(`/api/reports/${kind}/preview?${params.toString()}`);
      $('#previewTitle').textContent = report.title;
      $('#previewMeta').textContent = `Periodo: ${report.desde} al ${report.hasta}`;
      $('#previewCount').textContent = `${report.count} registros`;
      $('#previewContent').innerHTML = report.sections.map(section => {
        const head = `<thead><tr>${section.headers.map(h => `<th>${escapeHtml(h)}</th>`).join('')}</tr></thead>`;
        const body = section.rows.length
          ? section.rows.map(row => `<tr>${row.map(value => `<td>${escapeHtml(value ?? '')}</td>`).join('')}</tr>`).join('')
          : `<tr><td class="empty-cell" colspan="${section.headers.length}">Sin registros para los filtros seleccionados.</td></tr>`;
        const foot = section.totals ? `<tfoot><tr>${section.totals.map(value => `<th>${escapeHtml(value ?? '')}</th>`).join('')}</tr></tfoot>` : '';
        return `<div class="preview-section"><h4>${escapeHtml(section.title)}</h4><div class="table-responsive"><table class="table app-table preview-table">${head}<tbody>${body}</tbody>${foot}</table></div></div>`;
      }).join('');
      $('#reportPreview').hidden = false;
      $('#reportPreview').scrollIntoView({behavior:'smooth', block:'start'});
    } catch (err) { toast(err.message, 'error'); }
  }

  // Navegación móvil
  const menuButton = $('#mobileMenuBtn'), backdrop = $('#sidebarBackdrop');
  menuButton?.addEventListener('click', () => document.body.classList.toggle('sidebar-open'));
  backdrop?.addEventListener('click', () => document.body.classList.remove('sidebar-open'));
  $$('.sidebar .nav-link').forEach(a => a.addEventListener('click', () => document.body.classList.remove('sidebar-open')));
  setTodayDefaults();
  document.addEventListener('click', editHandler);

  if (page === 'dashboard') {
    loadDashboard(); $('#dashboardFilter')?.addEventListener('click', loadDashboard);
  }
  if (page === 'vessels') {
    loadVesselTable(); loadNextVesselCode();
    $('#vesselForm')?.addEventListener('submit', async event => {
      event.preventDefault(); const form = event.currentTarget; const button = form.querySelector('button'); button.disabled = true;
      try {
        const created = await api('/api/vessels', {method:'POST', body:JSON.stringify(formData(form))});
        toast(`Embarcación registrada con código ${created.codigo}.`);
        form.reset();
        await Promise.all([loadVesselTable(), loadNextVesselCode()]);
      }
      catch (err) { toast(err.message, 'error'); } finally { button.disabled = false; }
    });
    $('#vesselsBody')?.addEventListener('click', async event => {
      const btn = event.target.closest('.js-deactivate'); if (!btn) return;
      if (!confirm('¿Desactivar esta embarcación? Los registros históricos se conservarán.')) return;
      try { await api(`/api/vessels/${btn.dataset.id}/deactivate`, {method:'POST',body:'{}'}); toast('Embarcación desactivada.'); loadVesselTable(); }
      catch (err) { toast(err.message, 'error'); }
    });
  }
  if (page === 'fishing') {
    bindVesselNameFields();
    loadVessels().then(loadFishing).catch(err=>toast(err.message,'error'));
    bindForm('#fishingForm', '/api/fishing', loadFishing);
    $('#fishingFilter')?.addEventListener('click', loadFishing); bindAnnulDelegation();
  }
  if (page === 'valuation') {
    loadLandings(); loadValuations();
    const bindLandingDefault = (selectId, formId, infoId, unit) => {
      const select = $(selectId);
      select?.addEventListener('change', () => {
        const option = select.selectedOptions[0];
        const pending = option?.dataset.pending || '0';
        const form = $(formId);
        const qtyName = unit === 'TM' ? 'toneladas_valorizadas' : 'kilos_valorizados';
        const qty = form.elements[qtyName];
        qty.value = option?.value ? pending : '';
        $(infoId).textContent = option?.value
          ? `Saldo pendiente disponible: ${number(pending)} ${unit}. Puedes valorizarlo total o parcialmente.`
          : `Selecciona un desembarque con ${unit} pendientes.`;
      });
    };
    bindLandingDefault('#landingTmSelect', '#valuationTmForm', '#landingTmInfo', 'TM');
    bindLandingDefault('#landingKgSelect', '#valuationKgForm', '#landingKgInfo', 'KG');
    const bindSeparateValuation = (formId, unit, qtyName, priceName) => {
      const form = $(formId); if (!form) return;
      const output = unit === 'TM' ? '#valuationTmPreview' : '#valuationKgPreview';
      const calc = () => {
        const qty = Number(form.elements[qtyName].value || 0);
        const price = Number(form.elements[priceName].value || 0);
        $(output).textContent = money(qty * price);
      };
      form.addEventListener('input', calc);
      form.addEventListener('submit', async event => {
        event.preventDefault();
        const button = form.querySelector('button[type="submit"]');
        button.disabled = true;
        try {
          const payload = formData(form);
          payload.toneladas_valorizadas = unit === 'TM' ? payload.toneladas_valorizadas : '0';
          payload.precio_por_tm = unit === 'TM' ? payload.precio_por_tm : '0';
          payload.kilos_valorizados = unit === 'KG' ? payload.kilos_valorizados : '0';
          payload.precio_por_kg = unit === 'KG' ? payload.precio_por_kg : '0';
          await api('/api/valuations', {method:'POST', body:JSON.stringify(payload)});
          toast(`Valorización ${unit} guardada correctamente.`);
          form.reset(); setTodayDefaults(); calc();
          await loadLandings(); await loadValuations();
          $(unit === 'TM' ? '#landingTmInfo' : '#landingKgInfo').textContent = `Selecciona un desembarque con ${unit} pendientes.`;
        } catch (err) { toast(err.message, 'error'); }
        finally { button.disabled = false; }
      });
    };
    bindSeparateValuation('#valuationTmForm', 'TM', 'toneladas_valorizadas', 'precio_por_tm');
    bindSeparateValuation('#valuationKgForm', 'KG', 'kilos_valorizados', 'precio_por_kg');
    $('#valuationFilter')?.addEventListener('click', loadValuations); bindAnnulDelegation();
  }
  if (page === 'ice') {
    bindVesselNameFields();
    loadVessels().then(loadIce).catch(err=>toast(err.message,'error'));
    bindForm('#iceForm', '/api/ice', loadIce);
    bindLiveCalculation('#iceForm', 'cantidad', 'precio_unitario', '#icePreview');
    $('#iceFilter')?.addEventListener('click', loadIce); bindAnnulDelegation();
  }
  if (page === 'stay_expenses') {
    loadStayExpenses();
    bindForm('#stayExpenseForm', '/api/stay-expenses', loadStayExpenses);
    $('#stayExpenseFilter')?.addEventListener('click', loadStayExpenses);
    bindAnnulDelegation();
  }
  if (page === 'reports') {
    loadVessels().catch(err=>toast(err.message,'error'));
    const syncReportFilters = () => {
      const vesselFilter = $('#reportVesselFilter');
      if (vesselFilter) vesselFilter.hidden = $('#reportType').value === 'gastos_estadia';
    };
    $('#reportType')?.addEventListener('change', syncReportFilters);
    syncReportFilters();
    $('#previewReport')?.addEventListener('click', previewReport);
    $('#downloadPdf')?.addEventListener('click', () => downloadReport('pdf'));
    $('#downloadExcel')?.addEventListener('click', () => downloadReport('xlsx'));
  }
})();
