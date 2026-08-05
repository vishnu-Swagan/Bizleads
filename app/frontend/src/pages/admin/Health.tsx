/**
 * What is configured, and what has been going wrong.
 *
 * Providers report configuration, not reachability — a live probe on every
 * dashboard load would spend the operator's API quota to answer a question
 * the failure counts answer better.
 */
import { useEffect, useState } from 'react';
import AdminShell, { formatDateTime } from '@/components/AdminShell';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { client } from '@/lib/api';
import { cn } from '@/lib/utils';
import { CheckCircle2, XCircle, AlertTriangle } from 'lucide-react';

interface Health {
  providers: Record<string, boolean | string | null>;
  searches_24h: number;
  searches_failed_24h: number;
  search_failure_rate_24h: number;
  failures_7d: number;
  recent_failures: Array<{
    id: number; action: string; summary: string; user_email: string | null; created_at: string | null;
  }>;
  environment: string;
}

const LABELS: Record<string, string> = {
  discovery_configured: 'Discovery provider',
  google_places: 'Google Places',
  mapbox: 'MapBox',
  pagespeed: 'PageSpeed',
  ai_writer: 'AI writing',
  stripe: 'Stripe',
  stripe_webhook: 'Stripe webhook',
};

export default function AdminHealth() {
  const [data, setData] = useState<Health | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const res = await client.apiCall.invoke({
          url: '/api/v1/admin/health', method: 'GET', data: {},
        });
        setData(res.data);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const rate = data?.search_failure_rate_24h ?? 0;

  return (
    <AdminShell>
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Health</h1>
          <p className="text-sm text-slate-500">
            Provider configuration and recent failures.
            {data?.environment ? ` Environment: ${data.environment}.` : ''}
          </p>
        </div>

        {loading ? (
          <Skeleton className="h-40 rounded-xl" />
        ) : data ? (
          <>
            <div className="grid gap-4 md:grid-cols-3">
              <Card className="border-slate-200">
                <CardContent className="p-5">
                  <p className="text-xs uppercase tracking-wide text-slate-500">Searches (24h)</p>
                  <p className="text-2xl font-bold text-slate-900 mt-1">{data.searches_24h}</p>
                </CardContent>
              </Card>
              <Card className={cn('border-slate-200', rate > 10 && 'border-red-200 bg-red-50')}>
                <CardContent className="p-5">
                  <p className="text-xs uppercase tracking-wide text-slate-500">
                    Failure rate (24h)
                  </p>
                  <p
                    className={cn(
                      'text-2xl font-bold mt-1',
                      rate > 10 ? 'text-red-700' : 'text-slate-900',
                    )}
                  >
                    {rate}%
                  </p>
                  <p className="text-xs text-slate-500 mt-1">
                    {data.searches_failed_24h} failed
                  </p>
                </CardContent>
              </Card>
              <Card className="border-slate-200">
                <CardContent className="p-5">
                  <p className="text-xs uppercase tracking-wide text-slate-500">Failures (7d)</p>
                  <p className="text-2xl font-bold text-slate-900 mt-1">{data.failures_7d}</p>
                </CardContent>
              </Card>
            </div>

            <Card className="border-slate-200">
              <CardContent className="p-5">
                <h2 className="text-sm font-medium text-slate-900 mb-3">Providers</h2>
                <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                  {Object.entries(LABELS).map(([key, label]) => {
                    const on = data.providers[key] === true;
                    return (
                      <div
                        key={key}
                        className="flex items-center justify-between rounded border border-slate-200 px-3 py-2"
                      >
                        <span className="text-sm text-slate-700">{label}</span>
                        {on ? (
                          <span className="flex items-center gap-1 text-xs text-green-700">
                            <CheckCircle2 className="h-4 w-4" /> Configured
                          </span>
                        ) : (
                          <span className="flex items-center gap-1 text-xs text-slate-400">
                            <XCircle className="h-4 w-4" /> Not set
                          </span>
                        )}
                      </div>
                    );
                  })}
                </div>
                {data.providers.discovery_provider && (
                  <p className="text-xs text-slate-500 mt-3">
                    Active discovery provider:{' '}
                    <Badge variant="outline" className="text-xs">
                      {String(data.providers.discovery_provider)}
                    </Badge>
                    {data.providers.ai_model ? (
                      <>
                        {' '}· AI model:{' '}
                        <Badge variant="outline" className="text-xs">
                          {String(data.providers.ai_model)}
                        </Badge>
                      </>
                    ) : null}
                  </p>
                )}
              </CardContent>
            </Card>

            <Card className="border-slate-200">
              <CardContent className="p-0">
                <div className="px-5 py-4 border-b border-slate-100">
                  <h2 className="text-sm font-medium text-slate-900">Recent failures</h2>
                </div>
                {data.recent_failures.length === 0 ? (
                  <div className="p-8 text-center text-sm text-slate-500">
                    Nothing has failed in the last 7 days.
                  </div>
                ) : (
                  <div className="divide-y divide-slate-100">
                    {data.recent_failures.map((f) => (
                      <div key={f.id} className="px-5 py-3 flex items-start gap-3">
                        <AlertTriangle className="h-4 w-4 text-red-500 shrink-0 mt-0.5" />
                        <div className="min-w-0 flex-1">
                          <p className="text-sm text-slate-900 break-words">{f.summary}</p>
                          <p className="text-xs text-slate-500 mt-0.5">
                            {f.action} · {f.user_email || 'system'} · {formatDateTime(f.created_at)}
                          </p>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </>
        ) : null}
      </div>
    </AdminShell>
  );
}
