import LegalLayout from '@/components/LegalLayout';
import { LEGAL } from '@/lib/legal';

export default function Terms() {
  return (
    <LegalLayout
      title="Terms of Service"
      subtitle={`The agreement between you and ${LEGAL.entity} for use of ${LEGAL.product}.`}
      lastUpdated={LEGAL.lastUpdated}
    >
      <section>
        <h2 id="agreement">1. This agreement</h2>
        <p>
          These Terms are a contract between you (&ldquo;you&rdquo;, &ldquo;the
          customer&rdquo;) and {LEGAL.entity}, registered at {LEGAL.address}
          {LEGAL.companyNumber ? `, registration number ${LEGAL.companyNumber}` : ''}{' '}
          (&ldquo;we&rdquo;, &ldquo;us&rdquo;). {LEGAL.entity} operates {LEGAL.product},
          which is a trading name; your contract is with {LEGAL.entity}. They govern your
          use of {LEGAL.product} at{' '}
          <a href={LEGAL.siteUrl}>{LEGAL.siteUrl.replace('https://', '')}</a>.
        </p>
        <p>
          By creating an account you accept these Terms. If you are agreeing on behalf of a
          company, you confirm you are authorised to bind it, and &ldquo;you&rdquo; means that
          company.
        </p>
      </section>

      <section>
        <h2 id="service">2. What the service does</h2>
        <p>
          {LEGAL.product} helps you find local businesses whose websites may be
          underperforming. It does two things:
        </p>
        <ul>
          <li>
            <strong>Discovery</strong> returns real businesses from licensed third-party data
            (currently MapBox) matching a location and category you choose.
          </li>
          <li>
            <strong>Qualification</strong> fetches a prospect&rsquo;s public website and measures
            it against objective checks — HTTPS, mobile viewport, page title, meta description,
            structured data, tap-to-call links, image alt text and page weight — and records what
            it found.
          </li>
        </ul>
        <p>
          <strong>We do not generate businesses.</strong> Every result comes from a licensed data
          provider or from measuring a real, publicly reachable website. Where something has not
          been measured, the service reports it as unknown rather than guessing.
        </p>
      </section>

      <section>
        <h2 id="accuracy">3. Accuracy and your own judgement</h2>
        <p>
          Business listings come from third-party providers and may be out of date, incomplete or
          wrong. Website measurements describe a site at the moment it was fetched; sites change,
          and a site may be temporarily unreachable for reasons unrelated to its quality.
        </p>
        <p>
          The service is a research tool. It does not tell you whether a business wants your
          services, can pay for them, or is a suitable client. Those judgements — and any
          decision to contact a business — remain yours. We provide the service{' '}
          <strong>as is</strong> and do not warrant that results will be accurate, complete or
          fit for a particular purpose.
        </p>
      </section>

      <section>
        <h2 id="acceptable-use">4. Acceptable use</h2>
        <p>You agree not to:</p>
        <ul>
          <li>
            use the service to send unlawful marketing, or to contact people in breach of
            applicable direct-marketing or anti-spam law (see clause 5);
          </li>
          <li>
            resell, redistribute or republish the underlying business listing data as a dataset —
            our provider licences permit use within the product, not resale of the raw data;
          </li>
          <li>
            scrape, mirror or bulk-extract the service, or use automated means to exceed your
            plan&rsquo;s credit allowance;
          </li>
          <li>
            attempt to access another customer&rsquo;s workspace, probe our systems for
            vulnerabilities without written permission, or interfere with the service&rsquo;s
            operation;
          </li>
          <li>share your account credentials, or exceed the number of seats on your plan.</li>
        </ul>
        <p>
          We may suspend an account that breaches this clause. Where practical we will tell you
          first and give you a chance to put it right.
        </p>
      </section>

      <section>
        <h2 id="outreach">5. Your responsibilities when contacting prospects</h2>
        <p>
          The service helps you identify businesses. Any contact you then make is your own act,
          as sender and — in data-protection terms — as an independent controller of the contact
          details you use.
        </p>
        <p>You are responsible for complying with the law that applies to your outreach, which may include:</p>
        <ul>
          <li>
            UK PECR and the EU ePrivacy Directive, and equivalent rules elsewhere, on unsolicited
            electronic marketing;
          </li>
          <li>the CAN-SPAM Act if you contact recipients in the United States;</li>
          <li>
            UK/EU GDPR obligations that arise when you process a named individual&rsquo;s contact
            details, including telling them where you got their information.
          </li>
        </ul>
        <p>
          We are not responsible for your outreach, and you agree to indemnify us against claims
          arising from it.
        </p>
      </section>

      <section>
        <h2 id="plans">6. Plans, credits and trials</h2>
        <p>
          Discovery and qualification consume <strong>credits</strong>. Each plan includes a
          monthly credit allowance and a number of seats. Current allowances and prices are shown
          on the <a href="/pricing">pricing page</a>, which forms part of these Terms.
        </p>
        <ul>
          <li>Credits refresh at the start of each billing period.</li>
          <li>
            <strong>Unused credits do not roll over</strong> and have no cash value.
          </li>
          <li>
            A search that returns no matches, or fails because of a fault on our side, is not
            charged. Where a charge has already been taken in those circumstances, it is refunded
            to your balance automatically.
          </li>
          <li>
            Free trials include a limited allowance and require no card. If you do not subscribe,
            the account simply stops working at the end of the trial — nothing is charged.
          </li>
        </ul>
      </section>

      <section>
        <h2 id="payment">7. Subscriptions, card payments and renewals</h2>

        <h3>7.1 How your card is handled</h3>
        <p>
          Payments are processed by <strong>Stripe, Inc.</strong> and its affiliates. <strong>We never see or store your full card number.</strong> Card details
          are submitted directly to Stripe, which is certified to PCI-DSS Level 1. We receive only
          a payment token, the card brand, its last four digits and its expiry date, so we can show
          you which card is on file and take renewal payments.
        </p>
        <p>
          Your use of Stripe is also subject to Stripe&rsquo;s own terms and privacy policy.
        </p>

        <h3>7.2 Authority to charge</h3>
        <p>
          By subscribing you authorise us, through Stripe, to charge your card the plan fee plus
          any applicable tax, on each renewal date, until you cancel. This is a{' '}
          <strong>recurring payment</strong> — a continuous payment authority — not a one-off
          charge.
        </p>

        <h3>7.3 Automatic renewal — please read</h3>
        <p className="rounded-lg border border-slate-300 bg-slate-50 p-4">
          <strong>
            THIS IS A SUBSCRIPTION THAT RENEWS AUTOMATICALLY AND CHARGES YOUR CARD UNTIL YOU
            CANCEL.
          </strong>{' '}
          Monthly plans renew each month on the day you subscribed; annual plans renew every
          twelve months. The renewal amount is the then-current plan price plus tax. You may
          cancel at any time, without charge or penalty, from Settings in your account — the
          same place you subscribed, in no more steps than it took to sign up.
        </p>
        <ul>
          <li>
            Cancellation takes effect at the end of the period you have already paid for. It stops
            the next renewal; it does not retroactively refund the current period.
          </li>
          <li>
            After the paid period ends, the workspace becomes read-only. Your data is not deleted
            immediately — see clause 8.
          </li>
          <li>
            For annual plans we email a reminder before each renewal, stating the date and the
            amount.
          </li>
          <li>
            If you cannot reach the cancellation control for any reason, email{' '}
            <a href={`mailto:${LEGAL.supportEmail}`}>{LEGAL.supportEmail}</a> and we will cancel
            it for you. A cancellation request sent to that address is effective when we receive
            it, whatever the state of the interface.
          </li>
        </ul>

        <h3>7.4 Price changes</h3>
        <p>
          We may change prices. We will give you at least <strong>30 days&rsquo; notice</strong> by
          email before a change affects you, and the new price applies from your next renewal. If
          you do not accept it, cancel before that renewal.
        </p>

        <h3>7.5 Failed payments</h3>
        <p>
          If a payment fails we will retry it and email you. If it remains unpaid after 14 days we
          may suspend the workspace. Your data is retained during suspension and restored if you
          pay.
        </p>

        <h3>7.6 Refunds and your cancellation rights</h3>
        <p>
          Fees are generally non-refundable except where the law requires otherwise or where we
          have made an error.
        </p>
        <p>
          There is no statutory cooling-off period for digital services in the United States, and
          the free trial exists so you can evaluate the service before paying anything.
        </p>
        <p>
          <strong>Consumers in the UK and EU</strong> have a statutory 14-day right to cancel a
          distance contract, which applies even though we are established in the United States.
          Because the service is supplied digitally and immediately, by subscribing you ask us to
          begin supply at once and acknowledge that you lose that right once supply has begun.
          This does not affect your rights where the service is faulty or not as described. Most
          customers subscribe as a business, to whom the right does not apply.
        </p>

        <h3>7.7 Tax</h3>
        <p>
          Prices are in US dollars and exclusive of tax. Any US state sales tax, UK/EU VAT or
          other applicable tax is calculated at checkout based on your billing location. Where
          you are a UK or EU business supplying a valid VAT number, the reverse charge may apply
          and no VAT is added.
        </p>
      </section>

      <section>
        <h2 id="data">8. Your data</h2>
        <p>
          You own the leads, notes and pipeline records you create. We process them to run the
          service, as described in our <a href="/privacy">Privacy Policy</a>.
        </p>
        <p>
          You can export or delete your data at any time. If you close your account we delete your
          workspace data within 30 days, except where we must retain records for legal or
          accounting purposes.
        </p>
      </section>

      <section>
        <h2 id="availability">9. Availability</h2>
        <p>
          We aim to keep the service available but do not guarantee uninterrupted access. The
          service depends on third parties — hosting, the payment processor and the business data
          provider — and may be affected by their outages, by maintenance, or by changes to a
          provider&rsquo;s API or licence terms.
        </p>
        <p>
          Coverage varies by country because it depends on our data provider. Some countries return
          few or no results. This is a limitation of the underlying data, not a fault, and is not
          grounds for a refund.
        </p>
      </section>

      <section>
        <h2 id="disclaimers">10. Disclaimers</h2>
        <p>
          <strong>
            THE SERVICE IS PROVIDED &ldquo;AS IS&rdquo; AND &ldquo;AS AVAILABLE&rdquo;, WITHOUT
            WARRANTIES OF ANY KIND, EXPRESS OR IMPLIED.
          </strong>{' '}
          To the fullest extent permitted by law, we disclaim the implied warranties of
          merchantability, fitness for a particular purpose, title and non-infringement.
        </p>
        <p>We specifically do not warrant that:</p>
        <ul>
          <li>business listings are accurate, current, complete or still trading;</li>
          <li>
            a website measurement reflects a site&rsquo;s condition at any time other than the
            moment it was fetched;
          </li>
          <li>any prospect will respond to you, engage you, or be able to pay you;</li>
          <li>the service will be uninterrupted, error-free, or available in any given country.</li>
        </ul>
        <p>
          <strong>Nothing in the service is legal, tax, marketing or professional advice.</strong>{' '}
          Clause 5 describes obligations that may apply to your outreach; that description is
          general information, not advice, and does not create a lawyer-client relationship. You
          are responsible for obtaining your own advice on how the law applies to your business.
        </p>
      </section>

      <section>
        <h2 id="liability">11. Limitation of liability</h2>
        <p>
          Nothing in these Terms excludes liability that cannot lawfully be excluded — including
          liability for death or personal injury caused by negligence, for fraud or fraudulent
          misrepresentation, or, for consumers, any statutory right that cannot be waived.
        </p>
        <p>Subject to that, and to the fullest extent permitted by law:</p>
        <ul>
          <li>
            <strong>
              WE ARE NOT LIABLE FOR INDIRECT, INCIDENTAL, SPECIAL, CONSEQUENTIAL, EXEMPLARY OR
              PUNITIVE DAMAGES
            </strong>
            , or for lost profits, lost revenue, lost business, lost or missed opportunities, or
            loss of data, however caused and on any theory of liability, even if we were advised
            such damages were possible.
          </li>
          <li>
            <strong>
              OUR TOTAL AGGREGATE LIABILITY ARISING OUT OF OR RELATING TO THESE TERMS OR THE
              SERVICE IS LIMITED TO THE GREATER OF (A) THE FEES YOU PAID US IN THE TWELVE MONTHS
              BEFORE THE EVENT GIVING RISE TO THE CLAIM, OR (B) ONE HUNDRED US DOLLARS ($100).
            </strong>
          </li>
        </ul>
        <p>
          These limits apply in the aggregate across all claims, and reflect a reasonable
          allocation of risk that is part of the basis of our bargain: the fees would be
          materially higher without them. Some jurisdictions do not allow certain exclusions, in
          which case the exclusion applies only to the extent permitted.
        </p>
      </section>

      <section>
        <h2 id="indemnity">12. Indemnification</h2>
        <p>
          You agree to indemnify, defend and hold harmless {LEGAL.entity}, its members, officers
          and agents from any claim, demand, loss, liability, damages, fine, penalty or expense
          (including reasonable legal fees) arising out of or relating to:
        </p>
        <ul>
          <li>
            your outreach to, or contact with, any business or individual identified through the
            service, including any claim under marketing, anti-spam or data-protection law;
          </li>
          <li>your use of the service in breach of clause 4 or clause 5;</li>
          <li>your breach of these Terms or of any applicable law;</li>
          <li>
            any dispute between you and a prospect, client or third party arising from work you
            sourced through the service.
          </li>
        </ul>
        <p>
          We will notify you of any claim we seek indemnity for, and you may control its defence
          with counsel of your choosing, provided that any settlement releasing us must be agreed
          by us in writing.
        </p>
      </section>

      <section>
        <h2 id="disputes">13. Dispute resolution, arbitration and class-action waiver</h2>
        <p className="rounded-lg border border-slate-300 bg-slate-50 p-4">
          <strong>
            PLEASE READ THIS CLAUSE CAREFULLY. IT AFFECTS YOUR LEGAL RIGHTS, INCLUDING YOUR RIGHT
            TO FILE A LAWSUIT IN COURT AND TO HAVE A JURY TRIAL.
          </strong>
        </p>

        <h3>13.1 Talk to us first</h3>
        <p>
          Most disputes can be resolved quickly. Before starting formal proceedings, send a written
          description of the dispute and the relief you want to{' '}
          <a href={`mailto:${LEGAL.supportEmail}`}>{LEGAL.supportEmail}</a>. We will do the same
          for any claim we have against you. Both sides agree to try in good faith to resolve it
          for <strong>30 days</strong> before proceeding.
        </p>

        <h3>13.2 Binding arbitration</h3>
        <p>
          If the dispute is not resolved in those 30 days, you and {LEGAL.entity} agree that it
          will be settled by <strong>binding individual arbitration</strong> administered by the
          American Arbitration Association under its Consumer Arbitration Rules or Commercial
          Rules, as applicable. The Federal Arbitration Act governs this clause. Judgment on the
          award may be entered in any court of competent jurisdiction.
        </p>
        <p>
          Arbitration may be conducted by document submission, telephone or video. If an in-person
          hearing is required, it will be held in the county where you reside or another mutually
          agreed location, so that distance is not a barrier to bringing a claim.
        </p>

        <h3>13.3 Class-action waiver</h3>
        <p>
          <strong>
            YOU AND {LEGAL.entity.toUpperCase()} AGREE THAT EACH MAY BRING CLAIMS AGAINST THE
            OTHER ONLY IN AN INDIVIDUAL CAPACITY, AND NOT AS A PLAINTIFF OR CLASS MEMBER IN ANY
            PURPORTED CLASS, COLLECTIVE, CONSOLIDATED OR REPRESENTATIVE PROCEEDING.
          </strong>{' '}
          An arbitrator may not consolidate claims or preside over any form of representative
          proceeding. If this waiver is held unenforceable as to a particular claim, that claim —
          and only that claim — must proceed in court, and the rest of this clause still applies.
        </p>

        <h3>13.4 Exceptions</h3>
        <p>This clause does not prevent either of us from:</p>
        <ul>
          <li>bringing an individual claim in small-claims court, if it qualifies;</li>
          <li>
            seeking injunctive or equitable relief in court to stop unauthorised use, infringement
            or misuse of intellectual property;
          </li>
          <li>
            where you are a consumer resident outside the United States, exercising any
            non-waivable right to bring proceedings in your local courts under the mandatory law
            of your country of residence.
          </li>
        </ul>

        <h3>13.5 Your right to opt out</h3>
        <p>
          <strong>You may opt out of arbitration and the class-action waiver</strong> by emailing{' '}
          <a href={`mailto:${LEGAL.supportEmail}`}>{LEGAL.supportEmail}</a> with the subject
          &ldquo;Arbitration Opt-Out&rdquo; and your account email,{' '}
          <strong>within 30 days of first accepting these Terms</strong>. Opting out costs nothing,
          affects nothing else in this agreement, and will not be held against you in any way.
        </p>
      </section>

      <section>
        <h2 id="law">14. Governing law</h2>
        <p>
          These Terms are governed by the laws of {LEGAL.jurisdiction}, without regard to its
          conflict-of-law rules. Subject to clause 13, the state and federal courts located in
          Fayette County, Kentucky have jurisdiction over any dispute.
        </p>
        <p>
          If you are a consumer resident in the UK, the EU or elsewhere, this does not deprive you
          of the protection of mandatory consumer law in your country of residence, or of any
          non-waivable right to bring proceedings in your local courts.
        </p>
      </section>

      <section>
        <h2 id="changes">15. Changes to these Terms</h2>
        <p>
          We may update these Terms. For material changes we will give at least{' '}
          <strong>30 days&rsquo; notice</strong> by email or in the product before they take
          effect. If you do not accept a change, cancel before it takes effect; continuing to use
          the service afterwards means you accept it. Changes never apply retroactively to a
          dispute already notified under clause 13.1.
        </p>
      </section>

      <section>
        <h2 id="termination">16. Ending the agreement</h2>
        <p>
          You may stop using the service and close your account at any time. We may end this
          agreement on 30 days&rsquo; notice, or immediately if you materially breach these Terms
          or use the service unlawfully. If we end it without cause, we refund the unused portion
          of any period you have paid for.
        </p>
      </section>

      <section>
        <h2 id="general">17. General</h2>
        <ul>
          <li>
            <strong>Severability.</strong> If any provision is held unenforceable, it is modified
            to the minimum extent necessary to make it enforceable, or severed if it cannot be;
            the rest remains in force.
          </li>
          <li>
            <strong>No waiver.</strong> Not enforcing a provision on one occasion does not waive
            the right to enforce it later.
          </li>
          <li>
            <strong>Entire agreement.</strong> These Terms, the Privacy Policy and the pricing page
            are the whole agreement between us on this subject, and replace any earlier
            understanding.
          </li>
          <li>
            <strong>Assignment.</strong> You may not assign this agreement without our written
            consent. We may assign it to an affiliate or in connection with a merger or sale of
            the business, on notice to you.
          </li>
          <li>
            <strong>Force majeure.</strong> Neither party is liable for failure to perform caused
            by events beyond its reasonable control, including outages at a hosting, payment or
            data provider on which the service depends.
          </li>
          <li>
            <strong>Survival.</strong> Clauses 3, 5 and 10 to 14 survive termination.
          </li>
          <li>
            <strong>No third-party rights.</strong> Nobody other than you and us may enforce these
            Terms.
          </li>
          <li>
            <strong>Export and sanctions.</strong> You confirm you are not located in, and will not
            use the service from, a country subject to comprehensive US sanctions, and that you are
            not on any US restricted-party list.
          </li>
          <li>
            <strong>Notices.</strong> We give notice by email to your account address or in the
            product. You give notice to{' '}
            <a href={`mailto:${LEGAL.supportEmail}`}>{LEGAL.supportEmail}</a>.
          </li>
        </ul>
      </section>

      <section>
        <h2 id="contact">18. Contact</h2>
        <p>
          Questions about these Terms:{' '}
          <a href={`mailto:${LEGAL.supportEmail}`}>{LEGAL.supportEmail}</a>. Data-protection
          enquiries: <a href={`mailto:${LEGAL.privacyEmail}`}>{LEGAL.privacyEmail}</a>.
        </p>
        <p>
          {LEGAL.entity}
          <br />
          {LEGAL.address}
        </p>
      </section>

    </LegalLayout>
  );
}
