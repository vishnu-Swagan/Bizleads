import { useEffect, useState } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { useNavigate, useLocation, useSearchParams } from 'react-router-dom';
import AppShell from '@/components/AppShell';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { toast } from 'sonner';
import { client } from '@/lib/api';
import { CreditCard, Settings as SettingsIcon, Users, Plug, CheckCircle2, ArrowRight, Loader2 } from 'lucide-react';
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

export default function AppSettings() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const [usage, setUsage] = useState<UsageData | null>(null);
  const [loading, setLoading] = useState(true);
  const [upgrading, setUpgrading] = useState<string | null>(null);
  const [verifying, setVerifying] = useState(false);

  const activeTab = location.pathname.includes('billing') ? 'billing' : 'workspace';

  useEffect(() => {
    if (user) fetchUsage();
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

            {/* Integrations */}
            <Card className="border-slate-200">
              <CardHeader>
                <CardTitle className="text-sm font-medium text-slate-600">Integrations</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  {[
                    { name: 'Google Places API', desc: 'Live business discovery', status: 'not_configured' },
                    { name: 'PageSpeed Insights', desc: 'Website performance audits', status: 'not_configured' },
                    { name: 'Email Sender (SMTP/Gmail)', desc: 'Outreach delivery', status: 'not_configured' },
                  ].map((intg) => (
                    <div key={intg.name} className="flex items-center justify-between p-3 rounded-lg border border-slate-200">
                      <div className="flex items-center gap-3">
                        <Plug className="h-4 w-4 text-slate-400" />
                        <div>
                          <p className="text-sm font-medium text-slate-700">{intg.name}</p>
                          <p className="text-xs text-slate-500">{intg.desc}</p>
                        </div>
                      </div>
                      <Badge variant="outline" className="text-xs border-slate-200 text-slate-500">
                        Not Connected
                      </Badge>
                    </div>
                  ))}
                </div>
                <p className="text-xs text-slate-500 mt-4">
                  Provider integrations enable live discovery, audits, and outreach. 
                  Without them, BizLeads uses AI-powered analysis.
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