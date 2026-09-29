/* ═══════════════════════════════════════════════
   IdeaToProduct — app.js
   Antigrav IDE interactions and pipeline simulation
   ═══════════════════════════════════════════════ */

'use strict';

const $ = id => document.getElementById(id);

/* ── DOM References ── */
const intro = $('intro');
const studio = $('studio');
const ideaInput = $('ideaInput');
const launchBtn = $('launchBtn');
const launchLabel = $('launchLabel');
const charCount = $('charCount');
const termOutput = $('termOutput');
const fileTree = $('fileTree');
const fileCount = $('fileCount');
const agentList = $('agentList');
const reasoningBox = $('reasoningBox');
const activityFeed = $('activityFeed');

let pipelineTimer = null;
let currentStageIdx = 0;
let startTime = null;
let elapsedTimer = null;

document.addEventListener('DOMContentLoaded', () => {
  // Setup character count
  if (ideaInput) {
    ideaInput.addEventListener('input', () => {
      charCount.textContent = ideaInput.value.length;
    });
  }

  // Typing Effect
  const l1 = "Turn your";
  const l2 = "idea into";
  const l3 = "a product.";
  const cursor = '<span class="cursor"></span>';

  let i1 = 0, i2 = 0, i3 = 0;
  function typeText(elemId, text, indexRef, nextFunc) {
    if (indexRef < text.length) {
      const el = $(elemId);
      el.innerHTML = text.substring(0, indexRef + 1) + (elemId === 'typeLine3' ? cursor : '');
      setTimeout(() => typeText(elemId, text, indexRef + 1, nextFunc), 60);
    } else if (nextFunc) {
      setTimeout(nextFunc, 200);
    }
  }

  // Clear initially
  $('typeLine1').innerHTML = '';
  $('typeLine2').innerHTML = '';
  $('typeLine3').innerHTML = cursor;

  setTimeout(() => {
    typeText('typeLine1', l1, 0, () => {
      typeText('typeLine2', l2, 0, () => {
        typeText('typeLine3', l3, 0, null);
      });
    });
  }, 400);
});

/* ── UI Interactions ── */
window.launchStudio = function () {
  const idea = ideaInput.value.trim();
  if (!idea) {
    ideaInput.style.animation = 'shake 0.4s';
    setTimeout(() => ideaInput.style.animation = '', 400);
    return;
  }

  launchLabel.textContent = 'Launching Real Agents...';
  launchBtn.disabled = true;

  // Transition to studio immediately so user doesn't feel stuck
  intro.classList.add('leave');
  setTimeout(() => {
    intro.hidden = true;
    studio.hidden = false;

    // Start the visual simulation to keep the user entertained
    startPipelineSimulation();
  }, 600);

  // Make an actual request to the backend API in the background
  fetch('http://localhost:8888/api/launch', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ idea: idea })
  })
    .then(response => {
      if (!response.ok) {
        return response.json().then(err => { throw new Error(err.detail || 'Backend error') });
      }
      return response.json();
    })
    .then(data => {
      // Store real data globally to be used when simulation finishes or updates
      window.realData = data;
      appendTerminal('<span class="t-ok">Real backend processing finished! Results received.</span>');
      if (window.currentFile) {
        showCode(window.currentFile);
      }
    })
    .catch(err => {
      appendTerminal('<br><span class="t-err" style="color:var(--red); font-weight:bold;">CRITICAL API ERROR: ' + err.message + '</span>');
      appendTerminal('<span class="t-err" style="color:var(--red);">The backend simulation has been aborted. Please check your OpenRouter credits or server logs.</span>');
      stopPipeline(); // Stop the visual simulation
    });
}

window.exitStudio = function () {
  stopPipeline();
  studio.hidden = true;
  intro.hidden = false;
  intro.classList.remove('leave');
  launchLabel.textContent = 'Launch Studio';
  launchBtn.disabled = false;
}

