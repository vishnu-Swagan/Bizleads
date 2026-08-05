/** Workspaces, their plan, and how much of it they are using. */
import { useCallback, useEffect, useState } from 'react';
import AdminShell, { formatDateTime, formatNumber } from '@/components/AdminShell';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table';
import { client } from '@/lib/api';
import { cn } from '@/lib/utils';
import { Download, ChevronLeft, ChevronRight } from 'lucide-react';

interface AdminWorkspace {
  id: number;
  name: string;
  owner_id: string;
  plan: string;
  plan_name: string;
  subscription_status: string;
  monthly_credits: number;
  credits_used: number;
  credits_remaining: number;
  max_seats: number;
  trial_ends_at: string | null;
  stripe_customer_id: string | null;
  leads: number;
  created_at: string | null;
}

const PAGE = 50;

const STATUS_CLASS: Record<string, string> = {
  active: 'bg-green-50 text-green-700 border-green-200',
  trialing: 'bg-blue-50 text-blue-700 border-blue-200',
  canceled: 'bg-slate-50 text-slate-500 border-slate-200',
  past_due: 'bg-red-50 text-red-700 border-red-200',
};

export default function AdminWorkspaces() {
  const [items, setItems] = useState<AdminWorkspace[]>([]);
  const [total, setTotal] = useState(0);
  const [skip, setSkip] = useState(0);
  const [plan, setPlan] = useState('all');
  const [loading, setLoading] = useState(true);

  const load = useCallback(async (offset: number) => {
    setLoading(true);
    try {
      const p = new URLSearchParams({ skip: String(offset), limit: String(PAGE) });
      if (plan !== 'all') p.set('plan', plan);
      const res = await client.apiCall.invoke({
        url: `/api/v1/admin/workspaces?${p.toString()}`, method: 'GET', data: {},
      });
      setItems(res.data?.items ?? []);
      setTotal(res.data?.total ?? 0);
      setSkip(offset);
    } finally {
      setLoading(false);
    }
  }, [plan]);

  useEffect(() => { void load(0); }, [load]);

  return (
    <AdminShell>
      <div className="space-y-6">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <h1 className="text-2xl font-bold text-slate-900">Workspaces</h1>
            <p className="text-sm text-slate-500">{total.toLocaleString()} workspaces</p>
          </div>
          <div className="flex gap-2">
            <Select value={plan} onValueChange={setPlan}>
              <SelectTrigger className="w-[150px] border-slate-200">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All plans</SelectItem>
                <SelectItem value="trial">Trial</SelectItem>
                <SelectItem value="solo">Solo</SelectItem>
                <SelectItem value="pro">Pro</SelectItem>
                <SelectItem value="agency">Agency</SelectItem>
              </SelectContent>
            </Select>
            <Button
              variant="outline" size="sm" className="gap-2"
              onClick={() => window.open('/api/v1/admin/export/workspaces.csv', '_blank')}
            >
              <Download className="h-4 w-4" />
              Export CSV
            </Button>
          </div>
        </div>

        <Card className="border-slate-200">
          <CardContent className="p-0">
            {loading ? (
              <div className="p-4 space-y-2">
                {[...Array(6)].map((_, i) => <Skeleton key={i} className="h-10 rounded" />)}
              </div>
            ) : (
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow className="bg-slate-50">
                      <TableHead>Workspace</TableHead>
                      <TableHead>Plan</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead className="text-right">Credits used</TableHead>
                      <TableHead className="text-right">Leads</TableHead>
                      <TableHead>Created</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {items.map((w) => (
                      <TableRow key={w.id}>
                        <TableCell>
                          <p className="text-slate-900">{w.name}</p>
                          <p className="text-xs text-slate-400 font-mono">#{w.id}</p>
                        </TableCell>
                        <TableCell className="text-slate-600">{w.plan_name}</TableCell>
                        <TableCell>
                          <Badge
                            variant="outline"
                            className={cn(
                              'text-xs capitalize',
                              STATUS_CLASS[w.subscription_status] ??
                                'bg-slate-50 text-slate-600 border-slate-200',
                            )}
                          >
                            {w.subscription_status}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-right text-slate-600">
                          {formatNumber(w.credits_used)} / {formatNumber(w.monthly_credits)}
                        </TableCell>
                        <TableCell className="text-right">{formatNumber(w.leads)}</TableCell>
                        <TableCell className="text-slate-500 text-xs">
                          {formatDateTime(w.created_at)}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
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
