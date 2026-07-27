/**
 * Company and policy facts referenced by the legal pages.
 *
 * Single source of truth: change a value here and it propagates to the Terms,
 * the Privacy Policy, the Cookies page, the Sub-processors page and the
 * footer at once, so the documents cannot contradict each other.
 *
 * Fields that may legitimately be empty (companyNumber, euRepresentative) are
 * rendered conditionally by the pages that use them. Empty omits the clause
 * cleanly; it never prints a blank or a placeholder. Do not put a stand-in
 * value in one to "fill it" — a false statement in a privacy policy is worse
 * than a silent omission.
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

  /**
   * Deliberately empty, and it must stay that way.
   *
   * The company's federal EIN is NOT recorded here. Everything in this file
   * is compiled into the public JavaScript bundle and served to every
   * visitor, and this repository is public — so a value here is published
   * twice over, and a comment would leak it just as effectively as rendering
   * it. An EIN is a tax identifier used in fraudulent filings and identity
   * theft; there is no reason to expose one to identify a party to a
   * consumer contract, and no law requires it.
   *
   * An empty string is the correct value, not a missing one: both the Terms
   * and the Privacy Policy render the registration clause conditionally, so
   * this omits the sentence cleanly rather than printing a gap. The entity
   * is identified by its registered name and address, which is sufficient.
   *
   * If a state organisation number is ever wanted here, that is a public
   * record and safe to publish — an EIN is not.
   */
  companyNumber: '',

  /** Registered address. Required by GDPR Art. 13(1)(a) as controller identity. */
  address: '271 W Short St, Ste 410 #2463, Lexington, KY 40507, United States',

  /** Governing law. Kentucky is a Commonwealth, hence the formal styling. */
  jurisdiction: 'the Commonwealth of Kentucky, United States',

  /** General support enquiries. */
  supportEmail: 'support@torquetrendsllc.co.site',

  /**
   * Data-protection enquiries and data-subject requests.
   *
   * Separate from support on purpose: access, correction and erasure requests
   * carry a one-month statutory deadline under GDPR Art. 12(3), and a missed
   * one is a breach. Keeping them out of general support traffic gives that
   * clock somewhere visible to run, and leaves a clean audit trail if a
   * supervisory authority ever asks how requests were handled.
   */
  privacyEmail: 'privacy@torquetrendsllc.co.site',

  /**
   * UK/EU representative under GDPR Art. 27, once appointed.
   *
   * Empty renders no representative section at all, rather than a promise we
   * cannot keep. Naming a representative who does not exist would be a false
   * statement in a privacy policy — worse than the omission, and exactly the
   * kind of thing a supervisory authority treats as bad faith.
   *
   * The obligation itself is not removed by leaving this blank. A controller
   * established outside the UK/EU that offers services to people there must
   * designate one in writing. Whether that bites depends on whether the
   * service is genuinely offered into those territories; the policy now
   * states the position honestly either way. Set this to the representative's
   * name and address once appointed and the section appears automatically.
   */
  euRepresentative: '',

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
