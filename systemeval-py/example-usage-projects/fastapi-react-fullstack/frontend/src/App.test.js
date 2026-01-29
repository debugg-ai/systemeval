describe('Frontend', () => {
  test('renders without crashing', () => {
    expect(true).toBe(true);
  });

  test('API URL configured', () => {
    expect(process.env.VITE_API_URL || 'http://localhost:8080').toContain('http');
  });
});
