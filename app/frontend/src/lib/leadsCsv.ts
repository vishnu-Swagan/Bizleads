/**
 * CSV export for leads.
 *
 * Kept out of the page component so the rules below can be read — and tested —
 * without mounting React. They are rules about correctness, not presentation:
 * the previous export produced a file that looked plausible and was wrong.
 */

/** The subset of a lead the export reads. */
export interface ExportableLead {
  business_name: string;
  category: string;
  location: string;
  country: string;
  website_score: number | null;
  social_score: number | null;
  has_website: boolean | null;
  pipeline_stage: string;
  priority: string;
  contact_email: string;
  created_at: string;
  data_source?: string | null;
  contact_phone?: string | null;
  website_url?: string | null;
  address?: string | null;
  findings?: string | null;
  qualified_at?: string | null;
  social_platforms?: string | null;
  notes_count?: number | null;
  last_contacted?: string | null;
}

export const stageLabels: Record<string, string> = {
  new_lead: 'New',
  contacted: 'Contacted',
  in_progress: 'In Progress',
  won: 'Won',
  lost: 'Lost',
};

/**
 * Whether a value would be executed as a formula by a spreadsheet.
 *
 * `=` and `@` always start one, as do a leading tab or carriage return.
 *
 * `+` and `-` are the awkward pair: they open a formula too, but they also
 * open every international phone number and every negative number. Blanket-
 * prefixing them put an apostrophe in front of `+44 20 7000 0000`, which
 * displays correctly in Excel and then corrupts the value for everything
 * downstream — a CRM re-importing this file would store the apostrophe as
 * part of the phone number. For a tool whose whole output feeds other
 * systems, that is worse than the display quirk it avoids.
 *
 * So a signed value made only of digits and phone punctuation is left alone;
 * anything else after the sign (letters, pipes, parens with words) is treated
 * as hostile, which still catches the payloads that matter, e.g.
 * `-2+3+cmd|' /C calc'!A0`.
 */
function isFormulaRisk(text: string): boolean {
  if (/^[=@\t\r]/.test(text)) return true;
  if (!/^[+\-]/.test(text)) return false;
  return !/^[+\-][\d\s().\-]*$/.test(text);
}

/**
 * Quote one CSV field per RFC 4180.
 *
 * The previous export joined raw values with commas, so a lead in
 * "Soho, London" split into two fields and shifted every column after it —
 * the file looked fine until you opened it and found emails under Priority.
 *
 * The leading apostrophe on formula characters is deliberate. Business names,
 * addresses and findings are read off third-party websites, so a site can
 * choose to call itself `=HYPERLINK(...)`. Excel and Sheets execute that on
 * open, which turns exporting your own leads into running someone else's code.
 * Prefixing renders it inert text, which is the OWASP guidance.
 */
export function csvField(value: unknown): string {
  if (value === null || value === undefined) return '';

  let text = String(value);
  if (isFormulaRisk(text)) text = `'${text}`;

  // Quote when the value carries a delimiter, a quote, a newline, or edge
  // whitespace a parser would otherwise trim.
  if (/[",\r\n]/.test(text) || text !== text.trim()) {
    return `"${text.replace(/"/g, '""')}"`;
  }
  return text;
}

/** Human-readable summary of the JSON-encoded findings on a lead. */
export function describeFindings(raw?: string | null): { count: string; labels: string } {
  // Null means the site could not be read; '[]' means it was read and nothing
  // was wrong. Reporting both as "0 issues" would claim a clean bill of health
  // for a site nobody could reach, so the unmeasured case stays blank.
  if (!raw) return { count: '', labels: '' };
  try {
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return { count: '', labels: '' };
    return {
      count: String(parsed.length),
      labels: parsed.map((f) => f?.label).filter(Boolean).join('; '),
    };
  } catch {
    return { count: '', labels: '' };
  }
}

function parseJsonList(raw?: string | null): string[] {
  try {
    const parsed = JSON.parse(raw || '[]');
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

/** Every column the app holds on a lead, in a stable order. */
export const CSV_COLUMNS: Array<{ header: string; value: (l: ExportableLead) => unknown }> = [
  { header: 'Business Name', value: (l) => l.business_name },
  { header: 'Category', value: (l) => l.category },
  { header: 'Location', value: (l) => l.location },
  { header: 'Country', value: (l) => l.country },
  { header: 'Address', value: (l) => l.address },
  { header: 'Email', value: (l) => l.contact_email },
  { header: 'Phone', value: (l) => l.contact_phone },
  { header: 'Website', value: (l) => l.website_url },
  // Blank rather than 0 when unmeasured — see describeFindings.
  { header: 'Website Score', value: (l) => l.website_score ?? '' },
  {
    header: 'Has Website',
    value: (l) =>
      l.has_website === null || l.has_website === undefined ? '' : l.has_website ? 'Yes' : 'No',
  },
  { header: 'Social Score', value: (l) => l.social_score ?? '' },
  { header: 'Social Platforms', value: (l) => parseJsonList(l.social_platforms).join('; ') },
  { header: 'Issues Found', value: (l) => describeFindings(l.findings).count },
  { header: 'Issues', value: (l) => describeFindings(l.findings).labels },
  { header: 'Stage', value: (l) => stageLabels[l.pipeline_stage] ?? l.pipeline_stage },
  { header: 'Priority', value: (l) => l.priority },
  { header: 'Notes', value: (l) => l.notes_count ?? '' },
  { header: 'Last Contacted', value: (l) => l.last_contacted },
  { header: 'Measured At', value: (l) => l.qualified_at },
  // Raw provenance rather than the UI badge label. A spreadsheet is filtered
  // and pivoted on, so the stable machine value is worth more here than the
  // sentence the table shows. 'unverified' matches what the badge says about
  // rows predating provenance tracking.
  { header: 'Source', value: (l) => l.data_source || 'unverified' },
  { header: 'Created At', value: (l) => l.created_at },
];

/** Render leads as an RFC 4180 CSV. */
export function buildLeadsCsv(leads: ExportableLead[]): string {
  const header = CSV_COLUMNS.map((c) => csvField(c.header)).join(',');
  const rows = leads.map((lead) => CSV_COLUMNS.map((c) => csvField(c.value(lead))).join(','));
  // CRLF is what RFC 4180 specifies, and what Excel expects.
  return [header, ...rows].join('\r\n');
}
