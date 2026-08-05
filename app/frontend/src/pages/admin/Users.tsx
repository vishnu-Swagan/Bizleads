/** Every account, with what it has actually done. */
import { useCallback, useEffect, useState } from 'react';
import AdminShell, { formatDateTime, formatNumber } from '@/components/AdminShell';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table';
import { client } from '@/lib/api';
import { Download, ChevronLeft, ChevronRight } from 'lucide-react';

interface AdminUser {
  id: string;
  email: string;
  name: string | null;
  role: string;
  created_at: string | null;
  last_login: string | null;
  last_activity: string | null;
  leads: number;
  searches: number;
  plan: string | null;
  workspace_id: number | null;
  unmetered: boolean;
}

const PAGE = 50;

export default function AdminUsers() {
  const [items, setItems] = useState<AdminUser[]>([]);
  const [total, setTotal] = useState(0);
  const [skip, setSkip] = useState(0);
  const [q, setQ] = useState('');
  const [loading, setLoading] = useState(true);

  const load = useCallback(async (offset: number) => {
    setLoading(true);
    try {
      const p = new URLSearchParams({ skip: String(offset), limit: String(PAGE) });
      if (q.trim()) p.set('q', q.trim());
      const res = await client.apiCall.invoke({
        url: `/api/v1/admin/users?${p.toString()}`, method: 'GET', data: {},
      });
      setItems(res.data?.items ?? []);
      setTotal(res.data?.total ?? 0);
      setSkip(offset);
    } finally {
      setLoading(false);
    }
  }, [q]);

  useEffect(() => { void load(0); }, [load]);

  return (
    <AdminShell>
      <div className="space-y-6">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <h1 className="text-2xl font-bold text-slate-900">Users</h1>
            <p className="text-sm text-slate-500">{total.toLocaleString()} accounts</p>
          </div>
          <Button
            variant="outline" size="sm" className="gap-2"
            onClick={() => window.open('/api/v1/admin/export/users.csv', '_blank')}
          >
            <Download className="h-4 w-4" />
            Export CSV
          </Button>
        </div>

        <Card className="border-slate-200">
          <CardContent className="p-4">
            <Input
              placeholder="Search by email or name…"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              className="border-slate-200 max-w-md"
            />
          </CardContent>
        </Card>

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
                      <TableHead>Email</TableHead>
                      <TableHead>Plan</TableHead>
                      <TableHead className="text-right">Searches</TableHead>
                      <TableHead className="text-right">Leads</TableHead>
                      <TableHead>Signed up</TableHead>
                      <TableHead>Last activity</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {items.map((u) => (
                      <TableRow key={u.id}>
                        <TableCell>
                          <div className="flex items-center gap-2">
                            <span className="text-slate-900">{u.email}</span>
                            {u.unmetered && (
                              <Badge
                                variant="outline"
                                className="text-[10px] bg-amber-50 text-amber-700 border-amber-200"
                                title="Exempt from credit metering — excluded from revenue figures."
                              >
                                internal
                              </Badge>
                            )}
                            {u.role === 'admin' && (
                              <Badge variant="outline" className="text-[10px]">admin</Badge>
                            )}
                          </div>
                          {u.name && <p className="text-xs text-slate-400">{u.name}</p>}
                        </TableCell>
                        <TableCell className="capitalize text-slate-600">{u.plan ?? '—'}</TableCell>
                        <TableCell className="text-right">{formatNumber(u.searches)}</TableCell>
                        <TableCell className="text-right">{formatNumber(u.leads)}</TableCell>
                        <TableCell className="text-slate-500 text-xs">
                          {formatDateTime(u.created_at)}
                        </TableCell>
                        <TableCell className="text-slate-500 text-xs">
                          {formatDateTime(u.last_activity)}
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
