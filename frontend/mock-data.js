/* ─────────────────────────────────────────────────
   mock-data.js
   All demo/mock data lives here. Replace with
   apiService calls when backend is ready.
   ───────────────────────────────────────────────── */

'use strict';

window.MockData = {

  project: {
    id: 'project-001',
    name: 'Habit Tracker',
    idea: 'A minimalist habit tracker where users set daily goals and check them off. Streaks reset at midnight.',
    status: 'building', // building | review | ready
    started: '14:02',
    elapsed: '03:12',
    currentAgent: 'code',
  },

  pipeline: [
    { id: 'requirement', label: 'Requirements', status: 'done', completedAt: '14:03', count: '12 requirements' },
    { id: 'design', label: 'Design', status: 'done', completedAt: '14:06', count: '8 components' },
    { id: 'code', label: 'Code', status: 'running', completedAt: null, count: null },
    { id: 'test', label: 'Tests', status: 'queued', completedAt: null, count: null },
    { id: 'review', label: 'Review', status: 'queued', completedAt: null, count: null },
    { id: 'documentation', label: 'Docs', status: 'queued', completedAt: null, count: null },
  ],

  activity: [
    { time: '14:02', agent: 'Requirement Agent', event: 'started', detail: 'Analyzing idea and extracting scope…' },
    { time: '14:03', agent: 'Requirement Agent', event: 'completed', detail: '12 requirements generated, 4 user stories.' },
    { time: '14:03', agent: 'Design Agent', event: 'started', detail: 'Mapping architecture from requirements…' },
    { time: '14:05', agent: 'Design Agent', event: 'progress', detail: '8 components identified, 3 API endpoints defined.' },
    { time: '14:06', agent: 'Design Agent', event: 'completed', detail: 'Architecture finalized.' },
    { time: '14:06', agent: 'Code Agent', event: 'started', detail: 'Scaffolding repository…' },
    { time: '14:08', agent: 'Code Agent', event: 'progress', detail: 'Generating source files using claude-sonnet-4-6…' },
  ],

  requirements: {
    problem_statement: 'Users need a simple, low-friction way to build and sustain daily habits. Existing tools are either too complex or don\'t provide enough accountability.',
    objectives: [
      'Allow users to create named daily habits',
      'Track daily completions and calculate streaks',
      'Reset uncompleted habits at midnight',
      'Deliver weekly summaries via email',
    ],
    actors: ['End User', 'System (cron scheduler)', 'Email Service'],
    user_stories: [
      { id: 'US-001', role: 'user', want: 'create a new habit with a name and optional description', so_that: 'I can start tracking it', priority: 'high' },
      { id: 'US-002', role: 'user', want: 'mark a habit as complete each day', so_that: 'my streak is updated', priority: 'high' },
      { id: 'US-003', role: 'user', want: 'view my current streaks for all habits', so_that: 'I can see my progress at a glance', priority: 'high' },
      { id: 'US-004', role: 'user', want: 'receive a weekly summary email on Sunday', so_that: 'I can reflect on my week', priority: 'medium' },
    ],
    functional_requirements: [
      'FR-001: Users can create habits with a name (required) and description (optional)',
      'FR-002: Users can mark a habit complete once per day',
      'FR-003: Streak counter increments on consecutive daily completions',
      'FR-004: Streak resets to 0 if a day is missed',
      'FR-005: Weekly summary email sent every Sunday at 09:00 local time',
      'FR-006: Users can archive (soft-delete) a habit',
    ],
    non_functional_requirements: [
      'NFR-001: Page load under 2 seconds on a standard connection',
      'NFR-002: API response time under 200ms for read operations',
      'NFR-003: Streak calculations must be timezone-aware',
      'NFR-004: Email delivery must be idempotent (no duplicate weekly sends)',
    ],
    acceptance_criteria: [
      'AC-001: A habit can be created with a name between 2–80 characters',
      'AC-002: Completing a habit twice on the same day has no effect',
      'AC-003: Streak counter displays correctly after timezone change',
      'AC-004: Weekly email contains all habits and their 7-day completion summary',
    ],
    in_scope: ['Habit creation', 'Daily check-off', 'Streak tracking', 'Weekly email summary'],
    out_of_scope: ['Social/sharing features', 'Mobile native app', 'Push notifications', 'Habit templates library'],
    constraints: ['Must support modern browsers (Chrome 90+, Firefox 88+, Safari 14+)', 'Email delivery via SMTP — no third-party email SaaS required'],
    open_questions: ['Should missed-day forgiveness (vacation mode) be included in V1?', 'Should streaks persist across habit edits?'],
  },

  design: {
    architecture: 'REST API with server-side rendering for the frontend. Stateless API layer, PostgreSQL for persistence.',
    components: [
      { id: 'C-01', name: 'Habit Service', responsibility: 'CRUD operations for habits', deps: ['C-04'] },
      { id: 'C-02', name: 'Completion Service', responsibility: 'Records daily completions, idempotency checks', deps: ['C-04'] },
      { id: 'C-03', name: 'Streak Calculator', responsibility: 'Computes and updates streak values', deps: ['C-02', 'C-04'] },
      { id: 'C-04', name: 'PostgreSQL Database', responsibility: 'Primary data store', deps: [] },
      { id: 'C-05', name: 'Scheduler (cron)', responsibility: 'Triggers midnight resets and Sunday summary', deps: ['C-02', 'C-06'] },
      { id: 'C-06', name: 'Email Service', responsibility: 'Renders and sends weekly summary email', deps: [] },
      { id: 'C-07', name: 'REST API (FastAPI)', responsibility: 'Exposes HTTP endpoints to frontend', deps: ['C-01', 'C-02', 'C-03'] },
      { id: 'C-08', name: 'Frontend (Jinja/HTML)', responsibility: 'Server-rendered UI', deps: ['C-07'] },
    ],
    api_endpoints: [
      'GET  /habits               — List all habits',
      'POST /habits               — Create a habit',
      'GET  /habits/{id}          — Get habit detail',
      'PUT  /habits/{id}          — Update habit',
      'DELETE /habits/{id}        — Archive habit',
      'POST /habits/{id}/complete — Record daily completion',
    ],
    decisions: [
      { id: 'DEC-001', decision: 'Use FastAPI for the REST API', reason: 'Fast async support, automatic OpenAPI docs, well-typed.', impacted: ['C-07'] },
      { id: 'DEC-002', decision: 'Use PostgreSQL over SQLite', reason: 'Timezone-aware timestamps (TIMESTAMPTZ) natively supported.', impacted: ['C-04'] },
      { id: 'DEC-003', decision: 'Server-side rendering for V1 UI', reason: 'Reduces complexity; no JS framework needed for V1 feature set.', impacted: ['C-08'] },
    ],
    edge_cases: [
      'User completes habit at 23:59 — must count for the correct day in their timezone',
      'User changes timezone — streaks must not break',
      'SMTP failure during weekly send — must retry without duplicate delivery',
    ],
  },

  code: {
    files: [
      { path: 'app/main.py', description: 'FastAPI app entrypoint' },
      { path: 'app/models.py', description: 'SQLAlchemy ORM models' },
      { path: 'app/schemas.py', description: 'Pydantic request/response schemas' },
      { path: 'app/routes/habits.py', description: 'Habit CRUD endpoints' },
      { path: 'app/routes/complete.py', description: 'Completion recording endpoint' },
      { path: 'app/services/streak.py', description: 'Streak calculation logic' },
      { path: 'app/services/email.py', description: 'Weekly summary email sender' },
      { path: 'app/scheduler.py', description: 'APScheduler cron jobs' },
      { path: 'tests/test_habits.py', description: 'Unit tests for habit CRUD' },
      { path: 'tests/test_streaks.py', description: 'Unit tests for streak logic' },
      { path: 'alembic/', description: 'Database migrations' },
      { path: 'requirements.txt', description: 'Python dependencies' },
      { path: 'README.md', description: 'Setup and usage guide' },
    ],
    dependencies: ['fastapi', 'uvicorn', 'sqlalchemy', 'alembic', 'psycopg2-binary', 'apscheduler', 'jinja2', 'pydantic'],
    setup_instructions: 'pip install -r requirements.txt\nalembic upgrade head\nuvicorn app.main:app --reload',
    generated_project_path: './generated_projects/project-001',
  },

  tests: {
    status: 'pass',
    passed: 8,
    failed: 1,
    errors: 0,
    duration: '4.82s',
    cases: [
      { id: 'T-001', name: 'Create habit', status: 'pass', expected: '201', actual: '201' },
      { id: 'T-002', name: 'List habits', status: 'pass', expected: '200', actual: '200' },
      { id: 'T-003', name: 'Complete habit', status: 'pass', expected: '200', actual: '200' },
      { id: 'T-004', name: 'Idempotent completion', status: 'pass', expected: '200', actual: '200' },
      { id: 'T-005', name: 'Streak increments', status: 'pass', expected: '2', actual: '2' },
      { id: 'T-006', name: 'Streak resets on miss', status: 'pass', expected: '0', actual: '0' },
      { id: 'T-007', name: 'Archive habit', status: 'pass', expected: '204', actual: '204' },
      { id: 'T-008', name: 'Invalid date handling', status: 'pass', expected: '400', actual: '400' },
      {
        id: 'T-009', name: 'Timezone boundary streak', status: 'fail', expected: '1', actual: '0',
        logs: 'AssertionError: streak should be 1 for completion at 23:59 UTC-5\nExpected: 1\nGot: 0\nFile: tests/test_streaks.py line 87'
      },
    ],
    output: 'tests/test_habits.py ........\ntests/test_streaks.py ....F\n\nFAILED tests/test_streaks.py::test_timezone_boundary - AssertionError',
  },

  review: {
    approval_status: 'pending',
    checks: [
      { area: 'Requirements', status: 'pass', note: 'All functional requirements addressed.' },
      { area: 'Design', status: 'pass', note: 'Architecture consistent with requirements.' },
      { area: 'Implementation', status: 'warn', note: 'Missing input validation on habit name field.' },
      { area: 'Tests', status: 'warn', note: '1 test failing — timezone boundary case.' },
      { area: 'Security', status: 'warn', note: 'No rate limiting on /habits/{id}/complete.' },
      { area: 'Documentation', status: 'pass', note: 'README covers setup and usage.' },
    ],
    findings: [
      { id: 'F-001', severity: 'medium', title: 'Missing input validation', detail: 'The habit name field accepts any string including empty and very long inputs. Add validation with Pydantic Field constraints.' },
      { id: 'F-002', severity: 'low', title: 'No rate limiting on completion endpoint', detail: 'POST /habits/{id}/complete has no rate limiting. A user could spam the endpoint.' },
      { id: 'F-003', severity: 'low', title: 'Insufficient logging', detail: 'Streak calculation lacks structured logging. Difficult to debug production issues.' },
    ],
    summary: 'The implementation covers the core requirements but has 3 findings. The failing timezone test (T-009) must be resolved before approval. Input validation is a medium-severity issue.',
    rationale: null,
  },

  documentation: {
    overview: 'Habit Tracker is a server-rendered web application built with FastAPI and PostgreSQL. Users create daily habits, mark them complete, and build streaks. A scheduled job sends weekly summaries via email.',
    getting_started: 'pip install -r requirements.txt\nalembic upgrade head\nuvicorn app.main:app --reload --port 8000\n\nVisit http://localhost:8000',
    features: ['Create and manage daily habits', 'Mark habits complete with one click', 'Automatic streak tracking', 'Weekly email summary (Sunday 09:00)', 'Archive habits without data loss'],
    api_reference: 'Full API documentation auto-generated at http://localhost:8000/docs (Swagger UI).',
    architecture: 'FastAPI → SQLAlchemy ORM → PostgreSQL. APScheduler handles cron. Jinja2 for server-rendered templates.',
    known_limitations: ['Streaks are timezone-sensitive — a known bug exists at timezone boundary (T-009)', 'No mobile-native app in V1', 'Email requires working SMTP credentials'],
  },

  artifacts: {
    requirement: [
      { version: 2, status: 'current', timestamp: '14:03', changes: 'Added NFR-004 (email idempotency) after market grounding' },
      { version: 1, status: 'previous', timestamp: '14:02', changes: 'Initial requirements from idea' },
    ],
    design: [
      { version: 1, status: 'current', timestamp: '14:06', changes: 'Initial architecture and component map' },
    ],
    code: [
      { version: 1, status: 'current', timestamp: '14:08', changes: 'Repository scaffold and source generation' },
    ],
    test: [
      { version: 1, status: 'current', timestamp: '14:14', changes: 'First test run — 8/9 passing' },
    ],
    review: [
      { version: 1, status: 'current', timestamp: '14:15', changes: 'Initial review — 3 findings, pending approval' },
    ],
  },

  memory: {
    decisions: [
      { id: 'DEC-001', title: 'Use FastAPI', detail: 'Chosen for async support and automatic OpenAPI documentation.', impact: ['Design', 'Code'] },
      { id: 'DEC-002', title: 'PostgreSQL over SQLite', detail: 'SQLite lacks native TIMESTAMPTZ. Timezone-aware streaks require PostgreSQL.', impact: ['Design', 'Code', 'Tests'] },
    ],
    constraints: [
      { id: 'CON-001', title: 'Modern browser support only', detail: 'Chrome 90+, Firefox 88+, Safari 14+. No IE11.' },
      { id: 'CON-002', title: 'No third-party email SaaS', detail: 'Must use SMTP directly. No SendGrid/Mailgun dependency.' },
    ],
    rejected: [
      { title: 'GraphQL over REST', reason: 'Unnecessary complexity for a V1 CRUD application.' },
      { title: 'SQLite for database', reason: 'Lacks TIMESTAMPTZ support needed for timezone-aware streaks.' },
      { title: 'React frontend', reason: 'V1 feature set does not require a JS framework. Server rendering is sufficient.' },
    ],
    previous_findings: [
      { from: 'Review v1', title: 'Input validation missing', status: 'open' },
      { from: 'Review v1', title: 'Timezone boundary bug (T-009)', status: 'open' },
    ],
  },

};
