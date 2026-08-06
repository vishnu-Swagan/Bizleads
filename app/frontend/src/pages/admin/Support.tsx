/**
 * The request queue.
 *
 * Written as a queue, not a chat, and the copy says so in the one place it
 * matters: next to the box you type into. Nobody is sitting in this
 * application waiting for a message — requests are collected when whoever
 * works on the product next sits down. Styling this like a messenger would
 * promise a reply that is not coming, and someone watching for one is worse
 * off than someone who was told plainly when to expect it.
 */
import { useCallback, useEffect, useState } from 'react';
import AdminShell, { formatDateTime } from '@/components/AdminShell';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import { client } from '@/lib/api';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';
import { Plus, Send, CheckCircle2, RotateCcw, Info, AlertTriangle } from 'lucide-react';

interface Message {
  id: number;
  author_type: 'operator' | 'engineer';
  author: string | null;
  body: string;
  created_at: string | null;
}

interface Ticket {
  id: number;
  title: string;
  body: string;
  status: string;
  priority: string;
  kind: string;
  area: string;
  created_by_email: string | null;
  created_at: string | null;
  resolved_at: string | null;
  message_count?: number;
  messages?: Message[];
}

const STATUS_CLASS: Record<string, string> = {
  open: 'bg-amber-50 text-amber-700 border-amber-200',
  in_progress: 'bg-blue-50 text-blue-700 border-blue-200',
  resolved: 'bg-green-50 text-green-700 border-green-200',
  closed: 'bg-slate-50 text-slate-500 border-slate-200',
};

const STATUS_LABEL: Record<string, string> = {
  open: 'Open',
  in_progress: 'In progress',
  resolved: 'Resolved',
  closed: 'Closed',
};

