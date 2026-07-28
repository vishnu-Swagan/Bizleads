import { useState, useEffect } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import AppShell from '@/components/AppShell';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Skeleton } from '@/components/ui/skeleton';
import { Switch } from '@/components/ui/switch';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog';
import {
  AlertDialog, AlertDialogContent, AlertDialogHeader, AlertDialogTitle, AlertDialogDescription,
  AlertDialogFooter, AlertDialogAction, AlertDialogCancel,
} from '@/components/ui/alert-dialog';
import { toast } from 'sonner';
import { client } from '@/lib/api';
import {
  CheckCircle2, XCircle, Mail, Send, Loader2, ExternalLink, Sparkles,
  AlertCircle, CalendarClock, Plus, Play, Pencil, Trash2, Inbox, X,
  Wand2, Undo2, Bot,
} from 'lucide-react';

/**
 * Outreach.
 *
 * This page used to be a static mock: three tabs of hardcoded empty states
 * that called no endpoint at all. Meanwhile a working SMTP sender and four
 * live outreach routes sat unused, so "automations is not working" was
 * literally true — nothing was wired to anything.
 *
 * It now reports real email configuration and sends real mail through
 * /api/v1/outreach. When SMTP is unconfigured it names the exact missing
 * variables rather than saying "not connected", because that message sends
 * people hunting through dashboards for a setting they have not created yet.
 */

interface Draft {
  id?: number;
  lead_id: number;
  business_name: string;
  to_email: string;
  subject: string;
  body_text: string;
  body_html: string;
  based_on: string;
}

/** Wording style passed to the AI polish/draft endpoints. Never changes facts. */
type Tone = 'professional' | 'friendly' | 'direct';

const TONE_OPTIONS: { value: Tone; label: string }[] = [
  { value: 'professional', label: 'Professional' },
  { value: 'friendly', label: 'Friendly' },
  { value: 'direct', label: 'Direct' },
];

/** GET /api/v1/outreach/ai/status. Never assume available before this resolves. */
interface AiStatus {
  available: boolean;
  model: string | null;
}

/** Counts measured findings a draft cites, from its `based_on` JSON string. Malformed or missing data honestly counts as zero, never a guess. */
function countBasedOn(basedOn: string | null | undefined): number {
  try {
    const parsed = JSON.parse(basedOn || '[]');
    return Array.isArray(parsed) ? parsed.length : 0;
  } catch {
    return 0;
  }
}

interface Skipped {
  lead_id: number;
  reason: string;
  message: string;
}

interface Lead {
  id: number;
  business_name: string;
  contact_email: string | null;
  website_score: number | null;
  findings: string | null;
}

interface EmailStatus {
  provider?: 'smtp' | 'resend';
  configured: boolean;
  host: string | null;
  port: number;
  from_email: string | null;
  use_tls: boolean;
  username_set: boolean;
  password_set: boolean;
  missing: string[];
}

/** A saved scheduled search + qualify + draft pipeline. */
interface Automation {
  id: number;
  name: string;
  city: string | null;
  country: string | null;
  category: string | null;
  query: string | null;
  website_state: string | null;
  auto_qualify: boolean;
  auto_draft: boolean;
  max_leads_per_run: number;
  schedule: 'manual' | 'daily' | 'weekly' | string;
  enabled: boolean;
  // All null until the automation has actually run once. A null here is
  // never rendered as a fabricated "0" or "-" — it means "never run".
  last_run_at: string | null;
  next_run_at: string | null;
  last_run_summary: string | null;
  last_run_error: string | null;
}

/** A pending draft in the approval queue, awaiting a human Send/Discard. */
interface QueueItem {
  id: number;
  lead_id: number;
  business_name?: string | null;
  to_email: string;
  subject: string;
  body_text: string;
  based_on: string;
  sequence_step?: number;
  status: string;
  send_error?: string | null;
  created_at: string;
}

const SCHEDULE_LABELS: Record<string, string> = {
  manual: 'Manual',
  daily: 'Daily',
  weekly: 'Weekly',
};

/** Formats an ISO timestamp for display; never invents a value for a missing one. */
function formatWhen(iso: string | null): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
}

/**
 * Shared AI control row: tone + "Improve writing" + optional "Rewrite with
 * AI" + "Revert". Used by both the Draft-from-findings results and the
 * Approval queue rows so the two do not drift into different behaviour.
 *
 * Every control is disabled — with a tooltip naming why — whenever AI is
 * unavailable, still loading, or the row itself is mid-action. Wrapping each
 * disabled Button in a <span> is required for the tooltip: a native
 * `disabled` button drops pointer-events entirely, so nothing would ever
 * trigger the hover without it.
 */
