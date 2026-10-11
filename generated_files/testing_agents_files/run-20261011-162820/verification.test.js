const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');

test('TC-01: logic.js exports expected functions', () => {
  const logic = require('./logic.js');
  assert.strictEqual(typeof logic.STORAGE_KEY, 'string');
  assert.strictEqual(typeof logic.loadTasks, 'function');
  assert.strictEqual(typeof logic.saveTasks, 'function');
  assert.strictEqual(typeof logic.addTask, 'function');
  assert.strictEqual(typeof logic.toggleTask, 'function');
});

test('TC-02: addTask adds task with non-empty title (AC-01)', () => {
  const logic = require('./logic.js');
  const tasks = [];
  const result = logic.addTask(tasks, 'Buy groceries');
  assert.deepStrictEqual(result, [
    { id: 1, title: 'Buy groceries', completed: false }
  ]);
});

test('TC-03: addTask throws on empty or whitespace title (EDGE-02)', () => {
  const logic = require('./logic.js');
  const tasks = [];
  assert.throws(() => logic.addTask(tasks, ''), /Task title is required/);
  assert.throws(() => logic.addTask(tasks, '   '), /Task title is required/);
});

test('TC-04: toggleTask toggles completion state (AC-03)', () => {
  const logic = require('./logic.js');
  const tasks = [{ id: 1, title: 'Test', completed: false }];
  const result = logic.toggleTask(tasks, 1);
  assert.deepStrictEqual(result, [
    { id: 1, title: 'Test', completed: true }
  ]);
  const result2 = logic.toggleTask(result, 1);
  assert.deepStrictEqual(result2, [
    { id: 1, title: 'Test', completed: false }
  ]);
});

test('TC-05: saveTasks and loadTasks persist data (AC-04)', () => {
  const logic = require('./logic.js');
  const mockStorage = {
    getItem: () => null,
    setItem: (key, value) => { mockStorage.last = { key, value }; }
  };
  const tasks = [{ id: 1, title: 'Test', completed: true }];
  logic.saveTasks(tasks, mockStorage);
  assert.deepStrictEqual(mockStorage.last, {
    key: logic.STORAGE_KEY,
    value: JSON.stringify(tasks)
  });
  const loaded = logic.loadTasks(mockStorage);
  assert.deepStrictEqual(loaded, tasks);
});

test('TC-06: index.html contains required elements', () => {
  const html = fs.readFileSync('./index.html', 'utf8');
  assert.ok(html.includes('<form id="task-form">'));
  assert.ok(html.includes('<input id="task-input"'));
  assert.ok(html.includes('<ul id="task-list">'));
  assert.ok(html.includes('<p id="empty-state">No tasks yet.</p>'));
});

test('TC-07: app.js defines renderTasks function', () => {
  const app = fs.readFileSync('./app.js', 'utf8');
  assert.ok(app.includes('function renderTasks() {'));
});

test('TC-08: app.js includes form submit event listener', () => {
  const app = fs.readFileSync('./app.js', 'utf8');
  assert.ok(app.includes("form.addEventListener('submit',"));
});

test('TC-09: app.js includes task button click event listener', () => {
  const app = fs.readFileSync('./app.js', 'utf8');
  assert.ok(app.includes("button.addEventListener('click',"));
});

test('TC-10: app.js includes input event listener to clear validity', () => {
  const app = fs.readFileSync('./app.js', 'utf8');
  assert.ok(app.includes("input.addEventListener('input',"));
});

test('TC-11: app.js toggles emptyState visibility based on task count (EDGE-01)', () => {
  const app = fs.readFileSync('./app.js', 'utf8');
  assert.ok(app.includes("emptyState.classList.toggle('hidden', tasks.length > 0);"));
});