import LegalLayout from '@/components/LegalLayout';
import { LEGAL } from '@/lib/legal';

/**
 * There is no consent banner on this site, and that is a deliberate,
 * defensible position rather than an omission: UK PECR reg. 6(4) and the EU
 * ePrivacy Directive Art. 5(3) exempt storage that is strictly necessary to
 * deliver a service the user asked for. Everything listed below is in that
 * category. The moment anything analytic or advertising is added, a banner
 * becomes mandatory — which is why this page enumerates the storage rather
 * than describing it vaguely.
 */

const STORAGE = [
  {
    name: 'Supabase auth session',
    type: 'Local storage',
    purpose:
      'Keeps you signed in between page loads. Without it you would be signed out on every navigation.',
    duration: 'Until you sign out, or the session expires',
    essential: true,
  },
  {
    name: 'sidebar:state',
    type: 'Cookie',
    purpose: 'Remembers whether you collapsed the navigation sidebar.',
    duration: '7 days',
    essential: true,
  },
];

export default function Cookies() {
  return (
    <LegalLayout
      title="Cookies and local storage"
      subtitle="A complete list. There are no advertising or analytics cookies on this site."
      lastUpdated={LEGAL.lastUpdated}
    >
      <section>
        <h2 id="why-no-banner">Why there is no cookie banner</h2>
        <p>
          You have not been shown a consent banner because we do not use anything that requires
          consent. UK PECR and the EU ePrivacy Directive exempt storage that is{' '}
          <strong>strictly necessary</strong> to provide a service you have asked for. Everything
          we store falls into that category.
        </p>
        <p>
          We run <strong>no analytics, no advertising, no session recording and no third-party
          trackers</strong>. Nobody is following you around the internet on our behalf.
        </p>
      </section>

      <section>
        <h2 id="what-we-store">Everything we store on your device</h2>

        {/* Scrolls within its own container so the page never scrolls sideways. */}
        <div className="mt-4 overflow-x-auto rounded-lg border border-slate-200">
          <table className="w-full text-sm min-w-[34rem]">
            <thead className="bg-slate-50">
              <tr className="text-left">
                <th className="px-4 py-3 font-medium text-slate-600">Name</th>
                <th className="px-4 py-3 font-medium text-slate-600">Type</th>
                <th className="px-4 py-3 font-medium text-slate-600">Purpose</th>
                <th className="px-4 py-3 font-medium text-slate-600">Retained</th>
              </tr>
            </thead>
            <tbody>
              {STORAGE.map((item) => (
                <tr key={item.name} className="border-t border-slate-200 align-top">
                  <td className="px-4 py-3 font-medium text-slate-900">{item.name}</td>
                  <td className="px-4 py-3 text-slate-600">{item.type}</td>
                  <td className="px-4 py-3 text-slate-600">{item.purpose}</td>
                  <td className="px-4 py-3 text-slate-600 whitespace-nowrap">{item.duration}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section>
        <h2 id="payments">Payment pages</h2>
        <p>
          When you subscribe, Stripe sets its own cookies to process the payment and detect fraud.
          These are necessary to take a payment securely and are governed by Stripe&rsquo;s
          privacy policy.
        </p>
      </section>

      <section>
        <h2 id="control">Controlling storage</h2>
        <p>
          You can clear or block cookies and local storage in your browser settings. Because
          everything we store is essential, blocking it will sign you out and prevent the
          application from working.
        </p>
      </section>

      <section>
        <h2 id="contact">Questions</h2>
        <p>
          Email <a href={`mailto:${LEGAL.privacyEmail}`}>{LEGAL.privacyEmail}</a>, or read the
          full <a href="/privacy">Privacy Policy</a>.
        </p>
      </section>
    </LegalLayout>
  );
}
