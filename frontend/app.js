/* ─────────────────────────────────────────────────
   IdeaToProduct — app.js
   E2E Antigrav Editorial Frontend
   ─────────────────────────────────────────────────
   API Contract (preserved from server.py):
   POST /api/start        { idea, project_id? }  → { session_id, project_id, status }
   GET  /api/status/:sid                          → { session_id, project_id, is_running, status, stage, error, result }
   POST /api/answer        { session_id, answers[] } → { status:"resumed", session_id }

   Status values: running | clarification | done | error
   Pipeline stages: requirement → design → code → test → review → documentation (→ release)
   ───────────────────────────────────────────────── */
'use strict';

/* ── Config ──────────────────────────────── */
const API = (window.location.origin && window.location.origin.startsWith('http'))
  ? window.location.origin
  : 'http://localhost:8000';

/* ── State ───────────────────────────────── */
const State = {
  sessionId: null,
  projectId: null,
  projectName: 'Untitled',
  idea: '',
  githubRepo: '',
  currentView: 'overview',
  pollTimer: null,
  isLive: false,
  pipelineData: null,
  activityLog: [],
  startTime: null,
};

/* ── DOM refs ────────────────────────────── */
const $ = id => document.getElementById(id);

/* ── Stage definitions (matches graph.py nodes) ── */
const STAGE_DEFS = [
  { id: 'requirement',    label: 'Requirements',  desc: 'Analyzes the idea, extracts scope, generates user stories and functional requirements.' },
  { id: 'design',         label: 'Design',        desc: 'Maps architecture from requirements, defines components and API contracts.' },
  { id: 'code',           label: 'Code',           desc: 'Generates repository scaffold, source files, and dependencies.' },
  { id: 'test',           label: 'Tests',          desc: 'Runs test suite against generated code, reports pass/fail.' },
  { id: 'review',         label: 'Review',         desc: 'Evaluates quality, consistency, and identifies findings.' },
  { id: 'documentation',  label: 'Docs',           desc: 'Generates README, API reference, and setup documentation.' },
];

/* ── Model configuration (read from backend imports.py) ── */
const MODEL_CONFIG = {
  requirement:    { provider: 'Ollama', model: 'qwen2.5-coder:7b', role: 'Requirement analysis & scope extraction' },
  design:         { provider: 'Ollama', model: 'qwen2.5-coder:7b', role: 'Architecture & component design' },
  code:           { provider: 'Ollama', model: 'qwen2.5-coder:7b', role: 'Code generation & repository scaffold' },
  test:           { provider: 'Ollama', model: 'qwen2.5-coder:7b', role: 'Test generation & execution' },
  review:         { provider: 'Ollama', model: 'qwen2.5-coder:7b', role: 'Quality review & approval gate' },
  documentation:  { provider: 'Ollama', model: 'qwen2.5-coder:7b', role: 'Documentation & README generation' },
};

/* ═════════════════════════════════════════════════
   1. BOOT
═════════════════════════════════════════════════ */
document.addEventListener('DOMContentLoaded', () => {
  navScrollEffect();
  wireCharCount();
  wireModelConfigButtons();
  wireMobileMenu();
  wireSidebarResize();
});

function navScrollEffect() {
  const nav = $('mainNav');
  if (!nav) return;
  window.addEventListener('scroll', () => {
    nav.classList.toggle('scrolled', window.scrollY > 30);
  }, { passive: true });
}

function wireCharCount() {
  const ta = $('ideaInput');
  const cc = $('charCount');
  if (!ta || !cc) return;
  ta.addEventListener('input', () => {
    cc.textContent = ta.value.length;
  });
}

function wireModelConfigButtons() {
  const btn1 = $('navModelCfgBtn');
  const btn2 = $('navModelCfgBtn2');
  if (btn1) btn1.addEventListener('click', openModelConfig);
  if (btn2) btn2.addEventListener('click', openModelConfig);
}

function wireMobileMenu() {
  const toggle = $('mobileMenuToggle');
  const sidebar = $('studioSidebar');
  const overlay = $('mobileSidebarOverlay');
  if (!toggle) return;

  toggle.addEventListener('click', () => {
    const isOpen = sidebar.classList.contains('open');
    sidebar.classList.toggle('open', !isOpen);
    overlay.classList.toggle('hidden', isOpen);
  });

  if (overlay) {
    overlay.addEventListener('click', () => {
      sidebar.classList.remove('open');
      overlay.classList.add('hidden');
    });
  }

}

function wireSidebarResize() {
  const handle = $('sidebarResizeHandle');
  if (!handle) return;
  handle.addEventListener('pointerdown', event => {
    if (window.innerWidth <= 800) return;
    handle.setPointerCapture(event.pointerId);
    const move = moveEvent => {
      const width = Math.max(190, Math.min(420, moveEvent.clientX));
      document.documentElement.style.setProperty('--sb-w', `${width}px`);
    };
    const stop = () => {
      handle.removeEventListener('pointermove', move);
      handle.removeEventListener('pointerup', stop);
    };
    handle.addEventListener('pointermove', move);
    handle.addEventListener('pointerup', stop);
  });
}

/* ═════════════════════════════════════════════════
   2. IDEA INPUT
═════════════════════════════════════════════════ */
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
    State.idea = idea;
    State.projectName = deriveProjectName(idea);
    State.isLive = true;
    State.pipelineData = null;
    State.activityLog = [];
    State.startTime = Date.now();

    addActivity('System', 'Pipeline started', `Session ${data.session_id.slice(0, 8)}…`);

    enterStudio(State.projectName, 'running');
    startPolling();

  } catch (err) {
    if (btn) btn.disabled = false;
    if (label) label.textContent = 'Start building';
    alert('Could not connect to pipeline: ' + err.message);
  }
};

function deriveProjectName(idea) {
  const words = idea.split(' ').slice(0, 4).join(' ');
  return words.length > 30 ? words.slice(0, 30) + '…' : words;
}

/* ═════════════════════════════════════════════════
   4. ENTER / EXIT STUDIO
═════════════════════════════════════════════════ */
function enterStudio(name, status) {
  // Switch nav
  $('navLanding')?.classList.add('hidden');
  $('navStudio')?.classList.remove('hidden');
  $('studioProjectName').textContent = name;
  $('mobileMenuToggle')?.classList.remove('hidden');
  setNavPipelineStatus(status);

  // Show studio, hide landing
  $('screenLanding')?.classList.add('hidden');
  $('screenStudio')?.classList.remove('hidden');

  // Set up sidebar
  $('sbProjName').textContent = name;
  setSbStatus(status);

  // Build sidebar stages and empty overview
  if (State.isLive) {
    buildPipelineStages([]);
    buildActivityFeed([]);
    renderOverview(null);
  } else {
    buildPipelineStages(MockData.pipeline);
    buildActivityFeed(MockData.activity);
    renderOverview(MockData);
  }

  switchView('overview');
  window.scrollTo(0, 0);
}

window.exitStudio = function () {
  clearInterval(State.pollTimer);
  State.sessionId = null;
  State.isLive = false;
  State.pipelineData = null;

  $('navStudio')?.classList.add('hidden');
  $('navLanding')?.classList.remove('hidden');
  $('screenStudio')?.classList.add('hidden');
  $('screenLanding')?.classList.remove('hidden');
  $('mobileMenuToggle')?.classList.add('hidden');

  const btn = $('launchBtn');
  const label = $('launchBtnLabel');
  if (btn) btn.disabled = false;
  if (label) label.textContent = 'Start building';

  // Clear rendered flags so views re-render on next entry
  document.querySelectorAll('.studio-view').forEach(el => {
    delete el.dataset.rendered;
    if (el.id !== 'view-overview') el.innerHTML = '';
  });
};

/* ═════════════════════════════════════════════════
   5. POLLING (real backend)
═════════════════════════════════════════════════ */
function startPolling() {
  clearInterval(State.pollTimer);
  State.pollTimer = setInterval(pollStatus, 2500);
  pollStatus(); // immediate first poll
}

