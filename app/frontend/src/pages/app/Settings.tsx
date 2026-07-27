import { useEffect, useState } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { useNavigate, useLocation, useSearchParams } from 'react-router-dom';
import AppShell from '@/components/AppShell';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Switch } from '@/components/ui/switch';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { toast } from 'sonner';
import { client } from '@/lib/api';
import {
  CreditCard, Settings as SettingsIcon, Users, Plug, CheckCircle2, ArrowRight, Loader2,
  Mail, XCircle, AlertTriangle, ExternalLink, Send, ShieldAlert, Trash2,
} from 'lucide-react';
import { cn } from '@/lib/utils';

interface UsageData {
  workspace_id: number;
  plan: string;
  plan_name: string;
  subscription_status: string;
  credits_total: number;
  credits_used: number;
  credits_remaining: number;
  max_seats: number;
  trial_ends_at: string;
  credits_reset_at: string;
}

/**
 * Per-customer email delivery configuration.
 *
 * This product is sold on subscription — every customer sends outreach from
 * THEIR OWN mailbox, never a shared one. The backend never echoes back a
 * secret: `smtp_password_set` / `resend_api_key_set` are booleans, not the
 * values themselves, so the UI never has a real secret to accidentally
 * render after the initial load.
 */
interface EmailSettingsData {
  provider: 'smtp' | 'resend';
  from_email: string | null;
  from_name: string | null;
  smtp_host: string | null;
  smtp_port: number | null;
  smtp_username: string | null;
  smtp_use_tls: boolean;
  smtp_password_set: boolean;
  resend_api_key_set: boolean;
  verified_at: string | null;
  last_error: string | null;
  encryption_available: boolean;
}

/** Formats an ISO timestamp for display; never invents a value for a missing one. */
function formatWhen(iso: string | null): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
}

