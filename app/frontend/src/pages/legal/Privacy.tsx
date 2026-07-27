import LegalLayout from '@/components/LegalLayout';
import { LEGAL } from '@/lib/legal';

export default function Privacy() {
  return (
    <LegalLayout
      title="Privacy Policy"
      subtitle="What we collect, why, how long we keep it, and the rights you have over it."
      lastUpdated={LEGAL.lastUpdated}
    >
      <section>
        <h2 id="controller">1. Who is responsible</h2>
        <p>
          {LEGAL.entity}, of {LEGAL.address}
          {LEGAL.companyNumber ? ` (registration number ${LEGAL.companyNumber})` : ''}, is the
          controller of personal data described in this policy. {LEGAL.entity} operates{' '}
          {LEGAL.product} as a trading name.
        </p>
        {LEGAL.euRepresentative && (
          <>
            <p>
              Article 27 of the UK and EU GDPR requires a controller established outside those
              territories, which offers services to people in them, to designate a representative
              there. Ours is <strong>{LEGAL.euRepresentative}</strong>, who may be contacted by
              data subjects and supervisory authorities on all matters relating to processing.
              Contacting them does not replace your right to contact us directly.
            </p>
          </>
        )}
        <p>
          Data-protection enquiries:{' '}
          <a href={`mailto:${LEGAL.privacyEmail}`}>{LEGAL.privacyEmail}</a>.
        </p>
      </section>

      <section>
        <h2 id="what">2. What we collect</h2>

        <h3>Account data</h3>
        <p>
          Your email address and a securely hashed password. We do not store your password in a
          readable form. If you sign in with a third-party provider we receive your email address
          and that provider&rsquo;s account identifier.
        </p>

        <h3>Workspace data</h3>
        <p>
          The searches you run, the leads you save, and the notes and pipeline stages you record.
          Saved leads are business records — company name, category, address, business phone,
          business email and website — which are generally company information rather than
          personal data, though a sole trader&rsquo;s details can be both. See clause 6.
        </p>

        <h3>Billing data</h3>
        <p>
          Your plan, billing status, and — from Stripe — the card brand, last four digits and
          expiry date. <strong>We never receive or store your full card number.</strong>
        </p>

        <h3>Technical data</h3>
        <p>
          Server logs containing IP address, browser user agent, requested URL and timestamp,
          generated automatically when you use the service and kept for security and debugging.
        </p>

        <h3>What we do not collect</h3>
        <p>
          <strong>We run no analytics, advertising or tracking of any kind.</strong> There is no
          Google Analytics, no advertising pixel, no session recorder and no third-party
          behavioural tracking. We do not sell or share personal data with data brokers, and we do
          not use your data to train machine-learning models.
        </p>
      </section>

      <section>
        <h2 id="why">3. Why we use it, and our lawful basis</h2>
        <p>Under UK/EU GDPR Article 6 we rely on the following bases:</p>
        <ul>
          <li>
            <strong>Performance of a contract</strong> — creating and running your account,
            providing discovery and qualification, storing your leads, and taking payment.
          </li>
          <li>
            <strong>Legitimate interests</strong> — keeping the service secure, preventing abuse
            and fraud, debugging faults, and sending essential service messages such as billing
            failures. We have considered your rights and consider these interests not to override
            them.
          </li>
          <li>
            <strong>Legal obligation</strong> — retaining invoices and tax records.
          </li>
          <li>
            <strong>Consent</strong> — only if we ever send marketing email, which we do not do
            today. Where consent is used you may withdraw it at any time.
          </li>
        </ul>
      </section>

      <section>
        <h2 id="sharing">4. Who we share it with</h2>
        <p>
          We use a small number of processors, each contractually bound to protect your data and
          to use it only on our instructions. The current list, with what each receives and where
          it is located, is on our <a href="/subprocessors">sub-processors page</a>.
        </p>
        <p>
          We may also disclose data where the law requires it, or to establish or defend legal
          claims. If our business is sold, data may transfer to the buyer, who remains bound by
          this policy.
        </p>
      </section>

      <section>
        <h2 id="transfers">5. Where your data is held</h2>
        <p>
          Your account and workspace data are stored in the <strong>United Kingdom</strong> (AWS
          London), and the application programming interface runs in{' '}
          <strong>Frankfurt, Germany</strong>.
        </p>
        <p>
          {LEGAL.entity} is established in the United States, so your data is accessible from
          there for support and administration even though it is stored in the UK and EU. Several
          of our processors are also US-based. These transfers are covered by the UK International
          Data Transfer Addendum and the EU Standard Contractual Clauses, together with the
          additional safeguards those instruments require.
        </p>
      </section>

      <section>
        <h2 id="prospects">6. Data about the businesses you research</h2>
        <p>
          This deserves its own section, because it is the part customers most often get wrong.
        </p>
        <p>
          Discovery returns business listings from a licensed provider. Most describe a company
          and are not personal data. But a sole trader, a partnership, or a business whose name or
          email identifies a named individual <em>is</em> personal data under UK/EU GDPR.
        </p>
        <p>
          Where that is the case, and you save the record and use it for outreach,{' '}
          <strong>you become an independent controller of it</strong>. Your obligations then
          include:
        </p>
        <ul>
          <li>
            having a lawful basis for contacting them — usually legitimate interests for B2B
            outreach, which requires a balancing assessment you should be able to evidence;
          </li>
          <li>
            telling them, within a month of first contact, that you hold their data and that you
            obtained it from a business-listing source (Article 14);
          </li>
          <li>honouring any objection, erasure or access request they make to you;</li>
          <li>keeping the data no longer than you need it.</li>
        </ul>
        <p>
          We act as your processor for the leads stored in your workspace. If a business contacts{' '}
          <em>us</em> about data held in your workspace, we will pass the request to you and
          support you in answering it.
        </p>
      </section>

      <section>
        <h2 id="retention">7. How long we keep it</h2>
        <ul>
          <li>
            <strong>Account and workspace data</strong> — while your account is open, and for up
            to 30 days after you close it, after which it is deleted.
          </li>
          <li>
            <strong>Server logs</strong> — up to 90 days.
          </li>
          <li>
            <strong>Invoices and tax records</strong> — six years, as tax law requires.
          </li>
          <li>
            <strong>Backups</strong> — encrypted and overwritten on a rolling 30-day cycle, so
            deleted data may persist in a backup for up to 30 days after deletion.
          </li>
        </ul>
      </section>

      <section>
        <h2 id="rights">8. Your rights</h2>
        <p>
          If you are in the UK, the EU or the EEA, you have the right to:
        </p>
        <ul>
          <li>
            <strong>Access</strong> — a copy of the personal data we hold about you.
          </li>
          <li>
            <strong>Rectification</strong> — correction of anything inaccurate.
          </li>
          <li>
            <strong>Erasure</strong> — deletion, where we have no overriding reason to keep it.
          </li>
          <li>
            <strong>Restriction</strong> — to limit how we use it while a dispute is resolved.
          </li>
          <li>
            <strong>Portability</strong> — your data in a structured, machine-readable format.
          </li>
          <li>
            <strong>Objection</strong> — to processing based on legitimate interests, and at any
            time to direct marketing.
          </li>
          <li>
            <strong>Withdraw consent</strong> — where processing relies on consent.
          </li>
          <li>
            <strong>Not to be subject to solely automated decisions</strong> producing legal or
            similarly significant effects. Our scoring ranks prospects for your review; it makes no
            decision about you.
          </li>
        </ul>
        <p>
          To exercise any of these, email{' '}
          <a href={`mailto:${LEGAL.privacyEmail}`}>{LEGAL.privacyEmail}</a>. We respond within one
          month, and will tell you if we need longer because a request is complex. There is no
          charge unless a request is manifestly unfounded or excessive.
        </p>
        <p>
          You may also complain to a supervisory authority. In the UK that is the Information
          Commissioner&rsquo;s Office (<a href="https://ico.org.uk">ico.org.uk</a>); in the EU it
          is the authority where you live or work.
        </p>
      </section>

      <section>
        <h2 id="us-rights">9. United States privacy rights</h2>
        <p>
          Some US states — California, Colorado, Connecticut, Virginia and others — give residents
          rights over their personal information, including rights to know what is collected, to
          delete it, to correct it, and to opt out of its sale or of targeted advertising.
        </p>
        <p>
          <strong>We do not sell or share personal information</strong> as those terms are defined
          under the California Consumer Privacy Act, and we do not use it for targeted advertising
          or profiling. We run no advertising or analytics of any kind.
        </p>
        <p>
          Whether a given state law applies to us depends on thresholds most small businesses do
          not meet. Regardless of whether we are strictly covered, we honour access, correction
          and deletion requests from US residents on the same terms as those described in clause
          8. Email <a href={`mailto:${LEGAL.privacyEmail}`}>{LEGAL.privacyEmail}</a>, and we will
          not discriminate against you for asking.
        </p>
      </section>

      <section>
        <h2 id="security">10. Security</h2>
        <ul>
          <li>All traffic is encrypted in transit with TLS, and data is encrypted at rest.</li>
          <li>Passwords are hashed; nobody at {LEGAL.entity} can read yours.</li>
          <li>
            Every request is authenticated and scoped to your workspace, so one customer cannot
            read another&rsquo;s data.
          </li>
          <li>Card data never reaches our servers — Stripe handles it directly.</li>
          <li>Administrative access is restricted to those who need it.</li>
        </ul>
        <p>
          No system is perfectly secure. If a breach affects your rights we will notify the
          relevant supervisory authority within 72 hours and tell you without undue delay where the
          risk to you is high.
        </p>
      </section>

      <section>
        <h2 id="children">11. Children</h2>
        <p>
          The service is for business use and is not directed at anyone under 16. We do not
          knowingly collect their data; if we learn we have, we delete it.
        </p>
      </section>

      <section>
        <h2 id="cookies">12. Cookies</h2>
        <p>
          We use only what is strictly necessary to keep you signed in and remember interface
          preferences. There are no advertising or analytics cookies. Details are on our{' '}
          <a href="/cookies">cookie page</a>.
        </p>
      </section>

      <section>
        <h2 id="changes">13. Changes</h2>
        <p>
          We will post any update here and change the date above. For material changes we will
          notify you by email or in the product.
        </p>
      </section>

      <section>
        <h2 id="contact">14. Contact</h2>
        <p>
          {LEGAL.entity}
          <br />
          {LEGAL.address}
          <br />
          <a href={`mailto:${LEGAL.privacyEmail}`}>{LEGAL.privacyEmail}</a>
        </p>
      </section>
    </LegalLayout>
  );
}