async function pollStatus() {
  if (!State.sessionId) return;
  try {
    const res = await fetch(`${API}/api/status/${State.sessionId}`);
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    handlePollResult(data);
  } catch (e) { /* transient — keep polling */ }
}


function handlePollResult(data) {
  // Render any real outputs that are already available,
  // even while the pipeline is still running.
  const result = data.result;

  if (result && typeof result === 'object') {
    State.pipelineData = result;
    populateLiveViews(result);
  }

  // Pipeline is still running: keep polling.
  if (data.is_running) {
    const stage = data.stage || 'requirements';
    updateLiveStage(stage);
    setNavPipelineStatus('running');
    setSbStatus('running');
    return;
  }

  // Pipeline stopped: stop polling.
  clearInterval(State.pollTimer);

  if (data.status === 'error') {
    showPipelineError(data.error || 'Unknown error.');
    addActivity('System', 'Error', data.error || 'Pipeline stopped');
    return;
  }

  if (data.status === 'clarification') {
    addActivity(
      'Requirement Agent',
      'Clarification needed',
      'Waiting for user input'
    );
    setNavPipelineStatus('paused');
    setSbStatus('paused');
    showClarifyOverlay(
      data.result?.clarification_questions || []
    );
    return;
  }

  // Pipeline finished successfully.
  State.pipelineData = data.result;
  completePipeline(data.result);
}


function updateLiveStage(stage) {
  const idx = STAGE_DEFS.findIndex(s => s.id === stage || s.id === stage.replace(/s$/, ''));
  if (idx < 0) return;

  STAGE_DEFS.forEach((def, i) => {
    const el = document.querySelector(`.sb-stage-item[data-stage="${def.id}"]`);
    if (!el) return;
    el.classList.remove('active', 'done');
    if (i < idx) el.classList.add('done');
    else if (i === idx) el.classList.add('active');
  });
}

function completePipeline(result) {
  setNavPipelineStatus('done');
  setSbStatus('done');
  addActivity('System', 'Pipeline complete', 'All stages finished');

  if (result) {
    const stage = result.current_stage || 'documentation';
    updateSidebarStages(stage, result);
    populateLiveViews(result);

    // Re-render overview with completion info
    renderOverview(result);
  }
}

function populateLiveViews(result) {
  // Clear rendered flags to force re-render with real data
  document.querySelectorAll('.studio-view').forEach(el => {
    delete el.dataset.rendered;
  });

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
  if (result.token_usage)
    renderTokenUsageView(result.token_usage);
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
    return ["Modern Dark Theme", "Sleek Minimalist", "Mobile Responsive", "High Contrast"];
  }
  if (t.includes('platform') || t.includes('deploy') || t.includes('target') || t.includes('device')) {
    return ["Web Application", "Mobile (iOS / Android)", "Desktop App", "CLI Tool", "Cloud / Docker"];
  }
  if (t.includes('api') || t.includes('backend') || t.includes('architecture') || t.includes('protocol')) {
    return ["RESTful API", "GraphQL API", "WebSocket Realtime", "Serverless Functions"];
  }
  return ["Standard Best Practice", "Minimal MVP", "Production & Scalable", "Security First"];
}