export default function AppSettings() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const [usage, setUsage] = useState<UsageData | null>(null);
  const [loading, setLoading] = useState(true);
  const [upgrading, setUpgrading] = useState<string | null>(null);
  const [verifying, setVerifying] = useState(false);
  const [providerStatus, setProviderStatus] = useState<{ mapbox_connected: boolean; pagespeed_connected: boolean } | null>(null);

  // Email delivery — see EmailSettingsData above for why secrets are booleans.
  const [emailData, setEmailData] = useState<EmailSettingsData | null>(null);
  const [emailLoading, setEmailLoading] = useState(true);
  const [emailSaving, setEmailSaving] = useState(false);
  const [emailTesting, setEmailTesting] = useState(false);
  const [emailDeleting, setEmailDeleting] = useState(false);
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null);
  const [emailProvider, setEmailProvider] = useState<'smtp' | 'resend'>('smtp');
  const [fromEmail, setFromEmail] = useState('');
  const [fromName, setFromName] = useState('');
  const [smtpHost, setSmtpHost] = useState('smtp.gmail.com');
  const [smtpPort, setSmtpPort] = useState('587');
  const [smtpUsername, setSmtpUsername] = useState('');
  const [smtpPassword, setSmtpPassword] = useState('');
  const [smtpUseTls, setSmtpUseTls] = useState(true);
  const [resendApiKey, setResendApiKey] = useState('');

  const activeTab = location.pathname.includes('billing') ? 'billing' : 'workspace';

  useEffect(() => {
    // Ask the API which providers are actually configured rather than
    // asserting it in the markup.
    client.apiCall
      .invoke({ url: '/api/v1/discover/filters', method: 'GET', data: {} })
      .then((res) => setProviderStatus({
        mapbox_connected: !!res.data?.mapbox_connected,
        pagespeed_connected: !!res.data?.pagespeed_connected,
      }))
      .catch(() => setProviderStatus({ mapbox_connected: false, pagespeed_connected: false }));
  }, []);

  useEffect(() => {
    if (user) fetchUsage();
  }, [user]);

  useEffect(() => {
    if (user) void loadEmailSettings();
  }, [user]);

  useEffect(() => {
    const sessionId = searchParams.get('session_id');
    if (sessionId) {
      verifyPayment(sessionId);
    }
  }, [searchParams]);

  const fetchUsage = async () => {
    try {
      const res = await client.apiCall.invoke({ url: '/api/v1/billing/usage', method: 'GET', data: {} });
      setUsage(res.data);
    } catch (err) {
      console.error('Failed to fetch usage:', err);
    } finally {
      setLoading(false);
    }
  };

  const verifyPayment = async (sessionId: string) => {
    setVerifying(true);
    try {
      const res = await client.apiCall.invoke({
        url: '/api/v1/billing/verify-payment',
        method: 'POST',
        data: { session_id: sessionId },
      });
      if (res.data?.status === 'active') {
        toast.success(`Upgraded to ${res.data.plan_name}! ${res.data.credits} credits activated.`);
        fetchUsage();
      }
    } catch (err) {
      toast.error('Payment verification failed. Please contact support.');
    } finally {
      setVerifying(false);
    }
  };

  /** Populates the form from the server. Secrets never arrive — only *_set booleans. */
  const loadEmailSettings = async () => {
    setEmailLoading(true);
    try {
      const res = await client.apiCall.invoke({ url: '/api/v1/settings/email', method: 'GET', data: {} });
      const d: EmailSettingsData = res.data;
      setEmailData(d);
      setEmailProvider(d.provider ?? 'smtp');
      setFromEmail(d.from_email ?? '');
      setFromName(d.from_name ?? '');
      setSmtpHost(d.smtp_host ?? 'smtp.gmail.com');
      setSmtpPort(d.smtp_port != null ? String(d.smtp_port) : '587');
      setSmtpUsername(d.smtp_username ?? '');
      setSmtpUseTls(d.smtp_use_tls ?? true);
      setSmtpPassword('');
      setResendApiKey('');
      setTestResult(null);
    } catch (err) {
      console.error('Failed to load email settings:', err);
      setEmailData(null);
    } finally {
      setEmailLoading(false);
    }
  };

  /** True once the form differs from what is actually saved — a typed secret always counts. */
  const emailFormDirty = (() => {
    if (!emailData) return false;
    return (
      emailProvider !== emailData.provider ||
      (fromEmail.trim() || null) !== (emailData.from_email || null) ||
      (fromName.trim() || null) !== (emailData.from_name || null) ||
      (smtpHost.trim() || null) !== (emailData.smtp_host || null) ||
      (smtpPort ? parseInt(smtpPort, 10) : null) !== emailData.smtp_port ||
      (smtpUsername.trim() || null) !== (emailData.smtp_username || null) ||
      smtpUseTls !== emailData.smtp_use_tls ||
      smtpPassword !== '' ||
      resendApiKey !== ''
    );
  })();

  const saveEmailSettings = async () => {
    if (!fromEmail.trim()) {
      toast.error('Enter the From email address you want outreach to send from.');
      return;
    }
    setEmailSaving(true);
    try {
      const payload: Record<string, unknown> = {
        provider: emailProvider,
        from_email: fromEmail.trim(),
        from_name: fromName.trim() || null,
        smtp_host: smtpHost.trim() || null,
        smtp_port: smtpPort ? parseInt(smtpPort, 10) : null,
        smtp_username: smtpUsername.trim() || null,
        smtp_use_tls: smtpUseTls,
      };
      // Omitted entirely when blank, so the backend keeps whatever secret is
      // already stored rather than overwriting it with an empty value.
      if (smtpPassword) payload.smtp_password = smtpPassword;
      if (resendApiKey) payload.resend_api_key = resendApiKey;

      const res = await client.apiCall.invoke({ url: '/api/v1/settings/email', method: 'PUT', data: payload });
      const d: EmailSettingsData = res.data;
      setEmailData(d);
      setEmailProvider(d.provider ?? emailProvider);
      setFromEmail(d.from_email ?? '');
      setFromName(d.from_name ?? '');
      setSmtpHost(d.smtp_host ?? '');
      setSmtpPort(d.smtp_port != null ? String(d.smtp_port) : '');
      setSmtpUsername(d.smtp_username ?? '');
      setSmtpUseTls(d.smtp_use_tls ?? true);
      // Cleared even though we just typed them — never keep a secret sitting
      // in state once it has been sent, so it can never render again.
      setSmtpPassword('');
      setResendApiKey('');
      setTestResult(null);
      toast.success('Email settings saved');
    } catch (err: any) {
      toast.error(err?.data?.detail ?? 'Could not save email settings');
    } finally {
      setEmailSaving(false);
    }
  };

  const sendTestEmail = async () => {
    setEmailTesting(true);
    setTestResult(null);
    try {
      const res = await client.apiCall.invoke({ url: '/api/v1/settings/email/test', method: 'POST', data: {} });
      const result = { success: !!res.data?.success, message: res.data?.message ?? '' };
      setTestResult(result);
      if (result.success) {
        toast.success('Test email sent — check your inbox');
        await loadEmailSettings();
      } else {
        toast.error(result.message || 'Test email failed');
      }
    } catch (err: any) {
      const message = err?.data?.message ?? err?.data?.detail ?? 'Failed to send test email';
      setTestResult({ success: false, message });
      toast.error(message);
    } finally {
      setEmailTesting(false);
    }
  };

  const deleteEmailSettings = async () => {
    setEmailDeleting(true);
    try {
      await client.apiCall.invoke({ url: '/api/v1/settings/email', method: 'DELETE', data: {} });
      toast.success('Email configuration removed');
      await loadEmailSettings();
    } catch (err: any) {
      toast.error(err?.data?.detail ?? 'Could not remove email configuration');
    } finally {
      setEmailDeleting(false);
    }
  };

  const handleUpgrade = async (plan: string, annual: boolean = false) => {
    setUpgrading(plan);
    try {
      const res = await client.apiCall.invoke({
        url: '/api/v1/billing/create-checkout',
        method: 'POST',
        data: {
          plan,
          annual,
          success_url: window.location.origin + '/app/settings/billing',
          cancel_url: window.location.origin + '/pricing',
        },
      });
      const checkoutUrl = res?.data?.url;
      if (!checkoutUrl) {
        toast.error('No checkout URL received. Please try again.');
        return;
      }
      client.utils.openUrl(checkoutUrl);
    } catch (err: any) {
      const detail = err?.data?.detail || err?.response?.data?.detail || err?.message || 'Failed to start checkout';
      toast.error(detail);
    } finally {
      setUpgrading(null);
    }
  };

  return (
    <AppShell>
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Settings</h1>
          <p className="text-sm text-slate-500">Manage your workspace, billing, and integrations</p>
        </div>

        <Tabs value={activeTab} onValueChange={(v) => navigate(`/app/settings/${v}`)}>
          <TabsList className="bg-slate-100">
            <TabsTrigger value="workspace">Workspace</TabsTrigger>
            <TabsTrigger value="billing">Billing</TabsTrigger>
          </TabsList>

          <TabsContent value="workspace" className="space-y-4 mt-4">
            {/* Offer Profile */}
            <Card className="border-slate-200">
              <CardHeader>
                <CardTitle className="text-sm font-medium text-slate-600">Offer Profile</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <p className="text-sm text-slate-500">
                  Configure your services and target market to improve Agency Fit scoring for discovered leads.
                </p>
                <div className="grid gap-4 sm:grid-cols-2">
                  <div className="space-y-1.5">
                    <Label className="text-xs text-slate-600">Services Offered</Label>
                    <Input placeholder="Web design, SEO, Branding..." className="border-slate-200" />
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-xs text-slate-600">Platforms</Label>
                    <Input placeholder="WordPress, Webflow, Shopify..." className="border-slate-200" />
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-xs text-slate-600">Price Range (USD)</Label>
                    <div className="flex gap-2">
                      <Input placeholder="Min" type="number" className="border-slate-200" />
                      <Input placeholder="Max" type="number" className="border-slate-200" />
                    </div>
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-xs text-slate-600">Target Categories</Label>
                    <Input placeholder="Restaurants, Salons, Clinics..." className="border-slate-200" />
                  </div>
                </div>
                <Button size="sm" className="bg-indigo-600 hover:bg-indigo-700">Save Profile</Button>
              </CardContent>
            </Card>

            {/* Email delivery — the first thing every new customer must complete before
                outreach can send, because each customer sends from their own mailbox. */}
            <Card className="border-slate-200">
              <CardHeader>
                <CardTitle className="text-sm font-medium text-slate-600 flex items-center gap-2">
                  <Mail className="h-4 w-4 text-slate-500" />
                  Email delivery
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-5">
                {emailLoading ? (
                  <Skeleton className="h-40 w-full" />
                ) : (
                  <>
                    {/* Verification state, always visible at the top. Untested must never
                        look like working — a gray badge, not a green one, is the default. */}
                    {emailData?.last_error ? (
                      <div className="rounded-lg border border-red-200 bg-red-50 p-3">
                        <div className="flex items-start gap-2">
                          <XCircle className="h-4 w-4 shrink-0 mt-0.5 text-red-600" />
                          <div className="min-w-0">
                            <p className="text-sm font-medium text-red-800">Last test failed</p>
                            <p className="mt-0.5 text-sm text-red-700 break-words">{emailData.last_error}</p>
                            {emailData.verified_at && (
                              <p className="mt-1 text-xs text-red-600">
                                Previously verified {formatWhen(emailData.verified_at)}
                              </p>
                            )}
                          </div>
                        </div>
                      </div>
                    ) : emailData?.verified_at ? (
                      <div className="flex items-center gap-2 rounded-lg border border-green-200 bg-green-50 p-3">
                        <CheckCircle2 className="h-4 w-4 shrink-0 text-green-600" />
                        <p className="text-sm text-green-800">
                          <span className="font-medium">Verified</span> — test email sent{' '}
                          {formatWhen(emailData.verified_at)}
                        </p>
                      </div>
                    ) : (
                      <div className="flex items-center gap-2 rounded-lg border border-slate-200 bg-slate-50 p-3">
                        <AlertTriangle className="h-4 w-4 shrink-0 text-amber-500" />
                        <p className="text-sm text-slate-600">
                          Not yet tested — send a test email below to confirm delivery actually works
                          before you rely on it for outreach.
                        </p>
                      </div>
                    )}

                    {emailData && !emailData.encryption_available && (
                      <Alert variant="destructive">
                        <ShieldAlert className="h-4 w-4" />
                        <AlertTitle>Credential storage is unavailable</AlertTitle>
                        <AlertDescription>
                          The operator must set <code className="text-xs">CREDENTIAL_ENCRYPTION_KEY</code>{' '}
                          on the API service before any password or API key can be saved. The form below
                          is disabled so nothing you type is lost or stored insecurely.
                        </AlertDescription>
                      </Alert>
                    )}

                    <fieldset
                      disabled={!emailData?.encryption_available}
                      className="space-y-5 disabled:opacity-60"
                    >
                      {/* Provider choice */}
                      <div className="space-y-1.5">
                        <Label className="text-xs font-medium text-slate-600">Send using</Label>
                        <RadioGroup
                          value={emailProvider}
                          onValueChange={(v) => setEmailProvider(v as 'smtp' | 'resend')}
                          className="grid gap-2 sm:grid-cols-2"
                        >
                          <Label
                            htmlFor="provider-smtp"
                            className={cn(
                              'flex cursor-pointer items-center gap-2 rounded-lg border p-3 text-sm',
                              emailProvider === 'smtp'
                                ? 'border-indigo-300 bg-indigo-50 text-indigo-900'
                                : 'border-slate-200 text-slate-700',
                            )}
                          >
                            <RadioGroupItem value="smtp" id="provider-smtp" className="cursor-pointer" />
                            SMTP (e.g. Gmail)
                          </Label>
                          <Label
                            htmlFor="provider-resend"
                            className={cn(
                              'flex cursor-pointer items-center gap-2 rounded-lg border p-3 text-sm',
                              emailProvider === 'resend'
                                ? 'border-indigo-300 bg-indigo-50 text-indigo-900'
                                : 'border-slate-200 text-slate-700',
                            )}
                          >
                            <RadioGroupItem value="resend" id="provider-resend" className="cursor-pointer" />
                            Resend
                          </Label>
                        </RadioGroup>
                      </div>

                      {emailProvider === 'smtp' ? (
                        <div className="grid gap-4 sm:grid-cols-2">
                          <div className="space-y-1.5">
                            <Label htmlFor="smtp-host" className="text-xs font-medium text-slate-600">
                              SMTP host
                            </Label>
                            <Input
                              id="smtp-host"
                              placeholder="smtp.gmail.com"
                              value={smtpHost}
                              onChange={(e) => setSmtpHost(e.target.value)}
                              className="border-slate-200"
                            />
                          </div>
                          <div className="space-y-1.5">
                            <Label htmlFor="smtp-port" className="text-xs font-medium text-slate-600">
                              Port
                            </Label>
                            <Input
                              id="smtp-port"
                              type="number"
                              placeholder="587"
                              value={smtpPort}
                              onChange={(e) => setSmtpPort(e.target.value)}
                              className="border-slate-200"
                            />
                          </div>
                          <div className="space-y-1.5">
                            <Label htmlFor="smtp-username" className="text-xs font-medium text-slate-600">
                              Username
                            </Label>
                            <Input
                              id="smtp-username"
                              placeholder="you@gmail.com"
                              value={smtpUsername}
                              onChange={(e) => setSmtpUsername(e.target.value)}
                              className="border-slate-200"
                            />
                          </div>
                          <div className="space-y-1.5">
                            <Label htmlFor="smtp-password" className="text-xs font-medium text-slate-600">
                              Password
                            </Label>
                            <Input
                              id="smtp-password"
                              type="password"
                              placeholder={
                                emailData?.smtp_password_set
                                  ? '••••••••  (leave blank to keep)'
                                  : 'App password (16 characters)'
                              }
                              value={smtpPassword}
                              onChange={(e) => setSmtpPassword(e.target.value)}
                              className="border-slate-200"
                              autoComplete="new-password"
                            />
                          </div>
                          <div className="flex items-center justify-between gap-3 rounded-lg border border-slate-200 p-3 sm:col-span-2">
                            <div>
                              <Label htmlFor="smtp-tls" className="text-sm font-medium text-slate-900">
                                Use TLS
                              </Label>
                              <p className="text-xs text-slate-500">Required by Gmail and most providers.</p>
                            </div>
                            <Switch id="smtp-tls" checked={smtpUseTls} onCheckedChange={setSmtpUseTls} />
                          </div>
                        </div>
                      ) : (
                        <div className="space-y-1.5">
                          <Label htmlFor="resend-key" className="text-xs font-medium text-slate-600">
                            Resend API key
                          </Label>
                          <Input
                            id="resend-key"
                            type="password"
                            placeholder={
                              emailData?.resend_api_key_set
                                ? '••••••••  (leave blank to keep)'
                                : 're_xxxxxxxxxxxxxxxxxxxxxxxx'
                            }
                            value={resendApiKey}
                            onChange={(e) => setResendApiKey(e.target.value)}
                            className="border-slate-200"
                            autoComplete="new-password"
                          />
                        </div>
                      )}

                      <div className="grid gap-4 sm:grid-cols-2">
                        <div className="space-y-1.5">
                          <Label htmlFor="from-email" className="text-xs font-medium text-slate-600">
                            From email
                          </Label>
                          <Input
                            id="from-email"
                            type="email"
                            placeholder="you@yourbusiness.com"
                            value={fromEmail}
                            onChange={(e) => setFromEmail(e.target.value)}
                            className="border-slate-200"
                          />
                        </div>
                        <div className="space-y-1.5">
                          <Label htmlFor="from-name" className="text-xs font-medium text-slate-600">
                            From name
                          </Label>
                          <Input
                            id="from-name"
                            placeholder="Your name or business"
                            value={fromName}
                            onChange={(e) => setFromName(e.target.value)}
                            className="border-slate-200"
                          />
                        </div>
                      </div>

                      {/* Provider-specific setup help, answered inline rather than making
                          the customer go find it. */}
                      <div className="rounded-lg border border-slate-200 bg-slate-50 p-4 text-sm text-slate-700">
                        {emailProvider === 'smtp' ? (
                          <>
                            <p className="font-medium text-slate-900">Using Gmail?</p>
                            <ol className="mt-2 list-decimal space-y-1.5 pl-5">
                              <li>Turn on 2-Step Verification for the account first.</li>
                              <li>
                                Create an App Password at{' '}
                                <a
                                  href="https://myaccount.google.com/apppasswords"
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="inline-flex items-center gap-1 text-indigo-600 underline underline-offset-2"
                                >
                                  myaccount.google.com/apppasswords
                                  <ExternalLink className="h-3 w-3" />
                                </a>
                              </li>
                              <li>
                                Use those 16 letters as the password above. Your normal account
                                password is always rejected.
                              </li>
                            </ol>
                          </>
                        ) : (
                          <>
                            <p className="font-medium text-slate-900">Using Resend</p>
                            <p className="mt-2">
                              Verify your sending domain at{' '}
                              <a
                                href="https://resend.com/domains"
                                target="_blank"
                                rel="noopener noreferrer"
                                className="inline-flex items-center gap-1 text-indigo-600 underline underline-offset-2"
                              >
                                resend.com/domains
                                <ExternalLink className="h-3 w-3" />
                              </a>{' '}
                              — until it is verified, Resend only delivers to the address that owns
                              the account.
                            </p>
                          </>
                        )}
                      </div>

                      {testResult && !testResult.success && (
                        <div className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
                          <XCircle className="h-4 w-4 shrink-0 mt-0.5" />
                          <span className="break-words">{testResult.message}</span>
                        </div>
                      )}

                      <div className="flex flex-wrap items-center gap-3 pt-1">
                        <Button
                          onClick={saveEmailSettings}
                          disabled={emailSaving || !emailFormDirty}
                          className="bg-indigo-600 hover:bg-indigo-700 gap-2 cursor-pointer disabled:cursor-not-allowed"
                        >
                          {emailSaving && <Loader2 className="h-4 w-4 animate-spin" />}
                          Save
                        </Button>
                        <Button
                          variant="outline"
                          onClick={sendTestEmail}
                          disabled={emailTesting || emailFormDirty || !emailData?.from_email}
                          title={
                            emailFormDirty
                              ? 'Save your changes first'
                              : !emailData?.from_email
                              ? 'Set a From email and save first'
                              : undefined
                          }
                          className="border-slate-200 gap-2 cursor-pointer disabled:cursor-not-allowed"
                        >
                          {emailTesting ? (
                            <Loader2 className="h-3.5 w-3.5 animate-spin" />
                          ) : (
                            <Send className="h-3.5 w-3.5" />
                          )}
                          {emailTesting ? 'Sending...' : 'Send test email'}
                        </Button>
                        {(emailData?.smtp_password_set || emailData?.resend_api_key_set || emailData?.from_email) && (
                          <Button
                            variant="outline"
                            onClick={deleteEmailSettings}
                            disabled={emailDeleting}
                            className="border-red-200 text-red-600 hover:bg-red-50 gap-1.5 cursor-pointer disabled:cursor-not-allowed"
                          >
                            {emailDeleting ? (
                              <Loader2 className="h-3.5 w-3.5 animate-spin" />
                            ) : (
                              <Trash2 className="h-3.5 w-3.5" />
                            )}
                            Remove
                          </Button>
                        )}
                        <p className="text-xs text-slate-500">
                          The test sends to <strong className="text-slate-700">your own</strong> signed-in
                          account address.
                        </p>
                      </div>
                    </fieldset>
                  </>
                )}
              </CardContent>
            </Card>

            {/* Integrations */}
            <Card className="border-slate-200">
              <CardHeader>
                <CardTitle className="text-sm font-medium text-slate-600">Integrations</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  {/* Status comes from the API, never a hardcoded value. This
                      block previously rendered 'Not Connected' unconditionally,
                      so a correctly configured provider still read as missing. */}
                  {[
                    {
                      name: 'MapBox Places API',
                      desc: 'Live business discovery',
                      connected: providerStatus?.mapbox_connected ?? null,
                      note: 'Set MAPBOX_ACCESS_TOKEN on the API service',
                    },
                    {
                      name: 'PageSpeed Insights',
                      desc: 'Website performance audits — optional',
                      connected: providerStatus?.pagespeed_connected ?? null,
                      note: 'Optional. Without it, site quality is scored from the page we already fetch.',
                    },
                  ].map((intg) => (
                    <div key={intg.name} className="flex items-center justify-between p-3 rounded-lg border border-slate-200">
                      <div className="flex items-center gap-3">
                        <Plug className={cn('h-4 w-4', intg.connected ? 'text-green-600' : 'text-slate-400')} />
                        <div>
                          <p className="text-sm font-medium text-slate-700">{intg.name}</p>
                          <p className="text-xs text-slate-500">
                            {intg.connected ? intg.desc : `${intg.desc} · ${intg.note}`}
                          </p>
                        </div>
                      </div>
                      {intg.connected === null ? (
                        <Badge variant="outline" className="text-xs border-slate-200 text-slate-400">
                          Checking…
                        </Badge>
                      ) : intg.connected ? (
                        <Badge variant="outline" className="text-xs bg-green-50 text-green-700 border-green-200">
                          Connected
                        </Badge>
                      ) : (
                        <Badge variant="outline" className="text-xs bg-amber-50 text-amber-700 border-amber-200">
                          Not Connected
                        </Badge>
                      )}
                    </div>
                  ))}
                </div>
                <p className="text-xs text-slate-500 mt-4">
                  {providerStatus?.mapbox_connected
                    ? 'Discovery is live. Searches return real businesses from the connected provider.'
                    : 'Discovery requires a connected provider. Without one, Discover returns no results rather than inventing businesses.'}
                </p>
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="billing" className="space-y-4 mt-4">
            {verifying && (
              <Card className="border-indigo-200 bg-indigo-50">
                <CardContent className="p-4 flex items-center gap-3">
                  <Loader2 className="h-5 w-5 animate-spin text-indigo-600" />
                  <span className="text-sm text-indigo-800">Verifying payment...</span>
                </CardContent>
              </Card>
            )}

            {/* Current Plan */}
            <Card className="border-slate-200">
              <CardHeader>
                <CardTitle className="text-sm font-medium text-slate-600">Current Plan</CardTitle>
              </CardHeader>
              <CardContent>
                {loading ? (
                  <div className="h-20 animate-pulse bg-slate-100 rounded" />
                ) : usage ? (
                  <div className="space-y-4">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-lg font-bold text-slate-900 capitalize">{usage.plan_name}</p>
                        <Badge variant="outline" className="text-xs capitalize mt-1">{usage.subscription_status}</Badge>
                      </div>
                      <div className="text-right">
                        <p className="text-sm text-slate-600">
                          {usage.credits_remaining} / {usage.credits_total} credits
                        </p>
                        <div className="w-32 h-1.5 rounded-full bg-slate-100 mt-1">
                          <div
                            className="h-full rounded-full bg-indigo-600"
                            style={{ width: `${(usage.credits_used / Math.max(1, usage.credits_total)) * 100}%` }}
                          />
                        </div>
                      </div>
                    </div>
                    {usage.subscription_status === 'trialing' && usage.trial_ends_at && (
                      <p className="text-xs text-amber-700 bg-amber-50 rounded px-2 py-1">
                        Trial ends: {new Date(usage.trial_ends_at).toLocaleDateString()}
                      </p>
                    )}
                  </div>
                ) : null}
              </CardContent>
            </Card>

            {/* Upgrade Options */}
            {usage && usage.plan !== 'agency' && (
              <Card className="border-slate-200">
                <CardHeader>
                  <CardTitle className="text-sm font-medium text-slate-600">Upgrade</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="grid gap-3 sm:grid-cols-3">
                    {[
                      { id: 'solo', name: 'Solo', price: '$29/mo', credits: '300 credits' },
                      { id: 'pro', name: 'Pro', price: '$79/mo', credits: '1,500 credits' },
                      { id: 'agency', name: 'Agency', price: '$199/mo', credits: '5,000 credits' },
                    ].filter(p => {
                      const order = ['trial', 'solo', 'pro', 'agency'];
                      return order.indexOf(p.id) > order.indexOf(usage.plan);
                    }).map((plan) => (
                      <div key={plan.id} className="rounded-lg border border-slate-200 p-4">
                        <p className="font-medium text-slate-900">{plan.name}</p>
                        <p className="text-sm text-slate-500">{plan.price} · {plan.credits}</p>
                        <Button
                          size="sm"
                          className="mt-3 w-full bg-indigo-600 hover:bg-indigo-700 gap-1"
                          onClick={() => handleUpgrade(plan.id)}
                          disabled={upgrading === plan.id}
                        >
                          {upgrading === plan.id ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <ArrowRight className="h-3.5 w-3.5" />}
                          Upgrade
                        </Button>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            )}
          </TabsContent>
        </Tabs>
      </div>
    </AppShell>
  );
}