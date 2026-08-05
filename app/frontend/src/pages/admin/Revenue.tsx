/**
 * Subscription mix and roughly what it is worth.
 *
 * The estimate warning is rendered prominently and deliberately. A number on
 * a dashboard that looks like accounting gets quoted like accounting, and
 * this one knows nothing about discounts, refunds or failed payments.
 */
import { useEffect, useState } from 'react';
import AdminShell, { formatNumber } from '@/components/AdminShell';
import { Card, CardContent } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { client } from '@/lib/api';
import { Info } from 'lucide-react';

interface PlanRow {
  plan: string;
  plan_name: string;
  workspaces: number;
  monthly_price: number;
  monthly_value: number;
}

interface Revenue {
  by_plan: PlanRow[];
  mrr: number;
  paying_workspaces: number;
  total_workspaces: number;
  conversion_rate: number;
  subscription_status: { trialing: number; active: number; canceled: number };
  mrr_is_estimated: boolean;
  mrr_note: string;
}

const money = (n: number) =>
  n.toLocaleString(undefined, { style: 'currency', currency: 'GBP', maximumFractionDigits: 0 });

export default function AdminRevenue() {
  const [data, setData] = useState<Revenue | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const res = await client.apiCall.invoke({
          url: '/api/v1/admin/revenue', method: 'GET', data: {},
        });
        setData(res.data);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  return (
    <AdminShell>
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Revenue</h1>
          <p className="text-sm text-slate-500">Subscription mix across all workspaces.</p>
        </div>

        {loading ? (
          <div className="grid gap-4 md:grid-cols-3">
            {[...Array(3)].map((_, i) => <Skeleton key={i} className="h-28 rounded-xl" />)}
          </div>
        ) : data ? (
          <>
            <div className="grid gap-4 md:grid-cols-3">
              <Card className="border-slate-200">
                <CardContent className="p-5">
                  <p className="text-xs uppercase tracking-wide text-slate-500">
                    Estimated MRR
                  </p>
                  <p className="text-2xl font-bold text-slate-900 mt-1">{money(data.mrr)}</p>
                </CardContent>
              </Card>
              <Card className="border-slate-200">
                <CardContent className="p-5">
                  <p className="text-xs uppercase tracking-wide text-slate-500">Paying</p>
                  <p className="text-2xl font-bold text-slate-900 mt-1">
                    {formatNumber(data.paying_workspaces)}
                    <span className="text-sm font-normal text-slate-400">
                      /{formatNumber(data.total_workspaces)}
                    </span>
                  </p>
                </CardContent>
              </Card>
              <Card className="border-slate-200">
                <CardContent className="p-5">
                  <p className="text-xs uppercase tracking-wide text-slate-500">Conversion</p>
                  <p className="text-2xl font-bold text-slate-900 mt-1">{data.conversion_rate}%</p>
                  <p className="text-xs text-slate-500 mt-1">Paying ÷ all workspaces</p>
                </CardContent>
              </Card>
            </div>

            <Card className="border-amber-200 bg-amber-50">
              <CardContent className="p-4 flex gap-3">
                <Info className="h-4 w-4 text-amber-600 shrink-0 mt-0.5" />
                <p className="text-xs text-amber-900">{data.mrr_note}</p>
              </CardContent>
            </Card>

            <Card className="border-slate-200">
              <CardContent className="p-0">
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-slate-200 bg-slate-50">
                        <th className="text-left font-medium text-slate-600 px-5 py-3">Plan</th>
                        <th className="text-right font-medium text-slate-600 px-5 py-3">Workspaces</th>
                        <th className="text-right font-medium text-slate-600 px-5 py-3">Price</th>
                        <th className="text-right font-medium text-slate-600 px-5 py-3">Monthly value</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.by_plan.map((p) => (
                        <tr key={p.plan} className="border-b border-slate-100 last:border-0">
                          <td className="px-5 py-3 text-slate-900">{p.plan_name}</td>
                          <td className="px-5 py-3 text-right">{formatNumber(p.workspaces)}</td>
                          <td className="px-5 py-3 text-right text-slate-600">
                            {p.monthly_price ? money(p.monthly_price) : '—'}
                          </td>
                          <td className="px-5 py-3 text-right font-medium text-slate-900">
                            {p.monthly_value ? money(p.monthly_value) : '—'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>

            <div className="grid gap-4 md:grid-cols-3">
              {([
                ['Trialing', data.subscription_status.trialing],
                ['Active', data.subscription_status.active],
                ['Cancelled', data.subscription_status.canceled],
              ] as const).map(([label, value]) => (
                <Card key={label} className="border-slate-200">
                  <CardContent className="p-5">
                    <p className="text-xs uppercase tracking-wide text-slate-500">{label}</p>
                    <p className="text-2xl font-bold text-slate-900 mt-1">{formatNumber(value)}</p>
                  </CardContent>
                </Card>
              ))}
            </div>
          </>
        ) : null}
      </div>
    </AdminShell>
  );
}
