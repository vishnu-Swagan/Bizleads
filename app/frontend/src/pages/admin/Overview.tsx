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
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { client } from '@/lib/api';
import { AlertTriangle, Search, Users, Mail, Sparkles, CreditCard, UserPlus } from 'lucide-react';
import { toast } from 'sonner';

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
  const [remeasuring, setRemeasuring] = useState(false);
  const [remeasure, setRemeasure] = useState<{
    attempted: number; emails_found: number; still_without_email: number;
  } | null>(null);

  const runRemeasure = async () => {
    setRemeasuring(true);
    try {
      const res = await client.apiCall.invoke({
        url: '/api/v1/admin/leads/remeasure', method: 'POST', data: { limit: 50 },
        options: { timeout: 300000 },
      });
      setRemeasure(res.data);
      toast.success(`Found ${res.data?.emails_found ?? 0} email addresses`);
    } catch (err: any) {
      toast.error(err?.data?.detail ?? 'Re-measure failed.');
    } finally {
      setRemeasuring(false);
    }
  };

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

            {/* Leads saved before discovery started measuring have no email
                and no way to acquire one, since measurement now happens at
                discovery and they were found before it did. */}
            {data.all_time.leads_discovered > data.all_time.leads_with_email && (
              <Card className="border-slate-200">
                <CardContent className="p-5 flex items-start justify-between gap-4 flex-wrap">
                  <div>
                    <p className="text-sm font-medium text-slate-900">
                      {formatNumber(data.all_time.leads_discovered - data.all_time.leads_with_email)} leads
                      have no email address
                    </p>
                    <p className="text-xs text-slate-500 mt-0.5">
                      Mostly leads found before measurement moved into discovery. Re-measuring
                      reads their contact pages and fills in what it finds. Runs 50 at a time
                      and never overwrites an address already on file.
                    </p>
                    {remeasure && (
                      <p className="text-xs text-green-700 mt-1.5">
                        Checked {remeasure.attempted}, found {remeasure.emails_found} email
                        {remeasure.emails_found === 1 ? '' : 's'} · {remeasure.still_without_email} still blank
                      </p>
                    )}
                  </div>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={remeasuring}
                    onClick={runRemeasure}
                    className="gap-2 shrink-0"
                  >
                    {remeasuring ? 'Re-measuring…' : 'Re-measure 50'}
                  </Button>
                </CardContent>
              </Card>
            )}

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
