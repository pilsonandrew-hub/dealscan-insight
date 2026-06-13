import { readFileSync } from 'fs';
import { resolve } from 'path';
import { describe, expect, test } from 'vitest';

// Behavioral contract for the public-source age/mileage prefilters.
//
// Canonical policy (backend/business_rules/gates.determine_vehicle_tier) applies the
// 18k miles/year cap ONLY to the standard lane. Premium-lane vehicles (<= 4 model years
// AND <= 50k miles) are NOT subject to any miles/year cap. The Apify prefilters must not
// be stricter than this, or late-model high-mileage fleet vehicles (a core government-auction
// segment) are silently dropped before they ever reach scoring.

const CURRENT_YEAR = new Date().getFullYear();

// Superset of module-level identifiers the extracted gate functions may reference.
// Standard config mirrors the governed standard lane (10 model years / 100k miles).
const SCOPE = {
  CURRENT_YEAR,
  currentYear: CURRENT_YEAR,
  STANDARD_MAX_MILES_PER_YEAR: 18000,
  STANDARD_MAX_MILEAGE: 100000,
  STANDARD_MAX_MODEL_AGE_YEARS: 10,
  STANDARD_MAX_AGE_YEARS: 10,
  PREMIUM_MAX_MODEL_AGE_YEARS: 4,
  PREMIUM_MAX_AGE_YEARS: 4,
  PREMIUM_MAX_MILEAGE: 50000,
  EFFECTIVE_MIN_YEAR: CURRENT_YEAR - 10,
  EFFECTIVE_MAX_MILEAGE: 100000,
  MIN_YEAR: CURRENT_YEAR - 10,
  MAX_MILEAGE: 100000,
  DEFAULT_MIN_YEAR: CURRENT_YEAR - 10,
  DEFAULT_MAX_MILEAGE: 100000,
  DEFAULT_MAX_YEAR_AGE: 10,
  minYear: CURRENT_YEAR - 10,
  maxYear: CURRENT_YEAR + 1,
  maxMileage: 100000,
  maxYearAge: 10,
  parseMileageValue: (value) => {
    const parsed = parseInt(String(value).replace(/[^\d]/g, ''), 10);
    return Number.isNaN(parsed) ? 0 : parsed;
  },
};

function extractFunction(source, fnName) {
  const startToken = `function ${fnName}(`;
  const start = source.indexOf(startToken);
  if (start === -1) throw new Error(`function ${fnName} not found in source`);
  let depth = 0;
  let end = source.indexOf('{', start);
  for (let i = end; i < source.length; i += 1) {
    if (source[i] === '{') depth += 1;
    else if (source[i] === '}') {
      depth -= 1;
      if (depth === 0) {
        end = i + 1;
        break;
      }
    }
  }
  const fnSource = source.slice(start, end);
  const factory = new Function(...Object.keys(SCOPE), `${fnSource}\n return ${fnName};`);
  return factory(...Object.values(SCOPE));
}

// Each actor exposes a rejection predicate (true == dropped before scoring).
const ACTORS = [
  { name: 'ds-govdeals', file: 'src/main_api.js', fn: 'failsDealerScopeAgeMileageGate', call: (gate, year, mileage) => gate({ modelYear: year, mileage }) },
  { name: 'ds-publicsurplus', file: 'src/main.js', fn: 'failsDealerScopeAgeMileageGate', call: (gate, year, mileage) => gate(year, mileage) },
  { name: 'ds-municibid', file: 'src/main.js', fn: 'failsDealerScopeAgeMileageGate', call: (gate, year, mileage) => gate(year, mileage) },
  { name: 'ds-proxibid', file: 'src/main.js', fn: 'failsDealerScopeAgeMileageGate', call: (gate, year, mileage) => gate(year, mileage) },
  { name: 'ds-hibid-v2', file: 'src/main.js', fn: 'failsDealerScopeAgeMileageGate', call: (gate, year, mileage) => gate(year, mileage) },
  { name: 'ds-gsaauctions', file: 'src/main.js', fn: 'failsDealerScopeAgeMileageGate', call: (gate, year, mileage) => gate(year, mileage) },
  { name: 'ds-jjkane', file: 'src/main.js', fn: 'failsDealerScopeAgeMileageGate', call: (gate, year, mileage) => gate(year, mileage) },
  { name: 'ds-equipmentfacts', file: 'src/main.js', fn: 'failsDealerScopeAgeMileageGate', call: (gate, year, mileage) => gate(year, mileage) },
  { name: 'ds-bidspotter', file: 'src/main.js', fn: 'failsDealerScopeAgeMileageGate', call: (gate, year, mileage) => gate(year, mileage) },
  { name: 'ds-allsurplus', file: 'src/main.js', fn: 'failsDealerScopeAgeMileageGate', call: (gate, year, mileage) => gate(year, mileage) },
  { name: 'ds-purplewave', file: 'src/main.js', fn: 'failsDealerScopeAgeMileageGate', call: (gate, year, mileage) => gate(year, mileage, CURRENT_YEAR - 10, 100000) },
  { name: 'ds-govplanet', file: 'src/main.js', fn: 'isMilesPerYearOverLimit', call: (gate, year, mileage) => gate(year, mileage) },
];

describe('public-source age/mileage prefilters honor the premium lane', () => {
  for (const actor of ACTORS) {
    const source = readFileSync(resolve(`apify/actors/${actor.name}/${actor.file}`), 'utf8');
    const gate = extractFunction(source, actor.fn);

    test(`${actor.name}: keeps premium-lane high-miles/year vehicles (regression)`, () => {
      // 1-year-old, 30k miles == 30k miles/year (> 18k) but premium-eligible (<= 4 yr, <= 50k mi).
      // Pre-fix this was silently rejected by the standard-lane miles/year cap.
      expect(actor.call(gate, CURRENT_YEAR - 1, 30000)).toBe(false);
      // 2-year-old, 45k miles == 22.5k miles/year, still premium-eligible.
      expect(actor.call(gate, CURRENT_YEAR - 2, 45000)).toBe(false);
    });

    test(`${actor.name}: still rejects standard-lane vehicles over 18k miles/year`, () => {
      // 5-year-old, 95k miles == 19k miles/year, standard lane (age > 4) -> rejected.
      expect(actor.call(gate, CURRENT_YEAR - 5, 95000)).toBe(true);
    });

    test(`${actor.name}: keeps clean premium and standard vehicles`, () => {
      // Premium, low miles/year.
      expect(actor.call(gate, CURRENT_YEAR - 2, 20000)).toBe(false);
      // Standard lane within the per-year cap (6 yr, 90k == 15k/yr).
      expect(actor.call(gate, CURRENT_YEAR - 6, 90000)).toBe(false);
    });

    test(`${actor.name}: wires premium ceiling constants into the gate source`, () => {
      expect(source).toContain('PREMIUM_MAX_MILEAGE');
      expect(source).toMatch(/PREMIUM_MAX_(MODEL_)?AGE_YEARS/);
    });
  }
});
