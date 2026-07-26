import { ReactNode } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { LogoMark } from '@/components/Logo';
import SiteFooter from '@/components/SiteFooter';

/**
 * Shell for the policy pages.
 *
 * Legal text is only useful if people can read it, so the measure is capped
 * near 70 characters and the type scales with the viewport. Headings carry
 * ids so individual clauses can be linked to directly — which matters when a
 * customer or a regulator asks you to point at one.
 */

interface LegalLayoutProps {
  title: string;
  subtitle?: string;
  lastUpdated: string;
  children: ReactNode;
}

export default function LegalLayout({
  title,
  subtitle,
  lastUpdated,
  children,
}: LegalLayoutProps) {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen bg-white flex flex-col">
      <header className="border-b border-slate-200 sticky top-0 bg-white/90 backdrop-blur z-20">
        <div className="mx-auto max-w-5xl px-4 sm:px-6 h-16 flex items-center justify-between gap-4">
          <button
            onClick={() => navigate('/')}
            className="flex items-center gap-2.5 cursor-pointer min-w-0"
            aria-label="BizLeads home"
          >
            <LogoMark className="h-8 w-8 shrink-0" />
            <span className="font-semibold text-lg tracking-tight text-slate-900 truncate">
              BizLeads
            </span>
          </button>
          <nav className="flex items-center gap-4 sm:gap-6 text-sm shrink-0">
            <Link to="/pricing" className="text-slate-600 hover:text-slate-900 font-medium">
              Pricing
            </Link>
            <Link to="/login" className="text-slate-600 hover:text-slate-900 font-medium">
              Sign in
            </Link>
          </nav>
        </div>
      </header>

      <main className="flex-1 mx-auto w-full max-w-3xl px-4 sm:px-6 py-10 sm:py-16">
        <h1 className="text-3xl sm:text-4xl font-semibold tracking-tight text-slate-900">
          {title}
        </h1>
        {subtitle && <p className="mt-3 text-base sm:text-lg text-slate-600">{subtitle}</p>}
        <p className="mt-4 text-sm text-slate-500">Last updated: {lastUpdated}</p>

        {/*
          Prose sizing is deliberate: 16px minimum on mobile (smaller text
          triggers zoom-on-focus in iOS Safari and fails WCAG readability),
          relaxed leading, and a measure that stays inside 65-75 characters.
        */}
        <div
          className="mt-10 space-y-10 text-[16px] leading-relaxed text-slate-700
                     [&_h2]:text-xl [&_h2]:sm:text-2xl [&_h2]:font-semibold
                     [&_h2]:text-slate-900 [&_h2]:tracking-tight [&_h2]:scroll-mt-20
                     [&_h3]:text-base [&_h3]:font-semibold [&_h3]:text-slate-900 [&_h3]:mt-6
                     [&_p]:mt-3 [&_ul]:mt-3 [&_ul]:space-y-2 [&_ul]:list-disc [&_ul]:pl-5
                     [&_ol]:mt-3 [&_ol]:space-y-2 [&_ol]:list-decimal [&_ol]:pl-5
                     [&_a]:text-indigo-600 [&_a]:underline [&_a]:underline-offset-2
                     [&_strong]:text-slate-900 [&_strong]:font-semibold"
        >
          {children}
        </div>
      </main>

      <SiteFooter />
    </div>
  );
}
