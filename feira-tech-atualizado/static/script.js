(() => {
  const $ = (id) => document.getElementById(id);
  const courseLabels = { python: 'Python', web: 'Web Design', audio: 'Audiovisual', outro: 'Outro' };
  const state = { stars: 0, visitId: null, startedAt: Date.now(), timer: null };
  const path = location.pathname;

  function visitorKey() {
    let key = localStorage.getItem('feira-tech-visitor');
    if (!key) {
      key = `${Date.now().toString(36)}_${crypto.randomUUID().replaceAll('-', '')}`;
      localStorage.setItem('feira-tech-visitor', key);
    }
    return key;
  }

  async function request(url, options = {}) {
    const response = await fetch(url, options);
    const data = await response.json();
    if (!response.ok) throw Object.assign(new Error(data.error || 'Não foi possível concluir.'), { status: response.status, data });
    return data;
  }

  function post(url, body) {
    return request(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  }

  function showOnly(id) {
    document.querySelectorAll('.view').forEach((view) => { view.hidden = view.id !== id; });
  }

  function toast(message) {
    const element = $('toast');
    element.textContent = message;
    element.classList.add('show');
    clearTimeout(element.timer);
    element.timer = setTimeout(() => element.classList.remove('show'), 2600);
  }

  function formatDuration(seconds) {
    if (!seconds) return '—';
    const minutes = Math.floor(seconds / 60);
    const remaining = seconds % 60;
    return minutes ? `${minutes}min ${remaining}s` : `${remaining}s`;
  }

  async function loadStands() {
    const stands = await request('/api/stands');
    const list = $('standList');
    const select = $('standSelect');
    list.innerHTML = '';
    select.innerHTML = '<option value="">Selecione seu stand</option>';
    $('emptyStands').hidden = stands.length > 0;
    stands.forEach((stand) => {
      const link = document.createElement('a');
      link.href = `/visitar/${stand.id}`;
      link.className = 'stand-row';
      link.innerHTML = `<span class="course-dot course-${stand.course}"></span><span><strong></strong><small>${courseLabels[stand.course]}</small></span><b>→</b>`;
      link.querySelector('strong').textContent = stand.name;
      list.appendChild(link);
      select.add(new Option(`${stand.name} · ${courseLabels[stand.course]}`, stand.id));
    });
    return stands;
  }

  function initHome() {
    showOnly('homeView');
    $('visitorEntry').addEventListener('click', async () => {
      $('standBrowser').hidden = false;
      await loadStands();
      $('standBrowser').scrollIntoView({ behavior: 'smooth' });
    });
    $('closeBrowser').addEventListener('click', () => { $('standBrowser').hidden = true; });
  }

  async function initVisit(standId) {
    showOnly('visitView');
    try {
      const stand = await request(`/api/stands/${standId}`);
      $('visitStandName').textContent = stand.name;
      $('visitCourse').textContent = courseLabels[stand.course];
      state.startedAt = Date.now();
      const started = await post(`/api/stands/${standId}/visits/start`, { visitor_key: visitorKey() });
      state.visitId = started.visit_id;
      state.timer = setInterval(() => {
        const total = Math.floor((Date.now() - state.startedAt) / 1000);
        $('visitTimer').textContent = `${String(Math.floor(total / 60)).padStart(2, '0')}:${String(total % 60).padStart(2, '0')}`;
      }, 1000);
    } catch (error) {
      $('ratingArea').hidden = true;
      $('visitError').hidden = false;
      $('visitError').querySelector('p').textContent = error.message;
    }
    $('starPicker').addEventListener('click', (event) => {
      const button = event.target.closest('button');
      if (!button) return;
      state.stars = Number(button.dataset.stars);
      [...$('starPicker').children].forEach((star) => star.classList.toggle('selected', Number(star.dataset.stars) <= state.stars));
      $('submitRating').disabled = false;
    });
    $('submitRating').addEventListener('click', async () => {
      if (!state.visitId || !state.stars) return;
      $('submitRating').disabled = true;
      try {
        await post(`/api/stands/${standId}/visits/${state.visitId}/finish`, { visitor_key: visitorKey(), stars: state.stars });
        clearInterval(state.timer);
        localStorage.setItem(`feira-tech-rated-${standId}`, '1');
        $('ratingArea').hidden = true;
        $('successState').hidden = false;
      } catch (error) {
        toast(error.message);
        $('submitRating').disabled = false;
      }
    });
  }

  async function initExhibitor() {
    showOnly('exhibitorView');
    await loadStands();
    $('accessForm').addEventListener('submit', async (event) => {
      event.preventDefault();
      const standId = $('standSelect').value;
      const code = $('accessCode').value.trim();
      try {
        await post(`/api/stands/${standId}/access`, { access_code: code });
        sessionStorage.setItem(`feira-tech-code-${standId}`, code);
        location.href = `/stand/${standId}`;
      } catch (error) { showFormMessage(error.message); }
    });
    $('createForm').addEventListener('submit', async (event) => {
      event.preventDefault();
      try {
        const result = await post('/api/stands', { name: $('standName').value.trim(), course: $('courseSelect').value });
        $('authLayout').hidden = true;
        $('newAccessCode').textContent = result.access_code;
        $('codeReveal').hidden = false;
        sessionStorage.setItem(`feira-tech-code-${result.stand.id}`, result.access_code);
        $('openNewDashboard').href = `/stand/${result.stand.id}`;
      } catch (error) { showFormMessage(error.message); }
    });
  }

  function showFormMessage(message) {
    $('formMessage').textContent = message;
    $('formMessage').hidden = false;
  }

  async function initDashboard(standId) {
    showOnly('dashboardView');
    const code = sessionStorage.getItem(`feira-tech-code-${standId}`);
    if (!code) { location.replace('/expositor'); return; }
    const load = async () => {
      try {
        const report = await request(`/api/stands/${standId}/dashboard?code=${encodeURIComponent(code)}`);
        $('dashboardName').textContent = report.stand.name;
        $('dashboardCourse').textContent = courseLabels[report.stand.course];
        $('metricVisitors').textContent = report.visitors;
        $('metricRating').textContent = report.visitors ? report.average_rating.toFixed(1) : '—';
        $('metricAverageTime').textContent = formatDuration(report.average_duration_seconds);
        $('metricTotalTime').textContent = formatDuration(report.total_duration_seconds);
        renderDistribution(report.distribution, report.visitors);
        renderRecent(report.recent_visits);
        const qrUrl = `/api/stands/${standId}/qr?code=${encodeURIComponent(code)}`;
        $('standQr').src = qrUrl;
        $('downloadQr').href = qrUrl;
        $('exportCsv').href = `/api/stands/${standId}/export?code=${encodeURIComponent(code)}`;
      } catch { sessionStorage.removeItem(`feira-tech-code-${standId}`); location.replace('/expositor'); }
    };
    $('refreshDashboard').addEventListener('click', load);
    await load();
  }

  function renderDistribution(distribution, total) {
    $('ratingDistribution').innerHTML = [5, 4, 3, 2, 1].map((star) => {
      const count = distribution[String(star)] || 0;
      const percentage = total ? Math.round(count / total * 100) : 0;
      return `<div class="rating-row"><span>${star} ★</span><div><i style="width:${percentage}%"></i></div><b>${count}</b></div>`;
    }).join('');
  }

  function renderRecent(visits) {
    $('recentVisits').innerHTML = visits.length ? visits.map((visit) => {
      const time = new Date(visit.finished_at).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
      return `<div class="recent-row"><span><strong>${visit.stars} ★</strong><small>${time}</small></span><b>${formatDuration(visit.duration_seconds)}</b></div>`;
    }).join('') : '<p class="empty-dark">As avaliações aparecerão aqui.</p>';
  }

  if (path.startsWith('/visitar/')) initVisit(path.split('/')[2]);
  else if (path.startsWith('/stand/')) initDashboard(path.split('/')[2]);
  else if (path === '/expositor') initExhibitor();
  else initHome();
})();