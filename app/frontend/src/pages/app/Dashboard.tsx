import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import AppShell from '@/components/AppShell';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { client } from '@/lib/api';
import {
  Search, TrendingUp, Users, Zap, ArrowRight,
  CreditCard, AlertCircle, CheckCircle2, Clock,
} from 'lucide-react';

interface UsageData {
  plan: string;
  plan_name: string;
  credits_total: number;
  credits_used: number;
  credits_remaining: number;
  subscription_status: string;
  trial_ends_at: string;
}

interface LeadStats {
  total: number;
  new_leads: number;
  contacted: number;
  won: number;
}

export default function AppDashboard() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [usage, setUsage] = useState<UsageData | null>(null);
  const [stats, setStats] = useState<LeadStats>({ total: 0, new_leads: 0, contacted: 0, won: 0 });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (user) fetchData();
  }, [user]);

  const fetchData = async () => {
    try {
      const [usageRes, leadsRes] = await Promise.all([
        client.apiCall.invoke({ url: '/api/v1/billing/usage', method: 'GET', data: {} }),
        client.entities.leads.query({ query: {}, limit: 200 }),
      ]);
      setUsage(usageRes.data);

      const leads = leadsRes.data?.items || [];
      setStats({
        total: leads.length,
        new_leads: leads.filter((l: any) => l.pipeline_stage === 'new_lead').length,
        contacted: leads.filter((l: any) => l.pipeline_stage === 'contacted').length,
        won: leads.filter((l: any) => l.pipeline_stage === 'won').length,
      });
    } catch (err) {
      console.error('Dashboard fetch error:', err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <AppShell>
      <div className="space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-slate-900">Dashboard</h1>
            <p className="text-sm text-slate-500">Welcome back. Here's your workspace overview.</p>
          </div>
          <Button onClick={() => navigate('/app/discover')} className="bg-indigo-600 hover:bg-indigo-700 gap-2">
            <Search className="h-4 w-4" />
            Discover Leads
          </Button>
        </div>

        {/* Usage & Plan */}
        {loading ? (
          <div className="grid gap-4 md:grid-cols-4">
            {[...Array(4)].map((_, i) => <Skeleton key={i} className="h-28 rounded-xl" />)}
          </div>
        ) : (
          <>
            {/* Plan status banner */}
            {usage?.subscription_status === 'trialing' && (
              <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <Clock className="h-5 w-5 text-amber-600" />
                  <div>
                    <p className="text-sm font-medium text-amber-900">Free Trial Active</p>
                    <p className="text-xs text-amber-700">
                      {usage.credits_remaining} credits remaining · Upgrade for more capacity
                    </p>
                  </div>
                </div>
                <Button size="sm" variant="outline" onClick={() => navigate('/app/settings/billing')} className="border-amber-300 text-amber-800 hover:bg-amber-100">
                  Upgrade Plan
                </Button>
              </div>
            )}

            {/* Metrics */}
            <div className="grid gap-4 md:grid-cols-4">
              <Card className="border-slate-200">
                <CardContent className="p-5">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-xs font-medium text-slate-500 uppercase tracking-wide">Credits</p>
                      <p className="text-2xl font-bold text-slate-900 mt-1">
                        {usage?.credits_remaining ?? 0}
                        <span className="text-sm font-normal text-slate-400">/{usage?.credits_total ?? 0}</span>
                      </p>
                    </div>
                    <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-indigo-50">
                      <CreditCard className="h-5 w-5 text-indigo-600" />
                    </div>
                  </div>
                  <div className="mt-3 h-1.5 rounded-full bg-slate-100">
                    <div
                      className="h-full rounded-full bg-indigo-600 transition-all"
                      style={{ width: `${Math.min(100, ((usage?.credits_used ?? 0) / Math.max(1, usage?.credits_total ?? 1)) * 100)}%` }}
                    />
                  </div>
                </CardContent>
              </Card>

              <Card className="border-slate-200">
                <CardContent className="p-5">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-xs font-medium text-slate-500 uppercase tracking-wide">Total Leads</p>
                      <p className="text-2xl font-bold text-slate-900 mt-1">{stats.total}</p>
                    </div>
                    <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-blue-50">
                      <Users className="h-5 w-5 text-blue-600" />
                    </div>
                  </div>
                  <p className="text-xs text-slate-500 mt-3">{stats.new_leads} new · {stats.contacted} contacted</p>
                </CardContent>
              </Card>

              <Card className="border-slate-200">
                <CardContent className="p-5">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-xs font-medium text-slate-500 uppercase tracking-wide">Won Deals</p>
                      <p className="text-2xl font-bold text-slate-900 mt-1">{stats.won}</p>
                    </div>
                    <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-green-50">
                      <CheckCircle2 className="h-5 w-5 text-green-600" />
                    </div>
                  </div>
                  <p className="text-xs text-slate-500 mt-3">
                    {stats.total > 0
                      ? `Lead-to-win: ${((stats.won / stats.total) * 100).toFixed(1)}% (${stats.won} of ${stats.total})`
                      : 'No leads yet'}
                  </p>
                </CardContent>
              </Card>

              <Card className="border-slate-200">
                <CardContent className="p-5">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-xs font-medium text-slate-500 uppercase tracking-wide">Plan</p>
                      <p className="text-2xl font-bold text-slate-900 mt-1 capitalize">{usage?.plan_name ?? 'Trial'}</p>
                    </div>
                    <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-purple-50">
                      <Zap className="h-5 w-5 text-purple-600" />
                    </div>
                  </div>
                  <Badge variant="secondary" className="mt-3 text-xs capitalize">
                    {usage?.subscription_status ?? 'trialing'}
                  </Badge>
                </CardContent>
              </Card>
            </div>
          </>
        )}

        {/* Quick Actions */}
        <div className="grid gap-4 md:grid-cols-3">
          <Card className="border-slate-200 hover:border-indigo-200 transition-colors cursor-pointer" onClick={() => navigate('/app/discover')}>
            <CardContent className="p-5">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-indigo-50">
                  <Search className="h-5 w-5 text-indigo-600" />
                </div>
                <div>
                  <h3 className="font-medium text-slate-900">Discover Businesses</h3>
                  <p className="text-xs text-slate-500">Find scored opportunities in your target market</p>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card className="border-slate-200 hover:border-indigo-200 transition-colors cursor-pointer" onClick={() => navigate('/app/pipeline')}>
            <CardContent className="p-5">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-blue-50">
                  <TrendingUp className="h-5 w-5 text-blue-600" />
                </div>
                <div>
                  <h3 className="font-medium text-slate-900">Pipeline</h3>
                  <p className="text-xs text-slate-500">Manage leads through your sales stages</p>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card className="border-slate-200 hover:border-indigo-200 transition-colors cursor-pointer" onClick={() => navigate('/app/settings/workspace')}>
            <CardContent className="p-5">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-green-50">
                  <Zap className="h-5 w-5 text-green-600" />
                </div>
                {/* Was "Offer Profile — Configure services for better Fit
                    scoring", pointing at a card that has been removed: it
                    saved nothing, and the Fit score it named is a hardcoded
                    constant. This now names the one thing on that page a
                    customer must actually do before outreach can send. */}
                <div>
                  <h3 className="font-medium text-slate-900">Sending account</h3>
                  <p className="text-xs text-slate-500">Set the address your outreach sends from</p>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </AppShell>
  );
}