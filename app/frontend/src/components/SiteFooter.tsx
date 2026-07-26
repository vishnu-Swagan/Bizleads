import { Link } from 'react-router-dom';
import { LogoMark } from '@/components/Logo';
import { LEGAL } from '@/lib/legal';

/**
 * Public site footer.
 *
 * Single source for the legal links and the copyright line, so the policies
 * stay reachable from every public page — a requirement in practice, since
 * terms nobody can find are terms nobody agreed to. The year is derived, not
 * typed: the previous footers were hardcoded to 2024 and had already drifted.
 */
export default function SiteFooter() {
  const year = new Date().getFullYear();

  return (
    <footer className="border-t border-slate-200 bg-slate-50">
      <div className="mx-auto max-w-6xl px-4 sm:px-6 py-10">
        <div className="flex flex-col gap-8 sm:flex-row sm:items-start sm:justify-between">
          <div className="max-w-xs">
            <div className="flex items-center gap-2.5">
              <LogoMark className="h-8 w-8" />
              <span className="font-semibold text-slate-900 tracking-tight">BizLeads</span>
            </div>
            <p className="mt-3 text-sm text-slate-600">
              Website opportunity intelligence. Real businesses from licensed data —
              never generated.
            </p>
          </div>

          <nav aria-label="Footer" className="grid grid-cols-2 gap-x-10 gap-y-6 sm:gap-x-16">
            <div>
              <h2 className="text-sm font-semibold text-slate-900">Product</h2>
              <ul className="mt-3 space-y-2 text-sm">
                <li>
                  <Link to="/pricing" className="text-slate-600 hover:text-slate-900">
                    Pricing
                  </Link>
                </li>
                <li>
                  <Link to="/login" className="text-slate-600 hover:text-slate-900">
                    Sign in
                  </Link>
                </li>
              </ul>
            </div>
            <div>
              <h2 className="text-sm font-semibold text-slate-900">Legal</h2>
              <ul className="mt-3 space-y-2 text-sm">
                <li>
                  <Link to="/terms" className="text-slate-600 hover:text-slate-900">
                    Terms of Service
                  </Link>
                </li>
                <li>
                  <Link to="/privacy" className="text-slate-600 hover:text-slate-900">
                    Privacy Policy
                  </Link>
                </li>
                <li>
                  <Link to="/cookies" className="text-slate-600 hover:text-slate-900">
                    Cookies
                  </Link>
                </li>
                <li>
                  <Link to="/subprocessors" className="text-slate-600 hover:text-slate-900">
                    Sub-processors
                  </Link>
                </li>
              </ul>
            </div>
          </nav>
        </div>

        <div className="mt-10 border-t border-slate-200 pt-6 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-xs text-slate-500">
            © {year} {LEGAL.entity}. All rights reserved.
          </p>
          <p className="text-xs text-slate-500">
            Business data licensed from MapBox. Payments processed by Stripe.
          </p>
        </div>
      </div>
    </footer>
  );
}
