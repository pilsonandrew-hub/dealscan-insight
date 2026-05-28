import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

describe('App route access control', () => {
  it('keeps direct deal detail links behind ProtectedRoute', () => {
    const appSource = readFileSync(resolve(process.cwd(), 'src/App.tsx'), 'utf8');

    expect(appSource).toMatch(/<Route\s+path="\/deal\/:id"\s+element=\{/);
    expect(appSource).toMatch(
      /<Route\s+path="\/deal\/:id"\s+element=\{[\s\S]*?<ProtectedRoute>[\s\S]*?<DealDetail\s*\/>[\s\S]*?<\/ProtectedRoute>[\s\S]*?\}\s*\/>/
    );
  });
});
