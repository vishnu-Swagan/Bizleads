/**
 * Chrome for the operators' console.
 *
 * Visually distinct from the customer app on purpose — a slate header rather
 * than the product's white one. Someone with both open should never have to
 * check the URL to know whether the numbers on screen are their own workspace
 * or everybody's.
 */
import { ReactNode } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { useCredits } from '@/contexts/CreditsContext';
import { cn } from '@/lib/utils';
import {
  Activity, BarChart3, Users, Building2, PoundSterling, HeartPulse, ArrowLeft, UserCheck, LifeBuoy,
} from 'lucide-react';

const NAV = [
  { to: '/admin', label: 'Overview', icon: BarChart3, exact: true },
  { to: '/admin/approvals', label: 'Approvals', icon: UserCheck },
  { to: '/admin/support', label: 'Support', icon: LifeBuoy },
  { to: '/admin/activity', label: 'Activity', icon: Activity },
  { to: '/admin/users', label: 'Users', icon: Users },
  { to: '/admin/workspaces', label: 'Workspaces', icon: Building2 },
  { to: '/admin/revenue', label: 'Revenue', icon: PoundSterling },
  { to: '/admin/health', label: 'Health', icon: HeartPulse },
];

export default function AdminShell({ children }: { children: ReactNode }) {
  const location = useLocation();
  const { credits } = useCredits();

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="bg-slate-900 text-white">
        <div className="mx-auto max-w-7xl px-4 py-3 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <span className="font-semibold tracking-tight">BizLeads Operations</span>
            <span className="text-[10px] uppercase tracking-wider bg-amber-400 text-slate-900 rounded px-1.5 py-0.5 font-bold">
              Internal
            </span>
          </div>
          <Link
            to="/app/dashboard"
            className="text-xs text-slate-300 hover:text-white flex items-center gap-1.5"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            Back to app
          </Link>
        </div>

        <nav className="mx-auto max-w-7xl px-4 flex gap-1 overflow-x-auto">
          {NAV.map(({ to, label, icon: Icon, exact }) => {
            const active = exact ? location.pathname === to : location.pathname.startsWith(to);
            return (
              <Link
                key={to}
                to={to}
                className={cn(
                  'flex items-center gap-1.5 px-3 py-2 text-sm border-b-2 whitespace-nowrap transition-colors',
                  active
                    ? 'border-amber-400 text-white'
                    : 'border-transparent text-slate-400 hover:text-slate-200',
                )}
              >
                <Icon className="h-4 w-4" />
                {label}
              </Link>
            );
          })}
        </nav>
      </header>

      <main className="mx-auto max-w-7xl px-4 py-6">{children}</main>

      <footer className="mx-auto max-w-7xl px-4 pb-8 text-xs text-slate-400">
        Read-only. Every figure here covers all tenants.
        {credits?.isAdmin ? '' : ' Your access may have been revoked — reload to check.'}
      </footer>
    </div>
  );
}

/** Shared helpers, so every admin page formats the same way. */
export function formatDateTime(value?: string | null): string {
  if (!value) return '—';
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleString();
}

export function formatNumber(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  return value.toLocaleString();
}