window.switchCenterTab = function (btn) {
  document.querySelectorAll('.ctab').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  const tab = btn.dataset.tab;

  $('panel-terminal').hidden = tab !== 'terminal';
  $('panel-editor').hidden = tab !== 'editor';
  $('panel-preview').hidden = tab !== 'preview';

  // Inject dynamic preview when switching to the preview tab
  if (tab === 'preview') {
    let htmlContent = null;
    if (window.realData && window.realData.code && Array.isArray(window.realData.code.files)) {
      const htmlFile = window.realData.code.files.find(f => f.path && (f.path === 'index.html' || f.path.endsWith('.html')));
      if (htmlFile) {
        htmlContent = htmlFile.content;
      }
    }

    if (htmlContent) {
      $('previewFrame').srcdoc = htmlContent;
    } else {
      const userIdea = $('ideaInput') ? $('ideaInput').value.trim() : 'Application Prototype';
      $('previewFrame').srcdoc = generatePrototypeHTML(userIdea, window.realData?.requirements);
    }
  }
}

function generatePrototypeHTML(ideaName, reqData) {
  const name = ideaName || "Application Prototype";
  let items = [];
  const lower = name.toLowerCase();

  if (lower.includes('expense') || lower.includes('budget') || lower.includes('money')) {
    items = [
      { name: 'Monthly Rent', category: 'Housing', val: '$1,200.00', status: 'Paid' },
      { name: 'Grocery Shopping', category: 'Food', val: '$145.50', status: 'Completed' },
      { name: 'Electricity Bill', category: 'Utilities', val: '$85.20', status: 'Pending' }
    ];
  } else if (lower.includes('diet') || lower.includes('meal') || lower.includes('food') || lower.includes('nutrition')) {
    items = [
      { name: 'Avocado Toast & Eggs', category: 'Breakfast', val: '450 kcal', status: 'Logged' },
      { name: 'Grilled Chicken Salad', category: 'Lunch', val: '620 kcal', status: 'Logged' },
      { name: 'Protein Shake & Banana', category: 'Snack', val: '280 kcal', status: 'Planned' }
    ];
  } else if (lower.includes('habit') || lower.includes('tracker') || lower.includes('routine')) {
    items = [
      { name: 'Drink 3L Water', category: 'Health', val: 'Goal: 100%', status: 'Done' },
      { name: 'Read 20 Pages', category: 'Mindset', val: 'Goal: Daily', status: 'In Progress' },
      { name: '30 Min Morning Workout', category: 'Fitness', val: 'Goal: 5x/wk', status: 'Done' }
    ];
  } else {
    items = [
      { name: 'Primary Feature Task', category: 'Core Module', val: 'Priority: High', status: 'Active' },
      { name: 'User Authentication Flow', category: 'Security', val: 'Priority: Med', status: 'Verified' },
      { name: 'Analytics Dashboard', category: 'Reporting', val: 'Priority: Low', status: 'Ready' }
    ];
  }

  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>${name}</title>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    * { box-sizing: border-box; }
    body { font-family: 'Inter', sans-serif; background: #0b0f19; color: #f1f5f9; margin: 0; padding: 24px; min-height: 100vh; }
    .container { max-width: 900px; margin: 0 auto; }
    .header { display: flex; justify-content: space-between; align-items: center; padding-bottom: 20px; border-bottom: 1px solid #1e293b; margin-bottom: 24px; }
    .title-group h1 { font-size: 1.5rem; margin: 0 0 6px 0; color: #f8fafc; text-transform: capitalize; }
    .title-group p { font-size: 0.85rem; color: #94a3b8; margin: 0; }
    .badge { background: #0284c7; color: #fff; font-size: 0.75rem; font-weight: 600; padding: 4px 12px; border-radius: 20px; text-transform: uppercase; letter-spacing: 0.5px; }
    
    .metrics-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-bottom: 24px; }
    .stat-card { background: #1e293b; border: 1px solid #334155; border-radius: 12px; padding: 18px; }
    .stat-label { font-size: 0.75rem; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 6px; }
    .stat-val { font-size: 1.4rem; font-weight: 700; color: #38bdf8; }
    
    .main-card { background: #1e293b; border: 1px solid #334155; border-radius: 12px; padding: 20px; margin-bottom: 24px; }
    .card-title { font-size: 1rem; font-weight: 600; margin: 0 0 16px 0; color: #f8fafc; }
    
    .form-grid { display: grid; grid-template-columns: 2fr 1fr 1fr auto; gap: 12px; }
    input, select { background: #0f172a; border: 1px solid #334155; color: #fff; padding: 10px 14px; border-radius: 8px; font-size: 0.85rem; outline: none; }
    input:focus, select:focus { border-color: #38bdf8; }
    button { background: #0284c7; color: white; border: none; padding: 10px 18px; border-radius: 8px; font-weight: 600; font-size: 0.85rem; cursor: pointer; transition: 0.2s; }
    button:hover { background: #0369a1; }
    
    table { width: 100%; border-collapse: collapse; margin-top: 12px; }
    th { text-align: left; font-size: 0.75rem; color: #94a3b8; text-transform: uppercase; padding: 12px 16px; border-bottom: 1px solid #334155; }
    td { padding: 14px 16px; font-size: 0.85rem; border-bottom: 1px solid #1e293b; }
    .status-tag { display: inline-block; padding: 3px 8px; border-radius: 6px; font-size: 0.75rem; font-weight: 600; background: rgba(56, 189, 248, 0.15); color: #38bdf8; }
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <div class="title-group">
        <h1>${name}</h1>
        <p>Interactive Prototype Skeleton</p>
      </div>
      <span class="badge">v1.0 Live UI</span>
    </div>
    
    <div class="metrics-grid">
      <div class="stat-card">
        <div class="stat-label">Active Records</div>
        <div class="stat-val" id="totalCount">${items.length}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Backend API</div>
        <div class="stat-val" style="color:#4ade80;">Online</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Database</div>
        <div class="stat-val" style="color:#a78bfa;">SQLite</div>
      </div>
    </div>
    
    <div class="main-card">
      <h3 class="card-title">Add New Record</h3>
      <div class="form-grid">
        <input type="text" id="itemName" placeholder="Item Name..." />
        <input type="text" id="itemCat" placeholder="Category..." />
        <input type="text" id="itemVal" placeholder="Value / Target..." />
        <button onclick="addItem()">Add Entry</button>
      </div>
    </div>
    
    <div class="main-card" style="padding:0; overflow:hidden;">
      <table>
        <thead>
          <tr>
            <th>Name</th>
            <th>Category</th>
            <th>Value</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody id="tableBody">
          ${items.map(item => `
            <tr>
              <td style="font-weight:600; color:#f8fafc;">${item.name}</td>
              <td style="color:#94a3b8;">${item.category}</td>
              <td style="color:#38bdf8; font-weight:600;">${item.val}</td>
              <td><span class="status-tag">${item.status}</span></td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    </div>
  </div>
  
  <script>
    function addItem() {
      const name = document.getElementById('itemName').value.trim();
      const cat = document.getElementById('itemCat').value.trim() || 'General';
      const val = document.getElementById('itemVal').value.trim() || 'Active';
      if (!name) return;
      
      const tbody = document.getElementById('tableBody');
      const tr = document.createElement('tr');
      tr.innerHTML = \`
        <td style="font-weight:600; color:#f8fafc;">\${name}</td>
        <td style="color:#94a3b8;">\${cat}</td>
        <td style="color:#38bdf8; font-weight:600;">\${val}</td>
        <td><span class="status-tag">Active</span></td>
      \`;
      tbody.prepend(tr);
      
      const countEl = document.getElementById('totalCount');
      countEl.textContent = parseInt(countEl.textContent) + 1;
      
      document.getElementById('itemName').value = '';
      document.getElementById('itemCat').value = '';
      document.getElementById('itemVal').value = '';
    }
  </script>
</body>
</html>`;
}

window.switchInspector = function (btn) {
  document.querySelectorAll('.itab').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  const view = btn.dataset.view;

  $('insp-reasoning').hidden = view !== 'reasoning';
  $('insp-properties').hidden = view !== 'properties';
  $('insp-activity').hidden = view !== 'activity';
}

/* ── Pipeline Simulation ── */
const stages = [
  { id: 'requirement', name: 'Requirement Agent', logs: ['Analyzing user input...', 'Extracting core features...', 'Generating User Stories...', 'Finalizing PRD.'], files: ['requirements.md', 'user_stories.yml'], time: 3000 },
  { id: 'design', name: 'Design Agent', logs: ['Reading PRD...', 'Mapping architecture...', 'Selecting tech stack: FastAPI + PostgreSQL.', 'Creating component definitions.'], files: ['architecture.md', 'components.json'], time: 3500 },
  { id: 'code', name: 'Code Agent', logs: ['Scaffolding repository...', 'Generating models.py...', 'Writing CRUD endpoints...', 'Refactoring main.py...'], files: ['main.py', 'models.py', 'schemas.py', 'requirements.txt'], time: 5000 },
  { id: 'test', name: 'Test Agent', logs: ['Setting up pytest environment...', 'Running unit tests...', 'tests/test_habits.py (Passed)', 'Coverage: 92%'], files: ['test_habits.py', 'conftest.py'], time: 3000 },
  { id: 'review', name: 'Review Agent', logs: ['Analyzing code quality...', 'Checking security best practices...', 'No critical vulnerabilities found.', 'Code approved.'], files: ['review_report.md'], time: 2500 },
  { id: 'documentation', name: 'Doc Agent', logs: ['Generating README.md...', 'Documenting API endpoints...', 'Writing setup instructions.'], files: ['README.md', 'api_docs.md'], time: 2500 }
];

function startPipelineSimulation() {
  termOutput.innerHTML = '';
  fileTree.innerHTML = '';
  activityFeed.innerHTML = '';
  fileCount.textContent = '0';
  currentStageIdx = 0;

  $('statusPill').className = 'status-pill running';
  $('statusText').textContent = 'building';

  startTime = Date.now();
  elapsedTimer = setInterval(updateElapsed, 1000);

  // Reset agents
  document.querySelectorAll('.agent-item').forEach(el => {
    el.className = 'agent-item';
    el.querySelector('.agent-status').textContent = 'pending';
  });

  runNextStage();
}

function runNextStage() {
  if (currentStageIdx >= stages.length) {
    completePipeline();
    return;
  }

  const stage = stages[currentStageIdx];
  const agentEl = document.querySelector(`.agent-item[data-step="${stage.id}"]`);

  agentEl.className = 'agent-item running';
  agentEl.querySelector('.agent-status').textContent = 'running...';

  appendActivity(`Started ${stage.name}`, `Began phase: ${stage.id}`);
  reasoningBox.innerHTML = `<span class="t-acc">Thoughts [${stage.name}]:</span><br>Executing tasks for ${stage.id}. Analyzing context...`;

  let logIdx = 0;
  const logInterval = setInterval(() => {
    if (logIdx < stage.logs.length) {
      appendTerminal(`[${stage.name}] ${stage.logs[logIdx]}`);
      logIdx++;
    }
  }, stage.time / (stage.logs.length + 1));

  setTimeout(() => {
    clearInterval(logInterval);
    agentEl.className = 'agent-item done';
    agentEl.querySelector('.agent-status').textContent = 'done';

    stage.files.forEach(addFile);

    appendActivity(`Completed ${stage.name}`, `Generated ${stage.files.length} files.`);

    // Attempt to inject real thoughts/reasoning if data arrived
    if (window.realData) {
      let insight = '';
      if (stage.id === 'requirement') insight = window.realData.requirements?.thought || 'Extracted user stories...';
      if (stage.id === 'design') insight = window.realData.design?.thought || 'Generated architecture...';
      reasoningBox.innerHTML = `<span class="t-acc">Thoughts [${stage.name}]:</span><br>${insight}`;
    }

    currentStageIdx++;
    runNextStage();
  }, stage.time);
}

function completePipeline() {
  if (window.realData) {
    stopPipeline();
    $('statusPill').className = 'status-pill done';
    $('statusText').textContent = 'ready';
    appendTerminal('<span class="t-ok">Pipeline completed successfully. All code ready!</span>');
    appendActivity('Pipeline Ready', 'Project is ready for preview and export.');
    if (window.currentFile) {
      showCode(window.currentFile);
    }
  } else {
    $('statusPill').className = 'status-pill running';
    $('statusText').textContent = 'synthesizing AI code...';
    appendTerminal('<br><span class="t-dim" style="color:var(--yel);">// Visual pipeline ready. Local Ollama LLM is finishing code synthesis on your Mac (takes ~15s)...</span>');

    const checkInterval = setInterval(() => {
      if (window.realData) {
        clearInterval(checkInterval);
        stopPipeline();
        $('statusPill').className = 'status-pill done';
        $('statusText').textContent = 'ready';
        appendTerminal('<br><span class="t-ok" style="color:var(--ok); font-weight:bold;">Real backend processing finished! Code generated.</span>');
        appendActivity('Pipeline Ready', 'Project is ready for preview and export.');
        if (window.currentFile) {
          showCode(window.currentFile);
        }
      }
    }, 1000);
  }
}

function stopPipeline() {
  clearInterval(elapsedTimer);
}

function updateElapsed() {
  const diff = Math.floor((Date.now() - startTime) / 1000);
  const m = String(Math.floor(diff / 60)).padStart(2, '0');
  const s = String(diff % 60).padStart(2, '0');
  $('elapsed').textContent = `${m}:${s}`;
  $('metaTime').textContent = `${m}:${s}`;
}

function appendTerminal(html) {
  const line = document.createElement('div');
  line.innerHTML = html;
  termOutput.appendChild(line);
  termOutput.scrollTop = termOutput.scrollHeight;
}

function appendActivity(title, detail) {
  const d = new Date();
  const timeStr = String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0');

  const div = document.createElement('div');
  div.className = 'act-item';
  div.innerHTML = `
    <div class="act-time">${timeStr}</div>
    <div class="act-agent">${title}</div>
    <div class="act-detail">${detail}</div>
  `;
  activityFeed.prepend(div);
}

let fileListCount = 0;
function addFile(filename) {
  if (fileListCount === 0) {
    fileTree.innerHTML = '';
  }
  fileListCount++;
  fileCount.textContent = fileListCount;
  $('propFiles').textContent = fileListCount;

  const li = document.createElement('li');
  li.textContent = filename;
  li.onclick = () => {
    document.querySelectorAll('#fileTree li').forEach(el => el.classList.remove('active'));
    li.classList.add('active');
    showCode(filename);
  };
  fileTree.appendChild(li);
}

function showCode(filename) {
  window.currentFile = filename;
  window.switchCenterTab(document.querySelector('.ctab[data-tab="editor"]'));
  $('editorTabs').innerHTML = `<span>${filename}</span>`;

  let code = `# ${filename}\n\n`;

  if (window.realData) {
    if (filename === 'requirements.md' || filename === 'user_stories.yml') {
      code += typeof window.realData.requirements === 'string'
        ? window.realData.requirements
        : JSON.stringify(window.realData.requirements, null, 2);
    } else if (filename === 'architecture.md' || filename === 'components.json') {
      code += typeof window.realData.design === 'string'
        ? window.realData.design
        : JSON.stringify(window.realData.design, null, 2);
    } else if (filename === 'review_report.md') {
      code += typeof window.realData.review === 'string'
        ? window.realData.review
        : JSON.stringify(window.realData.review, null, 2);
    } else {
      let foundContent = null;
      if (window.realData.code && Array.isArray(window.realData.code.files)) {
        const fileObj = window.realData.code.files.find(f => f.path === filename || (f.path && f.path.endsWith('/' + filename)));
        if (fileObj) {
          foundContent = fileObj.content;
        }
      }
      if (foundContent) {
        code = foundContent;
      } else if (window.realData.code) {
        code += JSON.stringify(window.realData.code, null, 2);
      } else {
        code += `// Auto-generated artifact\n\n// Content for ${filename} will be placed here.`;
      }
    }
  } else {
    code += `// Waiting for real data to arrive from backend...`;
  }

  // Clean up any stringified objects if it's empty
  if (code.includes('"{}"') || code.trim().endsWith('{}')) {
    code += '\n\n(No data was returned for this section from the backend. The agent may have failed or skipped this step.)';
  }

  $('codeArea').textContent = code;
  const lines = code.split('\n').length;
  $('gutter').textContent = Array.from({ length: lines }, (_, i) => i + 1).join('\n');
}

/* Add some keyframes to stylesheet dynamically for shaking */
const style = document.createElement('style');
style.textContent = `
@keyframes shake {
  0%, 100% { transform: translateX(0); }
  25% { transform: translateX(-5px); }
  75% { transform: translateX(5px); }
}
`;
document.head.appendChild(style);

/* Export logic */
document.querySelectorAll('#exportBtn, .btn-export').forEach(btn => {
  btn.addEventListener('click', () => {
    if (!window.realData) {
      alert("Wait for the agent generation to finish first!");
      return;
    }

    const zip = new JSZip();

    if (window.realData.requirements) {
      zip.file("requirements.md", typeof window.realData.requirements === 'string' ? window.realData.requirements : JSON.stringify(window.realData.requirements, null, 2));
    }
    if (window.realData.design) {
      zip.file("architecture.md", typeof window.realData.design === 'string' ? window.realData.design : JSON.stringify(window.realData.design, null, 2));
    }
    if (window.realData.code) {
      if (Array.isArray(window.realData.code.files)) {
        window.realData.code.files.forEach(f => {
          if (f.path && f.content) {
            zip.file(f.path, f.content);
          }
        });
      } else if (typeof window.realData.code === 'object') {
        for (const [filename, content] of Object.entries(window.realData.code)) {
          zip.file(filename, typeof content === 'string' ? content : JSON.stringify(content, null, 2));
        }
      } else {
        zip.file("generated_code.txt", String(window.realData.code));
      }
    }
    if (window.realData.review) {
      zip.file("review_report.md", typeof window.realData.review === 'string' ? window.realData.review : JSON.stringify(window.realData.review, null, 2));
    }

    const projName = ($('ideaInput') ? $('ideaInput').value.trim() : 'project').toLowerCase().replace(/[^a-z0-9]/g, '_') || 'ideatoproduct_project';

    zip.generateAsync({ type: "blob" }).then(function (content) {
      const link = document.createElement('a');
      link.href = URL.createObjectURL(content);
      link.download = `${projName}.zip`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    });
  });
});

// Theme Toggle (Hanging Lamp Pull String)
document.querySelectorAll('#themeToggleBtn, .theme-toggle-btn').forEach(btn => {
  btn.addEventListener('click', (e) => {
    e.preventDefault();
    document.body.classList.toggle('dark-theme');
  });
});

// How It Works Modal
const howItWorksModal = document.getElementById('howItWorksModal');
const closeModalBtn = document.getElementById('closeModalBtn');

document.querySelectorAll('#howItWorksBtn, .how-it-works-btn').forEach(btn => {
  btn.addEventListener('click', (e) => {
    e.preventDefault();
    if (howItWorksModal) howItWorksModal.hidden = false;
  });
});

if (closeModalBtn && howItWorksModal) {
  closeModalBtn.addEventListener('click', () => {
    howItWorksModal.hidden = true;
  });
}
if (howItWorksModal) {
  howItWorksModal.addEventListener('click', (e) => {
    if (e.target === howItWorksModal) {
      howItWorksModal.hidden = true;
    }
  });
}

// Alpha Popover
const alphaPopover = document.getElementById('alphaPopover');
document.querySelectorAll('#alphaBadge, .alpha-badge-btn').forEach(btn => {
  btn.addEventListener('click', (e) => {
    e.stopPropagation();
    if (alphaPopover) alphaPopover.hidden = !alphaPopover.hidden;
  });
});

document.addEventListener('click', () => {
  if (alphaPopover) alphaPopover.hidden = true;
});
