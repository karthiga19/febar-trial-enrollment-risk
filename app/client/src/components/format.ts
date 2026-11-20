export const usd = (v: unknown) => {
  const n = Number(v);
  if (v === null || v === undefined || Number.isNaN(n)) return '—';
  if (Math.abs(n) >= 1e6) return `$${(n / 1e6).toFixed(1)}M`;
  if (Math.abs(n) >= 1e3) return `$${(n / 1e3).toFixed(0)}K`;
  return `$${n.toFixed(0)}`;
};
export const pct = (v: unknown, digits = 0) => (v === null || v === undefined ? '—' : `${(Number(v) * 100).toFixed(digits)}%`);
export const num = (v: unknown) => (v === null || v === undefined ? '—' : Number(v).toLocaleString());
export const ACTION_LABEL: Record<string, string> = {
  add_sites: 'Add sites',
  protocol_amendment: 'Protocol amendment',
  recruitment_campaign: 'Recruitment campaign',
  site_remediation: 'Site remediation',
  monitor: 'Monitor',
};

/** Read `{ error }` from a failed fetch response without trusting its shape. */
export async function errorOf(r: Response): Promise<string> {
  const body: unknown = await r.json().catch(() => null);
  if (body && typeof body === 'object' && 'error' in body && typeof body.error === 'string') return body.error;
  return r.statusText;
}
