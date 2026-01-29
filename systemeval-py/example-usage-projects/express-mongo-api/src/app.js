const express = require('express');

const app = express();
app.use(express.json());

// In-memory todos store (no MongoDB connection required to start)
const todos = [
  { id: 1, title: 'Buy groceries', done: false },
  { id: 2, title: 'Write tests', done: true },
];
let nextId = 3;

// Health check
app.get('/health', (req, res) => {
  res.json({ status: 'ok', uptime: process.uptime() });
});

// List todos
app.get('/api/todos', (req, res) => {
  res.json(todos);
});

// Create todo
app.post('/api/todos', (req, res) => {
  const { title } = req.body;
  if (!title) {
    return res.status(400).json({ error: 'title is required' });
  }
  const todo = { id: nextId++, title, done: false };
  todos.push(todo);
  res.status(201).json(todo);
});

// Start server only when run directly (not when imported for testing)
if (require.main === module) {
  const PORT = process.env.PORT || 3000;
  app.server = app.listen(PORT, () => {
    console.log(`Server running on port ${PORT}`);
  });
}

module.exports = app;