function AiControls({
  idPrefix,
  tone,
  onToneChange,
  onPolish,
  polishing,
  onRewrite,
  rewriting,
  canRevert,
  onRevert,
  aiAvailable,
  aiUnavailableReason,
  rowDisabled,
}: {
  idPrefix: string;
  tone: Tone;
  onToneChange: (t: Tone) => void;
  onPolish: () => void;
  polishing: boolean;
  onRewrite?: () => void;
  rewriting?: boolean;
  canRevert: boolean;
  onRevert: () => void;
  aiAvailable: boolean;
  aiUnavailableReason: string;
  rowDisabled?: boolean;
}) {
  const controlsDisabled = !aiAvailable || !!rowDisabled;
  const toneId = `${idPrefix}-tone`;

  return (
    <div className="flex flex-wrap items-center gap-2 border-t border-slate-100 pt-3">
      <Bot className="h-3.5 w-3.5 shrink-0 text-slate-400" aria-hidden="true" />
      <div className="flex items-center gap-1.5">
        <Label htmlFor={toneId} className="text-xs text-slate-500">
          Tone
        </Label>
        <Select value={tone} onValueChange={(v) => onToneChange(v as Tone)} disabled={controlsDisabled}>
          <SelectTrigger
            id={toneId}
            className="h-8 w-[128px] border-slate-200 text-xs cursor-pointer disabled:cursor-not-allowed"
          >
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {TONE_OPTIONS.map((t) => (
              <SelectItem key={t.value} value={t.value}>
                {t.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <Tooltip>
        <TooltipTrigger asChild>
          <span>
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={onPolish}
              disabled={controlsDisabled || polishing}
              className="h-8 gap-1.5 border-slate-200 text-xs cursor-pointer disabled:cursor-not-allowed"
            >
              {polishing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Wand2 className="h-3.5 w-3.5" />}
              Improve writing
            </Button>
          </span>
        </TooltipTrigger>
        <TooltipContent>
          {aiAvailable ? 'Rewrites the wording only — never adds or changes a fact' : aiUnavailableReason}
        </TooltipContent>
      </Tooltip>

      {onRewrite && (
        <Tooltip>
          <TooltipTrigger asChild>
            <span>
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={onRewrite}
                disabled={controlsDisabled || !!rewriting}
                className="h-8 gap-1.5 border-slate-200 text-xs cursor-pointer disabled:cursor-not-allowed"
              >
                {rewriting ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Sparkles className="h-3.5 w-3.5" />
                )}
                Rewrite with AI
              </Button>
            </span>
          </TooltipTrigger>
          <TooltipContent>
            {aiAvailable
              ? "Writes a fresh email from this lead's same measured findings"
              : aiUnavailableReason}
          </TooltipContent>
        </Tooltip>
      )}

      {canRevert && (
        <Button
          type="button"
          size="sm"
          variant="ghost"
          onClick={onRevert}
          disabled={!!rowDisabled}
          className="h-8 gap-1.5 text-xs text-slate-500 cursor-pointer disabled:cursor-not-allowed"
        >
          <Undo2 className="h-3.5 w-3.5" />
          Revert
        </Button>
      )}
    </div>
  );
}

/** Small status badge for a queued draft's lifecycle. Failed carries its error inline, never just a red dot. */
function QueueStatusBadge({ status, sendError }: { status: string; sendError?: string | null }) {
  if (status === 'sent') {
    return (
      <Badge className="gap-1 border-green-200 bg-green-50 text-xs text-green-700">
        <CheckCircle2 className="h-3 w-3" />
        Sent
      </Badge>
    );
  }
  if (status === 'discarded') {
    return (
      <Badge variant="outline" className="text-xs border-slate-200 text-slate-500">
        Discarded
      </Badge>
    );
  }
  if (status === 'failed') {
    return (
      <Tooltip>
        <TooltipTrigger asChild>
          <Badge className="gap-1 border-red-200 bg-red-50 text-xs text-red-700 cursor-default">
            <AlertCircle className="h-3 w-3" />
            Failed
          </Badge>
        </TooltipTrigger>
        <TooltipContent>{sendError || 'Send failed'}</TooltipContent>
      </Tooltip>
    );
  }
  return (
    <Badge variant="outline" className="text-xs border-amber-200 bg-amber-50 text-amber-800">
      Pending
    </Badge>
  );
}

export default function AppAutomations() {
  const { user } = useAuth();
  const [status, setStatus] = useState<EmailStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [catchingUp, setCatchingUp] = useState(false);

  // AI writing assistant: status + per-item polish/rewrite state. AI only
  // ever touches wording — the facts it works from are whatever is already
  // in the subject/body, which itself only ever came from measured findings.
  const [aiStatus, setAiStatus] = useState<AiStatus | null>(null);
  const [aiStatusLoading, setAiStatusLoading] = useState(true);
  const aiAvailable = aiStatus?.available === true;
  const aiUnavailableReason = aiStatusLoading
    ? 'Checking AI availability…'
    : 'AI writing help is not configured for this workspace.';

  const [leads, setLeads] = useState<Lead[]>([]);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const [skipped, setSkipped] = useState<Skipped[]>([]);
  const [composing, setComposing] = useState(false);
  const [sendingAll, setSendingAll] = useState(false);
  const [sentIds, setSentIds] = useState<Set<number>>(new Set());
  const [draftErrors, setDraftErrors] = useState<Record<number, string>>({});

  // Per-draft AI state, keyed by lead_id.
  const [draftTone, setDraftTone] = useState<Record<number, Tone>>({});
  const [draftPolishing, setDraftPolishing] = useState<Set<number>>(new Set());
  const [draftRewriting, setDraftRewriting] = useState<Set<number>>(new Set());
  const [draftPrevious, setDraftPrevious] = useState<Record<number, { subject: string; body_text: string }>>({});

  const [to, setTo] = useState('');
  const [subject, setSubject] = useState('');
  const [body, setBody] = useState('');
  const [sending, setSending] = useState(false);
  const [senderName, setSenderName] = useState('');
  const [senderBusiness, setSenderBusiness] = useState('');

  // One-off composer AI state. No lead_id here, so only "Improve writing"
  // applies — there is nothing to re-draft from.
  const [composerTone, setComposerTone] = useState<Tone>('professional');
  const [composerPolishing, setComposerPolishing] = useState(false);
  const [composerPrevious, setComposerPrevious] = useState<string | null>(null);

  // Scheduled automations.
  const [automations, setAutomations] = useState<Automation[]>([]);
  const [automationsLoading, setAutomationsLoading] = useState(true);
  const [runningIds, setRunningIds] = useState<Set<number>>(new Set());
  const [deleteTarget, setDeleteTarget] = useState<Automation | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [filters, setFilters] = useState<{ countries: string[]; categories: string[] } | null>(null);

  // Create/edit automation form (dialog).
  const [formOpen, setFormOpen] = useState(false);
  const [editingAutomation, setEditingAutomation] = useState<Automation | null>(null);
  const [formName, setFormName] = useState('');
  const [formCity, setFormCity] = useState('');
  const [formCountry, setFormCountry] = useState('all');
  const [formCategory, setFormCategory] = useState('all');
  const [formSchedule, setFormSchedule] = useState<'manual' | 'daily' | 'weekly'>('manual');
  const [formAutoQualify, setFormAutoQualify] = useState(false);
  const [formAutoDraft, setFormAutoDraft] = useState(false);
  const [formMaxLeads, setFormMaxLeads] = useState('10');
  const [savingAutomation, setSavingAutomation] = useState(false);

  // Approval queue.
  const [queue, setQueue] = useState<QueueItem[]>([]);
  const [queueLoading, setQueueLoading] = useState(true);
  const [queueBusyIds, setQueueBusyIds] = useState<Set<number>>(new Set());
  const [queueSendingAll, setQueueSendingAll] = useState(false);

  // Per-queue-item AI state, keyed by draft id.
  const [queueTone, setQueueTone] = useState<Record<number, Tone>>({});
  const [queuePolishing, setQueuePolishing] = useState<Set<number>>(new Set());
  const [queueRewriting, setQueueRewriting] = useState<Set<number>>(new Set());
  const [queuePrevious, setQueuePrevious] = useState<Record<number, { subject: string; body_text: string }>>({});

  useEffect(() => {
    if (user) {
      void loadStatus();
      void loadAiStatus();
      void loadLeads();
      void loadFilters();
      void loadAutomations().then(() => void catchUpDueAutomations());
      void loadQueue();
    }
  }, [user]);

  const loadAiStatus = async () => {
    setAiStatusLoading(true);
    try {
      const res = await client.apiCall.invoke({ url: '/api/v1/outreach/ai/status', method: 'GET', data: {} });
      setAiStatus({ available: res.data?.available === true, model: res.data?.model ?? null });
    } catch {
      // Absent status means "assume unavailable", never a fabricated model name.
      setAiStatus({ available: false, model: null });
    } finally {
      setAiStatusLoading(false);
    }
  };

  /** POST /ai/polish for the current edited text. Never invents new facts — wording only. */
  const callAiPolish = async (text: string, tone: Tone): Promise<string> => {
    const res = await client.apiCall.invoke({
      url: '/api/v1/outreach/ai/polish',
      method: 'POST',
      data: { text, tone },
    });
    return typeof res.data?.text === 'string' ? res.data.text : text;
  };

  /** POST /ai/draft — a fresh email written only from that lead's stored measured findings. */
  const callAiDraft = async (leadId: number, tone: Tone) => {
    const res = await client.apiCall.invoke({
      url: '/api/v1/outreach/ai/draft',
      method: 'POST',
      data: { lead_id: leadId, tone },
    });
    return res.data as { subject: string; body_text: string; based_on: string };
  };

  /**
   * Run anything that has fallen due, whenever the page is opened.
   *
   * The hourly GitHub Actions trigger is the unattended path, but it needs a
   * shared secret configured in two dashboards, and until that is done a
   * schedule silently never fires — which makes the feature look broken when
   * it is merely unconfigured.
   *
   * This closes that gap with no configuration at all: /run-due is
   * authenticated as the signed-in user and scoped to their own automations,
   * so simply opening the page catches up anything overdue. For a daily or
   * weekly schedule that is usually enough on its own.
   *
   * Deliberately fire-and-forget. A run performs discovery and qualification
   * and can take a minute; blocking the page on it would make Outreach feel
   * broken. Failures are swallowed rather than shown — this is background
   * catch-up the user did not ask for, and "Run now" reports errors properly.
   */
  const catchUpDueAutomations = async () => {
    setCatchingUp(true);
    try {
      const res = await client.apiCall.invoke({
        url: '/api/v1/automations/run-due',
        method: 'POST',
        data: {},
        options: { timeout: 180000 },
      });
      const ran = res.data?.results?.length ?? res.data?.ran ?? 0;
      if (ran > 0) {
        toast.success(`Caught up ${ran} scheduled automation${ran === 1 ? '' : 's'}`);
        await Promise.all([loadAutomations(), loadQueue()]);
      }
    } catch {
      // Silent on purpose: see above.
    } finally {
      setCatchingUp(false);
    }
  };

  const loadFilters = async () => {
    try {
      const res = await client.apiCall.invoke({ url: '/api/v1/discover/filters', method: 'GET', data: {} });
      setFilters({ countries: res.data?.countries ?? [], categories: res.data?.categories ?? [] });
    } catch {
      setFilters({ countries: [], categories: [] });
    }
  };

  const loadAutomations = async () => {
    setAutomationsLoading(true);
    try {
      const res = await client.apiCall.invoke({ url: '/api/v1/automations', method: 'GET', data: {} });
      setAutomations(Array.isArray(res.data) ? res.data : res.data?.items ?? []);
    } catch {
      setAutomations([]);
    } finally {
      setAutomationsLoading(false);
    }
  };

  const loadQueue = async () => {
    setQueueLoading(true);
    try {
      const res = await client.apiCall.invoke({ url: '/api/v1/outreach/queue', method: 'GET', data: {} });
      setQueue(Array.isArray(res.data) ? res.data : res.data?.items ?? []);
    } catch {
      setQueue([]);
    } finally {
      setQueueLoading(false);
    }
  };

  /** Describes what an automation searches for, honestly reflecting unset filters. */
  const automationSummary = (a: Automation) => {
    const parts = [a.category, a.city, a.country].filter((p): p is string => !!p && p.trim() !== '');
    if (a.query) parts.push(`"${a.query}"`);
    return parts.length ? parts.join(' · ') : 'Any business, anywhere';
  };

  const openCreateForm = () => {
    setEditingAutomation(null);
    setFormName('');
    setFormCity('');
    setFormCountry('all');
    setFormCategory('all');
    setFormSchedule('manual');
    setFormAutoQualify(false);
    setFormAutoDraft(false);
    setFormMaxLeads('10');
    setFormOpen(true);
  };

  const openEditForm = (a: Automation) => {
    setEditingAutomation(a);
    setFormName(a.name);
    setFormCity(a.city ?? '');
    setFormCountry(a.country ?? 'all');
    setFormCategory(a.category ?? 'all');
    setFormSchedule((a.schedule as 'manual' | 'daily' | 'weekly') ?? 'manual');
    setFormAutoQualify(a.auto_qualify);
    setFormAutoDraft(a.auto_draft);
    setFormMaxLeads(String(a.max_leads_per_run ?? 10));
    setFormOpen(true);
  };

  const saveAutomation = async () => {
    if (!formName.trim()) {
      toast.error('Give the automation a name.');
      return;
    }
    const maxLeads = parseInt(formMaxLeads, 10);
    if (!Number.isFinite(maxLeads) || maxLeads < 1) {
      toast.error('Max leads per run must be at least 1.');
      return;
    }

    setSavingAutomation(true);
    const payload = {
      name: formName.trim(),
      city: formCity.trim() || null,
      country: formCountry === 'all' ? null : formCountry,
      category: formCategory === 'all' ? null : formCategory,
      query: editingAutomation?.query ?? null,
      website_state: editingAutomation?.website_state ?? 'all',
      auto_qualify: formAutoQualify,
      auto_draft: formAutoDraft,
      max_leads_per_run: maxLeads,
      schedule: formSchedule,
      enabled: editingAutomation ? editingAutomation.enabled : true,
    };

    try {
      if (editingAutomation) {
        await client.apiCall.invoke({
          url: `/api/v1/automations/${editingAutomation.id}`,
          method: 'PATCH',
          data: payload,
        });
        toast.success('Automation updated');
      } else {
        await client.apiCall.invoke({ url: '/api/v1/automations', method: 'POST', data: payload });
        toast.success('Automation created');
      }
      setFormOpen(false);
      await loadAutomations();
    } catch (err: any) {
      toast.error(err?.data?.detail ?? 'Could not save automation');
    } finally {
      setSavingAutomation(false);
    }
  };

  /** Enable/disable toggle in the list, applied optimistically and rolled back on failure. */
  const toggleEnabled = async (a: Automation) => {
    setAutomations((prev) => prev.map((x) => (x.id === a.id ? { ...x, enabled: !x.enabled } : x)));
    try {
      await client.apiCall.invoke({
        url: `/api/v1/automations/${a.id}`,
        method: 'PATCH',
        data: { enabled: !a.enabled },
      });
    } catch (err: any) {
      toast.error(err?.data?.detail ?? 'Could not update automation');
      setAutomations((prev) => prev.map((x) => (x.id === a.id ? { ...x, enabled: a.enabled } : x)));
    }
  };

  const runAutomation = async (a: Automation) => {
    setRunningIds((prev) => new Set(prev).add(a.id));
    try {
      const res = await client.apiCall.invoke({
        url: `/api/v1/automations/${a.id}/run`,
        method: 'POST',
        data: {},
        options: { timeout: 120000 },
      });
      const summary = res.data?.summary ?? res.data?.last_run_summary ?? 'Run complete.';
      toast.success(summary);
    } catch (err: any) {
      toast.error(err?.data?.detail ?? 'Run failed');
    } finally {
      setRunningIds((prev) => {
        const next = new Set(prev);
        next.delete(a.id);
        return next;
      });
      await loadAutomations();
      await loadQueue();
    }
  };

  const confirmDeleteAutomation = async () => {
    if (!deleteTarget) return;
    setDeletingId(deleteTarget.id);
    try {
      await client.apiCall.invoke({ url: `/api/v1/automations/${deleteTarget.id}`, method: 'DELETE', data: {} });
      setAutomations((prev) => prev.filter((a) => a.id !== deleteTarget.id));
      toast.success(`Deleted "${deleteTarget.name}"`);
    } catch (err: any) {
      toast.error(err?.data?.detail ?? 'Could not delete automation');
    } finally {
      setDeletingId(null);
      setDeleteTarget(null);
    }
  };

  const editQueueItem = (id: number, field: 'subject' | 'body_text', value: string) => {
    setQueue((prev) => prev.map((q) => (q.id === id ? { ...q, [field]: value } : q)));
  };

  const sendQueueItem = async (item: QueueItem) => {
    setQueueBusyIds((prev) => new Set(prev).add(item.id));
    try {
      const res = await client.apiCall.invoke({
        url: `/api/v1/outreach/queue/${item.id}/send`,
        method: 'POST',
        // Send the edited subject/body — sending the original would silently
        // discard whatever the reviewer just changed.
        data: { subject: item.subject, body_text: item.body_text },
      });
      const resultStatus: string = res.data?.status ?? 'sent';
      if (resultStatus === 'sent') {
        setQueue((prev) => prev.filter((q) => q.id !== item.id));
        toast.success(`Sent to ${item.to_email}`);
      } else {
        // A 200 response does not always mean delivery succeeded — the send
        // itself can still fail (bad recipient, provider error). Surface that
        // instead of reporting a send that did not actually happen.
        const sendError = res.data?.send_error ?? 'Send failed';
        setQueue((prev) =>
          prev.map((q) => (q.id === item.id ? { ...q, status: resultStatus, send_error: sendError } : q)),
        );
        toast.error(sendError);
        setQueueBusyIds((prev) => {
          const next = new Set(prev);
          next.delete(item.id);
          return next;
        });
      }
    } catch (err: any) {
      toast.error(err?.data?.detail ?? 'Failed to send');
      setQueueBusyIds((prev) => {
        const next = new Set(prev);
        next.delete(item.id);
        return next;
      });
    }
  };

  const discardQueueItem = async (item: QueueItem) => {
    setQueueBusyIds((prev) => new Set(prev).add(item.id));
    try {
      await client.apiCall.invoke({ url: `/api/v1/outreach/queue/${item.id}/discard`, method: 'POST', data: {} });
      setQueue((prev) => prev.filter((q) => q.id !== item.id));
      toast.success('Draft discarded');
    } catch (err: any) {
      toast.error(err?.data?.detail ?? 'Failed to discard');
      setQueueBusyIds((prev) => {
        const next = new Set(prev);
        next.delete(item.id);
        return next;
      });
    }
  };

  /** "Improve writing" on an Approval queue row: rewrites only the wording of the current edited body. */
  const polishQueueItem = async (item: QueueItem) => {
    setQueuePolishing((prev) => new Set(prev).add(item.id));
    try {
      const newText = await callAiPolish(item.body_text, queueTone[item.id] ?? 'professional');
      setQueuePrevious((prev) => ({ ...prev, [item.id]: { subject: item.subject, body_text: item.body_text } }));
      editQueueItem(item.id, 'body_text', newText);
      toast.success('Wording improved — review before sending.');
    } catch (err: any) {
      toast.error(err?.data?.detail ?? 'Could not improve writing');
    } finally {
      setQueuePolishing((prev) => {
        const next = new Set(prev);
        next.delete(item.id);
        return next;
      });
    }
  };

  const revertQueueItem = (id: number) => {
    const prev = queuePrevious[id];
    if (!prev) return;
    setQueue((list) => list.map((q) => (q.id === id ? { ...q, ...prev } : q)));
    setQueuePrevious((p) => {
      const next = { ...p };
      delete next[id];
      return next;
    });
  };

  /** "Rewrite with AI": a fresh subject + body from the same lead's measured findings. */
  const rewriteQueueItemWithAi = async (item: QueueItem) => {
    setQueueRewriting((prev) => new Set(prev).add(item.id));
    try {
      const res = await callAiDraft(item.lead_id, queueTone[item.id] ?? 'professional');
      setQueuePrevious((prev) => ({ ...prev, [item.id]: { subject: item.subject, body_text: item.body_text } }));
      setQueue((list) =>
        list.map((q) =>
          q.id === item.id
            ? { ...q, subject: res.subject, body_text: res.body_text, based_on: res.based_on }
            : q,
        ),
      );
      toast.success('Rewritten from the same measured findings.');
    } catch (err: any) {
      toast.error(err?.data?.detail ?? 'Could not rewrite with AI');
    } finally {
      setQueueRewriting((prev) => {
        const next = new Set(prev);
        next.delete(item.id);
        return next;
      });
    }
  };

  const sendAllQueue = async () => {
    if (!queue.length) return;
    setQueueSendingAll(true);
    try {
      const res = await client.apiCall.invoke({
        url: '/api/v1/outreach/queue/send-all',
        method: 'POST',
        data: {},
        options: { timeout: 120000 },
      });
      const sentCount = res.data?.sent ?? res.data?.sent_count;
      const failedCount = res.data?.failed ?? res.data?.failed_count;
      if (typeof sentCount === 'number') {
        if (!failedCount) toast.success(`Sent ${sentCount} email${sentCount === 1 ? '' : 's'}`);
        else toast.warning(`Sent ${sentCount}, ${failedCount} failed`);
      } else {
        toast.success(res.data?.summary ?? 'Sent all pending drafts');
      }
    } catch (err: any) {
      toast.error(err?.data?.detail ?? 'Could not send all drafts');
    } finally {
      setQueueSendingAll(false);
      await loadQueue();
    }
  };

  /** Only qualified leads can be written to, so only those are offered. */
  const loadLeads = async () => {
    try {
      const res = await client.entities.leads.query({ limit: 200 });
      const all: Lead[] = res.data?.items ?? [];
      setLeads(all.filter((l) => l.findings !== null && (l.contact_email || '').trim()));
    } catch {
      setLeads([]);
    }
  };

  const toggle = (id: number) => {
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const composeDrafts = async () => {
    if (!selected.size) return;
    setComposing(true);
    try {
      const res = await client.apiCall.invoke({
        url: '/api/v1/outreach/compose',
        method: 'POST',
        data: {
          lead_ids: [...selected],
          sender_name: senderName.trim() || null,
          sender_business: senderBusiness.trim() || null,
        },
      });
      const newDrafts: Draft[] = res.data?.drafts ?? [];
      setDrafts(newDrafts);
      setSkipped(res.data?.skipped ?? []);
      setSentIds(new Set());
      setDraftErrors({});
      setDraftPrevious({});
      if (!newDrafts.length) {
        toast.info('No drafts — those leads had nothing measurable to write about.');
      } else {
        toast.success(`Drafted ${newDrafts.length} email(s) from measured findings`);
      }
      // Compose persists every draft to the queue now, so the Approval queue
      // below should reflect them immediately rather than only after a reload.
      await loadQueue();
    } catch (err: any) {
      toast.error(err?.data?.detail ?? 'Could not draft emails');
    } finally {
      setComposing(false);
    }
  };

  const editDraft = (leadId: number, field: 'subject' | 'body_text', value: string) => {
    setDrafts((prev) =>
      prev.map((d) => (d.lead_id === leadId ? { ...d, [field]: value } : d)),
    );
  };

  const sendDraft = async (draft: Draft) => {
    if (draft.id != null) {
      // Compose persisted this draft to the queue, so sending must go through
      // that same queue row — sending via /send-email directly would leave a
      // duplicate "pending" row sitting in the Approval queue forever.
      await client.apiCall.invoke({
        url: `/api/v1/outreach/queue/${draft.id}/send`,
        method: 'POST',
        data: { subject: draft.subject, body_text: draft.body_text },
      });
    } else {
      await client.apiCall.invoke({
        url: '/api/v1/outreach/send-email',
        method: 'POST',
        data: {
          to_email: draft.to_email,
          subject: draft.subject,
          // Re-derive the HTML from the edited text so an edit is never lost:
          // sending the original body_html would silently discard the change.
          body_html: draft.body_text.replace(/\n/g, '<br>'),
          body_text: draft.body_text,
        },
      });
    }
  };

  const sendAllDrafts = async () => {
    const pending = drafts.filter((d) => !sentIds.has(d.lead_id));
    if (!pending.length) return;

    setSendingAll(true);
    const sent = new Set(sentIds);
    const errors: Record<number, string> = { ...draftErrors };
    let failed = 0;

    for (const draft of pending) {
      try {
        await sendDraft(draft);
        sent.add(draft.lead_id);
        delete errors[draft.lead_id];
      } catch (err: any) {
        failed += 1;
        errors[draft.lead_id] = err?.data?.detail ?? err?.message ?? 'Failed to send';
      }
    }

    setSentIds(sent);
    setDraftErrors(errors);
    setSendingAll(false);
    const ok = pending.length - failed;
    if (!failed) toast.success(`Sent ${ok} email(s)`);
    else if (!ok) toast.error(`All ${failed} failed to send`);
    else toast.warning(`Sent ${ok}, ${failed} failed`);
    await loadQueue();
  };

  /** "Improve writing" on a Draft-from-findings result: rewrites only the wording of the current edited body. */
  const polishDraft = async (d: Draft) => {
    setDraftPolishing((prev) => new Set(prev).add(d.lead_id));
    try {
      const newText = await callAiPolish(d.body_text, draftTone[d.lead_id] ?? 'professional');
      setDraftPrevious((prev) => ({ ...prev, [d.lead_id]: { subject: d.subject, body_text: d.body_text } }));
      setDrafts((prev) => prev.map((x) => (x.lead_id === d.lead_id ? { ...x, body_text: newText } : x)));
      toast.success('Wording improved — review before sending.');
    } catch (err: any) {
      toast.error(err?.data?.detail ?? 'Could not improve writing');
    } finally {
      setDraftPolishing((prev) => {
        const next = new Set(prev);
        next.delete(d.lead_id);
        return next;
      });
    }
  };

  const revertDraft = (leadId: number) => {
    const prev = draftPrevious[leadId];
    if (!prev) return;
    setDrafts((list) => list.map((x) => (x.lead_id === leadId ? { ...x, ...prev } : x)));
    setDraftPrevious((p) => {
      const next = { ...p };
      delete next[leadId];
      return next;
    });
  };

  /** "Rewrite with AI": a fresh subject + body from the same lead's measured findings. */
  const rewriteDraftWithAi = async (d: Draft) => {
    setDraftRewriting((prev) => new Set(prev).add(d.lead_id));
    try {
      const res = await callAiDraft(d.lead_id, draftTone[d.lead_id] ?? 'professional');
      setDraftPrevious((prev) => ({ ...prev, [d.lead_id]: { subject: d.subject, body_text: d.body_text } }));
      setDrafts((prev) =>
        prev.map((x) =>
          x.lead_id === d.lead_id
            ? { ...x, subject: res.subject, body_text: res.body_text, based_on: res.based_on }
            : x,
        ),
      );
      toast.success('Rewritten from the same measured findings.');
    } catch (err: any) {
      toast.error(err?.data?.detail ?? 'Could not rewrite with AI');
    } finally {
      setDraftRewriting((prev) => {
        const next = new Set(prev);
        next.delete(d.lead_id);
        return next;
      });
    }
  };

  const loadStatus = async () => {
    setLoading(true);
    try {
      const res = await client.apiCall.invoke({
        url: '/api/v1/outreach/email-status',
        method: 'GET',
        data: {},
      });
      setStatus(res.data);
    } catch {
      setStatus(null);
    } finally {
      setLoading(false);
    }
  };

  const sendEmail = async () => {
    if (!to.trim() || !subject.trim() || !body.trim()) {
      toast.error('Fill in the recipient, subject and message first.');
      return;
    }
    setSending(true);
    try {
      await client.apiCall.invoke({
        url: '/api/v1/outreach/send-email',
        method: 'POST',
        data: {
          to_email: to.trim(),
          subject: subject.trim(),
          // Sent as both HTML and plain text: a text alternative measurably
          // improves deliverability and is what strict clients render.
          body_html: body.replace(/\n/g, '<br>'),
          body_text: body,
        },
      });
      toast.success(`Email sent to ${to.trim()}`);
      setTo('');
      setSubject('');
      setBody('');
    } catch (err: any) {
      toast.error(err?.data?.detail ?? 'Failed to send. Check the settings above.');
    } finally {
      setSending(false);
    }
  };

  /** "Improve writing" for the manually-typed one-off email — the "auto-correct" ask. */
  const polishComposerBody = async () => {
    if (!body.trim()) return;
    setComposerPolishing(true);
    try {
      const newText = await callAiPolish(body, composerTone);
      setComposerPrevious(body);
      setBody(newText);
      toast.success('Wording improved — review before sending.');
    } catch (err: any) {
      toast.error(err?.data?.detail ?? 'Could not improve writing');
    } finally {
      setComposerPolishing(false);
    }
  };

  const revertComposerBody = () => {
    if (composerPrevious === null) return;
    setBody(composerPrevious);
    setComposerPrevious(null);
  };

  return (
    <AppShell>
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Outreach</h1>
          <p className="text-sm text-slate-500">
            Send evidence-based emails to the prospects you have qualified
          </p>
        </div>

        <Card className="border-slate-200">
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2">
              <Mail className="h-4 w-4 text-slate-500" />
              Email delivery
            </CardTitle>
          </CardHeader>
          <CardContent>
            {loading ? (
              <Skeleton className="h-16 w-full" />
            ) : status?.configured ? (
              <div className="flex flex-wrap items-center gap-3">
                <Badge className="bg-green-50 text-green-700 border-green-200 gap-1.5">
                  <CheckCircle2 className="h-3.5 w-3.5" />
                  Connected
                </Badge>
                <span className="text-sm text-slate-600">
                  Sending as <strong className="text-slate-900">{status.from_email}</strong> via{' '}
                  {status.provider === 'resend' ? 'Resend' : `${status.host}:${status.port}`}
                </span>
              </div>
            ) : (
              <div className="space-y-3">
                <Badge
                  variant="outline"
                  className="border-amber-200 bg-amber-50 text-amber-800 gap-1.5"
                >
                  <XCircle className="h-3.5 w-3.5" />
                  Not configured
                </Badge>

                {status?.missing?.length ? (
                  <p className="text-sm text-slate-600">
                    Set{' '}
                    {status.missing.map((m, i) => (
                      <span key={m}>
                        {i > 0 && ', '}
                        <code className="rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-800">
                          {m}
                        </code>
                      </span>
                    ))}{' '}
                    in your Render dashboard, then redeploy.
                  </p>
                ) : (
                  <p className="text-sm text-slate-600">
                    Email delivery is unavailable. Check the API configuration.
                  </p>
                )}

                {/* The single most common setup failure, answered inline. */}
                <div className="rounded-lg border border-slate-200 bg-slate-50 p-4 text-sm text-slate-700">
                  {status?.provider === 'resend' ? (
                    <>
                      <p className="font-medium text-slate-900">Using Resend</p>
                      <ol className="mt-2 list-decimal space-y-1.5 pl-5">
                        <li>
                          Create an API key at{' '}
                          <a
                            href="https://resend.com/api-keys"
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-indigo-600 underline underline-offset-2"
                          >
                            resend.com/api-keys
                          </a>{' '}
                          and set it as <code className="text-xs">RESEND_API_KEY</code>.
                        </li>
                        <li>
                          Verify your sending domain at{' '}
                          <a
                            href="https://resend.com/domains"
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-indigo-600 underline underline-offset-2"
                          >
                            resend.com/domains
                          </a>
                          . Until it is verified, Resend will only deliver to the address
                          that owns the account.
                        </li>
                        <li>
                          Set <code className="text-xs">RESEND_FROM_EMAIL</code> to an address
                          on that domain.
                        </li>
                      </ol>
                      <p className="mt-3 text-slate-600">
                        Check Resend&rsquo;s acceptable use policy before sending cold outreach.
                        Transactional providers generally prohibit unsolicited email.
                      </p>
                    </>
                  ) : (
                  <>
                  <p className="font-medium text-slate-900">Using Gmail?</p>
                  <ol className="mt-2 list-decimal space-y-1.5 pl-5">
                    <li>Turn on 2-Step Verification for the account.</li>
                    <li>
                      Create an App Password at{' '}
                      <a
                        href="https://myaccount.google.com/apppasswords"
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-indigo-600 underline underline-offset-2 inline-flex items-center gap-1"
                      >
                        myaccount.google.com/apppasswords
                        <ExternalLink className="h-3 w-3" />
                      </a>
                    </li>
                    <li>
                      Use those 16 characters as <code className="text-xs">SMTP_PASSWORD</code>.
                      Your normal account password is always rejected.
                    </li>
                  </ol>
                  <p className="mt-3 text-slate-600">
                    Gmail caps sending at roughly 500 a day and suspends accounts used for cold
                    outreach. Setting <code className="text-xs">RESEND_API_KEY</code> switches
                    delivery to Resend automatically.
                  </p>
                  </>
                  )}
                </div>

                <Button variant="outline" size="sm" onClick={loadStatus} className="cursor-pointer">
                  Re-check
                </Button>
              </div>
            )}
          </CardContent>
        </Card>

        {/* AI writing assistant status — visible everywhere the rest of the page uses it. */}
        <Card className="border-slate-200">
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2">
              <Bot className="h-4 w-4 text-slate-500" />
              AI writing assistant
            </CardTitle>
            <CardDescription>
              AI only ever rewrites wording. Every fact in an email — the score, the missing
              feature, whatever it cites — comes from what Qualify actually measured on the
              prospect&rsquo;s site. It never researches or invents anything on its own.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {aiStatusLoading ? (
              <Skeleton className="h-8 w-48" />
            ) : aiAvailable ? (
              <div className="flex flex-wrap items-center gap-3">
                <Badge className="bg-green-50 text-green-700 border-green-200 gap-1.5">
                  <CheckCircle2 className="h-3.5 w-3.5" />
                  Available
                </Badge>
                <span className="text-sm text-slate-600">
                  Model <strong className="text-slate-900">{aiStatus?.model ?? 'unknown'}</strong>
                </span>
              </div>
            ) : (
              <div className="flex flex-wrap items-center gap-3">
                <Badge variant="outline" className="border-amber-200 bg-amber-50 text-amber-800 gap-1.5">
                  <XCircle className="h-3.5 w-3.5" />
                  Not configured
                </Badge>
                <span className="text-sm text-slate-600">
                  Set{' '}
                  <code className="rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-800">
                    ANTHROPIC_API_KEY
                  </code>{' '}
                  in your Render dashboard to turn on wording help. Drafting from findings and
                  sending still work without it.
                </span>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Scheduled automations: repeats Discover (+ optional Qualify/Draft) on a cadence. */}
        <Card className="border-slate-200">
          <CardHeader className="pb-3">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <CardTitle className="text-base flex items-center gap-2">
                  <CalendarClock className="h-4 w-4 text-slate-500" />
                  Automations
                </CardTitle>
                <CardDescription className="mt-1">
                  Repeats a Discover search on a schedule, and can optionally qualify and draft
                  outreach for what it finds. Nothing is ever sent automatically — drafts wait
                  in the approval queue below.
                </CardDescription>
                {/*
                  Say plainly when scheduled work actually happens. A "Daily"
                  badge with no explanation implies a server is watching the
                  clock; on this stack, opening the page is what catches it up
                  unless the hourly trigger is configured.
                */}
                <p className="mt-1 text-xs text-slate-400">
                  {catchingUp
                    ? 'Checking for anything due…'
                    : 'Due automations run when you open this page. For unattended runs, see AUTOMATION_CRON_SECRET in DEPLOY.md.'}
                </p>
              </div>
              <Button
                size="sm"
                onClick={openCreateForm}
                className="bg-indigo-600 hover:bg-indigo-700 gap-1.5 cursor-pointer"
              >
                <Plus className="h-4 w-4" />
                New automation
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            {automationsLoading ? (
              <div className="space-y-2">
                {[...Array(2)].map((_, i) => (
                  <Skeleton key={i} className="h-28 rounded-lg" />
                ))}
              </div>
            ) : automations.length === 0 ? (
              <div className="rounded-lg border border-dashed border-slate-300 p-6 text-center">
                <CalendarClock className="mx-auto h-8 w-8 text-slate-300" />
                <p className="mt-2 text-sm font-medium text-slate-700">No automations yet</p>
                <p className="mx-auto mt-1 max-w-md text-sm text-slate-500">
                  An automation repeats a Discover search — daily or weekly — and can optionally qualify
                  and draft outreach for the leads it finds, so your pipeline fills up without you running
                  each search by hand. Qualifying spends 1 credit per lead measured; max leads per run caps
                  how many are pulled and measured each time it runs.
                </p>
                <Button
                  onClick={openCreateForm}
                  className="mt-4 bg-indigo-600 hover:bg-indigo-700 cursor-pointer"
                >
                  Create your first automation
                </Button>
              </div>
            ) : (
              <div className="space-y-3">
                {automations.map((a) => {
                  const running = runningIds.has(a.id);
                  const lastRun = formatWhen(a.last_run_at);
                  const nextRun = formatWhen(a.next_run_at);
                  return (
                    <div key={a.id} className="rounded-lg border border-slate-200 p-4 space-y-3">
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div className="min-w-0">
                          <p className="truncate font-medium text-slate-900">{a.name}</p>
                          <p className="truncate text-sm text-slate-500">{automationSummary(a)}</p>
                        </div>
                        <div className="flex shrink-0 items-center gap-3">
                          <Badge variant="outline" className="text-xs border-slate-200">
                            {SCHEDULE_LABELS[a.schedule] ?? a.schedule}
                          </Badge>
                          <label
                            className="flex cursor-pointer items-center gap-2"
                            title={a.enabled ? 'Enabled — runs on schedule' : 'Disabled — will not run automatically'}
                          >
                            <Switch checked={a.enabled} onCheckedChange={() => toggleEnabled(a)} />
                            <span className="text-xs text-slate-500">{a.enabled ? 'Enabled' : 'Disabled'}</span>
                          </label>
                        </div>
                      </div>

                      <div className="text-sm">
                        {lastRun ? (
                          <p className="text-slate-600">
                            Last run {lastRun}
                            {a.last_run_summary ? ` · ${a.last_run_summary}` : ''}
                          </p>
                        ) : (
                          <p className="text-slate-500">Never run</p>
                        )}
                        {a.schedule !== 'manual' && a.enabled && nextRun && (
                          <p className="mt-0.5 text-xs text-slate-400">Next run {nextRun}</p>
                        )}
                      </div>

                      {a.last_run_error && (
                        <div className="flex items-start gap-2 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
                          <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
                          <span>Last run failed: {a.last_run_error}</span>
                        </div>
                      )}

                      <div className="flex flex-wrap items-center gap-2 pt-1">
                        <Button
                          size="sm"
                          onClick={() => runAutomation(a)}
                          disabled={running}
                          className="bg-indigo-600 hover:bg-indigo-700 gap-1.5 cursor-pointer disabled:cursor-not-allowed"
                        >
                          {running ? (
                            <Loader2 className="h-3.5 w-3.5 animate-spin" />
                          ) : (
                            <Play className="h-3.5 w-3.5" />
                          )}
                          {running ? 'Running...' : 'Run now'}
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => openEditForm(a)}
                          className="border-slate-200 gap-1.5 cursor-pointer"
                        >
                          <Pencil className="h-3.5 w-3.5" />
                          Edit
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => setDeleteTarget(a)}
                          className="border-red-200 text-red-600 hover:bg-red-50 gap-1.5 cursor-pointer"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                          Delete
                        </Button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Create / edit automation */}
        <Dialog open={formOpen} onOpenChange={setFormOpen}>
          <DialogContent className="max-h-[90vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle>{editingAutomation ? 'Edit automation' : 'New automation'}</DialogTitle>
              <DialogDescription>
                Runs a Discover search on the schedule you choose. Qualifying and drafting are optional.
              </DialogDescription>
            </DialogHeader>

            <div className="space-y-4">
              <div className="space-y-1.5">
                <Label htmlFor="auto-name" className="text-xs font-medium text-slate-600">
                  Name
                </Label>
                <Input
                  id="auto-name"
                  placeholder="e.g. Leeds cafes, weekly"
                  value={formName}
                  onChange={(e) => setFormName(e.target.value)}
                  className="border-slate-200"
                />
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="auto-city" className="text-xs font-medium text-slate-600">
                  City or area
                </Label>
                <Input
                  id="auto-city"
                  placeholder="e.g. Leeds"
                  value={formCity}
                  onChange={(e) => setFormCity(e.target.value)}
                  className="border-slate-200"
                />
              </div>

              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-1.5">
                  <Label className="text-xs font-medium text-slate-600">Country</Label>
                  <Select value={formCountry} onValueChange={setFormCountry}>
                    <SelectTrigger className="border-slate-200">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">Any country</SelectItem>
                      {filters?.countries.map((c) => (
                        <SelectItem key={c} value={c}>{c}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs font-medium text-slate-600">Category</Label>
                  <Select value={formCategory} onValueChange={setFormCategory}>
                    <SelectTrigger className="border-slate-200">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">Any category</SelectItem>
                      {filters?.categories.map((c) => (
                        <SelectItem key={c} value={c}>{c}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <div className="space-y-1.5">
                <Label className="text-xs font-medium text-slate-600">Schedule</Label>
                <Select
                  value={formSchedule}
                  onValueChange={(v) => setFormSchedule(v as 'manual' | 'daily' | 'weekly')}
                >
                  <SelectTrigger className="border-slate-200">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="manual">Manual — only runs when you click Run now</SelectItem>
                    <SelectItem value="daily">Daily</SelectItem>
                    <SelectItem value="weekly">Weekly</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="flex items-center justify-between gap-3 rounded-lg border border-slate-200 p-3">
                <div className="pr-3">
                  <p className="text-sm font-medium text-slate-900">Auto-qualify new leads</p>
                  <p className="text-xs text-slate-500">
                    Measures each new lead&rsquo;s website before it lands in your pipeline. Spends 1
                    credit per lead measured.
                  </p>
                </div>
                <Switch
                  checked={formAutoQualify}
                  onCheckedChange={(v) => {
                    setFormAutoQualify(v);
                    if (!v) setFormAutoDraft(false);
                  }}
                />
              </div>

              <div className="flex items-center justify-between gap-3 rounded-lg border border-slate-200 p-3">
                <div className="pr-3">
                  <p className="text-sm font-medium text-slate-900">Auto-draft outreach</p>
                  <p className="text-xs text-slate-500">
                    Writes an email from each qualified lead&rsquo;s measured findings. Free — drafts wait
                    in the approval queue below until you send them. Requires auto-qualify.
                  </p>
                </div>
                <Switch
                  checked={formAutoDraft}
                  onCheckedChange={setFormAutoDraft}
                  disabled={!formAutoQualify}
                />
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="auto-max" className="text-xs font-medium text-slate-600">
                  Max leads per run
                </Label>
                <Input
                  id="auto-max"
                  type="number"
                  min={1}
                  value={formMaxLeads}
                  onChange={(e) => setFormMaxLeads(e.target.value)}
                  className="border-slate-200 w-32"
                />
                <p className="text-xs text-slate-500">
                  Caps how many leads this automation pulls — and, if auto-qualify is on, measures — in a
                  single run. This is both a search-size limit and a credit-spend limit.
                </p>
              </div>
            </div>

            <DialogFooter>
              <Button
                variant="outline"
                onClick={() => setFormOpen(false)}
                className="border-slate-200 cursor-pointer"
              >
                Cancel
              </Button>
              <Button
                onClick={saveAutomation}
                disabled={savingAutomation}
                className="bg-indigo-600 hover:bg-indigo-700 gap-2 cursor-pointer disabled:cursor-not-allowed"
              >
                {savingAutomation && <Loader2 className="h-4 w-4 animate-spin" />}
                {editingAutomation ? 'Save changes' : 'Create automation'}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        {/* Delete confirmation */}
        <AlertDialog open={!!deleteTarget} onOpenChange={(open) => !open && setDeleteTarget(null)}>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Delete &ldquo;{deleteTarget?.name}&rdquo;?</AlertDialogTitle>
              <AlertDialogDescription>
                This stops its schedule and removes it. Leads and drafts it already created are not
                deleted.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel className="cursor-pointer">Cancel</AlertDialogCancel>
              <AlertDialogAction
                onClick={confirmDeleteAutomation}
                disabled={deletingId === deleteTarget?.id}
                className="bg-red-600 hover:bg-red-700 cursor-pointer disabled:cursor-not-allowed"
              >
                {deletingId === deleteTarget?.id ? 'Deleting...' : 'Delete'}
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>

        {/* Approval queue: drafts an automation wrote, waiting for a human Send/Discard. */}
        <Card className="border-slate-200">
          <CardHeader className="pb-3">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <CardTitle className="text-base flex items-center gap-2">
                  <Inbox className="h-4 w-4 text-slate-500" />
                  Approval queue
                </CardTitle>
                <CardDescription className="mt-1">
                  Drafts your automations wrote. Nothing here sends itself — review, edit if needed, then
                  send or discard. AI can help with wording below; the facts stay exactly what was
                  measured.
                </CardDescription>
              </div>
              {queue.length > 0 && (
                <Button
                  onClick={sendAllQueue}
                  disabled={queueSendingAll || !status?.configured}
                  className="bg-indigo-600 hover:bg-indigo-700 gap-2 cursor-pointer disabled:cursor-not-allowed"
                  title={!status?.configured ? 'Configure email delivery above first' : undefined}
                >
                  {queueSendingAll ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Send className="h-4 w-4" />
                  )}
                  {queueSendingAll ? 'Sending...' : `Send all ${queue.length}`}
                </Button>
              )}
            </div>
          </CardHeader>
          <CardContent>
            {queueLoading ? (
              <div className="space-y-2">
                {[...Array(2)].map((_, i) => (
                  <Skeleton key={i} className="h-40 rounded-lg" />
                ))}
              </div>
            ) : queue.length === 0 ? (
              <div className="rounded-lg border border-dashed border-slate-300 p-6 text-center">
                <Inbox className="mx-auto h-8 w-8 text-slate-300" />
                <p className="mt-2 text-sm font-medium text-slate-700">Nothing waiting for review</p>
                <p className="mx-auto mt-1 max-w-md text-sm text-slate-500">
                  Turn on auto-draft on an automation above, or draft manually from &ldquo;Draft from
                  findings&rdquo; below — every draft lands here first, so nothing is ever sent without
                  your review.
                </p>
              </div>
            ) : (
              <div className="space-y-4">
                {queue.map((item) => {
                  const actionBusy = queueBusyIds.has(item.id);
                  const aiBusy = queuePolishing.has(item.id) || queueRewriting.has(item.id);
                  const rowLocked = actionBusy || aiBusy || item.status !== 'pending';
                  const basedOnCount = countBasedOn(item.based_on);
                  return (
                    <div key={item.id} className="rounded-lg border border-slate-200 p-4 space-y-3">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div className="min-w-0">
                          <p className="truncate text-sm font-medium text-slate-900">
                            {item.business_name || `Lead #${item.lead_id}`}
                          </p>
                          <p className="truncate text-xs text-slate-500">{item.to_email}</p>
                        </div>
                        <div className="flex shrink-0 items-center gap-2">
                          <Badge variant="outline" className="text-xs border-slate-200">
                            from {basedOnCount} measured finding{basedOnCount === 1 ? '' : 's'}
                          </Badge>
                          <QueueStatusBadge status={item.status} sendError={item.send_error} />
                        </div>
                      </div>
                      <Label htmlFor={`queue-subject-${item.id}`} className="sr-only">
                        Subject
                      </Label>
                      <Input
                        id={`queue-subject-${item.id}`}
                        value={item.subject}
                        onChange={(e) => editQueueItem(item.id, 'subject', e.target.value)}
                        disabled={rowLocked}
                        className="border-slate-200 font-medium disabled:cursor-not-allowed"
                      />
                      <Label htmlFor={`queue-body-${item.id}`} className="sr-only">
                        Message
                      </Label>
                      <Textarea
                        id={`queue-body-${item.id}`}
                        rows={7}
                        value={item.body_text}
                        onChange={(e) => editQueueItem(item.id, 'body_text', e.target.value)}
                        disabled={rowLocked}
                        className="border-slate-200 text-sm disabled:cursor-not-allowed"
                      />
                      <div className="flex flex-wrap items-center gap-2">
                        <Button
                          size="sm"
                          onClick={() => sendQueueItem(item)}
                          disabled={rowLocked || !status?.configured}
                          className="bg-indigo-600 hover:bg-indigo-700 gap-1.5 cursor-pointer disabled:cursor-not-allowed"
                          title={!status?.configured ? 'Configure email delivery above first' : undefined}
                        >
                          {actionBusy ? (
                            <Loader2 className="h-3.5 w-3.5 animate-spin" />
                          ) : (
                            <Send className="h-3.5 w-3.5" />
                          )}
                          {actionBusy ? 'Sending...' : 'Send'}
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => discardQueueItem(item)}
                          disabled={rowLocked}
                          className="border-slate-200 gap-1.5 cursor-pointer disabled:cursor-not-allowed"
                        >
                          <X className="h-3.5 w-3.5" />
                          Discard
                        </Button>
                      </div>
                      <AiControls
                        idPrefix={`queue-${item.id}`}
                        tone={queueTone[item.id] ?? 'professional'}
                        onToneChange={(t) => setQueueTone((prev) => ({ ...prev, [item.id]: t }))}
                        onPolish={() => polishQueueItem(item)}
                        polishing={queuePolishing.has(item.id)}
                        onRewrite={() => rewriteQueueItemWithAi(item)}
                        rewriting={queueRewriting.has(item.id)}
                        canRevert={!!queuePrevious[item.id]}
                        onRevert={() => revertQueueItem(item.id)}
                        aiAvailable={aiAvailable}
                        aiUnavailableReason={aiUnavailableReason}
                        rowDisabled={rowLocked}
                      />
                    </div>
                  );
                })}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Evidence-based drafting: the actual automation. */}
        <Card className="border-slate-200">
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2">
              <Sparkles className="h-4 w-4 text-slate-500" />
              Draft from findings
            </CardTitle>
            <CardDescription>
              Every sentence is written from what we measured on the prospect&rsquo;s site.
              Nothing is invented — a lead with nothing measurable gets no email. AI, where
              available, can only reword what is already here.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="sender-name" className="text-xs font-medium text-slate-600">
                  Your name
                </Label>
                <Input
                  id="sender-name"
                  placeholder="Vishnu"
                  value={senderName}
                  onChange={(e) => setSenderName(e.target.value)}
                  className="border-slate-200"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="sender-business" className="text-xs font-medium text-slate-600">
                  Your business
                </Label>
                <Input
                  id="sender-business"
                  placeholder="Torque Trends"
                  value={senderBusiness}
                  onChange={(e) => setSenderBusiness(e.target.value)}
                  className="border-slate-200"
                />
              </div>
            </div>

            {leads.length === 0 ? (
              <div className="rounded-lg border border-dashed border-slate-300 p-6 text-center">
                <p className="text-sm font-medium text-slate-700">No qualified leads with an email</p>
                <p className="mt-1 text-sm text-slate-500">
                  Run Qualify on some leads first — the findings it measures are what these
                  emails are written from.
                </p>
              </div>
            ) : (
              <>
                <div className="max-h-64 overflow-y-auto rounded-lg border border-slate-200 divide-y divide-slate-100">
                  {leads.map((l) => (
                    <label
                      key={l.id}
                      className="flex cursor-pointer items-center gap-3 px-3 py-2.5 hover:bg-slate-50"
                    >
                      <input
                        type="checkbox"
                        checked={selected.has(l.id)}
                        onChange={() => toggle(l.id)}
                        className="h-4 w-4 shrink-0 cursor-pointer accent-indigo-600"
                      />
                      <span className="min-w-0 flex-1 truncate text-sm text-slate-900">
                        {l.business_name}
                      </span>
                      {typeof l.website_score === 'number' && (
                        <Badge variant="outline" className="shrink-0 text-xs border-slate-200">
                          {l.website_score}/100
                        </Badge>
                      )}
                    </label>
                  ))}
                </div>

                <div className="flex flex-wrap items-center gap-3">
                  <Button
                    onClick={composeDrafts}
                    disabled={!selected.size || composing}
                    className="bg-indigo-600 hover:bg-indigo-700 gap-2 cursor-pointer"
                  >
                    {composing ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <Sparkles className="h-4 w-4" />
                    )}
                    {composing ? 'Drafting...' : `Draft ${selected.size || ''} email${selected.size === 1 ? '' : 's'}`}
                  </Button>
                  <span className="text-xs text-slate-500">Drafting is free — no credits used.</span>
                </div>
              </>
            )}

            {skipped.length > 0 && (
              <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm">
                <p className="font-medium text-amber-900">
                  {skipped.length} lead{skipped.length === 1 ? '' : 's'} skipped
                </p>
                <ul className="mt-1.5 space-y-1 text-amber-800">
                  {skipped.slice(0, 5).map((sk) => (
                    <li key={sk.lead_id}>&middot; {sk.message}</li>
                  ))}
                </ul>
              </div>
            )}

            {drafts.length > 0 && (
              <div className="space-y-4 pt-2">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <p className="text-sm text-slate-600">
                    <span className="font-medium text-slate-900">{drafts.length}</span> draft
                    {drafts.length === 1 ? '' : 's'} · review and edit before sending
                  </p>
                  <Button
                    onClick={sendAllDrafts}
                    disabled={!status?.configured || sendingAll || sentIds.size === drafts.length}
                    className="bg-indigo-600 hover:bg-indigo-700 gap-2 cursor-pointer"
                  >
                    {sendingAll ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <Send className="h-4 w-4" />
                    )}
                    Send all {drafts.length - sentIds.size || ''}
                  </Button>
                </div>

                {drafts.map((d) => {
                  const sent = sentIds.has(d.lead_id);
                  const draftError = draftErrors[d.lead_id];
                  const aiBusy = draftPolishing.has(d.lead_id) || draftRewriting.has(d.lead_id);
                  const rowLocked = sent || sendingAll || aiBusy;
                  const basedOnCount = countBasedOn(d.based_on);
                  return (
                    <div key={d.lead_id} className="rounded-lg border border-slate-200 p-4 space-y-3">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div className="min-w-0">
                          <p className="truncate text-sm font-medium text-slate-900">
                            {d.business_name}
                          </p>
                          <p className="truncate text-xs text-slate-500">{d.to_email}</p>
                        </div>
                        <div className="flex shrink-0 items-center gap-2">
                          <Badge variant="outline" className="text-xs border-slate-200">
                            from {basedOnCount} measured finding{basedOnCount === 1 ? '' : 's'}
                          </Badge>
                          {sent ? (
                            <Badge className="bg-green-50 text-green-700 border-green-200 gap-1">
                              <CheckCircle2 className="h-3 w-3" />
                              Sent
                            </Badge>
                          ) : draftError ? (
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <Badge className="gap-1 border-red-200 bg-red-50 text-xs text-red-700 cursor-default">
                                  <AlertCircle className="h-3 w-3" />
                                  Failed
                                </Badge>
                              </TooltipTrigger>
                              <TooltipContent>{draftError}</TooltipContent>
                            </Tooltip>
                          ) : (
                            <Badge variant="outline" className="text-xs border-amber-200 bg-amber-50 text-amber-800">
                              Pending
                            </Badge>
                          )}
                        </div>
                      </div>
                      <Label htmlFor={`draft-subject-${d.lead_id}`} className="sr-only">
                        Subject
                      </Label>
                      <Input
                        id={`draft-subject-${d.lead_id}`}
                        value={d.subject}
                        onChange={(e) => editDraft(d.lead_id, 'subject', e.target.value)}
                        disabled={rowLocked}
                        className="border-slate-200 font-medium disabled:cursor-not-allowed"
                      />
                      <Label htmlFor={`draft-body-${d.lead_id}`} className="sr-only">
                        Message
                      </Label>
                      <Textarea
                        id={`draft-body-${d.lead_id}`}
                        rows={9}
                        value={d.body_text}
                        onChange={(e) => editDraft(d.lead_id, 'body_text', e.target.value)}
                        disabled={rowLocked}
                        className="border-slate-200 text-sm disabled:cursor-not-allowed"
                      />
                      <AiControls
                        idPrefix={`draft-${d.lead_id}`}
                        tone={draftTone[d.lead_id] ?? 'professional'}
                        onToneChange={(t) => setDraftTone((prev) => ({ ...prev, [d.lead_id]: t }))}
                        onPolish={() => polishDraft(d)}
                        polishing={draftPolishing.has(d.lead_id)}
                        onRewrite={() => rewriteDraftWithAi(d)}
                        rewriting={draftRewriting.has(d.lead_id)}
                        canRevert={!!draftPrevious[d.lead_id]}
                        onRevert={() => revertDraft(d.lead_id)}
                        aiAvailable={aiAvailable}
                        aiUnavailableReason={aiUnavailableReason}
                        rowDisabled={sent || sendingAll}
                      />
                    </div>
                  );
                })}
              </div>
            )}
          </CardContent>
        </Card>

        <Card className="border-slate-200">
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Send a one-off email</CardTitle>
            <CardDescription>
              Written by hand. AI can clean up the wording below — quote the real numbers from
              Qualify yourself; it will not verify anything on its own.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="to" className="text-xs font-medium text-slate-600">
                  To
                </Label>
                <Input
                  id="to"
                  type="email"
                  placeholder="owner@business.com"
                  value={to}
                  onChange={(e) => setTo(e.target.value)}
                  disabled={!status?.configured}
                  className="border-slate-200"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="subject" className="text-xs font-medium text-slate-600">
                  Subject
                </Label>
                <Input
                  id="subject"
                  placeholder="Your site is missing a mobile viewport"
                  value={subject}
                  onChange={(e) => setSubject(e.target.value)}
                  disabled={!status?.configured}
                  className="border-slate-200"
                />
              </div>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="body" className="text-xs font-medium text-slate-600">
                Message
              </Label>
              <Textarea
                id="body"
                rows={8}
                placeholder="Quote the specific findings from Qualify — they are evidence the prospect can verify."
                value={body}
                onChange={(e) => setBody(e.target.value)}
                disabled={!status?.configured}
                className="border-slate-200"
              />
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <Label htmlFor="composer-tone" className="text-xs text-slate-500">
                Tone
              </Label>
              <Select
                value={composerTone}
                onValueChange={(v) => setComposerTone(v as Tone)}
                disabled={!aiAvailable}
              >
                <SelectTrigger
                  id="composer-tone"
                  className="h-8 w-[128px] border-slate-200 text-xs cursor-pointer disabled:cursor-not-allowed"
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {TONE_OPTIONS.map((t) => (
                    <SelectItem key={t.value} value={t.value}>
                      {t.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Tooltip>
                <TooltipTrigger asChild>
                  <span>
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      onClick={polishComposerBody}
                      disabled={!aiAvailable || composerPolishing || !body.trim()}
                      className="h-8 gap-1.5 border-slate-200 text-xs cursor-pointer disabled:cursor-not-allowed"
                    >
                      {composerPolishing ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <Wand2 className="h-3.5 w-3.5" />
                      )}
                      Improve writing
                    </Button>
                  </span>
                </TooltipTrigger>
                <TooltipContent>
                  {!aiAvailable
                    ? aiUnavailableReason
                    : !body.trim()
                      ? 'Write a message first'
                      : 'Rewrites the wording only — never adds or changes a fact'}
                </TooltipContent>
              </Tooltip>
              {composerPrevious !== null && (
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  onClick={revertComposerBody}
                  className="h-8 gap-1.5 text-xs text-slate-500 cursor-pointer"
                >
                  <Undo2 className="h-3.5 w-3.5" />
                  Revert
                </Button>
              )}
            </div>

            <div className="flex flex-wrap items-center gap-3">
              <Button
                onClick={sendEmail}
                disabled={!status?.configured || sending}
                className="bg-indigo-600 hover:bg-indigo-700 gap-2 cursor-pointer"
              >
                {sending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Send className="h-4 w-4" />
                )}
                {sending ? 'Sending...' : 'Send email'}
              </Button>
              <p className="text-xs text-slate-500">
                You are the sender. Follow the marketing rules that apply where your recipient is —
                see the{' '}
                <a href="/terms#outreach" className="text-indigo-600 underline underline-offset-2">
                  Terms
                </a>
                .
              </p>
            </div>
          </CardContent>
        </Card>
      </div>
    </AppShell>
  );
}
