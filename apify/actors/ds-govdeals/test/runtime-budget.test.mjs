import { describe, expect, test, vi } from 'vitest';
import { createRuntimeBudget } from '../src/runtime_budget.js';

describe('GovDeals runtime budget', () => {
  test('tracks remaining time and blocks work that cannot fit', () => {
    let now = 1_000;
    const budget = createRuntimeBudget({ totalMs: 10_000, now: () => now });

    expect(budget.elapsedMs()).toBe(0);
    expect(budget.remainingMs()).toBe(10_000);
    expect(budget.hasTimeFor(10_000)).toBe(true);

    now += 6_001;

    expect(budget.elapsedMs()).toBe(6_001);
    expect(budget.remainingMs()).toBe(3_999);
    expect(budget.hasTimeFor(4_000)).toBe(false);
    expect(budget.hasTimeFor(3_999)).toBe(true);
  });

  test('logs and returns false when a phase would exceed the budget', () => {
    let now = 0;
    const logger = { warning: vi.fn() };
    const budget = createRuntimeBudget({ totalMs: 5_000, now: () => now, logger });

    now = 4_500;

    expect(budget.shouldContinue(1_000, 'detail enrichment')).toBe(false);
    expect(logger.warning).toHaveBeenCalledTimes(1);
    expect(logger.warning.mock.calls[0][0]).toContain('Stopping detail enrichment');
  });

  test('uses a safe default for invalid input', () => {
    const budget = createRuntimeBudget({ totalMs: 'not-a-number', now: () => 0 });

    expect(budget.totalMs).toBe(330000);
    expect(budget.hasTimeFor(329999)).toBe(true);
  });
});