export default function AdminSupport() {
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [selected, setSelected] = useState<Ticket | null>(null);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('active');
  const [agentConfigured, setAgentConfigured] = useState(true);
  const [composing, setComposing] = useState(false);
  const [busy, setBusy] = useState(false);

  const [title, setTitle] = useState('');
  const [body, setBody] = useState('');
  const [priority, setPriority] = useState('normal');
  const [area, setArea] = useState('');
  const [reply, setReply] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const p = new URLSearchParams({ limit: '100' });
      if (filter !== 'all') p.set('status', filter);
      const res = await client.apiCall.invoke({
        url: `/api/v1/support?${p.toString()}`, method: 'GET', data: {},
      });
      setTickets(res.data?.items ?? []);
      setAgentConfigured(res.data?.agent_access_configured !== false);
    } catch {
      toast.error('Could not load requests.');
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => { void load(); }, [load]);

  const open = async (id: number) => {
    try {
      const res = await client.apiCall.invoke({
        url: `/api/v1/support/${id}`, method: 'GET', data: {},
      });
      setSelected(res.data);
    } catch {
      toast.error('Could not open that request.');
    }
  };

  const create = async () => {
    if (!title.trim()) return;
    setBusy(true);
    try {
      const res = await client.apiCall.invoke({
        url: '/api/v1/support', method: 'POST',
        data: { title, body, priority, area },
      });
      toast.success('Request logged.');
      setTitle(''); setBody(''); setPriority('normal'); setArea('');
      setComposing(false);
      await load();
      setSelected(res.data);
    } catch {
      toast.error('Could not log that request.');
    } finally {
      setBusy(false);
    }
  };

  const send = async () => {
    if (!reply.trim() || !selected) return;
    setBusy(true);
    try {
      const res = await client.apiCall.invoke({
        url: `/api/v1/support/${selected.id}/messages`, method: 'POST',
        data: { body: reply },
      });
      setSelected(res.data);
      setReply('');
      await load();
    } catch {
      toast.error('Could not add that message.');
    } finally {
      setBusy(false);
    }
  };

  const setStatus = async (status: string) => {
    if (!selected) return;
    setBusy(true);
    try {
      const res = await client.apiCall.invoke({
        url: `/api/v1/support/${selected.id}/status`, method: 'POST', data: { status },
      });
      setSelected(res.data);
      await load();
    } catch {
      toast.error('Could not change the status.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <AdminShell>
      <div className="space-y-6">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <h1 className="text-2xl font-bold text-slate-900">Support requests</h1>
            <p className="text-sm text-slate-500">
              Log issues and changes here. They are collected at the start of the next
              engineering session, and the outcome is written back onto the thread.
            </p>
          </div>
          <div className="flex gap-2">
            <Select value={filter} onValueChange={setFilter}>
              <SelectTrigger className="w-[150px] border-slate-200">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="active">Open</SelectItem>
                <SelectItem value="resolved">Resolved</SelectItem>
                <SelectItem value="closed">Closed</SelectItem>
                <SelectItem value="all">All</SelectItem>
              </SelectContent>
            </Select>
            <Button onClick={() => setComposing(!composing)} className="gap-2">
              <Plus className="h-4 w-4" />
              New request
            </Button>
          </div>
        </div>

        {/* Stated rather than hidden: a queue nobody can collect from is worth
            knowing about before you file into it. */}
        {!agentConfigured && (
          <Card className="border-amber-200 bg-amber-50">
            <CardContent className="p-4 flex gap-3">
              <AlertTriangle className="h-4 w-4 text-amber-600 shrink-0 mt-0.5" />
              <p className="text-xs text-amber-900">
                <strong>SUPPORT_AGENT_SECRET is not set</strong>, so nobody can collect
                these requests yet. Set it on the API service and share the value with
                whoever works on the product. Requests you log now are still saved.
              </p>
            </CardContent>
          </Card>
        )}

        {composing && (
          <Card className="border-slate-200">
            <CardContent className="p-5 space-y-3">
              <Input
                placeholder="What is the issue or change? (one line)"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                className="border-slate-200"
              />
              <Textarea
                placeholder="What happens, what you expected, and where. Screenshots described in words are fine."
                value={body}
                onChange={(e) => setBody(e.target.value)}
                rows={5}
                className="border-slate-200"
              />
              <div className="flex gap-2 flex-wrap">
                <Select value={priority} onValueChange={setPriority}>
                  <SelectTrigger className="w-[150px] border-slate-200">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="low">Low</SelectItem>
                    <SelectItem value="normal">Normal</SelectItem>
                    <SelectItem value="high">High</SelectItem>
                  </SelectContent>
                </Select>
                <Input
                  placeholder="Area (e.g. export, discovery)"
                  value={area}
                  onChange={(e) => setArea(e.target.value)}
                  className="border-slate-200 max-w-[240px]"
                />
                <Button onClick={create} disabled={busy || !title.trim()} className="gap-2">
                  <Send className="h-4 w-4" />
                  Log it
                </Button>
              </div>
            </CardContent>
          </Card>
        )}

        <div className="grid gap-4 lg:grid-cols-[minmax(0,360px)_1fr]">
          {/* List */}
          <Card className="border-slate-200 h-fit">
            <CardContent className="p-0">
              {loading ? (
                <div className="p-4 space-y-2">
                  {[...Array(4)].map((_, i) => <Skeleton key={i} className="h-14 rounded" />)}
                </div>
              ) : tickets.length === 0 ? (
                <div className="p-8 text-center text-sm text-slate-500">
                  Nothing here. Use <strong>New request</strong> when something needs fixing.
                </div>
              ) : (
                <div className="divide-y divide-slate-100 max-h-[70vh] overflow-y-auto">
                  {tickets.map((t) => (
                    <button
                      key={t.id}
                      onClick={() => open(t.id)}
                      className={cn(
                        'w-full text-left p-4 hover:bg-slate-50 transition-colors',
                        selected?.id === t.id && 'bg-slate-50',
                      )}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <span className="text-sm font-medium text-slate-900 truncate">
                          {t.title}
                        </span>
                        <Badge
                          variant="outline"
                          className={cn('text-[10px] shrink-0', STATUS_CLASS[t.status])}
                        >
                          {STATUS_LABEL[t.status] ?? t.status}
                        </Badge>
                      </div>
                      <p className="text-xs text-slate-500 mt-1">
                        #{t.id} · {formatDateTime(t.created_at)}
                        {t.priority === 'high' ? ' · high priority' : ''}
                        {t.message_count ? ` · ${t.message_count} message${t.message_count === 1 ? '' : 's'}` : ''}
                      </p>
                    </button>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Thread */}
          <Card className="border-slate-200">
            <CardContent className="p-5">
              {!selected ? (
                <div className="py-16 text-center text-sm text-slate-500">
                  Select a request to read its thread.
                </div>
              ) : (
                <div className="space-y-4">
                  <div className="flex items-start justify-between gap-4 flex-wrap">
                    <div>
                      <h2 className="text-lg font-medium text-slate-900">{selected.title}</h2>
                      <p className="text-xs text-slate-500 mt-0.5">
                        #{selected.id} · raised by {selected.created_by_email ?? 'unknown'} ·{' '}
                        {formatDateTime(selected.created_at)}
                        {selected.area ? ` · ${selected.area}` : ''}
                      </p>
                    </div>
                    <div className="flex gap-2">
                      {selected.status === 'resolved' || selected.status === 'closed' ? (
                        <Button
                          size="sm" variant="outline" disabled={busy}
                          onClick={() => setStatus('open')} className="gap-1.5"
                        >
                          <RotateCcw className="h-3.5 w-3.5" />
                          Reopen
                        </Button>
                      ) : (
                        <Button
                          size="sm" variant="outline" disabled={busy}
                          onClick={() => setStatus('closed')} className="gap-1.5"
                        >
                          <CheckCircle2 className="h-3.5 w-3.5" />
                          Close
                        </Button>
                      )}
                    </div>
                  </div>

                  {selected.body && (
                    <div className="rounded border border-slate-200 bg-slate-50 p-3">
                      <p className="text-sm text-slate-700 whitespace-pre-wrap">{selected.body}</p>
                    </div>
                  )}

                  <div className="space-y-3">
                    {(selected.messages ?? []).map((m) => (
                      <div
                        key={m.id}
                        className={cn(
                          'rounded border p-3',
                          m.author_type === 'engineer'
                            ? 'border-indigo-200 bg-indigo-50'
                            : 'border-slate-200',
                        )}
                      >
                        <p className="text-xs font-medium text-slate-600 mb-1">
                          {m.author_type === 'engineer' ? 'Engineering' : m.author}
                          <span className="font-normal text-slate-400">
                            {' '}· {formatDateTime(m.created_at)}
                          </span>
                        </p>
                        <p className="text-sm text-slate-800 whitespace-pre-wrap">{m.body}</p>
                      </div>
                    ))}
                  </div>

                  <div className="space-y-2 pt-2 border-t border-slate-100">
                    <Textarea
                      placeholder="Add detail, or reply…"
                      value={reply}
                      onChange={(e) => setReply(e.target.value)}
                      rows={3}
                      className="border-slate-200"
                    />
                    <div className="flex items-center justify-between gap-3 flex-wrap">
                      <p className="text-xs text-slate-400 flex items-center gap-1.5">
                        <Info className="h-3.5 w-3.5 shrink-0" />
                        Not a live chat — this is collected at the start of the next
                        engineering session.
                      </p>
                      <Button onClick={send} disabled={busy || !reply.trim()} size="sm" className="gap-2">
                        <Send className="h-4 w-4" />
                        Add message
                      </Button>
                    </div>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </AdminShell>
  );
}
