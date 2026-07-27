/**
 * Company and policy facts referenced by the legal pages.
 *
 * ─────────────────────────────────────────────────────────────────────────
 *  ACTION REQUIRED BEFORE TAKING PAYMENTS
 *  Every value marked TODO must be replaced with your real details. A
 *  privacy policy that names no controller, and terms that name no legal
 *  entity or governing law, are not enforceable — and under UK/EU GDPR the
 *  controller's identity and address are mandatory disclosures
 *  (Art. 13(1)(a)). They are left as visible TODOs on purpose: inventing a
 *  company address in a legal document would be far worse than an obvious
 *  blank.
 * ─────────────────────────────────────────────────────────────────────────
 */

export const LEGAL = {
  /** Trading name shown throughout the product. */
  product: 'BizLeads',

  /**
   * The contracting legal entity, which is not the same as the product name.
   * BizLeads is the trading name; Torque Trends LLC is who the customer
   * actually contracts with, and must match the register exactly.
   */
  entity: 'Torque Trends LLC',

  /** TODO: company registration number, if incorporated. */
  companyNumber: '[TODO: company number]',

  /** TODO: registered office address — required by UK/EU GDPR Art. 13(1)(a). */
  address: '[TODO: registered office address]',

  /** TODO: the jurisdiction whose law governs the contract. */
  jurisdiction: '[TODO: e.g. England and Wales]',

  /** General support enquiries. */
  supportEmail: '[TODO: support@yourdomain.com]',

  /** Data-protection enquiries and data-subject requests. */
  privacyEmail: '[TODO: privacy@yourdomain.com]',

  /** Last substantive revision of the policies. */
  lastUpdated: '26 July 2026',

  /** Public site origin, used in policy text and canonical links. */
  siteUrl: 'https://bizleads-five.vercel.app',
} as const;

/**
 * Third parties that process customer data on our behalf.
 *
 * UK/EU GDPR Art. 28 requires customers to be told who these are before they
 * are engaged. This list is derived from what the application actually calls:
 * Supabase (auth + database), Render (API), Vercel (frontend), Stripe
 * (payments), MapBox (business data). Google PageSpeed appears only when an
 * operator supplies a key.
 */
export const SUBPROCESSORS = [
  {
    name: 'Supabase',
    purpose: 'Account authentication and the application database',
    data: 'Email address, hashed password, saved leads, search history',
    location: 'AWS London (eu-west-2), United Kingdom',
  },
  {
    name: 'Render',
    purpose: 'Hosting for the application programming interface',
    data: 'Data in transit while a request is served; request logs',
    location: 'Frankfurt, Germany (EU)',
  },
  {
    name: 'Vercel',
    purpose: 'Hosting and content delivery for the web application',
    data: 'IP address and request metadata inherent to serving a page',
    location: 'Global edge network',
  },
  {
    name: 'Stripe',
    purpose: 'Subscription payments and card processing',
    data: 'Card details, billing address, transaction records',
    location: 'United States and EU (Standard Contractual Clauses)',
  },
  {
    name: 'MapBox',
    purpose: 'Licensed business listing data used by Discovery',
    data: 'Your search terms (location and category). No account data.',
    location: 'United States (Standard Contractual Clauses)',
  },
  {
    name: 'Google PageSpeed Insights',
    purpose: 'Optional deeper website performance measurement',
    data: 'The public URL of a prospect site being measured',
    location: 'United States (Standard Contractual Clauses)',
  },
] as const;