function showClarifyOverlay(questions) {
  const overlay = $('clarifyOverlay');
  const cont = $('cmQuestions');
  if (!overlay || !cont) return;
  cont.innerHTML = '';
  const visibleQuestions = Array.isArray(questions) && questions.length
    ? questions
    : ['What is the primary user workflow or outcome this product must support?'];

  visibleQuestions.forEach((q, i) => {
    const qText = typeof q === 'string' ? q : (q.question || q.text || 'Clarification Question');
    const presets = (Array.isArray(q.options) && q.options.length) ? q.options : getQuestionPresetOptions(qText);

    const div = document.createElement('div');
    div.className = 'cq-item';
    div.dataset.cqIndex = i;

    let optionsHtml = presets.map((opt) => `
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
      <div class="cq-subtitle">Select options or type custom details:</div>
      <div class="cq-chips-container" id="cq-chips-${i}">
        ${optionsHtml}
      </div>
      <div class="cq-custom-chip-row">
        <input type="text" class="cq-custom-chip-input" id="cq-custom-chip-in-${i}"
          placeholder="+ Add custom option…"
          onkeydown="if(event.key==='Enter'){event.preventDefault();addCustomCqChip(${i});}" />
        <button type="button" class="cq-add-chip-btn" onclick="addCustomCqChip(${i})">+ Add</button>
      </div>
      <div class="cq-input-wrapper">
        <textarea id="cq-${i}" class="cq-textarea" rows="2"
          placeholder="Additional context (optional)…"></textarea>
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
  btn.className = 'cq-chip selected';
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

  items.forEach((item) => {
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

  $('clarifyOverlay')?.classList.add('hidden');
  addActivity('User', 'Answered clarification', `${answers.length} response(s) submitted`);

  try {
    const res = await fetch(`${API}/api/answer`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: State.sessionId, answers }),
    });
    if (!res.ok) throw new Error(await res.text());

    setNavPipelineStatus('running');
    setSbStatus('running');
    startPolling();
  } catch (err) {
    showPipelineError(err.message);
  }
};

window.skipClarification = async function () {
  $('clarifyOverlay')?.classList.add('hidden');
  addActivity('User', 'Skipped clarification', 'Using standard defaults');

  try {
    const res = await fetch(`${API}/api/answer`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: State.sessionId,
        answers: ["skip (proceed with standard architectural defaults)"]
      }),
    });
    if (!res.ok) throw new Error(await res.text());

    setNavPipelineStatus('running');
    setSbStatus('running');
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
  const indicator = $('navStatusIndicator');
  const statusMap = {
    running: 'Running',
    done: 'Complete',
    error: 'Error',
    paused: 'Needs input',
  };
  if (label) label.textContent = statusMap[status] || 'Initializing';
  if (indicator) {
    indicator.className = 'status-indicator ' + status;
  }
}

function setSbStatus(status) {
  const dot = $('sbStatusDot');
  const label = $('sbStatusLabel');
  if (!dot || !label) return;
  const statusMap = {
    running: 'Building',
    done: 'Complete',
    error: 'Error',
    paused: 'Needs input',
  };
  dot.className = 'status-indicator ' + status;
  label.textContent = statusMap[status] || 'Initializing';
}

/* ═════════════════════════════════════════════════
   8. SIDEBAR PIPELINE STAGES
═════════════════════════════════════════════════ */
function buildPipelineStages(pipelineArr) {
  const cont = $('sbPipelineStages');
  if (!cont) return;
  cont.innerHTML = '';

  const statusMap = {};
  (pipelineArr || []).forEach(s => { statusMap[s.id] = s.status; });

  STAGE_DEFS.forEach(def => {
    const st = statusMap[def.id] || 'queued';
    const btn = document.createElement('button');
    btn.className = 'sb-stage-item' +
      (st === 'running' ? ' active' : '') +
      (st === 'done' ? ' done' : '');
    btn.dataset.stage = def.id;
    btn.type = 'button';
    btn.onclick = () => switchView(def.id);
    btn.innerHTML = `<span class="sb-stage-dot"></span>${escHtml(def.label)}`;
    cont.appendChild(btn);
  });
}

function updateSidebarStages(lastStage, result) {
  // Map stage names — backend uses "requirements" but stage id is "requirement"
  let mappedStage = lastStage;
  if (lastStage === 'requirements') mappedStage = 'requirement';

  const idx = STAGE_DEFS.findIndex(s => s.id === mappedStage);

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
function addActivity(agent, event, detail) {
  const now = new Date();
  const time = now.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false });
  State.activityLog.unshift({ time, agent, event, detail });
  buildActivityFeed(State.activityLog.slice().reverse());
}

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

  // Close mobile sidebar
  $('studioSidebar')?.classList.remove('open');
  $('mobileSidebarOverlay')?.classList.add('hidden');

  // Update sidebar highlight
  document.querySelectorAll('.sb-item, .sb-stage-item').forEach(el => {
    const matches = el.dataset.view === viewId || el.dataset.stage === viewId;
    el.classList.toggle('active', matches);
  });

  // Show/hide view panels
  document.querySelectorAll('.studio-view').forEach(el => {
    el.classList.toggle('hidden', el.id !== 'view-' + viewId);
  });

  renderViewIfNeeded(viewId);
};

function renderViewIfNeeded(viewId) {
  const el = $('view-' + viewId);
  if (!el || el.dataset.rendered) return;

  const d = State.pipelineData;
  const mock = window.MockData || {};

  switch (viewId) {
    case 'overview':
      renderOverview(d || null);
      break;
    case 'requirement':
      if (d?.requirements && Object.keys(d.requirements).length) {
        renderRequirementsView(d.requirements);
      } else if (!State.isLive && mock.requirements) {
        renderRequirementsView(mock.requirements);
      } else {
        renderEmptyView(el, 'Requirements', 'Requirements will appear once the requirement agent completes.');
      }
      break;
    case 'design':
      if (d?.design && Object.keys(d.design).length) {
        renderDesignView(d.design);
      } else if (!State.isLive && mock.design) {
        renderDesignView(mock.design);
      } else {
        renderEmptyView(el, 'Design', 'Architecture and component design will appear once the design agent completes.');
      }
      break;
    case 'code':
      if (d?.code && Object.keys(d.code).length) {
        renderCodeView(d.code);
      } else if (!State.isLive && mock.code) {
        renderCodeView(mock.code);
      } else {
        renderEmptyView(el, 'Code', 'Generated repository will appear once the code agent completes.');
      }
      break;
    case 'test':
      if (d?.test_results && Object.keys(d.test_results).length) {
        renderTestsView(d.test_results);
      } else if (!State.isLive && mock.tests) {
        renderTestsView(mock.tests);
      } else {
        renderEmptyView(el, 'Tests', 'Test results will appear once the test agent completes.');
      }
      break;
    case 'review':
      if (d?.review && Object.keys(d.review).length) {
        renderReviewView(d.review, d.approval_status);
      } else if (!State.isLive && mock.review) {
        renderReviewView(mock.review, mock.review.approval_status);
      } else {
        renderEmptyView(el, 'Review', 'Quality review will appear once the review agent completes.');
      }
      break;
    case 'documentation':
      if (d?.documentation && Object.keys(d.documentation).length) {
        renderDocsView(d.documentation);
      } else if (!State.isLive && mock.documentation) {
        renderDocsView(mock.documentation);
      } else {
        renderEmptyView(el, 'Documentation', 'Documentation will appear once the documentation agent completes.');
      }
      break;
    case 'usage':
      renderTokenUsageView(d?.token_usage || {});
      break;
    case 'artifacts':
      if (d) {
        renderArtifactsViewLive(d);
      } else if (!State.isLive && mock.artifacts) {
        renderArtifactsView(mock.artifacts);
      } else {
        renderEmptyView(el, 'Artifacts', 'Artifacts will appear as the pipeline produces outputs.');
      }

      break;
    case 'models':
        renderModelsView();
        break;
      case 'github':
        renderGitHubView();
        break;
  }
  el.dataset.rendered = '1';
}

function renderTokenUsageView(usage) {
  const el = $('view-usage');
  if (!el) return;
  const entries = Object.entries(usage || {});
  const total = entries.reduce((sum, [, item]) => sum + (item.total_tokens || 0), 0);
  el.innerHTML = `
    <div class="view-hd">
      <div class="view-breadcrumb">Project</div>
      <div class="view-title">Token Usage</div>
      <div class="view-sub">LLM usage is updated after each agent completes.</div>
    </div>
    <div class="ov-grid">
      <div class="ov-card">
        <div class="ov-card-label">Total Tokens</div>
        <div class="ov-card-val">${total.toLocaleString()}</div>
        <div class="ov-card-sub">All completed agents</div>
      </div>
      <div class="ov-card">
        <div class="ov-card-label">Agents Completed</div>
        <div class="ov-card-val">${entries.length} / ${STAGE_DEFS.length}</div>
        <div class="ov-card-sub">Usage appears stage by stage</div>
      </div>
    </div>
    <div class="sec">
      <div class="sec-title">Usage by Agent</div>
      <div class="token-usage-table">
        ${STAGE_DEFS.map(def => {
          const item = usage[def.id];
          return `<div class="token-row">
            <div class="token-agent">${escHtml(def.label)}</div>
            <div class="token-model">${escHtml(item?.model || 'Waiting')}</div>
            <div class="token-value">${item ? `${(item.total_tokens || 0).toLocaleString()} total` : 'Not completed'}</div>
            <div class="token-detail">${item ? `${(item.input_tokens || 0).toLocaleString()} in · ${(item.output_tokens || 0).toLocaleString()} out · ${item.calls || 0} call${item.calls === 1 ? '' : 's'}` : '—'}</div>
          </div>`;
        }).join('')}
      </div>
    </div>
  `;
  el.dataset.rendered = '1';
}

function renderEmptyView(el, title, message) {
  el.innerHTML = `
    <div class="view-hd">
      <div class="view-breadcrumb">Pipeline</div>
      <div class="view-title">${escHtml(title)}</div>
    </div>
    <div class="empty-state">
      <div class="empty-state-icon">○</div>
      <div class="empty-state-title">No data yet</div>
      <div class="empty-state-sub">${escHtml(message)}</div>
    </div>
  `;
}

/* ═════════════════════════════════════════════════
   11. VIEW RENDERERS
═════════════════════════════════════════════════ */

/* ── Overview ─────────────────────────────── */
function renderOverview(data) {
  const el = $('view-overview');
  if (!el) return;

  const mock = window.MockData || {};
  const isComplete = State.isLive && State.pipelineData;
  const elapsed = State.startTime ? formatElapsed(Date.now() - State.startTime) : '—';
  const requirements = State.pipelineData?.requirements || {};
  const problemStatement = requirements.problem_statement
    || (State.isLive ? State.idea : '')
    || 'Your submitted idea will appear here while requirements are generated.';

  // Determine pipeline stages display
  let pipeline;
  if (State.isLive && State.pipelineData) {
    // Build from real result
    const result = State.pipelineData;
    const lastStageId = (result.current_stage || 'documentation').replace(/s$/, '');
    const lastIdx = STAGE_DEFS.findIndex(s => s.id === lastStageId);
    pipeline = STAGE_DEFS.map((def, i) => ({
      ...def,
      status: i <= (lastIdx >= 0 ? lastIdx : STAGE_DEFS.length - 1) ? 'done' : 'queued',
    }));
  } else if (!State.isLive && mock.pipeline) {
    pipeline = mock.pipeline.map(p => ({ ...p }));
  } else {
    pipeline = STAGE_DEFS.map(def => ({ ...def, status: 'queued' }));
  }

  // Current stage label
  let currentStageName = '—';
  if (State.isLive && !State.pipelineData) {
    currentStageName = 'Processing…';
  } else if (State.pipelineData) {
    const cs = State.pipelineData.current_stage || 'documentation';
    const def = STAGE_DEFS.find(s => s.id === cs || s.id === cs.replace(/s$/, ''));
    currentStageName = def ? def.label + ' (Complete)' : cs;
  } else if (!State.isLive && mock.project) {
    currentStageName = agentLabel(mock.project.currentAgent);
  }

  el.innerHTML = `
    <div class="view-hd">
      <div class="view-breadcrumb">Project</div>
      <div class="view-title">Project Overview</div>
      <div class="view-sub">${State.isLive
        ? (isComplete ? 'Pipeline complete. Review the outputs below.' : 'Pipeline is running…')
        : 'Demo mode — showing sample data.'}</div>
    </div>

    <div class="ov-problem-card">
        <div class="ov-card-label">Problem Statement</div>
        <div class="ov-problem-text">${escHtml(problemStatement)}</div>
        ${requirements.problem_statement ? '' : '<div class="ov-card-sub">Based on your submitted idea; the Requirements Agent will refine it.</div>'}
    </div>

    ${isComplete ? `
      <div class="done-card">
        <div class="done-card-label">Pipeline Complete</div>
        <div class="done-card-title">All stages finished successfully</div>
        <div class="done-card-sub">Navigate the sidebar to inspect requirements, design, code, tests, review, and documentation.</div>
      </div>
    ` : ''}

    <div class="ov-grid">
      <div class="ov-card">
        <div class="ov-card-label">Current Stage</div>
        <div class="ov-card-val">${escHtml(currentStageName)}</div>
        <div class="ov-card-sub">${State.isLive ? 'Live pipeline' : 'Demo data'}</div>
      </div>
      <div class="ov-card">
        <div class="ov-card-label">Elapsed</div>
        <div class="ov-card-val">${escHtml(State.isLive ? elapsed : (mock.project?.elapsed || '—'))}</div>
        <div class="ov-card-sub">Session ${State.sessionId ? State.sessionId.slice(0, 8) + '…' : '—'}</div>
      </div>
    </div>

    <div class="sec">
      <div class="sec-title">Pipeline</div>
      <div class="pipeline-flow">
        ${pipeline.map((s, i) => `
          <div class="pf-stage ${s.status || 'queued'}">
            <div class="pf-track">
              <div class="pf-dot"></div>
              ${i < pipeline.length - 1 ? '<div class="pf-line"></div>' : ''}
            </div>
            <div class="pf-content">
              <div>
                <div class="pf-name">${escHtml(s.label)}</div>
                <div class="pf-meta">${s.count || statusLabel(s.status || 'queued')}</div>
              </div>
              <div class="pf-time">${s.completedAt || ''}</div>
            </div>
          </div>
        `).join('')}
      </div>
    </div>
  `;
}

function formatElapsed(ms) {
  const secs = Math.floor(ms / 1000);
  const mins = Math.floor(secs / 60);
  const s = secs % 60;
  return `${String(mins).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

function agentLabel(id) {
  const map = {
    requirement: 'Requirement Agent', design: 'Design Agent', code: 'Code Agent',
    test: 'Test Agent', review: 'Review Agent', documentation: 'Documentation Agent'
  };
  return map[id] || '—';
}
function statusLabel(s) {
  const map = { done: 'Completed', running: 'Running…', queued: 'Queued', failed: 'Failed' };
  return map[s] || s;
}

/* ── Requirements ────────────────────────── */
function renderRequirementsView(req) {
  const el = $('view-requirement');
  if (!el) return;
  const stories = req.user_stories || [];

  el.innerHTML = `
    <div class="view-hd">
      <div class="view-breadcrumb">Pipeline · Stage 01</div>
      <div class="view-title">Requirements</div>
      <div class="view-sub">${escHtml(req.problem_statement || '')}</div>
    </div>

    ${req.objectives?.length ? `<div class="sec">
      <div class="sec-title">Objectives</div>
      <ul class="req-list">${req.objectives.map(o => `<li>${escHtml(displayText(o))}</li>`).join('')}</ul>
    </div>` : ''}

    ${stories.length ? `<div class="sec">
      <div class="sec-title">User Stories</div>
      ${stories.map(s => `
        <div class="req-story">
          <div class="req-story-id">${escHtml(typeof s === 'string' ? '' : s.id || '')}</div>
          <div class="req-story-body">
            ${typeof s === 'string' ? escHtml(s) : renderUserStory(s)}
          </div>
        </div>
      `).join('')}
    </div>` : ''}

    ${req.functional_requirements?.length ? `<div class="sec">
      <div class="sec-title">Functional Requirements</div>
      <ul class="req-list">${req.functional_requirements.map(r => {
    const parts = typeof r === 'string' ? r.split(':') : [r.id || '', displayText(r)];
    return `<li><span class="req-id">${escHtml(parts[0] || '')}</span>${escHtml(parts.slice(1).join(':').trim() || displayText(r))}</li>`;
  }).join('')}</ul>
    </div>` : ''}

    ${req.non_functional_requirements?.length ? `<div class="sec">
      <div class="sec-title">Non-Functional Requirements</div>
      <ul class="req-list">${req.non_functional_requirements.map(r => `<li>${escHtml(displayText(r))}</li>`).join('')}</ul>
    </div>` : ''}

    ${req.acceptance_criteria?.length ? `<div class="sec">
      <div class="sec-title">Acceptance Criteria</div>
      <ul class="req-list">${req.acceptance_criteria.map(a => `<li>${escHtml(displayText(a))}</li>`).join('')}</ul>
    </div>` : ''}

    ${renderInOutScope(req)}

    ${req.constraints?.length ? `<div class="sec">
      <div class="sec-title">Constraints</div>
      <ul class="req-list">${req.constraints.map(c => `<li>${escHtml(displayText(c))}</li>`).join('')}</ul>
    </div>` : ''}

    ${req.open_questions?.length ? `<div class="sec">
      <div class="sec-title">Open Questions</div>
      <ul class="req-list">${req.open_questions.map(q => `<li>${escHtml(displayText(q))}</li>`).join('')}</ul>
    </div>` : ''}
  `;
  el.dataset.rendered = '1';
}

function renderUserStory(story) {
  // RequirementsList uses actor/story; keep fallback support for older payloads.
  if (story.story) return escHtml(story.story);

  const actor = story.actor || story.role || 'user';
  const want = story.want || '';
  const benefit = story.so_that || '';
  return `As a <strong>${escHtml(actor)}</strong>, I want to <strong>${escHtml(want)}</strong>${benefit ? ` so that ${escHtml(benefit)}.` : '.'}`;
}

function renderInOutScope(req) {
  if (!req.in_scope?.length && !req.out_of_scope?.length) return '';
  return `<div class="sec">
    <div class="sec-title">Scope</div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:24px">
      <div>
        <div style="font-size:11px;font-weight:600;color:var(--green);margin-bottom:10px">In Scope</div>
        <ul class="req-list">${(req.in_scope || []).map(s => `<li>${escHtml(displayText(s))}</li>`).join('')}</ul>
      </div>
      <div>
        <div style="font-size:11px;font-weight:600;color:var(--text-muted);margin-bottom:10px">Out of Scope</div>
        <ul class="req-list">${(req.out_of_scope || []).map(s => `<li>${escHtml(displayText(s))}</li>`).join('')}</ul>
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
      <div class="view-breadcrumb">Pipeline · Stage 02</div>
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
            <td style="font-weight:600">${escHtml(typeof c === 'string' ? c : displayText(c.name || c))}</td>
            <td class="tag-muted">${escHtml(typeof c === 'string' ? '' : displayText(c.responsibility))}</td>
            <td><div class="comp-deps">${(typeof c === 'string' ? [] : c.deps || []).map(d => `<span class="comp-dep-tag">${escHtml(d)}</span>`).join('')}</div></td>
          </tr>`).join('')}
        </tbody>
      </table>
    </div>` : ''}

    ${design.api_endpoints?.length ? `<div class="sec">
      <div class="sec-title">API Endpoints</div>
      <ul class="req-list">${design.api_endpoints.map(e => `<li style="font-family:var(--font-mono);font-size:12px">${escHtml(displayText(e))}</li>`).join('')}</ul>
    </div>` : ''}

    ${decisions.length ? `<div class="sec">
      <div class="sec-title">Design Decisions</div>
      ${decisions.map(d => `
        <div class="decision-card">
          <div class="dec-id">${escHtml(typeof d === 'string' ? 'DEC' : d.id || 'DEC')}</div>
          <div class="dec-decision">${escHtml(typeof d === 'string' ? d : d.decision || displayText(d))}</div>
          ${typeof d !== 'string' && d.reason ? `<div class="dec-reason">${escHtml(displayText(d.reason))}</div>` : ''}
          ${typeof d !== 'string' && d.impacted?.length ? `<div class="dec-impact">${d.impacted.map(i => `<span class="comp-dep-tag">${escHtml(i)}</span>`).join('')}</div>` : ''}
        </div>
      `).join('')}
    </div>` : ''}

    ${design.edge_cases?.length ? `<div class="sec">
      <div class="sec-title">Edge Cases</div>
      <div class="edge-case-list">${design.edge_cases.map((edge, index) => {
        const item = typeof edge === 'string' ? { description: edge } : edge;
        return `<div class="edge-case-card">
          <div class="edge-case-id">${escHtml(item.id || `EDGE-${String(index + 1).padStart(2, '0')}`)}</div>
          <div class="edge-case-description">${escHtml(displayText(item.description || item))}</div>
          ${item.requirement_ids?.length ? `<div class="edge-case-meta">Requirements: ${item.requirement_ids.map(id => `<span class="comp-dep-tag">${escHtml(id)}</span>`).join('')}</div>` : ''}
          ${item.component_ids?.length ? `<div class="edge-case-meta">Components: ${item.component_ids.map(id => `<span class="comp-dep-tag">${escHtml(id)}</span>`).join('')}</div>` : ''}
        </div>`;
      }).join('')}</div>
    </div>` : ''}
  `;
  el.dataset.rendered = '1';
}

/* ── Code ────────────────────────────────── */
function renderCodeView(code) {
  const el = $('view-code');
  if (!el) return;
  const files = code.files || [];
  const firstFile = files[0];

  el.innerHTML = `
    <div class="view-hd">
      <div class="view-breadcrumb">Pipeline · Stage 03</div>
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
        <div class="cw-content" id="cwContent">${firstFile
      ? `<pre class="cw-source">${escHtml(firstFile.content || `// ${firstFile.path || 'File'} has not been returned yet.`)}</pre>`
      : ''}</div>
      </div>
    </div>` : ''}

    ${code.dependencies?.length ? `<div class="sec">
      <div class="sec-title">Dependencies</div>
      <div style="display:flex;flex-wrap:wrap;gap:6px">
        ${code.dependencies.map(d => `<span class="comp-dep-tag" style="font-size:12px;padding:4px 8px">${escHtml(d)}</span>`).join('')}
      </div>
    </div>` : ''}

    ${code.setup_instructions ? `<div class="sec">
      <div class="sec-title">Setup Instructions</div>
      <pre class="arch-diagram" style="margin:0">${escHtml(code.setup_instructions)}</pre>
    </div>` : ''}
  `;
  el.dataset.rendered = '1';
}

window.selectCodeFile = function (fileEl) {
  document.querySelectorAll('.cw-file').forEach(f => f.classList.remove('active'));
  fileEl.classList.add('active');
  const content = $('cwContent');
  if (content) {
    const path = fileEl.dataset.path;
    const desc = fileEl.dataset.desc;
    const sourceFiles = State.pipelineData?.code?.files || window.MockData?.code?.files || [];
    const selectedFile = sourceFiles.find(file => file.path === path) || {};
    content.innerHTML = `<pre class="cw-source">${escHtml(selectedFile.content || `// ${path}\n// ${desc}\n// Source content is not available yet.`)}</pre>`;
  }
};

/* ── Tests ───────────────────────────────── */
function renderTestsView(tests) {
  const el = $('view-test');
  if (!el) return;
  const cases = tests.cases || tests.test_cases || [];
  const total = tests.total_tests ?? tests.total ?? 0;
  const passed = tests.passed ?? tests.passed_tests ?? 0;
  const failed = tests.failed ?? tests.failed_tests ?? 0;
  const errors = Array.isArray(tests.errors) ? tests.errors.length : (tests.errors ?? 0);
  const output = tests.output ?? tests.raw_output ?? '';
  const testStatus = tests.status ?? (tests.success ? 'pass' : tests.execution_status || 'fail');
  const duration = tests.duration ?? tests.duration_seconds;

  el.innerHTML = `
    <div class="view-hd">
      <div class="view-breadcrumb">Pipeline · Stage 04</div>
      <div class="view-title">Test Results</div>
    </div>
    <div class="test-header">
      <div class="test-summary-nums">
        <div class="tsn"><div class="tsn-val tag-green">${passed}</div><div class="tsn-lbl">Passed</div></div>
        <div class="tsn"><div class="tsn-val tag-red">${failed}</div><div class="tsn-lbl">Failed</div></div>
        <div class="tsn"><div class="tsn-val" style="color:var(--amber)">${errors}</div><div class="tsn-lbl">Errors</div></div>
        <div class="tsn"><div class="tsn-val" style="font-size:22px;color:var(--text-dim)">${escHtml(String(total))}</div><div class="tsn-lbl">Total</div></div>
        ${duration !== undefined && duration !== null ? `<div class="tsn"><div class="tsn-val" style="font-size:22px;color:var(--text-dim)">${escHtml(`${duration}s`)}</div><div class="tsn-lbl">Duration</div></div>` : ''}
      </div>
      <div class="artifact-badge ${testStatus === 'pass' ? 'badge-done' : testStatus === 'fail' ? 'badge-fail' : 'badge-queue'}">${escHtml(testStatus)}</div>
    </div>
    ${tests.test_plan ? `<div class="sec"><div class="sec-title">Test Plan</div><p class="test-plan">${escHtml(tests.test_plan)}</p></div>` : ''}
    ${Array.isArray(tests.errors) && tests.errors.length ? `<div class="sec">
      <div class="sec-title">Errors</div>
      <ul class="req-list">${tests.errors.map(error => `<li>${escHtml(String(error))}</li>`).join('')}</ul>
    </div>` : ''}
    ${cases.length ? `<div class="sec">
      <div class="sec-title">Test Cases</div>
      <div class="test-cases">
        ${cases.map(tc => `
          <div class="tc" onclick="toggleTestCase(this)">
            <div class="tc-status ${tc.status === 'pass' ? 'tc-pass' : tc.status === 'fail' ? 'tc-fail' : 'tc-pending'}">${tc.status === 'pass' ? '✓' : tc.status === 'fail' ? '✕' : '•'}</div>
            <div class="tc-id">${escHtml(tc.id || '')}</div>
            <div class="tc-name">${escHtml(tc.name || tc.description || '')}</div>
            <div class="tc-expect">${escHtml(tc.expected || tc.acceptance_criterion_id || '')}${tc.actual ? ` → ${escHtml(tc.actual)}` : ''}</div>
          </div>
          ${tc.status !== 'pass' && tc.logs ? `
            <div class="tc-detail hidden">
              <pre class="tc-log">${escHtml(tc.logs)}</pre>
            </div>
          ` : ''}
        `).join('')}
      </div>
    </div>` : ''}
    ${output ? `<div class="sec">
      <div class="sec-title">Raw Output</div>
      <pre class="arch-diagram">${escHtml(output)}</pre>
    </div>` : ''}
  `;
  el.dataset.rendered = '1';
}

window.toggleTestCase = function (el) {
  const next = el.nextElementSibling;
  if (next && next.classList.contains('tc-detail')) {
    next.classList.toggle('hidden');
  }
};

/* ── Review ──────────────────────────────── */
function renderReviewView(review, approvalStatus) {
  const el = $('view-review');
  if (!el) return;
  const checks = review.checks || [];
  const findings = review.findings || [];
  const approved = approvalStatus === 'approved' || (approvalStatus === undefined && review.approved === true);
  const rejected = approvalStatus === 'rejected' || (approvalStatus === undefined && review.approved === false);
  const verdictLabel = approved ? '✓ Approved' : rejected ? '✕ Rejected' : '⚠ Pending Review';

  el.innerHTML = `
    <div class="view-hd">
      <div class="view-breadcrumb">Pipeline · Stage 05</div>
      <div class="view-title">Quality Gate</div>
      <div class="artifact-badge ${approved ? 'badge-done' : rejected ? 'badge-fail' : 'badge-warn'}" style="margin-top:8px">
        ${verdictLabel}
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
      <div class="sec-title">Blocking Defects</div>
      ${review.defects.map(d => `
        <div class="finding high">
          <div class="finding-sev">Blocking Defect</div>
          <div class="finding-title">${escHtml(displayText(d))}</div>
        </div>
      `).join('')}
    </div>` : ''}

    ${findings.length ? `<div class="sec">
      <div class="sec-title">Findings & Recommendations</div>
      ${findings.map(f => `
        <div class="finding ${f.severity || 'low'}">
          <div class="finding-sev">${escHtml(f.severity || 'low')} · ${escHtml(f.id || '')}</div>
          <div class="finding-title">${escHtml(displayText(f.title || f))}</div>
          ${f.detail ? `<div class="finding-detail">${escHtml(displayText(f.detail))}</div>` : ''}
        </div>
      `).join('')}
    </div>` : ''}

    ${review.summary ? `<div class="sec">
      <div class="sec-title">Summary</div>
      <p style="font-size:13px;color:var(--text-dim);line-height:1.65">${escHtml(review.summary)}</p>
      ${review.overall_score ? `<div style="margin-top:8px;font-size:12px;font-family:var(--font-mono);color:var(--accent)">Quality Rating: ${escHtml(String(review.overall_score))}/10</div>` : ''}
    </div>` : ''}
  `;
  el.dataset.rendered = '1';
}

/* ── Documentation ───────────────────────── */
function renderDocsView(docs) {
  const el = $('view-documentation');
  if (!el) return;

  el.innerHTML = `
    <div class="view-hd">
      <div class="view-breadcrumb">Pipeline · Stage 06</div>
      <div class="view-title">Documentation</div>
      <button class="btn-ghost doc-export-btn" type="button" onclick="exportDocumentation()">
        ↓ Export documentation
      </button>
    </div>
    <div class="doc-prose">
      ${docs.readme ? `<h3>README</h3><pre>${escHtml(docs.readme)}</pre>` : ''}
      ${docs.api_reference ? `<h3>API Reference</h3><pre>${escHtml(docs.api_reference)}</pre>` : ''}
      ${docs.architecture_overview ? `<h3>Architecture</h3><pre>${escHtml(docs.architecture_overview)}</pre>` : ''}
      ${docs.user_guide ? `<h3>User Guide</h3><pre>${escHtml(docs.user_guide)}</pre>` : ''}
      ${docs.changelog ? `<h3>Changelog</h3><pre>${escHtml(docs.changelog)}</pre>` : ''}
    </div>
  `;
  el.dataset.rendered = '1';
}

window.exportDocumentation = function () {
  const docs = State.pipelineData?.documentation;
  if (!docs) return;

  const sections = [
    ['README', docs.readme],
    ['API Reference', docs.api_reference],
    ['Architecture', docs.architecture_overview],
    ['User Guide', docs.user_guide],
    ['Changelog', docs.changelog],
  ].filter(([, content]) => typeof content === 'string' && content.trim());

  if (!sections.length) return;

  const content = sections
    .map(([title, body]) => `# ${title}\n\n${body.trim()}`)
    .join('\n\n---\n\n') + '\n';

  const projectName = (State.projectName || 'project')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '') || 'project';
  const blob = new Blob([content], { type: 'text/markdown;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `${projectName}-documentation.md`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
};

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
  el.dataset.rendered = '1';
}

function renderArtifactsViewLive(result) {
  const el = $('view-artifacts');
  if (!el) return;

  const stages = [];
  if (result.requirements && Object.keys(result.requirements).length) {
    stages.push({ name: 'Requirements', version: result.requirements_version || 1 });
  }
  if (result.design && Object.keys(result.design).length) {
    stages.push({ name: 'Design', version: result.design_version || 1 });
  }
  if (result.code && Object.keys(result.code).length) {
    stages.push({ name: 'Code', version: result.code_version || 1 });
  }
  if (result.test_results && Object.keys(result.test_results).length) {
    stages.push({ name: 'Tests', version: result.test_version || 1 });
  }
  if (result.review && Object.keys(result.review).length) {
    stages.push({ name: 'Review', version: result.review_version || 1 });
  }
  if (result.documentation && Object.keys(result.documentation).length) {
    stages.push({ name: 'Documentation', version: result.documentation_version || 1 });
  }

  el.innerHTML = `
    <div class="view-hd">
      <div class="view-breadcrumb">Project</div>
      <div class="view-title">Artifacts</div>
      <div class="view-sub">Outputs generated by the pipeline.</div>
    </div>
    ${stages.length ? stages.map(s => `
      <div class="art-group">
        <div class="art-group-name">${escHtml(s.name)}</div>
        <div class="art-versions">
          <div class="art-ver">
            <div class="art-ver-num">v${s.version}</div>
            <div class="art-ver-info">
              <div class="art-ver-changes">${escHtml(s.name)} output</div>
            </div>
            <span class="artifact-badge badge-done">current</span>
          </div>
        </div>
      </div>
    `).join('') : `
      <div class="empty-state">
        <div class="empty-state-icon">○</div>
        <div class="empty-state-title">No artifacts yet</div>
        <div class="empty-state-sub">Artifacts will appear as the pipeline produces outputs.</div>
      </div>
    `}
  `;
  el.dataset.rendered = '1';
}

/* ── Models view ─────────────────────────── */
function renderModelsView() {
  const el = $('view-models');
  if (!el) return;

  el.innerHTML = `
    <div class="view-hd">
      <div class="view-breadcrumb">Configuration</div>
      <div class="view-title">Model Configuration</div>
      <div class="view-sub">Edit each agent's model ID below and click <strong>Save All Models</strong> to apply.</div>
    </div>
    <div class="models-view-grid">
      ${STAGE_DEFS.map(def => {
    const cfg = MODEL_CONFIG[def.id] || {};
    const isOllama = !cfg.model || cfg.provider === 'Ollama';
    return `
          <div class="mv-agent-card">
            <div class="mv-agent-left">
              <div class="mv-agent-name">
                ${escHtml(def.label)} Agent
              </div>
              <div class="mv-agent-desc">${escHtml(cfg.role || def.desc)}</div>
              <div style="margin-top:6px">
                <span class="mcm-provider-tag ${isOllama ? 'ollama' : 'openrouter'}">${escHtml(cfg.provider || 'Unknown')}</span>
                ${isOllama ? '<span class="mcm-provider-tag ollama" style="margin-left:4px">Local</span>' : ''}
              </div>
            </div>
            <div class="mv-agent-right">
              <div class="mcm-model-label">Model ID</div>
              <input
                class="mcm-model-select mv-model-input"
                id="mv-input-${def.id}"
                type="text"
                value="${escHtml(cfg.model || '')}"
                placeholder="e.g. google/gemma-4-26b-a4b-it:free"
              />
              <div class="mcm-ui-note">Edit then click Save All Models</div>
            </div>
          </div>
        `;
  }).join('')}
    </div>
    <div class="mv-save-row">
      <button class="mv-save-btn" id="mvSaveBtn" type="button" onclick="saveModelsView()">💾 Save All Models</button>
      <span class="mv-save-note" id="mvSaveNote"></span>
    </div>
  `;
  el.dataset.rendered = '1';
}

window.saveModelsView = async function () {
  const updated = {};
  STAGE_DEFS.forEach(def => {
    const input = $(`mv-input-${def.id}`);
    updated[def.id] = input ? input.value.trim() : '';
  });

  const saveBtn = $('mvSaveBtn');
  const note = $('mvSaveNote');
  if (saveBtn) { saveBtn.textContent = 'Saving…'; saveBtn.disabled = true; }

  try {
    const res = await fetch('/api/models/runtime', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ models: updated })
    });
    const data = await res.json();
    if (data.ok) {
      Object.entries(updated).forEach(([agentId, modelId]) => {
        if (MODEL_CONFIG[agentId]) MODEL_CONFIG[agentId].model = modelId;
      });
      if (saveBtn) { saveBtn.textContent = '✓ Saved!'; }
      if (note) { note.textContent = 'Runtime models updated. Changes apply to the next agent call.'; note.style.color = '#4ade80'; }
      setTimeout(() => {
        if (saveBtn) { saveBtn.textContent = '💾 Save All Models'; saveBtn.disabled = false; }
      }, 2000);
    } else {
      if (saveBtn) { saveBtn.textContent = '⚠ Error'; saveBtn.disabled = false; }
      if (note) { note.textContent = data.error || 'Save failed'; note.style.color = '#f87171'; }
    }
  } catch (err) {
    if (saveBtn) { saveBtn.textContent = '⚠ Error'; saveBtn.disabled = false; }
    if (note) { note.textContent = 'Server unreachable'; note.style.color = '#f87171'; }
  }
};
function renderGitHubView() {
  const el = $('view-github');
  if (!el) return;

  const releaseData = State.pipelineData?.release || {};
  const hasRelease = releaseData.status === 'success';

  el.innerHTML = `
    <div class="view-hd">
      <div class="view-breadcrumb">Project</div>
      <div class="view-title">GitHub Integration</div>
      <div class="view-sub">Push your generated project to a GitHub repository.</div>
    </div>

    <div class="gh-layout">
      <!-- Main config card -->
      <div class="gh-card">
        <div class="gh-card-header">
          <svg class="gh-icon" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
            <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z"/>
          </svg>
          <div class="gh-card-title">Repository Settings</div>
        </div>

        <div class="gh-card-body">
          <div class="gh-field">
            <label class="gh-label" for="githubRepoInput">
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true"><path d="M2 4.5h10M2 7h10M2 9.5h6" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/></svg>
              Repository URL or owner/repo
            </label>
            <div class="gh-input-wrap">
              <input id="githubRepoInput" class="gh-input" type="text" value="${escHtml(State.githubRepo)}" placeholder="https://github.com/owner/repo.git" spellcheck="false" />
            </div>
          </div>

          <div class="gh-field">
            <label class="gh-label" for="githubTokenInput">
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true"><path d="M7 1v4M5 3h4M3 7a4 4 0 108 0" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/></svg>
              Personal Access Token <span class="gh-optional">(optional)</span>
            </label>
            <div class="gh-input-wrap">
              <input id="githubTokenInput" class="gh-input" type="password" placeholder="ghp_xxxxxxxxxxxx" spellcheck="false" />
            </div>
            <div class="gh-hint">Used for private repos. Never stored beyond this session.</div>
          </div>

          <div class="gh-field">
            <label class="gh-label" for="githubCommitMsg">
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true"><circle cx="7" cy="7" r="3" stroke="currentColor" stroke-width="1.2"/><path d="M7 1v3M7 10v3" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/></svg>
              Commit message
            </label>
            <div class="gh-input-wrap">
              <input id="githubCommitMsg" class="gh-input" type="text" value="Release approved project via IdeaToProduct" placeholder="Initial commit" spellcheck="false" />
            </div>
          </div>
        </div>

        <div class="gh-card-footer">
          <div class="gh-status" id="ghStatus">
            ${hasRelease
              ? `<span class="gh-status-badge gh-status-success">
                   <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M2.5 6l2.5 2.5 4.5-5" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></svg>
                   Published to ${escHtml(releaseData.remote_url || '')}
                 </span>`
              : `<span class="gh-status-badge gh-status-idle">
                   <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><circle cx="6" cy="6" r="2" fill="currentColor" opacity="0.4"/></svg>
                   Ready to publish
                 </span>`
            }
          </div>
          <button class="gh-publish-btn" id="githubPublishBtn" type="button">
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
              <path d="M7 1v8M4 6l3 3 3-3" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/>
              <path d="M2 11h10" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>
            </svg>
            Publish to GitHub
          </button>
        </div>
      </div>

      <!-- Info panel -->
      <div class="gh-info">
        <div class="gh-info-card">
          <div class="gh-info-title">How it works</div>
          <div class="gh-info-steps">
            <div class="gh-step">
              <span class="gh-step-num">1</span>
              <span>Pipeline completes all 6 stages</span>
            </div>
            <div class="gh-step">
              <span class="gh-step-num">2</span>
              <span>Code is reviewed and approved</span>
            </div>
            <div class="gh-step">
              <span class="gh-step-num">3</span>
              <span>Release Agent pushes to your repo</span>
            </div>
          </div>
        </div>
        <div class="gh-info-card">
          <div class="gh-info-title">Generated files</div>
          <div class="gh-file-tree" id="ghFileTree">
            <span class="gh-file-empty">Run the pipeline to see generated files.</span>
          </div>
        </div>
      </div>
    </div>
  `;

  // Wire up publish button
  const btn = $('githubPublishBtn');
  if (btn) {
    btn.onclick = () => {
      const repo = $('githubRepoInput').value.trim();
      if (!repo) {
        $('githubRepoInput').classList.add('gh-input-error');
        setTimeout(() => $('githubRepoInput').classList.remove('gh-input-error'), 800);
        return;
      }
      State.githubRepo = repo;

      // Show publishing state
      btn.disabled = true;
      btn.innerHTML = `<span class="gh-spinner"></span> Publishing…`;
      const statusEl = $('ghStatus');
      if (statusEl) {
        statusEl.innerHTML = `<span class="gh-status-badge gh-status-running"><span class="gh-spinner"></span> Pushing to ${escHtml(repo)}…</span>`;
      }

      const token = $('githubTokenInput')?.value.trim() || '';
      const commitMessage = $('githubCommitMsg')?.value.trim() || '';
      fetch(`${API}/api/release`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: State.sessionId,
          repo_url: repo,
          github_token: token,
          commit_message: commitMessage,
        })
      }).then(async response => {
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Release failed');
        if (statusEl) statusEl.innerHTML = `<span class="gh-status-badge gh-status-running">Release started for ${escHtml(repo)}…</span>`;
        startPolling();
      }).catch(error => {
        if (statusEl) statusEl.innerHTML = `<span class="gh-status-badge gh-status-error">${escHtml(error.message)}</span>`;
        btn.disabled = false;
        btn.innerHTML = 'Retry Publish';
      });
    };
  }

  // Populate file tree if we have data
  const codeFiles = State.pipelineData?.code?.files;
  if (codeFiles && Array.isArray(codeFiles)) {
    const treeEl = $('ghFileTree');
    if (treeEl) {
      treeEl.innerHTML = codeFiles.map(f => `<div class="gh-file-item"><svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M3 1.5h4l3 3v6H3v-9z" stroke="currentColor" stroke-width="1" fill="none"/><path d="M7 1.5v3h3" stroke="currentColor" stroke-width="1"/></svg> ${escHtml(f.path || f)}</div>`).join('');
    }
  }

  el.dataset.rendered = '1';
}

