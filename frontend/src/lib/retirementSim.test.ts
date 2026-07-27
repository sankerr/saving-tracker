import { describe, expect, it } from 'vitest';
import { runSelfTest, simulate } from './retirementSim';

describe('retirementSim', () => {
  it('passes legacy self-test vectors', () => {
    const r = runSelfTest();
    expect(r.failures).toEqual([]);
    expect(r.passed).toBe(true);
  });

  it('rejects missing birth date', () => {
    const r = simulate({
      gender: 'male',
      birthDate: '',
      retirementAge: 67,
      comprehensiveIls: 100000,
    });
    expect(r.ok).toBe(false);
  });
});
