import { useState, useEffect } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import AppShell from '@/components/AppShell';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Skeleton } from '@/components/ui/skeleton';
import { toast } from 'sonner';
import { client } from '@/lib/api';
import { CheckCircle2, XCircle, Mail, Send, Loader2, ExternalLink, Sparkles } from 'lucide-react';

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
  lead_id: number;
  business_name: string;
  to_email: string;
  subject: string;
  body_text: string;
  body_html: string;
  based_on: string;
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
  configured: boolean;
  host: string | null;
  port: number;
  from_email: string | null;
  use_tls: boolean;
  username_set: boolean;
  password_set: boolean;
  missing: string[];
}

export default function AppAutomations() {
  const { user } = useAuth();
  const [status, setStatus] = useState<EmailStatus | null>(null);
  const [loading, setLoading] = useState(true);

  const [leads, setLeads] = useState<Lead[]>([]);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const [skipped, setSkipped] = useState<Skipped[]>([]);
  const [composing, setComposing] = useState(false);
  const [sendingAll, setSendingAll] = useState(false);
  const [sentIds, setSentIds] = useState<Set<number>>(new Set());

  const [to, setTo] = useState('');
  const [subject, setSubject] = useState('');
  const [body, setBody] = useState('');
  const [sending, setSending] = useState(false);
  const [senderName, setSenderName] = useState('');
  const [senderBusiness, setSenderBusiness] = useState('');

  useEffect(() => {
    if (user) {
      void loadStatus();
      void loadLeads();
    }
  }, [user]);

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
      setDrafts(res.data?.drafts ?? []);
      setSkipped(res.data?.skipped ?? []);
      setSentIds(new Set());
      if (!res.data?.drafts?.length) {
        toast.info('No drafts — those leads had nothing measurable to write about.');
      } else {
        toast.success(`Drafted ${res.data.drafts.length} email(s) from measured findings`);
      }
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
  };

  const sendAllDrafts = async () => {
    const pending = drafts.filter((d) => !sentIds.has(d.lead_id));
    if (!pending.length) return;

    setSendingAll(true);
    const sent = new Set(sentIds);
    let failed = 0;

    for (const draft of pending) {
      try {
        await sendDraft(draft);
        sent.add(draft.lead_id);
      } catch {
        failed += 1;
      }
    }

    setSentIds(sent);
    setSendingAll(false);
    const ok = pending.length - failed;
    if (!failed) toast.success(`Sent ${ok} email(s)`);
    else if (!ok) toast.error(`All ${failed} failed to send`);
    else toast.warning(`Sent ${ok}, ${failed} failed`);
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
                  {status.host}:{status.port}
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
                    outreach. For real volume, use a transactional provider on your own domain.
                  </p>
                </div>

                <Button variant="outline" size="sm" onClick={loadStatus} className="cursor-pointer">
                  Re-check
                </Button>
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
            <p className="text-sm text-slate-500">
              Every sentence is written from what we measured on the prospect&rsquo;s site.
              Nothing is invented — a lead with nothing measurable gets no email.
            </p>
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

                {drafts.map((d) => (
                  <div key={d.lead_id} className="rounded-lg border border-slate-200 p-4 space-y-3">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="min-w-0">
                        <p className="truncate text-sm font-medium text-slate-900">
                          {d.business_name}
                        </p>
                        <p className="truncate text-xs text-slate-500">{d.to_email}</p>
                      </div>
                      {sentIds.has(d.lead_id) ? (
                        <Badge className="bg-green-50 text-green-700 border-green-200 gap-1">
                          <CheckCircle2 className="h-3 w-3" />
                          Sent
                        </Badge>
                      ) : (
                        <Badge variant="outline" className="text-xs border-slate-200">
                          from {JSON.parse(d.based_on || '[]').length} measured finding
                          {JSON.parse(d.based_on || '[]').length === 1 ? '' : 's'}
                        </Badge>
                      )}
                    </div>
                    <Input
                      value={d.subject}
                      onChange={(e) => editDraft(d.lead_id, 'subject', e.target.value)}
                      disabled={sentIds.has(d.lead_id)}
                      className="border-slate-200 font-medium"
                    />
                    <Textarea
                      rows={9}
                      value={d.body_text}
                      onChange={(e) => editDraft(d.lead_id, 'body_text', e.target.value)}
                      disabled={sentIds.has(d.lead_id)}
                      className="border-slate-200 text-sm"
                    />
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        <Card className="border-slate-200">
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Send a one-off email</CardTitle>
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