/* ═════════════════════════════════════════════════
   12. MODEL CONFIG OVERLAY
═════════════════════════════════════════════════ */
function openModelConfig() {
  const overlay = $('modelConfigOverlay');
  const cont = $('mcmAgents');
  if (!overlay || !cont) return;

  cont.innerHTML = STAGE_DEFS.map(def => {
    const cfg = MODEL_CONFIG[def.id] || {};
    const isOllama = !cfg.model || cfg.provider === 'Ollama';
    return `
      <div class="mcm-agent">
        <div class="mcm-agent-info">
          <div class="mcm-agent-name">
            ${escHtml(def.label)} Agent
          </div>
          <div class="mcm-agent-role">${escHtml(cfg.role || '')}</div>
          <div class="mcm-agent-provider">
            <span class="mcm-provider-tag ${isOllama ? 'ollama' : 'openrouter'}">${escHtml(cfg.provider || 'Unknown')}</span>
            ${isOllama ? '<span class="mcm-provider-tag ollama">Local</span>' : ''}
          </div>
        </div>
        <div class="mcm-agent-config">
          <div class="mcm-model-label">Model ID</div>
          <input class="mcm-model-select" type="text"
            id="mcm-input-${def.id}"
            value="${escHtml(cfg.model || '')}"
            placeholder="e.g. google/gemma-4-26b-a4b-it:free"
            title="Enter the model ID to use for the ${escHtml(def.label)} agent" />
          <div class="mcm-ui-note">Leave empty to use the Ollama default. Changes apply to the next agent call.</div>
        </div>
      </div>
    `;
  }).join('');

  overlay.classList.remove('hidden');
}

