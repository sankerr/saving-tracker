import { t } from '../copy';

export const MINIMUM_PENSION = 5306;
export const TAX_FREE_LUMP_SUM = 1140000;
export const ESTIMATED_TAX_RATE = 0.35;
export const EARLY_WITHDRAWAL_PENALTY = 0.35;
export const MIN_RETIREMENT_AGE_LEGAL = 60;

const MULTIPLIER_TABLE = {
  male: { 60: 210, 62: 200, 65: 190, 67: 185 },
  female: { 60: 220, 62: 210, 65: 200, 67: 195 },
} as const;
const MULTIPLIER_AGES = [60, 62, 65, 67] as const;

export type Gender = 'male' | 'female';

export type SimInputs = {
  gender: Gender | string;
  birthDate: string;
  retirementAge: number | string;
  comprehensiveIls: number | string;
  supplementaryIls?: number | string;
  targetPensionIls?: number | string;
};

export type CashTax = {
  cashGross: number;
  taxFreeCash: number;
  taxableCash: number;
  estimatedTax: number;
  netCash: number;
};

export type PathResult = CashTax & {
  monthlyPension: number;
  lockedCapital: number;
};

export type SimOk = {
  ok: true;
  warnings: string[];
  birthDate: string;
  gender: Gender;
  retirementAge: number;
  retirementDate: { year: number; month: number; day: number; label: string } | null;
  currentAge: number | null;
  multiplier: number;
  comprehensiveIls: number;
  supplementaryIls: number;
  totalBalance: number;
  bounds: { minPension: number; maxPension: number; targetPension: number };
  path1: PathResult;
  path2: PathResult;
  path3: PathResult;
  path4: PathResult;
};

export type SimFail = { ok: false; error: string };
export type SimResult = SimOk | SimFail;

function monthName(monthIndex: number): string {
  return t(`rsim.month.${monthIndex + 1}`);
}

function parseDate(iso: string) {
  if (!iso) return null;
  const d = new Date(`${iso}T12:00:00`);
  return Number.isNaN(d.getTime()) ? null : d;
}

export function currentAge(birthDate: string): number | null {
  const b = parseDate(birthDate);
  if (!b) return null;
  const today = new Date();
  let age = today.getFullYear() - b.getFullYear();
  const m = today.getMonth() - b.getMonth();
  if (m < 0 || (m === 0 && today.getDate() < b.getDate())) age -= 1;
  return age;
}

export function retirementDate(birthDate: string, retirementAge: number) {
  const b = parseDate(birthDate);
  if (!b || retirementAge == null || Number.isNaN(+retirementAge)) return null;
  const year = b.getFullYear() + Math.floor(+retirementAge);
  const month = b.getMonth() + 1;
  const label = `${monthName(b.getMonth())} ${year}`;
  return { year, month, day: b.getDate(), label };
}

export function multiplier(gender: string, retirementAge: number): number {
  const g: Gender = gender === 'female' ? 'female' : 'male';
  const table = MULTIPLIER_TABLE[g];
  const age = +retirementAge;
  if (age <= MULTIPLIER_AGES[0]) return table[MULTIPLIER_AGES[0]];
  if (age >= MULTIPLIER_AGES[MULTIPLIER_AGES.length - 1]) {
    return table[MULTIPLIER_AGES[MULTIPLIER_AGES.length - 1]];
  }
  for (let i = 0; i < MULTIPLIER_AGES.length - 1; i++) {
    const a0 = MULTIPLIER_AGES[i]!;
    const a1 = MULTIPLIER_AGES[i + 1]!;
    if (age >= a0 && age <= a1) {
      const frac = (age - a0) / (a1 - a0);
      return table[a0] + frac * (table[a1] - table[a0]);
    }
  }
  return table[60];
}

export function calcCashTax(cashGross: number): CashTax {
  const gross = Math.max(0, cashGross);
  const taxFreeCash = Math.min(gross, TAX_FREE_LUMP_SUM);
  const taxableCash = gross - taxFreeCash;
  const estimatedTax = taxableCash * ESTIMATED_TAX_RATE;
  const netCash = gross - estimatedTax;
  return { cashGross: gross, taxFreeCash, taxableCash, estimatedTax, netCash };
}

