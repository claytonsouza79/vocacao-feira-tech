/**
 * script.js — Front-end da 1ª Feira Tech dos Jovens da Vocação
 *
 * Fluxo principal:
 *   1. Verificar se o visitante tem perfil salvo → caso contrário, ir para profileView
 *   2. Home: listar stands com filtro por curso + mural público
 *   3. Visita: avaliação com timer + trava de stand próprio (aluno)
 *   4. Sucesso: botões de compartilhamento rápido (WhatsApp, Twitter, Facebook) + Estúdio Social
 *   5. Expositor: cadastro / login + dashboard com métricas por perfil
 *   6. Admin: dashboard global com ranking e exportação
 */

(() => {
  // ── Utilitários básicos ────────────────────────────────────────────────
  const $ = (id) => document.getElementById(id);

  // Labels legíveis dos cursos (suporte a valores antigos e novos)
  const courseLabels = {
    webdesign:   '🎨 Web Design',
    programacao: '💻 Programação',
    audiovisual: '🎬 Audiovisual',
    ppt:         '📋 Prep. para o Trabalho',
    // Compatibilidade com valores legados do JSON
    python: '💻 Programação',
    web:    '🎨 Web Design',
    audio:  '🎬 Audiovisual',
    outro:  '📋 Outro',
  };

  const profileLabels = {
    aluno:             '🎓 Aluno Vocação',
    funcionario:       '🏫 Funcionário',
    visitante_externo: '🌐 Visitante Externo',
    empresa:           '💼 Empresa',
  };

  const profileBarClasses = {
    aluno:             'bar-aluno',
    funcionario:       'bar-funcionario',
    visitante_externo: 'bar-visitante_externo',
    empresa:           'bar-empresa',
    desconhecido:      'bar-desconhecido',
  };

  // Estado global da visita atual
  const state = {
    stars: 0,
    visitId: null,
    startedAt: Date.now(),
    timer: null,
    stand: null,
    photo: null,
  };

  const path = location.pathname;

  // Hashtags para compartilhamento
  const hashtags =
    '#feiratechvocacao #cursosvocacao #transformandovidas #vocacao ' +
    '#jovensvocacao #primeirafeiratechvocacao #conclusaocurso #partiunovoprojeto';

  // ── Identificação do visitante ─────────────────────────────────────────
  /**
   * Gera ou recupera a visitor_key persistida no localStorage.
   * Nunca é enviada diretamente ao servidor — o backend recebe apenas
   * o SHA-256 desta chave.
   */
  function visitorKey() {
    let key = localStorage.getItem('feira-tech-visitor');
    if (!key) {
      key = `${Date.now().toString(36)}_${crypto.randomUUID().replaceAll('-', '')}`;
      localStorage.setItem('feira-tech-visitor', key);
    }
    return key;
  }

  // ── Perfil do visitante ────────────────────────────────────────────────
  function getLocalProfile() {
    const raw = localStorage.getItem('feira-tech-profile');
    return raw ? JSON.parse(raw) : null;
  }

  function setLocalProfile(profile) {
    localStorage.setItem('feira-tech-profile', JSON.stringify(profile));
  }

  function clearLocalProfile() {
    localStorage.removeItem('feira-tech-profile');
  }

  // ── Requisições HTTP ───────────────────────────────────────────────────
  async function apiFetch(url, options = {}) {
    const res = await fetch(url, options);
    const data = await res.json();
    if (!res.ok) {
      throw Object.assign(
        new Error(data.error || 'Não foi possível concluir a requisição.'),
        { status: res.status, data }
      );
    }
    return data;
  }

  function post(url, body) {
    return apiFetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
  }

  // ── Navegação entre telas (SPA) ────────────────────────────────────────
  function showOnly(id) {
    document.querySelectorAll('.view').forEach((view) => {
      view.hidden = view.id !== id;
    });
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  // ── Toast de notificação ───────────────────────────────────────────────
  function toast(message, duration = 2800) {
    const el = $('toast');
    el.textContent = message;
    el.classList.add('show');
    clearTimeout(el._timer);
    el._timer = setTimeout(() => el.classList.remove('show'), duration);
  }

  // ── Formatação de duração ──────────────────────────────────────────────
  function formatDuration(seconds) {
    if (!seconds) return '—';
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return m ? `${m}min ${s}s` : `${s}s`;
  }

  // ── Dados: Stands ──────────────────────────────────────────────────────
  async function loadStands() {
    const stands = await apiFetch('/api/stands');
    const list = $('standList');
    const select = $('standSelect');

    list.innerHTML = '';
    if (select) select.innerHTML = '<option value="">Selecione seu stand</option>';
    if ($('emptyStands')) $('emptyStands').hidden = stands.length > 0;

    stands.forEach((stand) => {
      // Item na lista de seleção de stand (visitante)
      const link = document.createElement('a');
      link.href = `/visitar/${stand.id}`;
      link.className = 'stand-row';
      link.dataset.course = stand.course;
      link.innerHTML = `
        <span class="course-dot course-${stand.course}"></span>
        <span>
          <strong></strong>
          <small>${courseLabels[stand.course] || stand.course}</small>
        </span>
        <b>→</b>
      `;
      link.querySelector('strong').textContent = stand.name;
      list.appendChild(link);

      // Item no select do expositor
      if (select) {
        select.add(new Option(
          `${stand.name} · ${courseLabels[stand.course] || stand.course}`,
          stand.id
        ));
      }
    });

    return stands;
  }

  // ── Dados: Mural Público ───────────────────────────────────────────────
  async function loadWall() {
    const supports = await apiFetch('/api/mural');
    const grid = $('wallGrid');
    grid.replaceChildren();
    $('wallCount').textContent = supports.length ? `${supports.length} apoios` : '';
    $('emptyWall').hidden = supports.length > 0;

    supports.forEach((s) => {
      const art = document.createElement('article');
      const msg = document.createElement('p');
      const foot = document.createElement('div');
      const proj = document.createElement('strong');
      const stars = document.createElement('span');
      msg.textContent = `"${s.message}"`;
      proj.textContent = s.stand_name;
      stars.textContent = `${s.stars} ★`;
      foot.append(proj, stars);
      art.append(msg, foot);
      grid.appendChild(art);
    });
  }

  // ══════════════════════════════════════════════════════════════════════
  // TELA 0: Seleção de Perfil
  // ══════════════════════════════════════════════════════════════════════
  function initProfile(onComplete) {
    showOnly('profileView');
    let selectedType = null;
    let selectedCourse = null;

    // Seleção de cartão de perfil
    $('profileGrid').addEventListener('click', (e) => {
      const card = e.target.closest('.profile-card');
      if (!card) return;

      document.querySelectorAll('.profile-card').forEach((c) => c.classList.remove('selected'));
      card.classList.add('selected');
      selectedType = card.dataset.type;

      // Mostrar formulário extra apenas para alunos
      $('alunoForm').hidden = selectedType !== 'aluno';

      // Para não-alunos, confirmar imediatamente
      if (selectedType !== 'aluno') {
        saveAndContinue(selectedType, null, null, onComplete);
      }
    });

    // Seleção de curso (pílulas)
    $('coursePills').addEventListener('click', (e) => {
      const pill = e.target.closest('.course-pill');
      if (!pill) return;
      document.querySelectorAll('.course-pill').forEach((p) => p.classList.remove('selected'));
      pill.classList.add('selected');
      selectedCourse = pill.dataset.course;
    });

    // Confirmar perfil de aluno
    $('confirmAlunoProfile').addEventListener('click', () => {
      if (!selectedCourse) {
        toast('Selecione seu curso antes de continuar.');
        return;
      }
      const groupName = $('alunoGrupo').value.trim();
      if (groupName.length < 2) {
        toast('Informe o nome do seu grupo (mínimo 2 caracteres).');
        $('alunoGrupo').focus();
        return;
      }
      saveAndContinue(selectedType, selectedCourse, groupName, onComplete);
    });

    // Cancelar formulário de aluno
    $('cancelAlunoProfile').addEventListener('click', () => {
      $('alunoForm').hidden = true;
      document.querySelectorAll('.profile-card').forEach((c) => c.classList.remove('selected'));
      selectedType = null;
    });
  }

  async function saveAndContinue(profileType, cursoAluno, groupName, onComplete) {
    try {
      await post('/api/visitors/profile', {
        visitor_key: visitorKey(),
        profile_type: profileType,
        curso_aluno: cursoAluno || null,
        group_name: groupName || null,
      });
      const profile = { profile_type: profileType, curso_aluno: cursoAluno, group_name: groupName };
      setLocalProfile(profile);
      onComplete(profile);
    } catch (err) {
      toast(err.message);
    }
  }

  // ══════════════════════════════════════════════════════════════════════
  // TELA 1: Home
  // ══════════════════════════════════════════════════════════════════════
  function initHome(profile) {
    showOnly('homeView');

    // Exibir badge do perfil
    const badge = $('visitorBadge');
    $('badgeProfileLabel').textContent = profileLabels[profile.profile_type] || profile.profile_type;
    badge.hidden = false;

    // Trocar perfil
    $('changeProfile').addEventListener('click', () => {
      clearLocalProfile();
      initProfile(initHome);
    });

    // Carregar mural
    loadWall().catch(() => { $('publicWall').hidden = true; });

    // Abrir browser de stands
    $('visitorEntry').addEventListener('click', async () => {
      $('standBrowser').hidden = false;
      await loadStands();
      $('standBrowser').scrollIntoView({ behavior: 'smooth' });
    });

    // Fechar browser
    $('closeBrowser').addEventListener('click', () => {
      $('standBrowser').hidden = true;
    });

    // Filtro por curso
    $('courseFilter').addEventListener('click', (e) => {
      const pill = e.target.closest('.filter-pill');
      if (!pill) return;
      document.querySelectorAll('.filter-pill').forEach((p) => p.classList.remove('active'));
      pill.classList.add('active');
      const filter = pill.dataset.filter;
      document.querySelectorAll('.stand-row').forEach((row) => {
        row.hidden = filter ? row.dataset.course !== filter : false;
      });
    });
  }

  // ══════════════════════════════════════════════════════════════════════
  // TELA 2: Avaliação do Stand (Visita)
  // ══════════════════════════════════════════════════════════════════════
  async function initVisit(standId) {
    showOnly('visitView');

    try {
      const stand = await apiFetch(`/api/stands/${standId}`);
      state.stand = stand;
      $('visitStandName').textContent = stand.name;
      $('visitCourse').textContent = courseLabels[stand.course] || stand.course;
      state.startedAt = Date.now();

      const started = await post(`/api/stands/${standId}/visits/start`, {
        visitor_key: visitorKey(),
      });
      state.visitId = started.visit_id;

      // Inicia o timer de visita
      state.timer = setInterval(() => {
        const total = Math.floor((Date.now() - state.startedAt) / 1000);
        const mm = String(Math.floor(total / 60)).padStart(2, '0');
        const ss = String(total % 60).padStart(2, '0');
        $('visitTimer').textContent = `${mm}:${ss}`;
      }, 1000);

    } catch (err) {
      $('ratingArea').hidden = true;
      const errorDiv = $('visitError');
      errorDiv.hidden = false;

      // TRAVA DE OURO: mensagem específica quando aluno tenta avaliar o próprio stand
      if (err.data?.own_stand) {
        errorDiv.querySelector('h2').textContent = '🚫 Stand do seu grupo';
      }
      errorDiv.querySelector('p').textContent = err.message;
    }

    // Seleção de estrelas
    $('starPicker').addEventListener('click', (e) => {
      const btn = e.target.closest('button');
      if (!btn) return;
      state.stars = Number(btn.dataset.stars);
      [...$('starPicker').children].forEach((star) => {
        star.classList.toggle('selected', Number(star.dataset.stars) <= state.stars);
      });
      $('submitRating').disabled = false;
    });

    // Enviar avaliação
    $('submitRating').addEventListener('click', async () => {
      if (!state.visitId || !state.stars) return;
      $('submitRating').disabled = true;
      try {
        await post(`/api/stands/${standId}/visits/${state.visitId}/finish`, {
          visitor_key: visitorKey(),
          stars: state.stars,
        });
        clearInterval(state.timer);
        localStorage.setItem(`feira-tech-rated-${standId}`, '1');

        // Preparar botões de compartilhamento rápido
        setupQuickShare(standId);

        $('ratingArea').hidden = true;
        $('successState').hidden = false;
      } catch (err) {
        toast(err.message);
        $('submitRating').disabled = false;
      }
    });

    $('openSocialStudio').addEventListener('click', () => openSocialStudio(standId));
  }

  // ── Compartilhamento rápido pós-avaliação ──────────────────────────────
  function shareCaption() {
    return (
      `Acabei de conhecer o projeto "${state.stand?.name}" na 1ª Feira Tech ` +
      `dos Jovens da Vocação e dei ${state.stars} estrelas! ` +
      `Ideias que transformam vidas merecem ser compartilhadas.\n\n${hashtags}`
    );
  }

  function setupQuickShare(standId) {
    const pageUrl = encodeURIComponent(location.href);
    const text = encodeURIComponent(shareCaption());

    // WhatsApp
    $('shareWhatsapp').href = `https://wa.me/?text=${text}`;

    // Twitter/X
    $('shareTwitter').href = `https://twitter.com/intent/tweet?text=${text}&url=${pageUrl}`;

    // Facebook
    $('shareFacebook').href = `https://www.facebook.com/sharer/sharer.php?u=${pageUrl}`;

    // Registrar compartilhamento no servidor ao clicar
    [$('shareWhatsapp'), $('shareTwitter'), $('shareFacebook')].forEach((btn) => {
      btn.addEventListener('click', () => recordShare(standId), { once: true });
    });
  }

  async function recordShare(standId) {
    try {
      await post(`/api/stands/${standId}/engagement/share`, { visitor_key: visitorKey() });
    } catch {
      // Silencioso — o compartilhamento externo não deve ser bloqueado
    }
  }

  // ══════════════════════════════════════════════════════════════════════
  // TELA 3: Estúdio Social (Card para Redes Sociais)
  // ══════════════════════════════════════════════════════════════════════
  function wrapText(ctx, text, x, y, maxW, lineH) {
    let line = '';
    for (const word of text.split(' ')) {
      const test = `${line}${word} `;
      if (ctx.measureText(test).width > maxW && line) {
        ctx.fillText(line.trim(), x, y);
        line = `${word} `;
        y += lineH;
      } else {
        line = test;
      }
    }
    ctx.fillText(line.trim(), x, y);
  }

  function drawSocialCard() {
    const canvas = $('socialCanvas');
    const ctx = canvas.getContext('2d');

    // Fundo
    ctx.fillStyle = '#0e7692';
    ctx.fillRect(0, 0, 1080, 1080);

    // Círculos decorativos
    ctx.fillStyle = '#f5e024';
    ctx.beginPath(); ctx.arc(980, 90, 170, 0, Math.PI * 2); ctx.fill();

    ctx.fillStyle = '#c31f5e';
    ctx.beginPath(); ctx.arc(90, 970, 120, 0, Math.PI * 2); ctx.fill();

    // Área central
    ctx.fillStyle = '#073f53';
    ctx.beginPath(); ctx.roundRect(70, 185, 940, 555, 28); ctx.fill();

    if (state.photo) {
      const s = Math.min(state.photo.width, state.photo.height);
      ctx.save();
      ctx.beginPath(); ctx.roundRect(70, 185, 940, 555, 28); ctx.clip();
      ctx.drawImage(
        state.photo,
        (state.photo.width - s) / 2, (state.photo.height - s) / 2, s, s,
        70, 185, 940, 555
      );
      ctx.restore();
    } else {
      ctx.fillStyle = '#b4d33a';
      ctx.font = '800 180px sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText(`${state.stars}★`, 540, 525);
    }

    // Textos
    ctx.textAlign = 'left';
    ctx.fillStyle = '#ffffff';
    ctx.font = '800 44px sans-serif';
    ctx.fillText('1ª FEIRA TECH — JOVENS DA VOCAÇÃO', 70, 100);

    ctx.fillStyle = '#f5e024';
    ctx.font = '800 42px sans-serif';
    ctx.fillText('EU VIVI ESSA IDEIA.', 70, 810);

    ctx.fillStyle = '#ffffff';
    ctx.font = '800 56px sans-serif';
    wrapText(ctx, state.stand?.name || '', 70, 875, 940, 64);

    ctx.font = '600 26px sans-serif';
    ctx.fillStyle = '#d8f3f7';
    ctx.fillText(`#feiratechvocacao  •  ${state.stars} estrela${state.stars !== 1 ? 's' : ''}`, 70, 1025);
  }

  function canvasBlob() {
    return new Promise((res) => $('socialCanvas').toBlob(res, 'image/png'));
  }

  function openSocialStudio(standId) {
    showOnly('socialView');
    drawSocialCard();

    $('backToSuccess').onclick = (e) => {
      e.preventDefault();
      showOnly('visitView');
    };

    $('socialPhoto').onchange = () => {
      const file = $('socialPhoto').files[0];
      if (!file || !file.type.startsWith('image/') || file.size > 12 * 1024 * 1024) {
        toast('Escolha uma imagem de até 12 MB.');
        return;
      }
      const img = new Image();
      img.onload = () => { state.photo = img; drawSocialCard(); URL.revokeObjectURL(img.src); };
      img.src = URL.createObjectURL(file);
    };

    $('downloadCard').onclick = async () => {
      const link = document.createElement('a');
      link.download = 'meu-card-feira-tech.png';
      link.href = $('socialCanvas').toDataURL('image/png');
      link.click();
      await recordShare(standId);
    };

    $('shareCard').onclick = async () => {
      const blob = await canvasBlob();
      if (!blob) { toast('Não foi possível criar o card.'); return; }
      const file = new File([blob], 'feira-tech.png', { type: 'image/png' });
      try {
        if (navigator.share && navigator.canShare?.({ files: [file] })) {
          await navigator.share({ title: '1ª Feira Tech Vocação', text: shareCaption(), files: [file] });
        } else {
          await navigator.clipboard.writeText(shareCaption());
          toast('Texto copiado. Baixe o card para publicar.');
        }
        await recordShare(standId);
      } catch (err) {
        if (err.name !== 'AbortError') toast('Não foi possível abrir o compartilhamento.');
      }
    };

    $('copyCaption').onclick = async () => {
      await navigator.clipboard.writeText(shareCaption());
      toast('Texto e hashtags copiados!');
    };

    $('supportForm').onsubmit = async (e) => {
      e.preventDefault();
      try {
        await post(`/api/stands/${standId}/engagement/support`, {
          visitor_key: visitorKey(),
          message: $('supportMessage').value.trim(),
          consent: $('supportConsent').checked,
        });
        $('supportForm').replaceChildren(
          Object.assign(document.createElement('p'), {
            className: 'support-sent',
            textContent: 'Apoio enviado! O expositor fará a aprovação antes de aparecer no mural.',
          })
        );
      } catch (err) {
        toast(err.message);
      }
    };
  }

  // ══════════════════════════════════════════════════════════════════════
  // TELA 4: Área do Expositor
  // ══════════════════════════════════════════════════════════════════════
  async function initExhibitor() {
    showOnly('exhibitorView');
    await loadStands();

    // Acessar stand existente
    $('accessForm').addEventListener('submit', async (e) => {
      e.preventDefault();
      const standId = $('standSelect').value;
      const code = $('accessCode').value.trim();
      if (!standId) { showFormMsg('Selecione um stand.'); return; }
      try {
        await post(`/api/stands/${standId}/access`, { access_code: code });
        sessionStorage.setItem(`feira-tech-code-${standId}`, code);
        location.href = `/stand/${standId}`;
      } catch (err) {
        showFormMsg(err.message);
      }
    });

    // Cadastrar novo stand
    $('createForm').addEventListener('submit', async (e) => {
      e.preventDefault();
      try {
        const result = await post('/api/stands', {
          name: $('standName').value.trim(),
          course: $('courseSelect').value,
        });
        $('authLayout').hidden = true;
        $('newAccessCode').textContent = result.access_code;
        $('codeReveal').hidden = false;
        sessionStorage.setItem(`feira-tech-code-${result.stand.id}`, result.access_code);
        $('openNewDashboard').href = `/stand/${result.stand.id}`;
      } catch (err) {
        // TRAVA 1: grupo já cadastrado → exibe mensagem de erro visível
        showFormMsg(err.message);
      }
    });
  }

  function showFormMsg(msg) {
    const el = $('formMessage');
    el.textContent = msg;
    el.hidden = false;
    el.scrollIntoView({ behavior: 'smooth' });
  }

  // ══════════════════════════════════════════════════════════════════════
  // TELA 5: Dashboard do Expositor
  // ══════════════════════════════════════════════════════════════════════
  async function initDashboard(standId) {
    showOnly('dashboardView');
    const code = sessionStorage.getItem(`feira-tech-code-${standId}`);
    if (!code) { location.replace('/expositor'); return; }

    const load = async () => {
      try {
        const report = await apiFetch(
          `/api/stands/${standId}/dashboard?code=${encodeURIComponent(code)}`
        );

        $('dashboardName').textContent = report.stand.name;
        $('dashboardCourse').textContent = courseLabels[report.stand.course] || report.stand.course;
        $('metricVisitors').textContent = report.visitors;
        $('metricRating').textContent = report.visitors ? report.average_rating.toFixed(1) : '—';
        $('metricAverageTime').textContent = formatDuration(report.average_duration_seconds);
        $('metricTotalTime').textContent = formatDuration(report.total_duration_seconds);
        $('metricShares').textContent = report.shares;
        $('metricSupports').textContent = report.approved_supports;

        renderDistribution(report.distribution, report.visitors);
        renderProfileBreakdown(report.by_profile || {}, report.visitors, 'profileBreakdown');
        renderRecent(report.recent_visits);
        renderPending(report.pending_supports, standId, code, load);

        const qrUrl = `/api/stands/${standId}/qr?code=${encodeURIComponent(code)}`;
        $('standQr').src = qrUrl;
        $('downloadQr').href = qrUrl;
        $('exportCsv').href = `/api/stands/${standId}/export?code=${encodeURIComponent(code)}`;
      } catch {
        sessionStorage.removeItem(`feira-tech-code-${standId}`);
        location.replace('/expositor');
      }
    };

    $('refreshDashboard').addEventListener('click', load);
    await load();
  }

  function renderDistribution(dist, total) {
    $('ratingDistribution').innerHTML = [5, 4, 3, 2, 1]
      .map((star) => {
        const count = dist[String(star)] || 0;
        const pct = total ? Math.round((count / total) * 100) : 0;
        return `
          <div class="rating-row">
            <span>${star} ★</span>
            <div><i style="width:${pct}%"></i></div>
            <b>${count}</b>
          </div>`;
      })
      .join('');
  }

  function renderProfileBreakdown(byProfile, total, containerId) {
    const container = $(containerId);
    if (!container) return;

    const profileNameMap = {
      aluno:             '🎓 Aluno Vocação',
      funcionario:       '🏫 Funcionário',
      visitante_externo: '🌐 Visitante Externo',
      empresa:           '💼 Empresa',
      desconhecido:      '❓ Sem perfil',
    };

    const entries = Object.entries(byProfile).sort((a, b) => b[1] - a[1]);
    if (!entries.length) {
      container.innerHTML = '<p class="empty-dark">Nenhum dado por perfil ainda.</p>';
      return;
    }

    container.innerHTML = entries
      .map(([type, count]) => {
        const pct = total ? Math.round((count / total) * 100) : 0;
        const barClass = profileBarClasses[type] || 'bar-desconhecido';
        return `
          <div class="profile-bar-row">
            <span>${profileNameMap[type] || type}</span>
            <div class="bar-track"><div class="bar-fill ${barClass}" style="width:${pct}%"></div></div>
            <b>${count}</b>
          </div>`;
      })
      .join('');
  }

  function renderRecent(visits) {
    $('recentVisits').innerHTML = visits.length
      ? visits
          .map((v) => {
            const time = new Date(v.finished_at).toLocaleTimeString('pt-BR', {
              hour: '2-digit',
              minute: '2-digit',
            });
            const profileTag = profileLabels[v.profile_type] || v.profile_type || '';
            return `
              <div class="recent-row">
                <span>
                  <strong>${v.stars} ★</strong>
                  <small class="profile-tag">${profileTag}</small>
                  <small>${time}</small>
                </span>
                <b>${formatDuration(v.duration_seconds)}</b>
              </div>`;
          })
          .join('')
      : '<p class="empty-dark">As avaliações aparecerão aqui.</p>';
  }

  function renderPending(supports, standId, code, reload) {
    $('pendingCount').textContent = supports.length;
    const list = $('pendingSupports');
    list.replaceChildren();

    if (!supports.length) {
      list.innerHTML = '<p class="empty-dark">Nenhum apoio aguardando aprovação.</p>';
      return;
    }

    supports.forEach((s) => {
      const row = document.createElement('div');
      row.className = 'pending-row';

      const copy = document.createElement('div');
      const msg = document.createElement('p');
      msg.textContent = s.message;
      const meta = document.createElement('small');
      meta.textContent = `${s.stars} ★ · ${new Date(s.created_at).toLocaleString('pt-BR')}`;
      copy.append(msg, meta);

      const actions = document.createElement('div');
      actions.className = 'moderation-actions';

      [['approve', 'Aprovar', 'btn-primary'], ['reject', 'Rejeitar', 'btn-secondary']].forEach(
        ([action, label, cls]) => {
          const btn = document.createElement('button');
          btn.className = `btn ${cls}`;
          btn.textContent = label;
          btn.onclick = async () => {
            btn.disabled = true;
            try {
              await post(
                `/api/stands/${standId}/engagement/${s.id}/moderate`,
                { access_code: code, action }
              );
              await reload();
            } catch (err) {
              toast(err.message);
              btn.disabled = false;
            }
          };
          actions.appendChild(btn);
        }
      );

      row.append(copy, actions);
      list.appendChild(row);
    });
  }

  // ══════════════════════════════════════════════════════════════════════
  // TELA 6: Admin Global
  // ══════════════════════════════════════════════════════════════════════
  function initAdmin() {
    showOnly('adminView');

    $('adminLoginForm').addEventListener('submit', async (e) => {
      e.preventDefault();
      const password = $('adminPassword').value;
      try {
        const report = await apiFetch(
          `/api/admin/dashboard?password=${encodeURIComponent(password)}`
        );
        // Login bem-sucedido — esconde o form, exibe o dashboard
        sessionStorage.setItem('feira-tech-admin', password);
        $('adminLoginArea').hidden = true;
        $('adminDashboardArea').hidden = false;
        renderAdminDashboard(report, password);
      } catch (err) {
        const errEl = $('adminLoginError');
        errEl.textContent = err.message;
        errEl.hidden = false;
      }
    });

    // Tentar login automático se já autenticado nesta sessão
    const savedPw = sessionStorage.getItem('feira-tech-admin');
    if (savedPw) {
      apiFetch(`/api/admin/dashboard?password=${encodeURIComponent(savedPw)}`)
        .then((report) => {
          $('adminLoginArea').hidden = true;
          $('adminDashboardArea').hidden = false;
          renderAdminDashboard(report, savedPw);
        })
        .catch(() => sessionStorage.removeItem('feira-tech-admin'));
    }
  }

  function renderAdminDashboard(report, password) {
    $('adminTotalStands').textContent = report.total_stands;
    $('adminTotalVisitors').textContent = report.total_visitors;
    $('adminGlobalAvg').textContent = report.total_ratings ? report.global_average.toFixed(1) : '—';
    $('adminTotalShares').textContent = report.total_shares;
    $('adminTotalSupports').textContent = report.total_approved_supports;

    renderProfileBreakdown(report.by_profile || {}, report.total_visitors, 'adminProfileBreakdown');
    renderLeaderboard(report.leaderboard || []);

    // Exportação CSV global
    $('adminExportCsv').href =
      `/api/admin/export?password=${encodeURIComponent(password)}`;

    $('adminRefresh').onclick = async () => {
      const fresh = await apiFetch(
        `/api/admin/dashboard?password=${encodeURIComponent(password)}`
      );
      renderAdminDashboard(fresh, password);
      toast('Dados atualizados!');
    };
  }

  function renderLeaderboard(leaderboard) {
    const medals = ['🥇', '🥈', '🥉'];
    $('adminLeaderboard').innerHTML = leaderboard.length
      ? leaderboard
          .map((item, i) => {
            const medal = medals[i] ?? `#${i + 1}`;
            return `
              <div class="leaderboard-row">
                <span class="rank-medal">${medal}</span>
                <div>
                  <div class="leaderboard-name">${item.name}</div>
                  <div class="leaderboard-course">${courseLabels[item.course] || item.course}</div>
                </div>
                <div class="leaderboard-stars">
                  ${item.average_rating ? item.average_rating.toFixed(1) + ' ★' : '—'}
                </div>
                <div class="leaderboard-visitors">${item.visitors} visit.</div>
              </div>`;
          })
          .join('')
      : '<p class="empty-dark">Nenhum dado disponível ainda.</p>';
  }

  // ══════════════════════════════════════════════════════════════════════
  // Roteamento SPA
  // ══════════════════════════════════════════════════════════════════════
  function route() {
    // Rota admin: nunca precisa de perfil de visitante
    if (path === '/admin') {
      initAdmin();
      return;
    }

    // Rota do expositor: nunca precisa de perfil de visitante
    if (path === '/expositor') {
      initExhibitor();
      return;
    }

    // Rota do dashboard do expositor
    if (path.startsWith('/stand/')) {
      initDashboard(path.split('/')[2]);
      return;
    }

    // Rotas que exigem perfil do visitante
    const profile = getLocalProfile();

    if (path.startsWith('/visitar/')) {
      const standId = path.split('/')[2];
      if (!profile) {
        // Primeiro, coleta o perfil; depois inicia a visita
        initProfile(() => initVisit(standId));
      } else {
        initVisit(standId);
      }
      return;
    }

    // Home
    if (!profile) {
      initProfile(initHome);
    } else {
      initHome(profile);
    }
  }

  // Inicializa
  route();
})();