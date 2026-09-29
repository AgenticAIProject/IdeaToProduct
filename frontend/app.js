/* ─────────────────────────────────────────────────
  IdeaToProduct — app.js
  Orchestrates: landing → pipeline → studio
  Real API: /api/start, /api/status, /api/answer
  Mock data: window.MockData (mock-data.js)
  ───────────────────────────────────────────────── */
'use strict';

/* ── Config ──────────────────────────────────── */
const API = (window.location.origin && window.location.origin.startsWith('http')) ? window.location.origin : 'http://localhost:8000';

/* ── State ───────────────────────────────────── */
const State = {
  sessionId: null,
  projectId: null,
  projectName: 'Untitled',
  currentView: 'overview',
  pollTimer: null,
  isLive: false,    // true = real backend running
  pipelineData: null,     // from real API result
};

/* ── DOM refs ────────────────────────────────── */
const $ = id => document.getElementById(id);

/* ═════════════════════════════════════════════════
   1. BOOT
═════════════════════════════════════════════════ */
document.addEventListener('DOMContentLoaded', () => {
  navScrollEffect();
  wireCharCount();
  animateLandingIn();
  observeHiwCards();
  wireGridParallax();
  injectTracePanelDOM();
});

function navScrollEffect() {
  const nav = $('mainNav');
  window.addEventListener('scroll', () => {
    nav.classList.toggle('scrolled', window.scrollY > 30);
  }, { passive: true });
}

function wireCharCount() {
  const ta = $('ideaInput');
  const cc = $('charCount');
  if (!ta || !cc) return;
  ta.addEventListener('input', () => { cc.textContent = ta.value.length; });
}

function animateLandingIn() {
  const left = $('landingLeft');
  const right = $('landingRight');
  [left, right].forEach((el, i) => {
    if (!el) return;
    el.style.opacity = '0';
    el.style.transform = 'translateY(20px)';
    setTimeout(() => {
      el.style.transition = 'opacity 0.7s cubic-bezier(0.16,1,0.3,1), transform 0.7s cubic-bezier(0.16,1,0.3,1)';
      el.style.opacity = '1';
      el.style.transform = 'translateY(0)';
    }, 100 + i * 80);
  });
}

function observeHiwCards() {
  const cards = document.querySelectorAll('.hiw-card');
  const obs = new IntersectionObserver(entries => {
    entries.forEach(e => {
      if (!e.isIntersecting) return;
      const i = Array.from(cards).indexOf(e.target);
      e.target.style.transition = `opacity 0.6s ${i * 50}ms, transform 0.6s ${i * 50}ms`;
      e.target.style.opacity = '1';
      e.target.style.transform = 'translateY(0)';
      obs.unobserve(e.target);
    });
  }, { threshold: 0.1 });
  cards.forEach(c => {
    c.style.opacity = '0';
    c.style.transform = 'translateY(16px)';
    obs.observe(c);
  });
}

/* ═════════════════════════════════════════════════
   1b. GRID MOUSE PARALLAX
═════════════════════════════════════════════════ */
function wireGridParallax() {
  const grid = document.querySelector('.landing-bg-grid');
  if (!grid) return;
  const landing = document.querySelector('.screen-landing');
  if (!landing) return;
  landing.addEventListener('mousemove', e => {
    const rect = landing.getBoundingClientRect();
    const cx = (e.clientX - rect.left) / rect.width;
    const cy = (e.clientY - rect.top) / rect.height;
    const ox = (cx - 0.5) * 4; // ±2px
    const oy = (cy - 0.5) * 4;
    grid.style.backgroundPosition = `${ox}px ${oy}px`;
  }, { passive: true });
  landing.addEventListener('mouseleave', () => {
    grid.style.backgroundPosition = '0 0';
  });
}

/* ═════════════════════════════════════════════════
   1c. IDEA INTERPRETATION STATE MACHINE
═════════════════════════════════════════════════ */
const IDEA_TYPES = [
  { kw: ['habit', 'streak', 'check', 'routine'], type: 'Habit app', workflow: 'Daily check-off & streaks', features: '4–6 detected' },
  { kw: ['expense', 'split', 'bill', 'money', 'pay'], type: 'Finance tool', workflow: 'Expense tracking & splits', features: '3–5 detected' },
  { kw: ['note', 'markdown', 'document', 'wiki', 'kb'], type: 'Knowledge base', workflow: 'Note creation & search', features: '4–7 detected' },
  { kw: ['task', 'todo', 'project', 'kanban'], type: 'Task manager', workflow: 'Task creation & assignment', features: '5–8 detected' },
  { kw: ['chat', 'message', 'team', 'collab'], type: 'Collaboration', workflow: 'Real-time messaging', features: '6–10 detected' },
  { kw: ['shop', 'store', 'cart', 'product', 'buy'], type: 'E-commerce', workflow: 'Product listing & checkout', features: '8–12 detected' },
];

let interpretTimer = null;
function interpretIdea(text) {
  const low = text.toLowerCase();
  const match = IDEA_TYPES.find(t => t.kw.some(k => low.includes(k)));
  const panel = $('icInterpret');
  if (!panel) return;

  if (text.length < 20) {
    panel.style.display = 'none';
    return;
  }

  clearTimeout(interpretTimer);
  interpretTimer = setTimeout(() => {
    const type = match?.type || 'Custom app';
    const workflow = match?.workflow || 'Custom workflow';
    const features = match?.features || '3–5 detected';
    $('iciType').textContent = type;
    $('iciWorkflow').textContent = workflow;
    $('iciFeatures').textContent = features;
    panel.style.display = 'block';
  }, 600);
}

window.fillIdea = function (btn) {
  const ta = $('ideaInput');
  const cc = $('charCount');
  if (!ta) return;
  ta.value = btn.dataset.idea || btn.textContent.trim();
  if (cc) cc.textContent = ta.value.length;
  ta.focus();
};

