const form = document.querySelector('#task-form');
const input = document.querySelector('#task-input');
const list = document.querySelector('#task-list');
const emptyState = document.querySelector('#empty-state');
let tasks = TaskLogic.loadTasks();

function renderTasks() {
  list.replaceChildren();
  emptyState.classList.toggle('hidden', tasks.length > 0);
  for (const task of tasks) {
    const item = document.createElement('li');
    const button = document.createElement('button');
    button.type = 'button';
    button.textContent = task.title;
    button.classList.toggle('completed', task.completed);
    button.addEventListener('click', () => {
      tasks = TaskLogic.toggleTask(tasks, task.id);
      TaskLogic.saveTasks(tasks);
      renderTasks();
    });
    item.append(button);
    list.append(item);
  }
}

form.addEventListener('submit', (event) => {
  event.preventDefault();
  try {
    tasks = TaskLogic.addTask(tasks, input.value);
    TaskLogic.saveTasks(tasks);
    input.value = '';
    renderTasks();
  } catch (error) {
    input.setCustomValidity(error.message);
    input.reportValidity();
  }
});

input.addEventListener('input', () => input.setCustomValidity(''));
renderTasks();
