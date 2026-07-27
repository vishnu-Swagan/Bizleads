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
import { CheckCircle2, XCircle, Mail, Send, Loader2, ExternalLink } from 'lucide-react';

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

  const [to, setTo] = useState('');
  const [subject, setSubject] = useState('');
  const [body, setBody] = useState('');
  const [sending, setSending] = useState(false);

  useEffect(() => {
    if (user) void loadStatus();
  }, [user]);

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

        <Card className="border-slate-200">
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Send an email</CardTitle>
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
