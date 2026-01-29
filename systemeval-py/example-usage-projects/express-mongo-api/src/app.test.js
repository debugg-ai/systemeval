const request = require('supertest');
const app = require('./app');

describe('Health', () => {
  test('GET /health returns 200', async () => {
    const res = await request(app).get('/health');
    expect(res.statusCode).toBe(200);
    expect(res.body.status).toBe('ok');
  });
});

describe('Todos API', () => {
  test('GET /api/todos returns list', async () => {
    const res = await request(app).get('/api/todos');
    expect(res.statusCode).toBe(200);
    expect(Array.isArray(res.body)).toBe(true);
  });

  test('GET /api/todos has items', async () => {
    const res = await request(app).get('/api/todos');
    expect(res.body.length).toBeGreaterThan(0);
    expect(res.body[0]).toHaveProperty('id');
    expect(res.body[0]).toHaveProperty('title');
    expect(res.body[0]).toHaveProperty('done');
  });

  test('POST /api/todos creates todo', async () => {
    const res = await request(app)
      .post('/api/todos')
      .send({ title: 'Test todo' })
      .set('Content-Type', 'application/json');
    expect(res.statusCode).toBe(201);
    expect(res.body.title).toBe('Test todo');
    expect(res.body.done).toBe(false);
    expect(res.body).toHaveProperty('id');
  });
});

afterAll(() => {
  if (app.server) app.server.close();
});
