/**
 * Deciding who gets the free credits.
 *
 * The evidence sits beside the buttons on purpose. A queue that shows only
 * names trains whoever works it to approve everything, and the flags are the
 * entire reason a person rather than a rule is making this call.
 *
 * The flags are worded as observations, and the UI keeps that framing: a
 * shared address is a reason to look, not a verdict. Offices, families and
 * anyone behind one corporate connection share IPs legitimately, and the
 * innocent explanation is usually the right one.
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
import { toast } from 'sonner';
import { Check, X, Ban, RotateCcw, Trash2, AlertTriangle, ShieldCheck } from 'lucide-react';

interface Flag {
  code: string;
  severity: string;
  label: string;
  detail: string;
}

interface Risk {
  severity?: string;
  flags?: Flag[];
  ip?: string | null;
  accounts_from_ip?: string[];
  signups_from_ip_today?: number;
  ip_reputation?: { configured: boolean; is_vpn: boolean | null; note?: string };
}

interface Approval {
  id: number;
  user_id: string;
  email: string | null;
  workspace_id: number | null;
  status: string;
  credits_granted: number;
  decided_by: string | null;
  decided_at: string | null;
  reason: string | null;
  risk: Risk;
  created_at: string | null;
}

const STATUS_CLASS: Record<string, string> = {
  pending: 'bg-amber-50 text-amber-700 border-amber-200',
  approved: 'bg-green-50 text-green-700 border-green-200',
  rejected: 'bg-slate-50 text-slate-500 border-slate-200',
  blocked: 'bg-red-50 text-red-700 border-red-200',
};

export default function AdminApprovals() {
  const [items, setItems] = useState<Approval[]>([]);
  const [freeCredits, setFreeCredits] = useState(25);
  const [status, setStatus] = useState('pending');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const [confirmEmail, setConfirmEmail] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const p = new URLSearchParams({ limit: '100' });
      if (status !== 'all') p.set('status', status);
      const res = await client.apiCall.invoke({
        url: `/api/v1/admin/approvals?${p.toString()}`, method: 'GET', data: {},
      });
      setItems(res.data?.items ?? []);
      setFreeCredits(res.data?.free_credits ?? 25);
    } catch {
      toast.error('Could not load the approval queue.');
    } finally {
      setLoading(false);
    }
  }, [status]);

  useEffect(() => { void load(); }, [load]);

  const act = async (userId: string, action: string, label: string) => {
    setBusy(userId);
    try {
      await client.apiCall.invoke({
        url: `/api/v1/admin/approvals/${userId}/${action}`,
        method: 'POST',
        data: { reason: '' },
      });
      toast.success(label);
      await load();
    } catch (err: any) {
      toast.error(err?.data?.detail ?? `Could not ${action} this account.`);
    } finally {
      setBusy(null);
    }
  };

  const remove = async (userId: string, email: string | null) => {
    setBusy(userId);
    try {
      await client.apiCall.invoke({
        url: `/api/v1/admin/accounts/${userId}`,
        method: 'DELETE',
        data: { confirm_email: confirmEmail, reason: '' },
      });
      toast.success(`Deleted ${email ?? userId}`);
      setConfirmDelete(null);
      setConfirmEmail('');
      await load();
    } catch (err: any) {
      toast.error(err?.data?.detail ?? 'Could not delete this account.');
    } finally {
      setBusy(null);
    }
  };

  return (
    <AdminShell>
      <div className="space-y-6">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <h1 className="text-2xl font-bold text-slate-900">Approvals</h1>
            <p className="text-sm text-slate-500">
              Approving an account grants it {freeCredits} free credits. Until then it
              cannot search.
            </p>
          </div>
          <Select value={status} onValueChange={setStatus}>
            <SelectTrigger className="w-[160px] border-slate-200">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="pending">Pending</SelectItem>
              <SelectItem value="approved">Approved</SelectItem>
              <SelectItem value="rejected">Rejected</SelectItem>
              <SelectItem value="blocked">Blocked</SelectItem>
              <SelectItem value="all">All</SelectItem>
            </SelectContent>
          </Select>
        </div>

        {loading ? (
          <div className="space-y-3">
            {[...Array(3)].map((_, i) => <Skeleton key={i} className="h-32 rounded-xl" />)}
          </div>
        ) : items.length === 0 ? (
          <Card className="border-slate-200">
            <CardContent className="p-10 text-center text-sm text-slate-500">
              Nothing {status === 'all' ? 'here' : `is ${status}`} right now.
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-3">
            {items.map((a) => {
              const flags = a.risk?.flags ?? [];
              const high = flags.filter((f) => f.severity === 'high');
              const reputation = a.risk?.ip_reputation;

              return (
                <Card
                  key={a.id}
                  className={cn('border-slate-200', high.length > 0 && 'border-amber-300')}
                >
                  <CardContent className="p-5 space-y-4">
                    <div className="flex items-start justify-between gap-4 flex-wrap">
                      <div className="min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="font-medium text-slate-900">
                            {a.email ?? a.user_id}
                          </span>
                          <Badge
                            variant="outline"
                            className={cn('text-xs capitalize', STATUS_CLASS[a.status])}
                          >
                            {a.status}
                          </Badge>
                          {high.length > 0 && (
                            <Badge
                              variant="outline"
                              className="text-xs bg-amber-50 text-amber-800 border-amber-300"
                            >
                              <AlertTriangle className="h-3 w-3 mr-1" />
                              needs a look
                            </Badge>
                          )}
                        </div>
                        <p className="text-xs text-slate-500 mt-1">
                          Signed up {formatDateTime(a.created_at)}
                          {a.risk?.ip ? ` · from ${a.risk.ip}` : ''}
                          {a.decided_by ? ` · decided by ${a.decided_by}` : ''}
                        </p>
                      </div>

                      <div className="flex gap-2 flex-wrap">
                        {a.status !== 'approved' && (
                          <Button
                            size="sm"
                            disabled={busy === a.user_id}
                            onClick={() => act(a.user_id, 'approve', `Approved · ${freeCredits} credits granted`)}
                            className="gap-1.5 bg-green-600 hover:bg-green-700"
                          >
                            <Check className="h-3.5 w-3.5" />
                            Approve
                          </Button>
                        )}
                        {a.status === 'pending' && (
                          <Button
                            size="sm" variant="outline" disabled={busy === a.user_id}
                            onClick={() => act(a.user_id, 'reject', 'Rejected')}
                            className="gap-1.5"
                          >
                            <X className="h-3.5 w-3.5" />
                            Reject
                          </Button>
                        )}
                        {a.status === 'blocked' ? (
                          <Button
                            size="sm" variant="outline" disabled={busy === a.user_id}
                            onClick={() => act(a.user_id, 'unblock', 'Unblocked')}
                            className="gap-1.5"
                          >
                            <RotateCcw className="h-3.5 w-3.5" />
                            Unblock
                          </Button>
                        ) : (
                          <Button
                            size="sm" variant="outline" disabled={busy === a.user_id}
                            onClick={() => act(a.user_id, 'block', 'Blocked')}
                            className="gap-1.5 border-red-200 text-red-700 hover:bg-red-50"
                          >
                            <Ban className="h-3.5 w-3.5" />
                            Block
                          </Button>
                        )}
                        <Button
                          size="sm" variant="ghost" disabled={busy === a.user_id}
                          onClick={() => {
                            setConfirmDelete(confirmDelete === a.user_id ? null : a.user_id);
                            setConfirmEmail('');
                          }}
                          className="gap-1.5 text-slate-500 hover:text-red-700"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                          Delete
                        </Button>
                      </div>
                    </div>

                    {/* Evidence */}
                    {flags.length > 0 ? (
                      <div className="space-y-1.5">
                        {flags.map((f) => (
                          <div
                            key={f.code}
                            className={cn(
                              'rounded border px-3 py-2',
                              f.severity === 'high'
                                ? 'border-amber-200 bg-amber-50'
                                : 'border-slate-200 bg-slate-50',
                            )}
                          >
                            <p className={cn(
                              'text-xs font-medium',
                              f.severity === 'high' ? 'text-amber-900' : 'text-slate-700',
                            )}>
                              {f.label}
                            </p>
                            <p className="text-xs text-slate-600 mt-0.5">{f.detail}</p>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="text-xs text-green-700 flex items-center gap-1.5">
                        <ShieldCheck className="h-3.5 w-3.5" />
                        Nothing unusual found.
                      </p>
                    )}

                    {/* Stated rather than left blank: an unrun check must not
                        read as a clean one. */}
                    {reputation && !reputation.configured && (
                      <p className="text-xs text-slate-400">
                        VPN / proxy check did not run — no IP reputation provider is
                        configured, so this account has not been checked for one.
                      </p>
                    )}

                    {confirmDelete === a.user_id && (
                      <div className="rounded border border-red-200 bg-red-50 p-3 space-y-2">
                        <p className="text-xs text-red-900">
                          This deletes the account, its workspace and every lead it owns.
                          It cannot be undone. Type <strong>{a.email}</strong> to confirm.
                        </p>
                        <div className="flex gap-2">
                          <Input
                            value={confirmEmail}
                            onChange={(e) => setConfirmEmail(e.target.value)}
                            placeholder={a.email ?? ''}
                            className="border-red-200 bg-white text-sm"
                          />
                          <Button
                            size="sm"
                            variant="destructive"
                            disabled={busy === a.user_id || confirmEmail !== a.email}
                            onClick={() => remove(a.user_id, a.email)}
                          >
                            Delete permanently
                          </Button>
                        </div>
                      </div>
                    )}
                  </CardContent>
                </Card>
              );
            })}
          </div>
        )}
      </div>
    </AdminShell>
  );
}