/* ═════════════════════════════════════════════════
   3. LAUNCH PIPELINE
═════════════════════════════════════════════════ */
window.launchPipeline = async function () {
  const ta = $('ideaInput');
  const idea = ta ? ta.value.trim() : '';
  if (!idea) { shakeEl(ta); return; }

  const btn = $('launchBtn');
  const label = $('launchBtnLabel');
  if (btn) btn.disabled = true;
  if (label) label.textContent = 'Initializing…';

  try {
    const res = await fetch(`${API}/api/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ idea }),
    });
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();

    State.sessionId = data.session_id;
    State.projectId = data.project_id;
    State.projectName = deriveProjectName(idea);
    State.isLive = true;

    enterStudio(State.projectName, 'running');
    startPolling();

  } catch (err) {
    if (btn) btn.disabled = false;
    if (label) label.textContent = 'Launch Pipeline';
    alert('Could not connect to pipeline: ' + err.message);
  }
};

function deriveProjectName(idea) {
  // Take first 3-4 words as project name
  const words = idea.split(' ').slice(0, 4).join(' ');
  return words.length > 30 ? words.slice(0, 30) + '…' : words;
}

/* ═════════════════════════════════════════════════
   4. ENTER / EXIT STUDIO
═════════════════════════════════════════════════ */
function enterStudio(name, status) {
  // Switch nav
  $('navLanding').classList.add('hidden');
  $('navStudio').classList.remove('hidden');
  $('studioProjectName').textContent = name;
  setNavPipelineStatus(status);

  // Show studio, hide landing
  $('screenLanding').classList.add('hidden');
  $('screenStudio').classList.remove('hidden');

  // Set up sidebar
  $('sbProjName').textContent = name;
  setSbStatus(status);

  // Load overview
  renderOverview(State.isLive ? null : MockData);
  buildPipelineStages(State.isLive ? [] : MockData.pipeline);
  buildActivityFeed(State.isLive ? [] : MockData.activity);

  switchView('overview');
  window.scrollTo(0, 0);
}

window.exitStudio = function () {
  clearInterval(State.pollTimer);
  State.sessionId = null;
  State.isLive = false;

  $('navStudio').classList.add('hidden');
  $('navLanding').classList.remove('hidden');
  $('screenStudio').classList.add('hidden');
  $('screenLanding').classList.remove('hidden');

  const btn = $('launchBtn');
  const label = $('launchBtnLabel');
  if (btn) btn.disabled = false;
  if (label) label.textContent = 'Launch Pipeline';
};

/* ═════════════════════════════════════════════════
   5. POLLING (real backend)
═════════════════════════════════════════════════ */
function startPolling() {
  clearInterval(State.pollTimer);
  State.pollTimer = setInterval(pollStatus, 2500);
}

async function pollStatus() {
  if (!State.sessionId) return;
  try {
    const res = await fetch(`${API}/api/status/${State.sessionId}`);
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    handlePollResult(data);
  } catch { /* transient — keep polling */ }
}

function handlePollResult(data) {
  if (data.is_running) {
    // still running — update active stage from stage field when available
    return;
  }
  clearInterval(State.pollTimer);

  if (data.status === 'error') {
    showPipelineError(data.error || 'Unknown error.');
    return;
  }

  if (data.status === 'clarification') {
    showClarifyOverlay(data.result?.clarification_questions || []);
    return;
  }

  // Done
  State.pipelineData = data.result;
  completePipeline(data.result);
}

function completePipeline(result) {
  setNavPipelineStatus('done');
  setSbStatus('done');

  // Update sidebar stages to all done
  if (result) {
    const stage = result.current_stage || 'documentation';
    updateSidebarStages(stage, result);
    populateLiveViews(result);
  }
}

function populateLiveViews(result) {
  if (result.requirements && Object.keys(result.requirements).length)
    renderRequirementsView(result.requirements);
  if (result.design && Object.keys(result.design).length)
    renderDesignView(result.design);
  if (result.code && Object.keys(result.code).length)
    renderCodeView(result.code);
  if (result.test_results && Object.keys(result.test_results).length)
    renderTestsView(result.test_results);
  if (result.review && Object.keys(result.review).length)
    renderReviewView(result.review, result.approval_status);
  if (result.documentation && Object.keys(result.documentation).length)
    renderDocsView(result.documentation);
}

/* ═════════════════════════════════════════════════
   6. CLARIFICATION OVERLAY
═════════════════════════════════════════════════ */
function getQuestionPresetOptions(qText) {
  const t = qText.toLowerCase();
  if (t.includes('db') || t.includes('data') || t.includes('storage') || t.includes('database')) {
    return ["PostgreSQL", "SQLite / Local DB", "MongoDB / NoSQL", "Redis Cache", "Supabase"];
  }
  if (t.includes('auth') || t.includes('user') || t.includes('login') || t.includes('account')) {
    return ["Email & Password", "Google / Social OAuth", "JWT Token Auth", "Passwordless / Magic Link", "RBAC Permissions"];
  }
  if (t.includes('ui') || t.includes('frontend') || t.includes('design') || t.includes('theme') || t.includes('style')) {
    return ["Modern Dark Theme", "Sleek Minimalist", "Glassmorphism & Micro-animations", "Mobile Responsive", "High Contrast"];
  }
  if (t.includes('platform') || t.includes('deploy') || t.includes('target') || t.includes('device')) {
    return ["Web Application", "Mobile (iOS / Android)", "Desktop App", "CLI Tool", "Cloud / Docker Container"];
  }
  if (t.includes('api') || t.includes('backend') || t.includes('architecture') || t.includes('protocol')) {
    return ["RESTful API", "GraphQL API", "WebSocket Realtime", "Serverless Functions", "Modular Monolith"];
  }
  return ["Standard Best Practice", "Minimal MVP Approach", "Production & Scalable", "Strict Security First", "Fast Prototyping"];
}

function showClarifyOverlay(questions) {
  const overlay = $('clarifyOverlay');
  const cont = $('cmQuestions');
  cont.innerHTML = '';

  questions.forEach((q, i) => {
    const qText = typeof q === 'string' ? q : (q.question || q.text || 'Clarification Question');
    const presets = (Array.isArray(q.options) && q.options.length) ? q.options : getQuestionPresetOptions(qText);

    const div = document.createElement('div');
    div.className = 'cq-item';
    div.dataset.cqIndex = i;

    let optionsHtml = presets.map((opt, optIdx) => `
      <button type="button" class="cq-chip" data-val="${escHtml(opt)}" onclick="toggleCqChip(this)">
        <svg class="cq-chip-check" width="12" height="12" viewBox="0 0 12 12" fill="none">
          <path d="M2.5 6L5 8.5L9.5 3.5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
        <span>${escHtml(opt)}</span>
      </button>
    `).join('');

    div.innerHTML = `
      <div class="cq-header">
        <span class="cq-num">${String(i + 1).padStart(2, '0')}</span>
        <label class="cq-label" for="cq-${i}">${escHtml(qText)}</label>
      </div>
      <div class="cq-subtitle">Select multiple options below or type custom details:</div>
      <div class="cq-chips-container" id="cq-chips-${i}">
        ${optionsHtml}
      </div>
      <div class="cq-custom-chip-row">
        <input type="text" class="cq-custom-chip-input" id="cq-custom-chip-in-${i}"
          placeholder="+ Add custom option chip…"
          onkeydown="if(event.key==='Enter'){event.preventDefault();addCustomCqChip(${i});}" />
        <button type="button" class="cq-add-chip-btn" onclick="addCustomCqChip(${i})">+ Add</button>
      </div>
      <div class="cq-input-wrapper">
        <textarea id="cq-${i}" class="cq-textarea" rows="2"
          placeholder="Custom details / additional context (optional)…"></textarea>
      </div>
    `;
    cont.appendChild(div);
  });

  overlay.classList.remove('hidden');
}

window.toggleCqChip = function (btn) {
  btn.classList.toggle('selected');
};

window.addCustomCqChip = function (index) {
  const inp = $(`cq-custom-chip-in-${index}`);
  const val = inp?.value.trim();
  if (!val) return;

  const chipsCont = $(`cq-chips-${index}`);
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'cq-chip selected custom-added';
  btn.dataset.val = val;
  btn.setAttribute('onclick', 'toggleCqChip(this)');
  btn.innerHTML = `
    <svg class="cq-chip-check" width="12" height="12" viewBox="0 0 12 12" fill="none">
      <path d="M2.5 6L5 8.5L9.5 3.5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>
    <span>${escHtml(val)}</span>
  `;
  chipsCont.appendChild(btn);
  inp.value = '';
};

window.submitClarification = async function () {
  const items = document.querySelectorAll('#cmQuestions .cq-item');
  const answers = [];
  let valid = true;

  items.forEach((item, i) => {
    const selectedChips = Array.from(item.querySelectorAll('.cq-chip.selected')).map(c => c.dataset.val);
    const textarea = item.querySelector('.cq-textarea');
    const customText = textarea ? textarea.value.trim() : '';

    if (selectedChips.length === 0 && !customText) {
      valid = false;
      if (textarea) shakeEl(textarea);
      item.classList.add('cq-item-error');
    } else {
      item.classList.remove('cq-item-error');
      let combinedStr = '';
      if (selectedChips.length > 0) {
        combinedStr += `Selected options: [${selectedChips.join(', ')}]`;
      }
      if (customText) {
        if (combinedStr) combinedStr += ' | ';
        combinedStr += `Details: ${customText}`;
      }
      answers.push(combinedStr);
    }
  });

  if (!valid) return;

  $('clarifyOverlay').classList.add('hidden');

  try {
    const res = await fetch(`${API}/api/answer`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: State.sessionId, answers }),
    });
    if (!res.ok) throw new Error(await res.text());
    startPolling();
  } catch (err) {
    showPipelineError(err.message);
  }
};

window.skipClarification = async function () {
  $('clarifyOverlay').classList.add('hidden');
  try {
    const res = await fetch(`${API}/api/answer`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: State.sessionId, answers: ["skip (proceed with standard architectural defaults)"] }),
    });
    if (!res.ok) throw new Error(await res.text());
    startPolling();
  } catch (err) {
    showPipelineError(err.message);
  }
};

/* ═════════════════════════════════════════════════
   7. PIPELINE STATUS HELPERS
═════════════════════════════════════════════════ */
function setNavPipelineStatus(status) {
  const label = $('navPipelineLabel');
  const dot = $('navStudio')?.querySelector('.pill-dot');
  if (label) label.textContent = { running: 'Running', done: 'Complete', error: 'Error' }[status] || 'Initializing';
  if (dot) {
    dot.style.background = status === 'done' ? 'var(--green)'
      : status === 'error' ? 'var(--red)'
        : 'var(--green)';
    dot.style.animation = status === 'running' ? 'blink 2s infinite' : 'none';
  }
}

function setSbStatus(status) {
  const dot = $('sbStatusDot');
  const label = $('sbStatusLabel');
  if (!dot || !label) return;
  dot.className = 'status-dot ' + status;
  label.textContent = { running: 'Building', done: 'Complete', error: 'Error' }[status] || 'Initializing';
}

/* ═════════════════════════════════════════════════
   8. SIDEBAR PIPELINE STAGES
═════════════════════════════════════════════════ */
const STAGE_DEFS = [
  { id: 'requirement', label: 'Requirements' },
  { id: 'design', label: 'Design' },
  { id: 'code', label: 'Code' },
  { id: 'test', label: 'Tests' },
  { id: 'review', label: 'Review' },
  { id: 'documentation', label: 'Docs' },
];

function buildPipelineStages(pipelineArr) {
  const cont = $('sbPipelineStages');
  if (!cont) return;
  cont.innerHTML = '';

  const statusMap = {};
  (pipelineArr || []).forEach(s => { statusMap[s.id] = s.status; });

  STAGE_DEFS.forEach(def => {
    const st = statusMap[def.id] || 'queued';
    const btn = document.createElement('button');
    btn.className = 'sb-stage-item ' + (st === 'running' ? 'active' : st === 'done' ? 'done' : '');
    btn.dataset.stage = def.id;
    btn.onclick = () => switchView(def.id);
    btn.innerHTML = `<span class="sb-stage-dot"></span>${def.label}`;
    cont.appendChild(btn);
  });
}

function updateSidebarStages(lastStage, result) {
  const idx = STAGE_DEFS.findIndex(s => s.id === lastStage);
  STAGE_DEFS.forEach((def, i) => {
    const el = document.querySelector(`.sb-stage-item[data-stage="${def.id}"]`);
    if (!el) return;
    el.classList.remove('active');
    if (i <= idx) el.classList.add('done');
  });
}

/* ═════════════════════════════════════════════════
   9. ACTIVITY FEED
═════════════════════════════════════════════════ */
function buildActivityFeed(events) {
  const feed = $('sbActivityFeed');
  const count = $('sbActivityCount');
  if (!feed) return;
  feed.innerHTML = '';

  const evts = events || [];
  if (count) count.textContent = evts.length;

  evts.slice().reverse().forEach(evt => {
    const dot = document.createElement('div');
    dot.className = 'act-item';
    dot.innerHTML = `
      <div class="act-time">${escHtml(evt.time)}</div>
      <div class="act-agent">${escHtml(evt.agent)}</div>
      <div class="act-detail">${escHtml(evt.detail)}</div>
    `;
    feed.appendChild(dot);
  });
}

/* ═════════════════════════════════════════════════
   10. VIEW ROUTING
═════════════════════════════════════════════════ */
window.switchView = function (viewId) {
  State.currentView = viewId;

  // Update sidebar highlight
  document.querySelectorAll('.sb-item, .sb-stage-item').forEach(el => {
    const matches = el.dataset.view === viewId || el.dataset.stage === viewId;
    el.classList.toggle('active', matches);
  });

  // Show/hide view panels
  document.querySelectorAll('.studio-view').forEach(el => {
    el.classList.toggle('hidden', el.id !== 'view-' + viewId);
  });

  // Render view if not yet populated
  renderViewIfNeeded(viewId);
};

function renderViewIfNeeded(viewId) {
  const el = $('view-' + viewId);
  if (!el || el.dataset.rendered) return;

  // Use real data if available, fall back to mock
  const d = State.pipelineData;

  switch (viewId) {
    case 'overview': renderOverview(d ? { ...MockData, pipelineData: d } : MockData); break;
    case 'requirement': renderRequirementsView(d?.requirements || MockData.requirements); break;
    case 'design': renderDesignView(d?.design || MockData.design); break;
    case 'code': renderCodeView(d?.code || MockData.code); break;
    case 'test': renderTestsView(d?.test_results || MockData.tests); break;
    case 'review': renderReviewView(d?.review || MockData.review, d?.approval_status || MockData.review.approval_status); break;
    case 'documentation': renderDocsView(d?.documentation || MockData.documentation); break;
    case 'artifacts': renderArtifactsView(MockData.artifacts); break;
    case 'memory': renderMemoryView(MockData.memory); break;
  }
  el.dataset.rendered = '1';
}

/* ═════════════════════════════════════════════════
   11. VIEW RENDERERS
═════════════════════════════════════════════════ */

/* ── Overview ─────────────────────────────── */
function renderOverview(data) {
  const el = $('view-overview');
  if (!el) return;
  const proj = data?.project || MockData.project;
  const pipeline = MockData.pipeline;

  el.innerHTML = `
    <div class="view-hd">
      <div class="view-breadcrumb">Project</div>
      <div class="view-title">${escHtml(State.projectName || proj.name)}</div>
      <div class="view-sub">${escHtml(proj.status === 'building' ? 'Pipeline is running…' : proj.status === 'ready' ? 'Build complete.' : proj.status)}</div>
    </div>

    <div class="ov-grid">
      <div class="ov-card">
        <div class="ov-card-label">Current Agent</div>
        <div class="ov-card-val" style="font-size:20px">${agentLabel(proj.currentAgent)}</div>
        <div class="ov-card-sub">${agentSub(proj.currentAgent)}</div>
      </div>
      <div class="ov-card">
        <div class="ov-card-label">Elapsed</div>
        <div class="ov-card-val">${escHtml(proj.elapsed || '—')}</div>
        <div class="ov-card-sub">Started ${escHtml(proj.started || '—')}</div>
      </div>
    </div>

    <div class="sec">
      <div class="sec-title">Pipeline</div>
      <div class="pipeline-flow">
        ${pipeline.map((s, i) => `
          <div class="pf-stage ${s.status}">
            <div class="pf-track">
              <div class="pf-dot"></div>
              ${i < pipeline.length - 1 ? '<div class="pf-line"></div>' : ''}
            </div>
            <div class="pf-content">
              <div>
                <div class="pf-name">${escHtml(s.label)}</div>
                <div class="pf-meta">${s.count || statusLabel(s.status)}</div>
              </div>
              <div class="pf-time">${s.completedAt || ''}</div>
            </div>
          </div>
        `).join('')}
      </div>
    </div>
    ${State.isLive ? '<div style="margin-top:16px; font-family:var(--font-mono); font-size:11px; color:var(--text-muted)">Live · Real pipeline running</div>' : '<div style="margin-top:16px; font-family:var(--font-mono); font-size:11px; color:var(--text-muted)">Demo · Pipeline data from last run</div>'}
  `;

  // Inject pipeline signal into the flow visualization
  setTimeout(() => {
    const flow = el?.querySelector('.pipeline-flow');
    if (flow && !flow.querySelector('.pipeline-signal')) {
      const sig = document.createElement('div');
      sig.className = 'pipeline-signal';
      flow.appendChild(sig);
    }
  }, 80);
}

/* ── Trace map builder ─────────────────── */
function buildTraceMap(req) {
  const map = {};
  const design = MockData.design;
  (req.user_stories || []).forEach((s, i) => {
    const id = typeof s === 'string' ? `US-00${i + 1}` : s.id || `US-00${i + 1}`;
    const comp = design.components[i % design.components.length];
    map[id] = [
      { id, name: typeof s === 'string' ? s.slice(0, 40) : s.want || s, type: 'User Story' },
      { id: comp?.id || 'C-01', name: comp?.name || 'Component', type: 'Design Component' },
      { id: `tests/test_${(comp?.name || '').toLowerCase().replace(/\s/g, '_')}.py`, name: 'Test file', type: 'Test' },
    ];
  });
  return map;
}

window.traceStory = function (id, el) {
  if (!id) return;
  const panel = document.querySelector('.trace-panel');
  const chain = MockData && buildTraceMap(MockData.requirements)[id];
  if (!panel || !chain) return;

  panel.querySelector('.trace-chain').innerHTML = chain.map(n => `
    <div class="trace-node">
      <div class="trace-node-line"><div class="trace-node-dot"></div><div class="trace-node-stem"></div></div>
      <div class="trace-node-body">
        <div class="trace-node-id">${escHtml(n.id)}</div>
        <div class="trace-node-name">${escHtml(n.name)}</div>
        <div class="trace-node-type">${escHtml(n.type)}</div>
      </div>
    </div>
  `).join('');
  panel.classList.add('open');
};

function injectTracePanelDOM() {
  if (document.querySelector('.trace-panel')) return;
  const p = document.createElement('div');
  p.className = 'trace-panel';
  p.innerHTML = `
    <div class="trace-panel-title">
      Traceability
      <button class="trace-close" onclick="document.querySelector('.trace-panel').classList.remove('open')">✕</button>
    </div>
    <div class="trace-chain"></div>
  `;
  document.body.appendChild(p);
}

function agentLabel(id) {
  return { requirement: 'Requirement Agent', design: 'Design Agent', code: 'Code Agent', test: 'Test Agent', review: 'Review Agent', documentation: 'Documentation Agent' }[id] || '—';
}
function agentSub(id) {
  return { requirement: 'Generating requirements', design: 'Designing architecture', code: 'Generating repository', test: 'Running test suite', review: 'Evaluating quality', documentation: 'Writing docs' }[id] || '';
}
function statusLabel(s) {
  return { done: 'Completed', running: 'Running…', queued: 'Queued', failed: 'Failed' }[s] || s;
}

/* ── Requirements ────────────────────────── */
function renderRequirementsView(req) {
  const el = $('view-requirement');
  if (!el) return;
  const stories = req.user_stories || [];
  const traceMap = buildTraceMap(req);

  el.innerHTML = `
    <div class="view-hd">
      <div class="view-breadcrumb">Requirements</div>
      <div class="view-title">Requirements</div>
      <div class="view-sub">${escHtml(req.problem_statement || '')}</div>
    </div>

    ${req.objectives?.length ? `<div class="sec">
      <div class="sec-title">Objectives</div>
      <ul class="req-list">${req.objectives.map(o => `<li>${escHtml(o)}</li>`).join('')}</ul>
    </div>` : ''}

    ${stories.length ? `<div class="sec">
      <div class="sec-title">User Stories</div>
      ${stories.map(s => `
        <div class="req-story">
          <div class="req-story-id">${escHtml(typeof s === 'string' ? '' : s.id || '')}</div>
          <div class="req-story-body">
            ${typeof s === 'string' ? escHtml(s) : `As a <strong>${escHtml(s.role || 'user')}</strong>, I want to <strong>${escHtml(s.want || '')}</strong> so that ${escHtml(s.so_that || '')}.`}
          </div>
        </div>
      `).join('')}
    </div>` : ''}

    ${req.functional_requirements?.length ? `<div class="sec">
      <div class="sec-title">Functional Requirements</div>
      <ul class="req-list">${req.functional_requirements.map(r => {
    const parts = typeof r === 'string' ? r.split(':') : [r.id || '', r];
    return `<li><span class="req-id">${escHtml(parts[0] || '')}</span>${escHtml(parts.slice(1).join(':').trim() || r)}</li>`;
  }).join('')}</ul>
    </div>` : ''}

    ${req.non_functional_requirements?.length ? `<div class="sec">
      <div class="sec-title">Non-Functional Requirements</div>
      <ul class="req-list">${req.non_functional_requirements.map(r => `<li>${escHtml(typeof r === 'string' ? r : JSON.stringify(r))}</li>`).join('')}</ul>
    </div>` : ''}

    ${req.acceptance_criteria?.length ? `<div class="sec">
      <div class="sec-title">Acceptance Criteria</div>
      <ul class="req-list">${req.acceptance_criteria.map(a => `<li>${escHtml(a)}</li>`).join('')}</ul>
    </div>` : ''}

    ${renderInOutScope(req)}

    ${req.constraints?.length ? `<div class="sec">
      <div class="sec-title">Constraints</div>
      <ul class="req-list">${req.constraints.map(c => `<li>${escHtml(c)}</li>`).join('')}</ul>
    </div>` : ''}

    ${req.open_questions?.length ? `<div class="sec">
      <div class="sec-title">Open Questions</div>
      <ul class="req-list">${req.open_questions.map(q => `<li>${escHtml(q)}</li>`).join('')}</ul>
    </div>` : ''}
  `;
}

function renderInOutScope(req) {
  if (!req.in_scope?.length && !req.out_of_scope?.length) return '';
  return `<div class="sec">
    <div class="sec-title">Scope</div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:24px">
      <div>
        <div style="font-size:12px;font-weight:600;color:var(--green);margin-bottom:10px">In Scope</div>
        <ul class="req-list">${(req.in_scope || []).map(s => `<li>${escHtml(s)}</li>`).join('')}</ul>
      </div>
      <div>
        <div style="font-size:12px;font-weight:600;color:var(--text-muted);margin-bottom:10px">Out of Scope</div>
        <ul class="req-list">${(req.out_of_scope || []).map(s => `<li>${escHtml(s)}</li>`).join('')}</ul>
      </div>
    </div>
  </div>`;
}

/* ── Design ──────────────────────────────── */
function renderDesignView(design) {
  const el = $('view-design');
  if (!el) return;
  const comps = design.components || [];
  const decisions = design.decisions || [];

  el.innerHTML = `
    <div class="view-hd">
      <div class="view-breadcrumb">Design</div>
      <div class="view-title">Architecture</div>
      <div class="view-sub">${escHtml(design.architecture || '')}</div>
    </div>

    ${comps.length ? `<div class="sec">
      <div class="sec-title">Components</div>
      <table class="comp-table">
        <thead><tr><th>ID</th><th>Name</th><th>Responsibility</th><th>Depends on</th></tr></thead>
        <tbody>
          ${comps.map(c => `<tr>
            <td class="comp-id">${escHtml(typeof c === 'string' ? '' : c.id || '')}</td>
            <td style="font-weight:600">${escHtml(typeof c === 'string' ? c : c.name || '')}</td>
            <td class="tag-muted">${escHtml(typeof c === 'string' ? '' : c.responsibility || '')}</td>
            <td><div class="comp-deps">${(typeof c === 'string' ? [] : c.deps || []).map(d => `<span class="comp-dep-tag">${escHtml(d)}</span>`).join('')}</div></td>
          </tr>`).join('')}
        </tbody>
      </table>
    </div>` : ''}

    ${design.api_endpoints?.length ? `<div class="sec">
      <div class="sec-title">API Endpoints</div>
      <ul class="req-list">${design.api_endpoints.map(e => `<li style="font-family:var(--font-mono);font-size:13px">${escHtml(e)}</li>`).join('')}</ul>
    </div>` : ''}

    ${decisions.length ? `<div class="sec">
      <div class="sec-title">Design Decisions</div>
      ${decisions.map(d => `
        <div class="decision-card">
          <div class="dec-id">${escHtml(typeof d === 'string' ? 'DEC' : d.id || 'DEC')}</div>
          <div class="dec-decision">${escHtml(typeof d === 'string' ? d : d.decision || d)}</div>
          ${typeof d !== 'string' && d.reason ? `<div class="dec-reason">${escHtml(d.reason)}</div>` : ''}
          ${typeof d !== 'string' && d.impacted?.length ? `<div class="dec-impact">${d.impacted.map(i => `<span class="comp-dep-tag">${escHtml(i)}</span>`).join('')}</div>` : ''}
        </div>
      `).join('')}
    </div>` : ''}

    ${design.edge_cases?.length ? `<div class="sec">
      <div class="sec-title">Edge Cases</div>
      <ul class="req-list">${design.edge_cases.map(e => `<li>${escHtml(e)}</li>`).join('')}</ul>
    </div>` : ''}
  `;
}

/* ── Code ────────────────────────────────── */
function renderCodeView(code) {
  const el = $('view-code');
  if (!el) return;
  const files = code.files || [];

  const firstFile = files[0];
  el.innerHTML = `
    <div class="view-hd">
      <div class="view-breadcrumb">Code</div>
      <div class="view-title">Generated Repository</div>
      ${code.generated_project_path ? `<div class="view-sub" style="font-family:var(--font-mono);font-size:12px">${escHtml(code.generated_project_path)}</div>` : ''}
    </div>

    ${files.length ? `<div class="sec">
      <div class="sec-title">File Tree</div>
      <div class="code-workspace">
        <div class="cw-tree">
          <div class="cw-tree-title">Files</div>
          ${files.map((f, i) => `
            <div class="cw-file ${i === 0 ? 'active' : ''}" onclick="selectCodeFile(this)" data-path="${escHtml(f.path || '')}" data-desc="${escHtml(f.description || '')}">
              <span class="cw-file-dot"></span>${escHtml(f.path || '')}
            </div>
          `).join('')}
        </div>
        <div class="cw-content" id="cwContent">
          ${firstFile ? `<span style="color:var(--text-dim)"># ${escHtml(firstFile.path || '')}\n# ${escHtml(firstFile.description || '')}\n\n</span><span style="color:var(--text-muted)"># This file will be populated when the Code Agent\n# writes source files to disk.\n</span>` : ''}
        </div>
      </div>
    </div>` : ''}

    ${code.dependencies?.length ? `<div class="sec">
      <div class="sec-title">Dependencies</div>
      <div style="display:flex;flex-wrap:wrap;gap:8px">
        ${code.dependencies.map(d => `<span class="comp-dep-tag" style="font-size:13px;padding:4px 10px">${escHtml(d)}</span>`).join('')}
      </div>
    </div>` : ''}

    ${code.setup_instructions ? `<div class="sec">
      <div class="sec-title">Setup</div>
      <pre class="arch-diagram" style="margin:0">${escHtml(code.setup_instructions)}</pre>
    </div>` : ''}
  `;
}

window.selectCodeFile = function (el) {
  document.querySelectorAll('.cw-file').forEach(f => f.classList.remove('active'));
  el.classList.add('active');
  const content = $('cwContent');
  if (content) {
    content.innerHTML = `<span style="color:var(--text-dim)"># ${escHtml(el.dataset.path)}\n# ${escHtml(el.dataset.desc)}\n\n</span><span style="color:var(--text-muted)"># Source generated by Code Agent.\n# View the file on disk at:\n# ${escHtml(State.pipelineData?.code?.generated_project_path || MockData.code.generated_project_path)}/${escHtml(el.dataset.path)}\n</span>`;
  }
};

/* ── Tests ───────────────────────────────── */
function renderTestsView(tests) {
  const el = $('view-test');
  if (!el) return;
  const cases = tests.cases || [];

  el.innerHTML = `
    <div class="view-hd">
      <div class="view-breadcrumb">Tests</div>
      <div class="view-title">Test Results</div>
    </div>
    <div class="test-header">
      <div class="test-summary-nums">
        <div class="tsn"><div class="tsn-val tag-green">${tests.passed ?? 0}</div><div class="tsn-lbl">Passed</div></div>
        <div class="tsn"><div class="tsn-val tag-red">${tests.failed ?? 0}</div><div class="tsn-lbl">Failed</div></div>
        <div class="tsn"><div class="tsn-val" style="color:var(--amber)">${tests.errors ?? 0}</div><div class="tsn-lbl">Errors</div></div>
        ${tests.duration ? `<div class="tsn"><div class="tsn-val" style="font-size:24px;color:var(--text-dim)">${escHtml(tests.duration)}</div><div class="tsn-lbl">Duration</div></div>` : ''}
      </div>
      <div class="artifact-badge ${tests.status === 'pass' ? 'badge-done' : tests.status === 'fail' ? 'badge-fail' : 'badge-queue'}">${escHtml(tests.status || 'unknown')}</div>
    </div>
    ${cases.length ? `<div class="sec">
      <div class="sec-title">Test Cases</div>
      <div class="test-cases" id="testCaseList">
        ${cases.map(tc => `
          <div class="tc" onclick="toggleTestCase(this)">
            <div class="tc-status ${tc.status === 'pass' ? 'tc-pass' : 'tc-fail'}">${tc.status === 'pass' ? '✓' : '✕'}</div>
            <div class="tc-id">${escHtml(tc.id || '')}</div>
            <div class="tc-name">${escHtml(tc.name || '')}</div>
            <div class="tc-expect">${escHtml(tc.expected || '')} → ${escHtml(tc.actual || '')}</div>
          </div>
          ${tc.status !== 'pass' && tc.logs ? `
            <div class="tc-detail hidden" data-for="${escHtml(tc.id || '')}">
              <pre class="tc-log">${escHtml(tc.logs)}</pre>
            </div>
          ` : ''}
        `).join('')}
      </div>
    </div>` : ''}
    ${tests.output ? `<div class="sec">
      <div class="sec-title">Raw Output</div>
      <pre class="arch-diagram">${escHtml(tests.output)}</pre>
    </div>` : ''}
  `;
}

window.toggleTestCase = function (el) {
  const next = el.nextElementSibling;
  if (next && next.classList.contains('tc-detail')) {
    next.classList.toggle('hidden');
    el.classList.toggle('expanded');
  }
};

/* ── Review ──────────────────────────────── */
function renderReviewView(review, approvalStatus) {
  const el = $('view-review');
  if (!el) return;
  const checks = review.checks || [];
  const findings = review.findings || [];
  const approved = approvalStatus === 'approved';

  el.innerHTML = `
    <div class="view-hd">
      <div class="view-breadcrumb">Review</div>
      <div class="view-title">Quality Gate</div>
      <div class="artifact-badge ${approved ? 'badge-done' : 'badge-warn'}" style="margin-top:8px">
        ${approved ? '✓ Approved' : '⚠ Pending Review'}
      </div>
    </div>

    ${checks.length ? `<div class="sec">
      <div class="sec-title">Gate Checks</div>
      <table class="qg-table">
        <thead><tr><th>Area</th><th>Status</th><th>Note</th></tr></thead>
        <tbody>
          ${checks.map(c => `<tr>
            <td class="qg-area">${escHtml(c.area)}</td>
            <td><span class="artifact-badge ${c.status === 'pass' ? 'badge-done' : c.status === 'warn' ? 'badge-warn' : 'badge-fail'}">${escHtml(c.status)}</span></td>
            <td class="qg-note">${escHtml(c.note || '')}</td>
          </tr>`).join('')}
        </tbody>
      </table>
    </div>` : ''}

    ${(review.defects && review.defects.length) ? `<div class="sec">
      <div class="sec-title">Blocking Defects to Fix</div>
      ${review.defects.map(d => `
        <div class="finding high">
          <div class="finding-sev">BLOCKING DEFECT</div>
          <div class="finding-title">${escHtml(d)}</div>
        </div>
      `).join('')}
    </div>` : ''}

    ${findings.length ? `<div class="sec">
      <div class="sec-title">Findings & Recommendations</div>
      ${findings.map(f => `
        <div class="finding ${f.severity || 'low'}">
          <div class="finding-sev">${escHtml(f.severity || 'low')} · ${escHtml(f.id || '')}</div>
          <div class="finding-title">${escHtml(f.title || f)}</div>
          ${f.detail ? `<div class="finding-detail">${escHtml(f.detail)}</div>` : ''}
        </div>
      `).join('')}
    </div>` : ''}

    ${review.summary ? `<div class="sec">
      <div class="sec-title">Summary</div>
      <p style="font-size:14px;color:var(--text-dim);line-height:1.65">${escHtml(review.summary)}</p>
      ${review.overall_score ? `<div style="margin-top:8px;font-size:12px;font-family:var(--font-mono);color:var(--accent-glow)">Overall Quality Rating: ${escHtml(String(review.overall_score))}/10</div>` : ''}
    </div>` : ''}

    <div class="review-actions">
      <button class="action-btn action-approve" onclick="approveReview()">Approve</button>
      <button class="action-btn action-rework"  onclick="requestRework()">Request Rework</button>
    </div>
  `;
}
window.approveReview = function () { alert('Approval action — connect to backend to implement.'); };
window.requestRework = function () { alert('Rework action — connect to backend to implement.'); };

/* ── Documentation ───────────────────────── */
function renderDocsView(docs) {
  const el = $('view-documentation');
  if (!el) return;

  el.innerHTML = `
    <div class="view-hd">
      <div class="view-breadcrumb">Documentation</div>
      <div class="view-title">Documentation</div>
    </div>
    <div class="doc-prose">
      ${docs.overview ? `<h3>Overview</h3><p>${escHtml(docs.overview)}</p>` : ''}
      ${docs.getting_started ? `<h3>Getting Started</h3><pre>${escHtml(docs.getting_started)}</pre>` : ''}
      ${docs.features?.length ? `<h3>Features</h3><ul>${docs.features.map(f => `<li>${escHtml(f)}</li>`).join('')}</ul>` : ''}
      ${docs.api_reference ? `<h3>API Reference</h3><p>${escHtml(docs.api_reference)}</p>` : ''}
      ${docs.architecture ? `<h3>Architecture</h3><p>${escHtml(docs.architecture)}</p>` : ''}
      ${docs.known_limitations?.length ? `<h3>Known Limitations</h3><ul>${docs.known_limitations.map(l => `<li>${escHtml(l)}</li>`).join('')}</ul>` : ''}
    </div>
  `;
}

/* ── Artifacts ───────────────────────────── */
function renderArtifactsView(artifacts) {
  const el = $('view-artifacts');
  if (!el) return;

  const groups = Object.entries(artifacts || {});
  el.innerHTML = `
    <div class="view-hd">
      <div class="view-breadcrumb">Project</div>
      <div class="view-title">Artifacts</div>
      <div class="view-sub">Versioned outputs from each pipeline stage.</div>
    </div>
    ${groups.map(([stage, versions]) => `
      <div class="art-group">
        <div class="art-group-name">${escHtml(stage.charAt(0).toUpperCase() + stage.slice(1))}</div>
        <div class="art-versions">
          ${(versions || []).map(v => `
            <div class="art-ver">
              <div class="art-ver-num">v${v.version}</div>
              <div class="art-ver-info">
                <div class="art-ver-changes">${escHtml(v.changes)}</div>
                <div class="art-ver-ts">${escHtml(v.timestamp)}</div>
              </div>
              <span class="artifact-badge ${v.status === 'current' ? 'badge-done' : 'badge-queue'}">${escHtml(v.status)}</span>
            </div>
          `).join('')}
        </div>
      </div>
    `).join('')}
  `;
}

/* ── Memory ──────────────────────────────── */
function renderMemoryView(memory) {
  const el = $('view-memory');
  if (!el) return;

  el.innerHTML = `
    <div class="view-hd">
      <div class="view-breadcrumb">Project</div>
      <div class="view-title">Project Memory</div>
      <div class="view-sub">Decisions, constraints, and context retained across the pipeline.</div>
    </div>

    <div class="sec">
      <div class="sec-title">Decisions</div>
      ${(memory.decisions || []).map(d => `
        <div class="mem-item">
          <div class="mem-id">${escHtml(d.id)}</div>
          <div class="mem-title">${escHtml(d.title)}</div>
          <div class="mem-detail">${escHtml(d.detail)}</div>
          ${d.impact?.length ? `<div class="mem-impact">${d.impact.map(i => `<span class="mem-tag">${escHtml(i)}</span>`).join('')}</div>` : ''}
        </div>
      `).join('')}
    </div>

    <div class="sec">
      <div class="sec-title">Constraints</div>
      ${(memory.constraints || []).map(c => `
        <div class="mem-item">
          <div class="mem-id">${escHtml(c.id)}</div>
          <div class="mem-title">${escHtml(c.title)}</div>
          <div class="mem-detail">${escHtml(c.detail)}</div>
        </div>
      `).join('')}
    </div>

    <div class="sec">
      <div class="sec-title">Rejected Approaches</div>
      ${(memory.rejected || []).map(r => `
        <div class="mem-item mem-rejected">
          <div class="mem-title">${escHtml(r.title)}</div>
          <div class="mem-detail">${escHtml(r.reason)}</div>
        </div>
      `).join('')}
    </div>

    ${memory.previous_findings?.length ? `<div class="sec">
      <div class="sec-title">Previous Review Findings</div>
      ${memory.previous_findings.map(f => `
        <div class="mem-item">
          <div class="mem-id tag-muted">${escHtml(f.from)}</div>
          <div class="mem-title">${escHtml(f.title)}</div>
          <div style="margin-top:6px"><span class="artifact-badge ${f.status === 'open' ? 'badge-warn' : 'badge-done'}">${escHtml(f.status)}</span></div>
        </div>
      `).join('')}
    </div>` : ''}
  `;
}

/* ═════════════════════════════════════════════════
   12. PIPELINE ERROR
═════════════════════════════════════════════════ */
function showPipelineError(msg) {
  setNavPipelineStatus('error');
  setSbStatus('error');

  const el = $('view-overview');
  if (!el) return;
  el.insertAdjacentHTML('afterbegin', `
    <div class="err-card" style="margin-bottom:32px">
      <div class="err-label">Agent Interrupted</div>
      <div class="err-title">Pipeline stopped</div>
      <div class="err-msg">${escHtml(msg)}</div>
      <div class="err-actions">
        <button class="ghost-btn-sm" onclick="exitStudio()">Exit</button>
      </div>
    </div>
  `);
}

/* ═════════════════════════════════════════════════
   13. DEMO MODE — enter studio without running
       Called from the "How it works" section
═════════════════════════════════════════════════ */
window.openDemo = function () {
  State.projectName = MockData.project.name;
  State.isLive = false;
  enterStudio(MockData.project.name, 'done');
  buildPipelineStages(MockData.pipeline);
  buildActivityFeed(MockData.activity);

  // Pre-render all views with mock data
  STAGE_DEFS.forEach(s => renderViewIfNeeded(s.id));
  renderViewIfNeeded('artifacts');
  renderViewIfNeeded('memory');
};

/* ═════════════════════════════════════════════════
   14. HELPERS
═════════════════════════════════════════════════ */
function escHtml(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function shakeEl(el) {
  if (!el) return;
  el.style.animation = 'none';
  el.offsetHeight;
  el.style.animation = 'shake 0.35s ease';
  setTimeout(() => { el.style.animation = ''; }, 400);
}

/* Inject shake keyframe */
const _s = document.createElement('style');
_s.textContent = `
  @keyframes shake {
    0%,100%{transform:translateX(0)} 20%{transform:translateX(-6px)}
    40%{transform:translateX(6px)} 60%{transform:translateX(-4px)} 80%{transform:translateX(4px)}
  }
`;
document.head.appendChild(_s);

/* ===== visual/live-console layer (was fx.js) ===== */
/* fx.js — additive layer over app.js. Reads State (from app.js) and observes fetch responses; never changes API calls. */
(() => {
  'use strict';
  const RM = matchMedia('(prefers-reduced-motion:reduce)').matches;
  const AG = [['requirement', 'requirements.agent'], ['design', 'design.agent'], ['code', 'code.agent'], ['test', 'test.agent'], ['review', 'review.agent'], ['documentation', 'documentation.agent']];
  // Narration shown while a stage runs. Illustrative text — the backend does not stream logs yet.
  const SAY = { requirement: ['> analyzing product idea...', '> extracting actors...', '> generating user stories...', '> validating acceptance criteria...'], design: ['> selecting architecture...', '> generating component graph...', '> defining API contracts...'], code: ['> creating repository...', '> generating files...', '> installing dependencies...'], test: ['> running pytest...', 'test_user_auth ........ PASS', 'test_api_health ....... PASS'], review: ['> checking consistency...', '> checking implementation...', '> checking test coverage...'], documentation: ['> generating README...', '> generating API documentation...'] };
  const esc = t => String(t).replace(/&/g, '&amp;').replace(/</g, '&lt;');
  const hl = t => esc(t).replace(/(PASS|✓)/g, '<i class=g>$1</i>').replace(/(FAIL|✕)/g, '<i class=r>$1</i>').replace(/^&gt;/, '<i class=y>&gt;</i>').replace(/([\w-]+\.(?:md|json|py)|src\/|tests\/)/g, '<i class=b>$1</i>');
  const mk = (h, c) => { const d = document.createElement('div'); d.className = c; d.innerHTML = h; return d };
  const land = document.getElementById('screenLanding');

  // glow + ghost parallax
  const glow = mk('', 'fx-glow'); document.body.appendChild(glow);
  let mx = innerWidth / 2, my = innerHeight / 3; addEventListener('pointermove', e => { mx = e.clientX; my = e.clientY });
  const ghost = document.querySelector('.fx-ghost');
  (function t() { glow.style.transform = `translate(${mx}px,${my}px)`; if (ghost && !RM) ghost.style.transform = `translate(${(mx - innerWidth / 2) * -.012}px,${scrollY * -.06}px)`; requestAnimationFrame(t) })();

  // draggable
  function drag(w) {
    const bar = w.querySelector('.fx-bar'); let sx, sy, ox = 0, oy = 0, on = 0;
    bar.onpointerdown = e => { if (e.target.closest('button')) return; on = 1; sx = e.clientX - ox; sy = e.clientY - oy; bar.setPointerCapture(e.pointerId) };
    bar.onpointermove = e => { if (!on) return; ox = e.clientX - sx; oy = e.clientY - sy; w.style.transform = `translate(${ox}px,${oy}px)` };
    bar.onpointerup = () => on = 0
  }

  // landing windows: idea.md mirrors the textarea, pipeline mirrors run state
  const wIdea = mk('<div class="fx-bar"><span>idea.md</span><em>live</em></div><div class="fx-body" id="fxIdea"><div>waiting for your idea<i class="y">_</i></div></div>', 'fx-win fx-a');
  const wPipe = mk('<div class="fx-bar"><span>pipeline</span><em id="fxClock">idle</em></div><ol class="fx-body fx-flow" id="fxFlow" style="counter-reset:none"></ol>', 'fx-win fx-b');
  if (land) { land.append(wIdea, wPipe);[wIdea, wPipe].forEach(drag) }
  const ta = document.getElementById('ideaInput');
  if (ta) ta.addEventListener('input', () => {
    const ls = ta.value.trim().split(/(?<=[.!?])\s+|,\s*/).filter(Boolean).slice(0, 5);
    document.getElementById('fxIdea').innerHTML = (ls.length ? ls : ['waiting for your idea_']).map(l => `<div>${hl(l).replace(/\b(track|create|build|send|split|search|edit|export|reset|log|check)\w*/gi, '<i class=g>$&</i>')}</div>`).join('')
  });

  // console window (fixed, visible during a run, also inside the studio)
  const con = mk('<div class="fx-bar"><span id="fxTitle">agent-console</span><em id="fxState">idle</em><button id="fxMin" aria-label="Collapse console">–</button></div><div class="fx-flowrow" id="fxRow"></div><div class="fx-body" id="fxLog" aria-live="polite"></div>', 'fx-win fx-console');
  document.body.appendChild(con); drag(con);
  con.querySelector('#fxMin').onclick = () => con.classList.toggle('min');
  const log = con.querySelector('#fxLog'), row = con.querySelector('#fxRow');
  AG.forEach(() => row.appendChild(document.createElement('span')));
  const say = (t) => { log.appendChild(mk(hl(t), '')); log.scrollTop = 1e5 };

  let cur = -1, timer = null, t0 = 0, lines = 0;
  function paint() {
    const fl = document.getElementById('fxFlow'); if (fl) fl.innerHTML = AG.map((a, i) => `<li class="${i < cur ? 'done' : i === cur ? 'run' : ''}">${a[0]}</li>`).join('');
    [...row.children].forEach((s, i) => s.className = i < cur ? 'done' : i === cur ? 'run' : '');
    const c = document.getElementById('fxClock'); if (c) c.textContent = cur < 0 ? 'idle' : ((Date.now() - t0) / 1000 | 0) + 's'
  }
  function advance(to) {
    if (to <= cur) return; if (cur >= 0) say('✓ ' + AG[cur][0] + ' complete'); cur = to; lines = 0;
    document.getElementById('fxTitle').textContent = AG[cur] ? AG[cur][1] : 'agent-console'; document.getElementById('fxState').textContent = 'running'; paint()
  }
  function start() {
    con.classList.add('on'); log.innerHTML = ''; t0 = Date.now(); cur = -1; advance(0); clearInterval(timer);
    timer = setInterval(() => {
      const s = AG[cur] && SAY[AG[cur][0]]; if (!s) return;
      if (lines < s.length) say(s[lines++]); else if (cur < AG.length - 2 && !fromBackend && Date.now() - lastSwitch > 9000) { lastSwitch = Date.now(); advance(cur + 1) }
      paint()
    }, RM ? 200 : 1100)
  }
  let fromBackend = false, lastSwitch = Date.now();
  function finish(ok, msg) { clearInterval(timer); if (cur >= 0) say(ok ? '✓ ' + AG[cur][0] + ' complete' : '✕ ' + msg); cur = ok ? AG.length : cur; document.getElementById('fxState').textContent = ok ? '✓ done' : '✕ ' + (msg ? 'stopped' : 'error'); paint(); if (ok) say('✓ pipeline complete') }

  // observe (never alter) API traffic
  const _f = window.fetch;
  window.fetch = async function (u, o) {
    const r = await _f.apply(this, arguments);
    try {
      const url = String(u);
      if (url.endsWith('/api/start') && r.ok) start();
      else if (url.includes('/api/status/')) {
        r.clone().json().then(d => {
          const st = d.stage || d.current_stage || (d.result && d.result.current_stage); const i = AG.findIndex(a => a[0] === st);
          if (i >= 0 && d.is_running) { fromBackend = true; advance(i) }
          if (!d.is_running) { d.status === 'error' ? finish(false, d.error || 'error') : d.status === 'clarification' ? (say('? waiting for your answers'), document.getElementById('fxState').textContent = 'needs input', clearInterval(timer)) : finish(true) }
        }).catch(() => { })
      }
    } catch (e) { }
    return r
  };

  // bulb / cord theme toggle
  const root = document.documentElement;
  const setT = t => { root.dataset.theme = t; try { localStorage.setItem('itp-theme', t) } catch (e) { } };
  const flip = () => setT(root.dataset.theme === 'light' ? 'dark' : 'light');
  const bulb = mk('<div class="fx-cord" id="fxCord"></div><button id="fxBulb" aria-label="Toggle light or dark theme"><svg viewBox="0 0 40 56"><path d="M20 4a14 14 0 0 0-8 25c2 2 3 4 3 7h10c0-3 1-5 3-7A14 14 0 0 0 20 4z"/><rect x="14" y="38" width="12" height="9" rx="2"/></svg></button>', 'fx-bulb');
  document.body.appendChild(bulb);
  bulb.querySelector('#fxBulb').onclick = flip;
  const c = bulb.querySelector('#fxCord'); let y0 = null;
  c.onpointerdown = e => { y0 = e.clientY; c.setPointerCapture(e.pointerId); c.style.transition = 'none' };
  c.onpointermove = e => { if (y0 !== null) c.style.height = 64 + Math.min(60, Math.max(0, e.clientY - y0)) + 'px' };
  c.onpointerup = e => { if (y0 === null) return; const pulled = e.clientY - y0 > 25 || Math.abs(e.clientY - y0) < 3; y0 = null; c.style.transition = ''; c.style.height = '64px'; if (pulled) flip() };
  paint();
})();

/* ===== part 2: story sections, agent detail panel, artifact shelf, quality gate ===== */
(() => {
  'use strict';
  const host = document.getElementById('how-it-works'); if (!host) return;
  const RM = matchMedia('(prefers-reduced-motion:reduce)').matches, D = window.MockData || {};
  const esc = t => String(t == null ? '' : t).replace(/&/g, '&amp;').replace(/</g, '&lt;');
  const hl = t => esc(t).replace(/(PASS|✓)/g, '<i class=g>$1</i>').replace(/(FAIL|✕)/g, '<i class=r>$1</i>').replace(/^&gt;/, '<i class=y>&gt;</i>');
  const AG = [
    ['Requirements', 'requirements.agent', ['> analyzing product idea...', '> extracting actors...', '> generating user stories...', '> validating acceptance criteria...'], ['✓ 12 requirements generated', '✓ 8 acceptance criteria', '✓ scope validated']],
    ['Design', 'design.agent', ['> selecting architecture...', '> generating component graph...', '> defining API contracts...'], ['✓ 8 components', '✓ 6 endpoints']],
    ['Code', 'code.agent', ['> creating repository...', '> generating files...', '> installing dependencies...'], ['✓ 13 files written']],
    ['Tests', 'test.agent', ['> running pytest...', 'test_create_habit ..... PASS', 'test_streak_reset ..... PASS', 'test_timezone_edge ... FAIL'], ['✕ 1 test failed  → sent to review']],
    ['Review', 'review.agent', ['> checking consistency...', '> checking implementation...', '> checking test coverage...'], ['↻ rework requested: Code Agent', '✓ quality gate passed after rework']],
    ['Documentation', 'documentation.agent', ['> generating README...', '> generating API documentation...'], ['✓ README generated']]
  ];
  // sections (injected after "Six agents. One pipeline.")
  host.insertAdjacentHTML('afterend', `
<section class="p2" id="p2-live"><div class="p2-line"></div><h2 class="rv">Watch it<br><span class="o">work.</span></h2>
 <div class="p2-live"><div class="p2-tabs" id="p2Tabs" role="tablist"></div>
 <div class="fx-win p2-term" style="position:relative"><div class="fx-bar" style="cursor:default"><span id="p2File">requirements.agent</span><em>sample run · demo data</em></div><div class="fx-body" id="p2Log" aria-live="polite"></div></div></div></section>
<section class="p2" id="p2-art"><div class="p2-line"></div><h2 class="rv">Everything it builds,<br><span class="o">kept.</span></h2><div class="p2-shelf" id="p2Shelf"></div></section>
<section class="p2" id="p2-gate"><div class="p2-line"></div><h2 class="rv">Nothing ships<br><span class="o">unchecked.</span></h2>
 <div class="fx-win p2-gate" id="p2Gate" style="position:relative"><div class="fx-bar" style="cursor:default"><span>quality gate</span><em>demo data</em></div><div class="fx-body" id="p2GateBody" style="counter-reset:none"></div></div>
 <button class="p2-btn" id="p2Fail">Simulate a failed test</button></section>
<section class="p2 p2-cta"><div class="p2-line"></div><h2 class="rv">Start with one<br><span class="o">sentence.</span></h2><button class="p2-btn" id="p2Go">Describe your idea</button></section>
<div class="fx-win p2-prev" id="p2Prev" role="dialog" aria-label="Artifact preview"><div class="fx-bar" style="cursor:default"><span id="p2PName">file</span><button id="p2PClose" aria-label="Close preview">×</button></div><pre id="p2PBody"></pre></div>
<div class="fx-win p2-prev" id="p2Det" role="dialog" aria-label="Agent details"><div class="fx-bar" style="cursor:default"><span id="p2DName">agent</span><button id="p2DClose" aria-label="Close details">×</button></div><pre id="p2DBody" style="white-space:pre-wrap"></pre></div>`);

  // scroll reveals (mask + line draw), not generic fades
  const io = new IntersectionObserver(es => es.forEach(e => e.isIntersecting && (e.target.classList.add('in'), io.unobserve(e.target))), { threshold: .2 });
  document.querySelectorAll('.rv,.p2-line').forEach(el => RM ? el.classList.add('in') : io.observe(el));

  // connection track + click detail on the existing six cards
  const grid = host.querySelector('.hiw-grid'), cards = [...host.querySelectorAll('.hiw-card')];
  if (grid) {
    grid.insertAdjacentHTML('beforebegin', '<div class="p2-track" aria-hidden="true"><b id="p2Bar"></b><i></i></div>');
    const bar = document.getElementById('p2Bar');
    cards.forEach((c, i) => {
      c.tabIndex = 0; c.setAttribute('role', 'button');
      c.addEventListener('mouseenter', () => bar.style.width = ((i + 1) / cards.length * 100) + '%');
      c.addEventListener('focus', () => bar.style.width = ((i + 1) / cards.length * 100) + '%');
      const open = () => {
        const g = k => (c.querySelector('.ipo-tag.' + k)?.nextElementSibling?.textContent || '—').replace(/\s+/g, ' ').trim();
        document.getElementById('p2DName').textContent = c.querySelector('h3').textContent + ' agent';
        document.getElementById('p2DBody').textContent = 'Purpose\n  ' + g('proc') + '\n\nInput\n  ' + g('in') + '\n\nOutput\n  ' + g('out') + '\n\nStatus\n  ready\n\nDepends on\n  ' + (i ? cards[i - 1].querySelector('h3').textContent : 'nothing (starts the pipeline)');
        document.getElementById('p2Det').classList.add('on');
      };
      c.addEventListener('click', open); c.addEventListener('keydown', e => e.key === 'Enter' && open());
    });
  }
  document.getElementById('p2DClose').onclick = () => document.getElementById('p2Det').classList.remove('on');
  document.getElementById('p2PClose').onclick = () => document.getElementById('p2Prev').classList.remove('on');
  addEventListener('keydown', e => e.key === 'Escape' && document.querySelectorAll('.p2-prev').forEach(p => p.classList.remove('on')));

  // live execution replay (sample data, plays when scrolled into view or a tab is clicked)
  const tabs = document.getElementById('p2Tabs'), log = document.getElementById('p2Log');
  let tok = 0;
  async function play(i) {
    const my = ++tok; const [name, file, cmds, res] = AG[i];
    [...tabs.children].forEach((t, k) => t.className = 'p2-tab' + (k < i ? ' done' : k === i ? ' on' : ''));
    document.getElementById('p2File').textContent = file; log.innerHTML = '';
    const add = t => { const d = document.createElement('div'); d.innerHTML = hl(t); log.appendChild(d); };
    for (const t of cmds) { await new Promise(r => setTimeout(r, RM ? 20 : 480)); if (my !== tok) return; add(t); }
    for (const t of res) { await new Promise(r => setTimeout(r, RM ? 20 : 380)); if (my !== tok) return; add(t); }
    tabs.children[i].className = 'p2-tab done on';
  }
  AG.forEach((a, i) => { const b = document.createElement('button'); b.className = 'p2-tab'; b.textContent = a[0]; b.setAttribute('role', 'tab'); b.onclick = () => play(i); tabs.appendChild(b); });
  async function autoplay() { for (let i = 0; i < AG.length; i++) { const my = tok + 1; play(i); await new Promise(r => setTimeout(r, RM ? 200 : 4200)); if (tok !== my) return; } }
  new IntersectionObserver((es, o) => es[0].isIntersecting && (o.disconnect(), autoplay()), { threshold: .3 }).observe(document.getElementById('p2-live'));

  // artifact shelf (content comes from MockData samples)
  const j = o => JSON.stringify(o, null, 2);
  const R = D.requirements || {}, DS = D.design || {}, C = D.code || {}, T = D.tests || {}, RV = D.review || {}, DC = D.documentation || {};
  const ART = {
    'requirements.md': ['12 requirements', '# Requirements\n\n' + (R.problem_statement || '') + '\n\n' + (R.functional_requirements || []).join('\n')],
    'architecture.md': ['8 components', '# Architecture\n\n' + (DS.architecture || '') + '\n\n' + (DS.components || []).map(c => c.id + '  ' + c.name + ' — ' + c.responsibility).join('\n')],
    'api-spec.json': ['6 endpoints', j(DS.api_endpoints || [])],
    'src/': ['13 files', (C.files || []).map(f => f.path + '  — ' + f.description).join('\n')],
    'tests/': ['9 cases', (T.output || '') + '\n\n' + (T.cases || []).map(c => c.id + ' ' + c.name + ' ' + c.status.toUpperCase()).join('\n')],
    'review.md': ['3 findings', '# Review\n\n' + (RV.summary || '') + '\n\n' + (RV.findings || []).map(f => f.severity.toUpperCase() + '  ' + f.title).join('\n')],
    'README.md': ['setup + API docs', '# README\n\n' + (DC.overview || '') + '\n\n' + (DC.getting_started || '')]
  };
  const shelf = document.getElementById('p2Shelf');
  Object.entries(ART).forEach(([n, [s, body]]) => {
    const b = document.createElement('button'); b.className = 'p2-art'; b.innerHTML = esc(n) + '<small>' + esc(s) + '</small>';
    b.onclick = () => { document.getElementById('p2PName').textContent = n; document.getElementById('p2PBody').textContent = body || '(no sample content)'; document.getElementById('p2Prev').classList.add('on'); };
    shelf.appendChild(b);
  });

  // quality gate with rework demo
  const gate = document.getElementById('p2Gate'), gb = document.getElementById('p2GateBody'), fb = document.getElementById('p2Fail');
  const rows = a => a.map(([k, v, c]) => '<div class="row"><span>' + k + '</span><span class="st ' + (c || '') + '">' + v + '</span></div>').join('');
  function ok() { gate.className = 'fx-win p2-gate ok'; gb.innerHTML = rows([['Requirements', '✓'], ['Architecture', '✓'], ['Implementation', '✓'], ['Tests', '✓'], ['Consistency', '✓'], ['STATUS', 'READY', 'big']]); }
  ok();
  fb.onclick = async () => {
    fb.disabled = true; const w = ms => new Promise(r => setTimeout(r, RM ? 20 : ms));
    gate.className = 'fx-win p2-gate bad';
    gb.innerHTML = rows([['Implementation', '✓'], ['Tests', '✕'], ['Review', '◉ checking'], ['STATUS', 'REWORK REQUIRED', 'big']]); await w(1500);
    gb.innerHTML = rows([['Code Agent', '↻ returning to Code Agent...'], ['Tests', 'waiting'], ['Review', 'waiting'], ['STATUS', 'REWORK REQUIRED', 'big']]); await w(1800);
    gb.innerHTML = rows([['Code Agent', '✓ patched'], ['Tests', '◉ re-running'], ['Review', 'waiting'], ['STATUS', 'IN PROGRESS', 'big']]); await w(1600);
    ok(); fb.disabled = false;
  };
  document.getElementById('p2Go').onclick = () => { const l = document.getElementById('screenLanding'); scrollTo({ top: 0, behavior: RM ? 'auto' : 'smooth' }); setTimeout(() => { const t = document.getElementById('ideaInput'); t && t.focus(); }, RM ? 0 : 600); };
})();

/* ===== part 3: window canvas hero, question chips (auto-decide), tilt / magnetic / counters ===== */
(() => {
  'use strict';
  const RM = matchMedia('(prefers-reduced-motion:reduce)').matches;
  const land = document.getElementById('screenLanding'); if (!land) return;
  const sleep = ms => new Promise(r => setTimeout(r, RM ? 40 : ms));
  const esc = t => String(t).replace(/&/g, '&amp;').replace(/</g, '&lt;');
  const hl = t => esc(t).replace(/(PASS|✓)/g, '<i class=g>$1</i>').replace(/(FAIL|✕)/g, '<i class=r>$1</i>').replace(/(↻[^<]*)/, '<i class=y>$1</i>').replace(/^&gt;/, '<i class=y>&gt;</i>').replace(/([\w-]+\.(?:md|json|py)|src\/|tests\/)/g, '<i class=b>$1</i>');
  const mk = (h, c) => { const d = document.createElement('div'); d.className = c; d.innerHTML = h; return d; };
  const drag = w => {
    const bar = w.querySelector('.fx-bar'); let sx, sy, ox = 0, oy = 0, on = 0;
    bar.onpointerdown = e => { if (e.target.closest('button')) return; on = 1; sx = e.clientX - ox; sy = e.clientY - oy; bar.setPointerCapture(e.pointerId); };
    bar.onpointermove = e => { if (!on) return; ox = e.clientX - sx; oy = e.clientY - sy; w.style.transform = 'translate(' + ox + 'px,' + oy + 'px)'; };
    bar.onpointerup = () => on = 0;
  };

  // 1) more windows on the hero canvas: console loop, artifacts, quality gate
  const wC = mk('<div class="fx-bar"><span id="cvT">requirements.agent</span><em>sample loop · demo</em></div><div class="fx-body" id="cvL"></div>', 'fx-win fx-c');
  const wD = mk('<div class="fx-bar"><span>artifacts</span><em>click to open</em></div><div class="fx-body" id="cvA" style="padding:8px 10px"></div>', 'fx-win fx-d');
  const wE = mk('<div class="fx-bar"><span>quality-gate</span><em>demo</em></div><div class="fx-body fx-gate" id="cvG" style="counter-reset:none"></div>', 'fx-win fx-e');
  land.append(wC, wD, wE);[wC, wD, wE].forEach(drag);

  const S = [['requirements.agent', ['> analyzing product idea...', '> extracting actors...', '> generating user stories...', '✓ 12 requirements generated']],
  ['design.agent', ['> selecting architecture...', '> generating component graph...', '✓ 8 components, 6 APIs']],
  ['code.agent', ['> creating repository...', '> generating files...', '✓ 13 files written']],
  ['test.agent', ['> running pytest...', 'test_api_health ..... PASS', 'test_user_auth ...... FAIL', '✕ 1 test failed']],
  ['review.agent', ['> checking consistency...', '↻ rework: returning to Code Agent']],
  ['code.agent', ['> patching src/auth.py', '✓ 2 files updated']],
  ['test.agent', ['> running pytest...', 'test_user_auth ...... PASS', '✓ 42 tests executed']],
  ['documentation.agent', ['> generating README...', '✓ README generated']]];
  const L = wC.querySelector('#cvL'), T = wC.querySelector('#cvT');
  (async function loop() {
    for (; ;) for (const [f, ls] of S) {
      while (document.querySelector('.fx-console.on') || land.classList.contains('hidden') || document.hidden) await sleep(1500);
      T.textContent = f; L.innerHTML = '';
      for (const l of ls) { await sleep(650); const d = document.createElement('div'); d.innerHTML = hl(l); L.appendChild(d); }
      await sleep(900);
    }
  })();
  // artifacts open the preview built in part 2
  const A = wD.querySelector('#cvA');
  ['requirements.md', 'architecture.md', 'api-spec.json', 'src/', 'tests/', 'README.md'].forEach(n => {
    const b = document.createElement('button'); b.className = 'fx-art'; b.textContent = '▸ ' + n;
    b.onclick = () => { const t = [...document.querySelectorAll('.p2-art')].find(x => x.textContent.startsWith(n)); t && t.click(); };
    A.appendChild(b);
  });
  // quality gate cycles a pass and a rework
  const G = wE.querySelector('#cvG'), r = a => a.map(([k, v, c]) => '<div class="row"><span>' + k + '</span><span class="' + (c || '') + '">' + v + '</span></div>').join('');
  const GS = [r([['Requirements', '✓', 'ok'], ['Architecture', '✓', 'ok'], ['Implementation', '✓', 'ok'], ['Tests', '◉ running'], ['STATUS', 'IN PROGRESS']]),
  r([['Implementation', '✓', 'ok'], ['Tests', '✕', 'bad'], ['Review', '◉ checking'], ['STATUS', 'REWORK REQUIRED', 'bad']]),
  r([['Code Agent', '↻ returning...', 'bad'], ['Tests', 'waiting'], ['STATUS', 'REWORK REQUIRED', 'bad']]),
  r([['Requirements', '✓', 'ok'], ['Implementation', '✓', 'ok'], ['Tests', '✓', 'ok'], ['Consistency', '✓', 'ok'], ['STATUS', 'READY', 'ok']])];
  let gi = 0; G.innerHTML = GS[0]; if (!RM) setInterval(() => { gi = (gi + 1) % GS.length; G.innerHTML = GS[gi]; }, 2600);

  // 2) question chips: all optional, "auto" is always the default
  const Q = { Platform: ['Web', 'Mobile', 'Both', 'Auto-detect'], Scope: ['Prototype', 'MVP', 'Production', 'Let AI decide'], Auth: ['Yes', 'No', 'Recommend'] };
  const pick = { Platform: 'Auto-detect', Scope: 'Let AI decide', Auth: 'Recommend' };
  const auto = { Platform: 'Auto-detect', Scope: 'Let AI decide', Auth: 'Recommend' };
  const anchor = land.querySelector('.ic-examples');
  if (anchor) {
    const wrap = mk('', 'q-wrap');
    Object.keys(Q).forEach(k => {
      const row = mk('<span>' + k + '</span>', 'q-row'); row.setAttribute('role', 'radiogroup'); row.setAttribute('aria-label', k);
      Q[k].forEach(o => {
        const b = document.createElement('button'); b.type = 'button'; b.className = 'q-chip'; b.textContent = o; b.setAttribute('role', 'radio'); b.setAttribute('aria-checked', o === pick[k]);
        b.onclick = () => { pick[k] = o; row.querySelectorAll('.q-chip').forEach(x => x.setAttribute('aria-checked', x === b)); }; row.appendChild(b);
      });
      wrap.appendChild(row);
    });
    wrap.appendChild(mk('Optional. Leave as is and the agents decide.', 'q-note'));
    anchor.after(wrap);
    // adds only the choices you changed to the idea text before app.js sends it (API shape unchanged)
    document.addEventListener('click', e => {
      if (!e.target.closest('#launchBtn')) return;
      const ta = document.getElementById('ideaInput'); if (!ta || !ta.value.trim() || ta.value.includes('[Preferences:')) return;
      const ch = Object.keys(pick).filter(k => pick[k] !== auto[k]).map(k => k + ': ' + pick[k]);
      if (ch.length) ta.value = ta.value.trim() + '\n[Preferences: ' + ch.join('; ') + ']';
    }, true);
  }

  // 3) micro-interactions: tilt, magnetic buttons, counters
  if (!RM) {
    document.addEventListener('pointermove', e => {
      const c = e.target.closest && e.target.closest('.hiw-card,.p2-art'); if (!c) return;
      const b = c.getBoundingClientRect(); c.style.setProperty('--ry', ((e.clientX - b.left) / b.width - .5) * 6 + 'deg'); c.style.setProperty('--rx', (.5 - (e.clientY - b.top) / b.height) * 6 + 'deg');
    });
    document.addEventListener('pointerout', e => { const c = e.target.closest && e.target.closest('.hiw-card,.p2-art'); if (c) { c.style.setProperty('--rx', '0deg'); c.style.setProperty('--ry', '0deg'); } });
    document.addEventListener('pointermove', e => {
      const m = e.target.closest && e.target.closest('#launchBtn,.p2-btn'); if (!m || m.disabled) return;
      const b = m.getBoundingClientRect(); m.style.transform = 'translate(' + (e.clientX - b.left - b.width / 2) * .08 + 'px,' + (e.clientY - b.top - b.height / 2) * .18 + 'px)';
    });
    document.addEventListener('pointerout', e => { const m = e.target.closest && e.target.closest('#launchBtn,.p2-btn'); if (m) m.style.transform = ''; });
    land.querySelectorAll('.lst-val').forEach(el => {
      const n = parseInt(el.textContent, 10), sfx = el.textContent.replace(/[0-9]/g, ''); if (!n) return; let t0 = null;
      const step = ts => { t0 = t0 || ts; const p = Math.min((ts - t0) / 1200, 1); el.textContent = Math.round(n * (1 - Math.pow(1 - p, 3))) + sfx; p < 1 && requestAnimationFrame(step); }; requestAnimationFrame(step);
    });
  }
})();

/* ===== part 5: hero is one clean full screen; idea input + running code live in a sandbox screen below ===== */
(() => {
  'use strict';
  const land = document.getElementById('screenLanding'), card = document.getElementById('ideaCard'); if (!land || !card) return;
  const sb = document.createElement('section'); sb.id = 'sandbox'; sb.className = 'sb';
  sb.innerHTML = '<p class="sb-cap">sandbox · describe an idea, watch the agents work</p><div class="sb-canvas" id="sbCanvas"></div>';
  land.appendChild(sb);
  const cv = sb.querySelector('#sbCanvas');
  // idea input becomes a window (same DOM node, so #ideaInput / #launchBtn keep working with app.js)
  const w = document.createElement('div'); w.className = 'fx-win sb-idea';
  w.innerHTML = '<div class="fx-bar"><span>studio.idea</span><em>ready</em></div>';
  w.appendChild(card); cv.appendChild(w);
  [['.fx-c'], ['.fx-b'], ['.fx-d'], ['.fx-e'], ['.fx-a']].forEach(([s]) => { const e = land.querySelector(':scope > ' + s); if (e) cv.appendChild(e); });
  // draggable idea window
  (() => {
    const bar = w.querySelector('.fx-bar'); let sx, sy, ox = 0, oy = 0, on = 0;
    bar.onpointerdown = e => { on = 1; sx = e.clientX - ox; sy = e.clientY - oy; bar.setPointerCapture(e.pointerId); };
    bar.onpointermove = e => { if (!on) return; ox = e.clientX - sx; oy = e.clientY - sy; w.style.transform = 'translate(' + ox + 'px,' + oy + 'px)'; };
    bar.onpointerup = () => on = 0;
  })();
  // hero cue
  const body = land.querySelector('.landing-body');
  if (body) {
    const a = document.createElement('a'); a.className = 'sb-cta'; a.href = '#sandbox'; a.textContent = 'Start building ↓'; body.appendChild(a);
    a.onclick = e => { e.preventDefault(); sb.scrollIntoView({ behavior: matchMedia('(prefers-reduced-motion:reduce)').matches ? 'auto' : 'smooth' }); setTimeout(() => { const t = document.getElementById('ideaInput'); t && t.focus({ preventScroll: true }); }, 700); };
  }
  new IntersectionObserver((es, o) => es[0].isIntersecting && (sb.classList.add('in'), o.disconnect()), { threshold: .15 }).observe(sb);
})();

/* ===== part 8: typewriter headline (text is exactly: "Turn your / idea into / a product.") ===== */
(() => {
  'use strict';
  const h = document.querySelector('.landing-heading'); if (!h) return;
  const lines = [...h.querySelectorAll('.lh-line')]; if (!lines.length) return;
  h.setAttribute('aria-label', lines.map(l => l.textContent.trim()).join(' '));   // screen readers get the full sentence at once
  if (matchMedia('(prefers-reduced-motion:reduce)').matches) return;              // reduced motion: show the text as is
  const texts = lines.map(l => l.textContent.trim());
  const typed = lines.map((l, i) => {
    l.innerHTML = '';
    const wrap = document.createElement('span'); wrap.className = 'tw-wrap'; wrap.setAttribute('aria-hidden', 'true');
    const ghost = document.createElement('span'); ghost.className = 'tw-ghost'; ghost.textContent = texts[i];
    const t = document.createElement('span'); t.className = 'tw-type';
    wrap.append(ghost, t); l.appendChild(wrap); return t;
  });
  const caret = document.createElement('span'); caret.className = 'tw-caret';
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  (async () => {
    await sleep(350);
    for (let i = 0; i < texts.length; i++) {
      typed[i].appendChild(caret);
      for (let c = 1; c <= texts[i].length; c++) {
        typed[i].firstChild && typed[i].firstChild.nodeType === 3 ? typed[i].firstChild.nodeValue = texts[i].slice(0, c) : typed[i].insertBefore(document.createTextNode(texts[i].slice(0, c)), caret);
        await sleep(60 + Math.random() * 70);
      }
      await sleep(i < texts.length - 1 ? 260 : 0);
    }
  })();
})();

/* ===== part 9: floating artifacts around the hero (decorative; parallax + occasional glow) ===== */
(() => {
  'use strict';
  const land = document.getElementById('screenLanding'); if (!land) return;
  const RM = matchMedia('(prefers-reduced-motion:reduce)').matches;
  const esc = t => String(t).replace(/&/g, '&amp;').replace(/</g, '&lt;');
  const hl = t => esc(t).replace(/(PASS|✓)/g, '<i class=g>$1</i>').replace(/^&gt;/, '<i class=y>&gt;</i>').replace(/(\d+)/g, '<i class=p>$1</i>');
  const DEF = [
    ['hf1', 'requirements.agent', ['> extracting user stories', '✓ 12 requirements'], .6],
    ['hf2', 'design.agent', ['> generating component graph', '✓ 8 components, 6 APIs'], 1],
    ['hf3', 'test.agent', ['test_auth ..... PASS', '✓ 42 tests executed'], .8],
    ['hf4', 'review.agent', ['> checking consistency', '✓ quality gate passed'], 1.2]
  ];
  const items = DEF.map(([c, t, ls, d]) => {
    const el = document.createElement('div'); el.className = 'hf ' + c; el.setAttribute('aria-hidden', 'true'); el.dataset.d = d;
    el.innerHTML = '<div class="fx-win"><div class="fx-bar"><span>' + t + '</span></div><div class="fx-body" style="padding:8px 11px">' + ls.map(l => '<div>' + hl(l) + '</div>').join('') + '</div></div>';
    land.appendChild(el); return el;
  });
  if (RM) return;
  let tx = 0, ty = 0, cx = 0, cy = 0;
  addEventListener('pointermove', e => { tx = e.clientX / innerWidth - .5; ty = e.clientY / innerHeight - .5; });
  (function tick() {
    cx += (tx - cx) * .06; cy += (ty - cy) * .06;
    items.forEach(el => { const d = +el.dataset.d; el.style.transform = 'translate(' + (cx * -26 * d).toFixed(1) + 'px,' + (cy * -20 * d).toFixed(1) + 'px)'; });
    requestAnimationFrame(tick);
  })();
  setInterval(() => { if (document.hidden || land.classList.contains('hidden')) return; const w = items[Math.floor(Math.random() * items.length)].querySelector('.fx-win'); w.classList.add('lit'); setTimeout(() => w.classList.remove('lit'), 1400); }, 2600);
})();

/* ===== part 10: palette picker (accent + glow lights), saved in localStorage ===== */
(() => {
  'use strict';
  const root = document.documentElement;
  // [name, dark-mode colour, light-mode colour] — hues follow the code-editor palette idea
  const P = [['code-green', '#2fd18f', '#0f9d6b'], ['code-blue', '#5a82e8', '#3557c9'], ['code-red', '#e0606e', '#c23b4a'], ['code-yellow', '#dcb85f', '#a67a12'], ['code-purple', '#8461e4', '#6a44d0'], ['code-aqua', '#9ed3f7', '#2b86c5']];
  const rgb = h => [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16)).join(',');
  let cur = 0, glow = true;
  try { cur = Math.min(P.length - 1, Math.max(0, +localStorage.getItem('itp-pal') || 0)); glow = localStorage.getItem('itp-glow') !== '0'; } catch (e) { }
  function apply() {
    const c = root.dataset.theme === 'light' ? P[cur][2] : P[cur][1], r = rgb(c), s = root.style;
    s.setProperty('--accent', c); s.setProperty('--accent-rgb', r);
    s.setProperty('--accent-dim', 'rgba(' + r + ',.12)'); s.setProperty('--accent-glow', 'rgba(' + r + ',.25)'); s.setProperty('--fx-glow', 'rgba(' + r + ',' + (root.dataset.theme === 'light' ? .22 : .16) + ')');
    document.querySelectorAll('.pal .sw').forEach((b, i) => b.setAttribute('aria-checked', i === cur));
    document.body.classList.toggle('no-glow', !glow);
    const g = document.querySelector('.pal .gl'); g && g.setAttribute('aria-pressed', glow);
  }
  const bar = document.createElement('div'); bar.className = 'pal'; bar.setAttribute('role', 'radiogroup'); bar.setAttribute('aria-label', 'Accent colour');
  P.forEach((p, i) => {
    const b = document.createElement('button'); b.className = 'sw'; b.style.setProperty('--c', p[1]); b.title = p[0]; b.setAttribute('role', 'radio'); b.setAttribute('aria-label', p[0]);
    b.onclick = () => { cur = i; try { localStorage.setItem('itp-pal', i); } catch (e) { } apply(); }; bar.appendChild(b);
  });
  const gl = document.createElement('button'); gl.className = 'gl'; gl.textContent = 'glow'; gl.setAttribute('aria-label', 'Toggle glow lights');
  gl.onclick = () => { glow = !glow; try { localStorage.setItem('itp-glow', glow ? '1' : '0'); } catch (e) { } apply(); };
  bar.appendChild(gl); document.body.appendChild(bar);
  ['a', 'b'].forEach(k => { const o = document.createElement('div'); o.className = 'pal-orb ' + k; o.setAttribute('aria-hidden', 'true'); document.body.appendChild(o); });
  new MutationObserver(apply).observe(root, { attributes: true, attributeFilter: ['data-theme'] });
  apply();
})();
