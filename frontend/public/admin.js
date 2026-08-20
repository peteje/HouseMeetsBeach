const API_BASE = '/api';
let token = sessionStorage.getItem('party_admin_token') || '';
let guests = [];

function escapeHtml(str){
  const div = document.createElement('div');
  div.textContent = str == null ? '' : str;
  return div.innerHTML;
}

async function apiFetch(path, options = {}){
  options.headers = Object.assign({}, options.headers, { 'Authorization': `Bearer ${token}` });
  const res = await fetch(`${API_BASE}${path}`, options);
  if(res.status === 401){
    sessionStorage.removeItem('party_admin_token');
    showLogin();
    throw new Error('unauthorized');
  }
  return res;
}

function showLogin(){
  document.getElementById('loginCard').style.display = 'block';
  document.getElementById('appArea').style.display = 'none';
}

function showApp(){
  document.getElementById('loginCard').style.display = 'none';
  document.getElementById('appArea').style.display = 'block';
  loadGuests();
}

document.getElementById('loginForm').addEventListener('submit', async function(e){
  e.preventDefault();
  const errorEl = document.getElementById('loginError');
  errorEl.style.display = 'none';
  const password = document.getElementById('password').value;
  try{
    const res = await fetch(`${API_BASE}/admin/login`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ password })
    });
    const data = await res.json();
    if(!res.ok){
      errorEl.textContent = data.detail || 'Anmeldung fehlgeschlagen.';
      errorEl.style.display = 'block';
      return;
    }
    token = data.token;
    sessionStorage.setItem('party_admin_token', token);
    showApp();
  }catch(err){
    errorEl.textContent = 'Verbindung fehlgeschlagen.';
    errorEl.style.display = 'block';
  }
});

async function loadGuests(){
  try{
    const res = await apiFetch('/admin/guests');
    guests = await res.json();
    render();
  }catch(err){ /* handled in apiFetch */ }
}

function render(){
  const tbody = document.getElementById('guestTableBody');
  const emptyState = document.getElementById('emptyState');
  tbody.innerHTML = '';
  emptyState.style.display = guests.length === 0 ? 'block' : 'none';

  let totalAdults = 0, totalChildren = 0;

  guests.forEach(g => {
    if(g.status !== 'abgesagt'){
      totalAdults += Number(g.adults) || 0;
      totalChildren += Number(g.children) || 0;
    }
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${escapeHtml(g.first_name)} ${escapeHtml(g.last_name)}</td>
      <td>
        <div>${escapeHtml(g.email)}</div>
        <div class="muted-small">${escapeHtml(g.phone)}</div>
      </td>
      <td class="center">${g.adults}</td>
      <td class="center">${g.children}</td>
      <td class="center">
        <select class="status-select" data-id="${g.id}" data-action="status">
          <option value="offen" ${g.status==='offen'?'selected':''}>Offen</option>
          <option value="zugesagt" ${g.status==='zugesagt'?'selected':''}>Zugesagt</option>
          <option value="abgesagt" ${g.status==='abgesagt'?'selected':''}>Abgesagt</option>
        </select>
      </td>
      <td><input type="text" class="notes-input" placeholder="Notiz..." value="${escapeHtml(g.notes)}" data-id="${g.id}" data-action="notes"></td>
      <td><button class="btn-danger" data-id="${g.id}" data-action="delete">Entfernen</button></td>
    `;
    tbody.appendChild(tr);
  });

  document.getElementById('statGuests').textContent = guests.length;
  document.getElementById('statAdults').textContent = totalAdults;
  document.getElementById('statChildren').textContent = totalChildren;
  document.getElementById('statTotal').textContent = totalAdults + totalChildren;
}

document.getElementById('guestTableBody').addEventListener('click', async function(e){
  const btn = e.target.closest('button[data-action="delete"]');
  if(!btn) return;
  const id = btn.dataset.id;
  const g = guests.find(x => String(x.id) === String(id));
  if(!confirm(`${g.first_name} ${g.last_name} wirklich entfernen?`)) return;
  await apiFetch(`/admin/guests/${id}`, { method: 'DELETE' });
  loadGuests();
});

document.getElementById('guestTableBody').addEventListener('change', async function(e){
  if(e.target.dataset.action === 'status'){
    const id = e.target.dataset.id;
    await apiFetch(`/admin/guests/${id}`, {
      method: 'PATCH',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ status: e.target.value })
    });
    loadGuests();
  }
});

let notesTimers = {};
document.getElementById('guestTableBody').addEventListener('input', function(e){
  if(e.target.dataset.action === 'notes'){
    const id = e.target.dataset.id;
    const value = e.target.value;
    clearTimeout(notesTimers[id]);
    notesTimers[id] = setTimeout(async () => {
      await apiFetch(`/admin/guests/${id}`, {
        method: 'PATCH',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ notes: value })
      });
    }, 600);
  }
});

document.getElementById('refreshBtn').addEventListener('click', loadGuests);

document.getElementById('exportBtn').addEventListener('click', async function(){
  const res = await apiFetch('/admin/export.csv');
  const text = await res.text();
  const blob = new Blob([text], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'gaesteliste-chillaz.csv';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
});

if(token){ showApp(); } else { showLogin(); }
