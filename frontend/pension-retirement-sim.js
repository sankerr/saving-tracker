/**
 * Israeli pension retirement withdrawal simulator (2026 rules).
 * Stateless — no persistence. Exposed as window.PensionRetirementSim.
 */
(function (global) {
  'use strict';

  const MINIMUM_PENSION = 5306;
  const TAX_FREE_LUMP_SUM = 1140000;
  const ESTIMATED_TAX_RATE = 0.35;
  const EARLY_WITHDRAWAL_PENALTY = 0.35;
  const MIN_RETIREMENT_AGE_LEGAL = 60;

  const MULTIPLIER_TABLE = {
    male: { 60: 210, 62: 200, 65: 190, 67: 185 },
    female: { 60: 220, 62: 210, 65: 200, 67: 195 },
  };
  const MULTIPLIER_AGES = [60, 62, 65, 67];

  const MONTH_NAMES = [
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December',
  ];

  function parseDate(iso) {
    if (!iso) return null;
    const d = new Date(iso + 'T12:00:00');
    return Number.isNaN(d.getTime()) ? null : d;
  }

  function currentAge(birthDate) {
    const b = parseDate(birthDate);
    if (!b) return null;
    const today = new Date();
    let age = today.getFullYear() - b.getFullYear();
    const m = today.getMonth() - b.getMonth();
    if (m < 0 || (m === 0 && today.getDate() < b.getDate())) age -= 1;
    return age;
  }

  function retirementDate(birthDate, retirementAge) {
    const b = parseDate(birthDate);
    if (!b || retirementAge == null || Number.isNaN(+retirementAge)) return null;
    const year = b.getFullYear() + Math.floor(+retirementAge);
    const month = b.getMonth() + 1;
    const label = `${MONTH_NAMES[b.getMonth()]} ${year}`;
    return { year, month, day: b.getDate(), label };
  }

  function multiplier(gender, retirementAge) {
    const g = gender === 'female' ? 'female' : 'male';
    const table = MULTIPLIER_TABLE[g];
    const age = +retirementAge;
    if (age <= MULTIPLIER_AGES[0]) return table[MULTIPLIER_AGES[0]];
    if (age >= MULTIPLIER_AGES[MULTIPLIER_AGES.length - 1]) {
      return table[MULTIPLIER_AGES[MULTIPLIER_AGES.length - 1]];
    }
    for (let i = 0; i < MULTIPLIER_AGES.length - 1; i++) {
      const a0 = MULTIPLIER_AGES[i];
      const a1 = MULTIPLIER_AGES[i + 1];
      if (age >= a0 && age <= a1) {
        const t = (age - a0) / (a1 - a0);
        return table[a0] + t * (table[a1] - table[a0]);
      }
    }
    return table[60];
  }

  function calcCashTax(cashGross) {
    const gross = Math.max(0, cashGross);
    const taxFreeCash = Math.min(gross, TAX_FREE_LUMP_SUM);
    const taxableCash = gross - taxFreeCash;
    const estimatedTax = taxableCash * ESTIMATED_TAX_RATE;
    const netCash = gross - estimatedTax;
    return {
      cashGross: gross,
      taxFreeCash,
      taxableCash,
      estimatedTax,
      netCash,
    };
  }

  function simulate(inputs) {
    const gender = inputs.gender === 'female' ? 'female' : 'male';
    const birthDate = inputs.birthDate;
    const retirementAge = +inputs.retirementAge;
    const comprehensiveIls = Math.max(0, +inputs.comprehensiveIls || 0);
    const supplementaryIls = Math.max(0, +inputs.supplementaryIls || 0);
    const totalBalance = comprehensiveIls + supplementaryIls;

    const warnings = [];
    if (!birthDate) {
      return { ok: false, error: 'Birth date is required' };
    }
    if (Number.isNaN(retirementAge) || retirementAge < 55 || retirementAge > 75) {
      return { ok: false, error: 'Retirement age must be between 55 and 75' };
    }
    if (totalBalance <= 0) {
      return { ok: false, error: 'Enter at least one positive balance (מקיפה or משלימה)' };
    }

    const retDate = retirementDate(birthDate, retirementAge);
    const mult = multiplier(gender, retirementAge);
    const maxPension = totalBalance / mult;
    const minPension = MINIMUM_PENSION;

    if (retirementAge < MIN_RETIREMENT_AGE_LEGAL) {
      warnings.push(
        `Retirement before age ${MIN_RETIREMENT_AGE_LEGAL} may incur a ${EARLY_WITHDRAWAL_PENALTY * 100}% penalty on certain withdrawals (היוון קצבה). This simulator does not model that penalty on the amounts below.`
      );
    }

    let targetPension = +inputs.targetPensionIls;
    if (Number.isNaN(targetPension)) targetPension = Math.min(20000, maxPension);
    targetPension = Math.max(minPension, Math.min(maxPension, targetPension));

    // Path 1: full pension
    const path1Monthly = totalBalance / mult;
    const path1 = {
      monthlyPension: path1Monthly,
      lockedCapital: totalBalance,
      cashGross: 0,
      ...calcCashTax(0),
    };

    // Path 2: max cash, minimum pension
    const path2Locked = MINIMUM_PENSION * mult;
    const path2CashGross = totalBalance - path2Locked;
    const path2 = {
      monthlyPension: MINIMUM_PENSION,
      lockedCapital: path2Locked,
      ...calcCashTax(path2CashGross),
    };
    if (path2CashGross < 0) {
      warnings.push('Balance is too low for path 2 (minimum pension lock exceeds total balance).');
    }

    // Path 3: custom target pension
    const path3Locked = targetPension * mult;
    const path3CashGross = totalBalance - path3Locked;
    const path3 = {
      monthlyPension: targetPension,
      lockedCapital: path3Locked,
      ...calcCashTax(path3CashGross),
    };
    if (path3CashGross < 0) {
      return {
        ok: false,
        error: `Target pension ₪${Math.round(targetPension).toLocaleString()} requires ₪${Math.round(path3Locked).toLocaleString()} locked — more than your total balance.`,
      };
    }

    return {
      ok: true,
      warnings,
      birthDate,
      gender,
      retirementAge,
      retirementDate: retDate,
      currentAge: currentAge(birthDate),
      multiplier: mult,
      comprehensiveIls,
      supplementaryIls,
      totalBalance,
      bounds: {
        minPension,
        maxPension,
        targetPension,
      },
      path1,
      path2,
      path3,
    };
  }

  function runSelfTest() {
    const result = simulate({
      gender: 'male',
      birthDate: '1966-01-01',
      retirementAge: 60,
      comprehensiveIls: 6590000,
      supplementaryIls: 0,
      targetPensionIls: 20000,
    });
    const failures = [];
    const assert = (name, cond) => { if (!cond) failures.push(name); };

    assert('ok', result.ok === true);
    assert('multiplier', Math.abs(result.multiplier - 210) < 0.01);
    assert('path3 locked', Math.abs(result.path3.lockedCapital - 4200000) < 1);
    assert('path3 gross', Math.abs(result.path3.cashGross - 2390000) < 1);
    assert('path3 tax', Math.abs(result.path3.estimatedTax - 437500) < 1);
    assert('path3 net', Math.abs(result.path3.netCash - 1952500) < 1);

    return { passed: failures.length === 0, failures, result };
  }

  global.PensionRetirementSim = {
    MINIMUM_PENSION,
    TAX_FREE_LUMP_SUM,
    ESTIMATED_TAX_RATE,
    EARLY_WITHDRAWAL_PENALTY,
    MIN_RETIREMENT_AGE_LEGAL,
    currentAge,
    retirementDate,
    multiplier,
    calcCashTax,
    simulate,
    runSelfTest,
  };
})(typeof window !== 'undefined' ? window : globalThis);
