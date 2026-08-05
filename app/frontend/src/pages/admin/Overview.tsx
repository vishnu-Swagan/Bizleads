/**
 * Daily activity at a glance.
 *
 * Three windows side by side rather than one number, because "12 searches"
 * means nothing without knowing whether that is a good day. Today next to the
 * 7- and 30-day figures answers that without a chart.
 */
import { useEffect, useState } from 'react';
import AdminShell, { formatNumber } from '@/components/AdminShell';
import { Card, CardContent } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { client } from '@/lib/api';
import { AlertTriangle, Search, Users, Mail, Sparkles, CreditCard, UserPlus } from 'lucide-react';

interface Window {
  searches: number;
  searches_failed: number;
  leads_discovered: number;
  leads_with_email: number;
  outreach_sent: number;
  signups: number;
  credits_spent: number;
}

interface Overview {
  generated_at: string;
  today: Window;
  last_7_days: Window;
  last_30_days: Window;
  all_time: Window;
  totals: { users: number; workspaces: number; active_users_7d: number };
  admin_access_configured: boolean;
}

const ROWS: Array<{ key: keyof Window; label: string; icon: any; hint?: string }> = [
  { key: 'searches', label: 'Searches run', icon: Search },
  { key: 'searches_failed', label: 'Searches failed', icon: AlertTriangle },
  { key: 'leads_discovered', label: 'Leads discovered', icon: Users },
  {
    key: 'leads_with_email',
    label: 'Leads with an email',
    icon: Sparkles,
    hint: 'The difference between a lead you can act on and a row.',
  },
  { key: 'outreach_sent', label: 'Outreach sent', icon: Mail },
  { key: 'signups', label: 'New signups', icon: UserPlus },
  { key: 'credits_spent', label: 'Credits spent', icon: CreditCard },
];

export default function AdminOverview() {
  const [data, setData] = useState<Overview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const res = await client.apiCall.invoke({
          url: '/api/v1/admin/overview', method: 'GET', data: {},
        });
        setData(res.data);
      } catch (err: any) {
        setError(err?.data?.detail ?? 'Could not load the overview.');
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  return (
    <AdminShell>
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Overview</h1>
          <p className="text-sm text-slate-500">
            Platform-wide activity across every workspace.
          </p>
        </div>

        {error && (
          <Card className="border-red-200 bg-red-50">
            <CardContent className="p-4 text-sm text-red-800">{error}</CardContent>
          </Card>
        )}

        {loading ? (
          <div className="grid gap-4 md:grid-cols-3">
            {[...Array(3)].map((_, i) => <Skeleton key={i} className="h-28 rounded-xl" />)}
          </div>
        ) : data ? (
          <>
            <div className="grid gap-4 md:grid-cols-3">
              <Card className="border-slate-200">
                <CardContent className="p-5">
                  <p className="text-xs uppercase tracking-wide text-slate-500">Total users</p>
                  <p className="text-2xl font-bold text-slate-900 mt-1">
                    {formatNumber(data.totals.users)}
                  </p>
                </CardContent>
              </Card>
              <Card className="border-slate-200">
                <CardContent className="p-5">
                  <p className="text-xs uppercase tracking-wide text-slate-500">Workspaces</p>
                  <p className="text-2xl font-bold text-slate-900 mt-1">
                    {formatNumber(data.totals.workspaces)}
                  </p>
                </CardContent>
              </Card>
              <Card className="border-slate-200">
                <CardContent className="p-5">
                  <p className="text-xs uppercase tracking-wide text-slate-500">Active (7 days)</p>
                  <p className="text-2xl font-bold text-slate-900 mt-1">
                    {formatNumber(data.totals.active_users_7d)}
                  </p>
                  {/* Stated because "active" is the number most often quietly
                      redefined to whatever flatters the dashboard. */}
                  <p className="text-xs text-slate-500 mt-1">Accounts that did something</p>
                </CardContent>
              </Card>
            </div>

            <Card className="border-slate-200">
              <CardContent className="p-0">
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-slate-200 bg-slate-50">
                        <th className="text-left font-medium text-slate-600 px-5 py-3">Metric</th>
                        <th className="text-right font-medium text-slate-600 px-5 py-3">Today</th>
                        <th className="text-right font-medium text-slate-600 px-5 py-3">7 days</th>
                        <th className="text-right font-medium text-slate-600 px-5 py-3">30 days</th>
                        <th className="text-right font-medium text-slate-600 px-5 py-3">All time</th>
                      </tr>
                    </thead>
                    <tbody>
                      {ROWS.map(({ key, label, icon: Icon, hint }) => (
                        <tr key={key} className="border-b border-slate-100 last:border-0">
                          <td className="px-5 py-3">
                            <div className="flex items-center gap-2 text-slate-900">
                              <Icon className="h-4 w-4 text-slate-400" />
                              {label}
                            </div>
                            {hint && <p className="text-xs text-slate-400 mt-0.5 ml-6">{hint}</p>}
                          </td>
                          <td className="px-5 py-3 text-right font-medium text-slate-900">
                            {formatNumber(data.today[key])}
                          </td>
                          <td className="px-5 py-3 text-right text-slate-600">
                            {formatNumber(data.last_7_days[key])}
                          </td>
                          <td className="px-5 py-3 text-right text-slate-600">
                            {formatNumber(data.last_30_days[key])}
                          </td>
                          <td className="px-5 py-3 text-right text-slate-600">
                            {formatNumber(data.all_time[key])}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>

            <p className="text-xs text-slate-400">
              Activity counts start from when tracking was deployed, so older
              history shows as zero. Lead and signup totals are read from the
              records themselves and cover everything.
            </p>
          </>
        ) : null}
      </div>
    </AdminShell>
  );
}
