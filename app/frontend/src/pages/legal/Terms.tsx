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
          Payments are processed by <strong>Stripe Payments Europe, Ltd.</strong> and its
          affiliates. <strong>We never see or store your full card number.</strong> Card details
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

        <h3>7.3 Renewal and cancellation</h3>
        <ul>
          <li>
            Monthly plans renew every month on the date you subscribed. Annual plans renew every
            twelve months.
          </li>
          <li>
            <strong>Subscriptions renew automatically</strong> unless cancelled before the renewal
            date.
          </li>
          <li>
            You may cancel at any time from your account settings. Cancellation stops the next
            renewal; it does not retroactively refund the period already paid for.
          </li>
          <li>
            On cancellation you keep access until the end of the period you have paid for. After
            that the workspace becomes read-only.
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
          <strong>Consumers in the UK and EU</strong> have a statutory 14-day right to cancel a
          distance contract. Because the service is supplied digitally and immediately, by
          subscribing you ask us to begin supply at once and acknowledge that you lose that right
          once supply has begun. This does not affect your rights where the service is faulty or
          not as described. Most customers subscribe as a business and this right does not apply
          to them.
        </p>

        <h3>7.7 Tax</h3>
        <p>
          Prices are exclusive of VAT and any other applicable sales tax, which is added at
          checkout based on your billing location. Where you supply a valid VAT number, the
          reverse charge may apply.
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
        <h2 id="liability">10. Liability</h2>
        <p>
          Nothing in these Terms limits liability for death or personal injury caused by
          negligence, for fraud, or for anything else that cannot lawfully be limited.
        </p>
        <p>
          Subject to that, we are not liable for lost profits, lost business, lost or missed
          opportunities, or indirect or consequential loss. Our total liability in any twelve-month
          period is limited to the fees you paid us in that period.
        </p>
      </section>

      <section>
        <h2 id="changes">11. Changes to these Terms</h2>
        <p>
          We may update these Terms. For material changes we will give at least 30 days&rsquo;
          notice by email or in the product. Continuing to use the service after a change takes
          effect means you accept it.
        </p>
      </section>

      <section>
        <h2 id="termination">12. Ending the agreement</h2>
        <p>
          You may stop using the service and close your account at any time. We may end this
          agreement on 30 days&rsquo; notice, or immediately if you materially breach these Terms.
          If we end it without cause, we refund any period you have paid for but not used.
        </p>
      </section>

      <section>
        <h2 id="law">13. Governing law</h2>
        <p>
          These Terms are governed by the law of {LEGAL.jurisdiction}, and its courts have
          exclusive jurisdiction. If you are a consumer, you keep the protection of mandatory law
          in your country of residence.
        </p>
      </section>

      <section>
        <h2 id="contact">14. Contact</h2>
        <p>
          Questions about these Terms: <a href={`mailto:${LEGAL.supportEmail}`}>{LEGAL.supportEmail}</a>
          .
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