window.closeModelConfig = function () {
  $('modelConfigOverlay')?.classList.add('hidden');
};

window.saveModelConfig = async function () {
  const updated = {};
  STAGE_DEFS.forEach(def => {
    const input = $(`mcm-input-${def.id}`);
    updated[def.id] = input ? input.value.trim() : '';
  });

  const saveBtn = $('mcmSaveBtn');
  if (saveBtn) { saveBtn.textContent = 'Saving…'; saveBtn.disabled = true; }

  try {
    const res = await fetch('/api/models/runtime', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ models: updated })
    });
    const data = await res.json();
    if (data.ok) {
      // Update local MODEL_CONFIG
      Object.entries(updated).forEach(([agentId, modelId]) => {
        if (MODEL_CONFIG[agentId]) MODEL_CONFIG[agentId].model = modelId;
      });
      if (saveBtn) { saveBtn.textContent = '✓ Saved for next agent'; }
      setTimeout(() => {
        $('modelConfigOverlay')?.classList.add('hidden');
        if (saveBtn) { saveBtn.textContent = 'Save Changes'; saveBtn.disabled = false; }
        // Re-render models view if visible
        if ($('view-models') && !$('view-models').classList.contains('hidden')) {
          delete $('view-models').dataset.rendered;
          renderModelsView();
        }
      }, 900);
    } else {
      if (saveBtn) { saveBtn.textContent = '⚠ Error'; saveBtn.disabled = false; }
      alert('Save failed: ' + (data.error || 'Unknown error'));
    }
  } catch (err) {
    if (saveBtn) { saveBtn.textContent = '⚠ Error'; saveBtn.disabled = false; }
    alert('Could not reach server: ' + err.message);
  }
};

