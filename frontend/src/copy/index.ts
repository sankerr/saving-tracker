import { heStrings } from './he';

export { heStrings };

/** Look up a Hebrew string and replace `{var}` placeholders. */
export function t(
  key: string,
  vars?: Record<string, string | number>,
): string {
  let s = heStrings[key] ?? key;
  if (vars) {
    for (const [k, v] of Object.entries(vars)) {
      s = s.replaceAll(`{${k}}`, String(v));
    }
  }
  return s;
}