export function simulate(inputs: SimInputs): SimResult {
  const gender: Gender = inputs.gender === 'female' ? 'female' : 'male';
  const birthDate = inputs.birthDate;
  const retirementAge = +inputs.retirementAge;
  const comprehensiveIls = Math.max(0, +inputs.comprehensiveIls || 0);
  const supplementaryIls = Math.max(0, +(inputs.supplementaryIls ?? 0) || 0);
  const totalBalance = comprehensiveIls + supplementaryIls;
  const warnings: string[] = [];

  if (!birthDate) return { ok: false, error: t('rsim.err.birthRequired') };
  if (Number.isNaN(retirementAge) || retirementAge < 55 || retirementAge > 75) {
    return { ok: false, error: t('rsim.err.ageRange') };
  }
  if (totalBalance <= 0) return { ok: false, error: t('rsim.err.positiveBalance') };

  const retDate = retirementDate(birthDate, retirementAge);
  const mult = multiplier(gender, retirementAge);
  const maxPension = totalBalance / mult;
  const minPension = MINIMUM_PENSION;

  if (retirementAge < MIN_RETIREMENT_AGE_LEGAL) {
    warnings.push(
      t('rsim.warn.earlyRetirement', {
        age: MIN_RETIREMENT_AGE_LEGAL,
        penalty: EARLY_WITHDRAWAL_PENALTY * 100,
      }),
    );
  }

  let targetPension = +(inputs.targetPensionIls ?? NaN);
  if (Number.isNaN(targetPension)) targetPension = Math.min(20000, maxPension);
  if (maxPension < minPension) {
    warnings.push(t('rsim.warn.balanceTooLow'));
    targetPension = Math.max(0, maxPension);
  } else {
    targetPension = Math.max(minPension, Math.min(maxPension, targetPension));
  }

  const path1: PathResult = {
    monthlyPension: totalBalance / mult,
    lockedCapital: totalBalance,
    ...calcCashTax(0),
  };

  const path2Locked = MINIMUM_PENSION * mult;
  const path2CashGross = totalBalance - path2Locked;
  const path2: PathResult = {
    monthlyPension: MINIMUM_PENSION,
    lockedCapital: path2Locked,
    ...calcCashTax(path2CashGross),
  };
  if (path2CashGross < 0) warnings.push(t('rsim.warn.balanceTooLow'));

  const path3Locked = targetPension * mult;
  const path3CashGross = totalBalance - path3Locked;

  const path4Monthly = comprehensiveIls > 0 ? comprehensiveIls / mult : 0;
  const path4: PathResult = {
    monthlyPension: path4Monthly,
    lockedCapital: comprehensiveIls,
    ...calcCashTax(supplementaryIls),
  };
  if (supplementaryIls > 0 && comprehensiveIls <= 0) {
    warnings.push(t('rsim.warn.path4NoMakifa'));
  }

  let path3: PathResult;
  if (path3CashGross < 0) {
    warnings.push(t('rsim.warn.balanceTooLow'));
    path3 = {
      monthlyPension: maxPension,
      lockedCapital: totalBalance,
      ...calcCashTax(0),
    };
    targetPension = maxPension;
  } else {
    path3 = {
      monthlyPension: targetPension,
      lockedCapital: path3Locked,
      ...calcCashTax(path3CashGross),
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
    bounds: { minPension, maxPension, targetPension },
    path1,
    path2,
    path3,
    path4,
  };
}

export function runSelfTest(): { passed: boolean; failures: string[] } {
  const result = simulate({
    gender: 'male',
    birthDate: '1966-01-01',
    retirementAge: 60,
    comprehensiveIls: 6590000,
    supplementaryIls: 0,
    targetPensionIls: 20000,
  });
  const failures: string[] = [];
  const assert = (name: string, cond: boolean) => {
    if (!cond) failures.push(name);
  };
  assert('ok', result.ok === true);
  if (result.ok) {
    assert('multiplier', Math.abs(result.multiplier - 210) < 0.01);
    assert('path3 locked', Math.abs(result.path3.lockedCapital - 4200000) < 1);
    assert('path3 gross', Math.abs(result.path3.cashGross - 2390000) < 1);
    assert('path3 tax', Math.abs(result.path3.estimatedTax - 437500) < 1);
    assert('path3 net', Math.abs(result.path3.netCash - 1952500) < 1);
  }
  const split = simulate({
    gender: 'male',
    birthDate: '1966-01-01',
    retirementAge: 60,
    comprehensiveIls: 4000000,
    supplementaryIls: 2590000,
    targetPensionIls: 20000,
  });
  assert('path4 ok', split.ok === true);
  if (split.ok) {
    assert('path4 monthly', Math.abs(split.path4.monthlyPension - 4000000 / 210) < 1);
    assert('path4 cash', Math.abs(split.path4.cashGross - 2590000) < 1);
    assert('path4 locked', Math.abs(split.path4.lockedCapital - 4000000) < 1);
    assert('path4 tax', Math.abs(split.path4.estimatedTax - 507500) < 1);
    assert('path4 net', Math.abs(split.path4.netCash - 2082500) < 1);
  }
  return { passed: failures.length === 0, failures };
}