// Close overlays on Escape
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') {
    $('clarifyOverlay')?.classList.add('hidden');
    $('modelConfigOverlay')?.classList.add('hidden');
  }
});

/* ═════════════════════════════════════════════════
   13. PIPELINE ERROR
═════════════════════════════════════════════════ */
function showPipelineError(msg) {
  setNavPipelineStatus('error');
  setSbStatus('error');

  const el = $('view-overview');
  if (!el) return;
  el.insertAdjacentHTML('afterbegin', `
    <div class="err-card" style="margin-bottom:28px">
      <div class="err-label">Agent Interrupted</div>
      <div class="err-title">Pipeline stopped</div>
      <div class="err-msg">${escHtml(msg)}</div>
      <div class="err-actions">
        <button class="btn-ghost" type="button" onclick="exitStudio()">Exit</button>
      </div>
    </div>
  `);
}

/* ═════════════════════════════════════════════════
   14. DEMO MODE
═════════════════════════════════════════════════ */
window.openDemo = function () {
  const mock = window.MockData || {};
  State.projectName = mock.project?.name || 'Demo Project';
  State.isLive = false;
  State.pipelineData = null;
  enterStudio(State.projectName, 'done');
  buildPipelineStages(mock.pipeline || []);
  buildActivityFeed(mock.activity || []);

  STAGE_DEFS.forEach(s => renderViewIfNeeded(s.id));
  renderViewIfNeeded('artifacts');
};

