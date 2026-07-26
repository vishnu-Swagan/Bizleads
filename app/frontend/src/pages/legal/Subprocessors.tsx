import LegalLayout from '@/components/LegalLayout';
import { LEGAL, SUBPROCESSORS } from '@/lib/legal';

/**
 * UK/EU GDPR Art. 28(2) requires customers to be told which sub-processors
 * handle their data. Publishing the list — rather than answering it on
 * request — is also what enterprise buyers and their security reviews expect.
 */
export default function Subprocessors() {
  return (
    <LegalLayout
      title="Sub-processors"
      subtitle="The third parties that process customer data on our behalf, and what each one receives."
      lastUpdated={LEGAL.lastUpdated}
    >
      <section>
        <p>
          We keep this list short on purpose. Each provider below is bound by a data-processing
          agreement, may use your data only on our instructions, and is subject to the transfer
          safeguards described in our <a href="/privacy#transfers">Privacy Policy</a>.
        </p>
      </section>

      <section>
        <h2 id="current">Current sub-processors</h2>

        <div className="mt-4 space-y-4">
          {SUBPROCESSORS.map((p) => (
            <div key={p.name} className="rounded-lg border border-slate-200 p-4 sm:p-5">
              <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
                <h3 className="!mt-0 text-base font-semibold text-slate-900">{p.name}</h3>
                <span className="text-xs text-slate-500">{p.location}</span>
              </div>
              <p className="mt-2 text-sm text-slate-700">{p.purpose}</p>
              <p className="mt-1.5 text-sm text-slate-500">
                <span className="font-medium text-slate-600">Data processed:</span> {p.data}
              </p>
            </div>
          ))}
        </div>
      </section>

      <section>
        <h2 id="changes">Changes to this list</h2>
        <p>
          We will update this page before engaging a new sub-processor. If you have a data-processing
          agreement with us that requires advance notice, we will email you and you may object on
          reasonable data-protection grounds.
        </p>
      </section>

      <section>
        <h2 id="dpa">Data-processing agreement</h2>
        <p>
          If your organisation needs a signed DPA covering the leads you store with us, email{' '}
          <a href={`mailto:${LEGAL.privacyEmail}`}>{LEGAL.privacyEmail}</a>.
        </p>
      </section>
    </LegalLayout>
  );
}
