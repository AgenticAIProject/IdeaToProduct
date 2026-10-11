(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.TaskLogic = api;
})(globalThis, function () {
  const STORAGE_KEY = 'task-tracker.tasks';

  function loadTasks(storage = globalThis.localStorage) {
    try {
      const saved = storage.getItem(STORAGE_KEY);
      const tasks = saved ? JSON.parse(saved) : [];
      return Array.isArray(tasks) ? tasks : [];
    } catch {
      return [];
    }
  }

  function saveTasks(tasks, storage = globalThis.localStorage) {
    storage.setItem(STORAGE_KEY, JSON.stringify(tasks));
  }

  function addTask(tasks, title) {
    const normalizedTitle = String(title).trim();
    if (!normalizedTitle) throw new Error('Task title is required.');
    const id = Math.max(0, ...tasks.map((task) => task.id)) + 1;
    return [...tasks, { id, title: normalizedTitle, completed: false }];
  }

  function toggleTask(tasks, id) {
    if (!tasks.some((task) => task.id === id)) throw new Error('Task not found.');
    return tasks.map((task) => task.id === id ? { ...task, completed: !task.completed } : task);
  }

  return { STORAGE_KEY, loadTasks, saveTasks, addTask, toggleTask };
});