/* ═════════════════════════════════════════════════
   15. HELPERS
═════════════════════════════════════════════════ */
function displayText(value) {
  if (value === null || value === undefined) return '';
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
    return String(value);
  }
  if (Array.isArray(value)) return value.map(displayText).join(', ');
  if (typeof value === 'object') {
    const preferred = ['description', 'text', 'requirement', 'criterion', 'value', 'name', 'title', 'detail'];
    const key = preferred.find(candidate => value[candidate] !== undefined && value[candidate] !== null);
    if (key) return displayText(value[key]);
    try { return JSON.stringify(value); } catch { return String(value); }
  }
  return String(value);
}

function escHtml(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function shakeEl(el) {
  if (!el) return;
  el.style.animation = 'none';
  el.offsetHeight; // trigger reflow
  el.style.animation = 'shake 0.35s ease';
  setTimeout(() => { el.style.animation = ''; }, 400);
}

/* ═════════════════════════════════════════════════
   16. PARTICLE CANVAS ANIMATION
═════════════════════════════════════════════════ */
(function initParticles() {
  const canvas = document.getElementById('particleCanvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  if (!ctx) return;

  let w, h;
  const particles = [];
  const PARTICLE_COUNT = 50;

  function resize() {
    const rect = canvas.parentElement.getBoundingClientRect();
    w = canvas.width = rect.width;
    h = canvas.height = rect.height;
  }

  function createParticle() {
    return {
      x: Math.random() * w,
      y: Math.random() * h,
      vx: (Math.random() - 0.5) * 0.3,
      vy: -Math.random() * 0.4 - 0.1,
      radius: Math.random() * 1.5 + 0.5,
      opacity: Math.random() * 0.4 + 0.1,
      color: Math.random() > 0.6
        ? `rgba(46, 194, 126, OPACITY)`
        : Math.random() > 0.5
          ? `rgba(94, 120, 255, OPACITY)`
          : `rgba(212, 162, 78, OPACITY)`,
    };
  }

  function init() {
    resize();
    particles.length = 0;
    for (let i = 0; i < PARTICLE_COUNT; i++) {
      particles.push(createParticle());
    }
  }

  function animate() {
    ctx.clearRect(0, 0, w, h);

    for (let i = 0; i < particles.length; i++) {
      const p = particles[i];
      p.x += p.vx;
      p.y += p.vy;

      // Wrap around
      if (p.y < -10) { p.y = h + 10; p.x = Math.random() * w; }
      if (p.x < -10) p.x = w + 10;
      if (p.x > w + 10) p.x = -10;

      ctx.beginPath();
      ctx.arc(p.x, p.y, p.radius, 0, Math.PI * 2);
      ctx.fillStyle = p.color.replace('OPACITY', String(p.opacity));
      ctx.fill();
    }

    requestAnimationFrame(animate);
  }

  // Check reduced motion
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

  init();
  animate();
  window.addEventListener('resize', resize);
})();

/* ═════════════════════════════════════════════════
   17. PIPELINE STAGE HOVER GLOW
═════════════════════════════════════════════════ */
document.querySelectorAll('.pt-stage').forEach(stage => {
  stage.addEventListener('mouseenter', () => {
    stage.style.transition = 'transform 0.2s ease, color 0.2s ease';
    stage.style.transform = 'translateY(-2px)';
    const label = stage.querySelector('.pt-label');
    const num = stage.querySelector('.pt-num');
    if (label) label.style.color = 'var(--accent)';
    if (num) num.style.color = 'var(--accent)';
  });
  stage.addEventListener('mouseleave', () => {
    stage.style.transform = '';
    const label = stage.querySelector('.pt-label');
    const num = stage.querySelector('.pt-num');
    if (label) label.style.color = '';
    if (num) num.style.color = '';
  });
});
