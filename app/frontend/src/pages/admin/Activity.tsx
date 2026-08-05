/**
 * The audit trail: who did what, when, and whether it worked.
 *
 * Failures are shown in the same feed as successes rather than hidden behind
 * a filter, because the point of a trail is that the bad line is as visible
 * as the good one.
 */
import { useCallback, useEffect, useState } from 'react';
import AdminShell, { formatDateTime } from '@/components/AdminShell';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import { client } from '@/lib/api';
import { cn } from '@/lib/utils';
import { Download, ChevronLeft, ChevronRight } from 'lucide-react';

interface Event {
  id: number;
  action: string;
  status: string;
  user_email: string | null;
  user_id: string | null;
  workspace_id: number | null;
  entity_type: string | null;
  entity_id: string | null;
  summary: string;
  metadata: Record<string, unknown>;
  created_at: string | null;
}

const PAGE = 50;

export default function AdminActivity() {
  const [items, setItems] = useState<Event[]>([]);
  const [total, setTotal] = useState(0);
  const [skip, setSkip] = useState(0);
  const [loading, setLoading] = useState(true);
  const [actions, setActions] = useState<Array<{ action: string; count: number }>>([]);
  const [action, setAction] = useState('all');
  const [status, setStatus] = useState('all');
  const [days, setDays] = useState('7');
  const [q, setQ] = useState('');
  const [expanded, setExpanded] = useState<number | null>(null);

  const params = useCallback(() => {
    const p = new URLSearchParams();
    if (action !== 'all') p.set('action', action);
    if (status !== 'all') p.set('status', status);
    if (days !== 'all') p.set('days', days);
    if (q.trim()) p.set('q', q.trim());
    return p;
  }, [action, status, days, q]);

  const load = useCallback(async (offset: number) => {
    setLoading(true);
    try {
      const p = params();
      p.set('skip', String(offset));
      p.set('limit', String(PAGE));
      const res = await client.apiCall.invoke({
        url: `/api/v1/admin/activity?${p.toString()}`, method: 'GET', data: {},
      });
      setItems(res.data?.items ?? []);
      setTotal(res.data?.total ?? 0);
      setSkip(offset);
    } finally {
      setLoading(false);
    }
  }, [params]);

  useEffect(() => { void load(0); }, [load]);

  useEffect(() => {
    (async () => {
      try {
        const res = await client.apiCall.invoke({
          url: '/api/v1/admin/activity/actions', method: 'GET', data: {},
        });
        setActions(res.data?.items ?? []);
      } catch {
        // The filter simply stays limited to "all" — not worth an error state.
      }
    })();
  }, []);

  const exportUrl = () => {
    const p = params();
    p.set('limit', '5000');
    return `/api/v1/admin/export/activity.csv?${p.toString()}`;
  };

  return (
    <AdminShell>
      <div className="space-y-6">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <h1 className="text-2xl font-bold text-slate-900">Activity</h1>
            <p className="text-sm text-slate-500">
              {total.toLocaleString()} events match the current filters.
            </p>
          </div>
          <Button
            variant="outline"
            size="sm"
            className="gap-2"
            onClick={() => window.open(exportUrl(), '_blank')}
          >
            <Download className="h-4 w-4" />
            Export CSV
          </Button>
        </div>

        <Card className="border-slate-200">
          <CardContent className="p-4 flex flex-wrap gap-3">
            <Input
              placeholder="Search summaries and details…"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              className="flex-1 min-w-[220px] border-slate-200"
            />
            <Select value={action} onValueChange={setAction}>
              <SelectTrigger className="w-[200px] border-slate-200">
                <SelectValue placeholder="All actions" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All actions</SelectItem>
                {actions.map((a) => (
                  <SelectItem key={a.action} value={a.action}>
                    {a.action} ({a.count})
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={status} onValueChange={setStatus}>
              <SelectTrigger className="w-[140px] border-slate-200">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Any status</SelectItem>
                <SelectItem value="ok">Succeeded</SelectItem>
                <SelectItem value="failed">Failed</SelectItem>
              </SelectContent>
            </Select>
            <Select value={days} onValueChange={setDays}>
              <SelectTrigger className="w-[140px] border-slate-200">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="1">Last 24 hours</SelectItem>
                <SelectItem value="7">Last 7 days</SelectItem>
                <SelectItem value="30">Last 30 days</SelectItem>
                <SelectItem value="all">All time</SelectItem>
              </SelectContent>
            </Select>
          </CardContent>
        </Card>

        <Card className="border-slate-200">
          <CardContent className="p-0">
            {loading ? (
              <div className="p-4 space-y-2">
                {[...Array(6)].map((_, i) => <Skeleton key={i} className="h-12 rounded" />)}
              </div>
            ) : items.length === 0 ? (
              <div className="p-10 text-center text-sm text-slate-500">
                No activity matches these filters.
              </div>
            ) : (
              <div className="divide-y divide-slate-100">
                {items.map((e) => (
                  <div key={e.id} className="p-4 hover:bg-slate-50">
                    <div
                      className="flex items-start justify-between gap-4 cursor-pointer"
                      onClick={() => setExpanded(expanded === e.id ? null : e.id)}
                    >
                      <div className="min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <Badge
                            variant="outline"
                            className={cn(
                              'text-xs font-mono',
                              e.status === 'failed'
                                ? 'bg-red-50 text-red-700 border-red-200'
                                : 'bg-slate-50 text-slate-600 border-slate-200',
                            )}
                          >
                            {e.action}
                          </Badge>
                          <span className="text-sm text-slate-900 truncate">{e.summary}</span>
                        </div>
                        <p className="text-xs text-slate-500 mt-1">
                          {e.user_email || e.user_id || 'system'}
                          {e.workspace_id ? ` · workspace ${e.workspace_id}` : ''}
                          {e.entity_type ? ` · ${e.entity_type}${e.entity_id ? ` ${e.entity_id}` : ''}` : ''}
                        </p>
                      </div>
                      <span className="text-xs text-slate-400 whitespace-nowrap">
                        {formatDateTime(e.created_at)}
                      </span>
                    </div>
                    {expanded === e.id && (
                      <pre className="mt-3 text-xs bg-slate-900 text-slate-100 rounded p-3 overflow-x-auto">
                        {JSON.stringify(e.metadata, null, 2)}
                      </pre>
                    )}
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        <div className="flex items-center justify-between">
          <p className="text-xs text-slate-500">
            {total === 0 ? '0' : `${skip + 1}–${Math.min(skip + PAGE, total)}`} of {total.toLocaleString()}
          </p>
          <div className="flex gap-2">
            <Button
              variant="outline" size="sm" className="gap-1"
              disabled={skip === 0 || loading}
              onClick={() => void load(Math.max(0, skip - PAGE))}
            >
              <ChevronLeft className="h-4 w-4" /> Previous
            </Button>
            <Button
              variant="outline" size="sm" className="gap-1"
              disabled={skip + PAGE >= total || loading}
              onClick={() => void load(skip + PAGE)}
            >
              Next <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </div>
    </AdminShell>
  );
}
