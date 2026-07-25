import { useEffect, useState } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import AppShell from '@/components/AppShell';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { client } from '@/lib/api';
import { BarChart3, TrendingUp, Users, Target } from 'lucide-react';

interface Lead {
  pipeline_stage: string;
  priority: string;
  category: string;
  country: string;
  has_website: boolean;
  website_score: number;
}

export default function AppAnalytics() {
  const { user } = useAuth();
  const [leads, setLeads] = useState<Lead[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (user) fetchData();
  }, [user]);

  const fetchData = async () => {
    try {
      const res = await client.entities.leads.query({ query: {}, limit: 500 });
      setLeads(res.data?.items || []);
    } catch (err) {
      console.error('Analytics fetch error:', err);
    } finally {
      setLoading(false);
    }
  };

  const total = leads.length;
  const newLeads = leads.filter(l => l.pipeline_stage === 'new_lead').length;
  const contacted = leads.filter(l => l.pipeline_stage === 'contacted').length;
  const inProgress = leads.filter(l => l.pipeline_stage === 'in_progress').length;
  const won = leads.filter(l => l.pipeline_stage === 'won').length;
  const lost = leads.filter(l => l.pipeline_stage === 'lost').length;
  const closed = won + lost;

  const leadToWin = total > 0 ? ((won / total) * 100).toFixed(1) : '0.0';
  const closedDealWin = closed > 0 ? ((won / closed) * 100).toFixed(1) : '—';

  // Category distribution
  const categories: Record<string, number> = {};
  leads.forEach(l => { categories[l.category] = (categories[l.category] || 0) + 1; });
  const topCategories = Object.entries(categories).sort((a, b) => b[1] - a[1]).slice(0, 5);

  // Country distribution
  const countries: Record<string, number> = {};
  leads.forEach(l => { countries[l.country] = (countries[l.country] || 0) + 1; });
  const topCountries = Object.entries(countries).sort((a, b) => b[1] - a[1]).slice(0, 5);

  if (loading) {
    return (
      <AppShell>
        <div className="space-y-4">
          <Skeleton className="h-8 w-48" />
          <div className="grid gap-4 md:grid-cols-4">
            {[...Array(4)].map((_, i) => <Skeleton key={i} className="h-28 rounded-xl" />)}
          </div>
        </div>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Analytics</h1>
          <p className="text-sm text-slate-500">Pipeline performance and lead insights</p>
        </div>

        {/* Funnel metrics */}
        <div className="grid gap-4 md:grid-cols-4">
          <Card className="border-slate-200">
            <CardContent className="p-5">
              <p className="text-xs font-medium text-slate-500 uppercase">Total Leads</p>
              <p className="text-2xl font-bold text-slate-900 mt-1">{total}</p>
            </CardContent>
          </Card>
          <Card className="border-slate-200">
            <CardContent className="p-5">
              <p className="text-xs font-medium text-slate-500 uppercase">Lead-to-Win Rate</p>
              <p className="text-2xl font-bold text-slate-900 mt-1">{leadToWin}%</p>
              <p className="text-xs text-slate-500 mt-1">{won} of {total} total leads</p>
            </CardContent>
          </Card>
          <Card className="border-slate-200">
            <CardContent className="p-5">
              <p className="text-xs font-medium text-slate-500 uppercase">Closed-Deal Win Rate</p>
              <p className="text-2xl font-bold text-slate-900 mt-1">{closedDealWin}{closedDealWin !== '—' ? '%' : ''}</p>
              <p className="text-xs text-slate-500 mt-1">
                {closed > 0 ? `${won} of ${closed} closed deals` : 'No closed deals yet'}
              </p>
            </CardContent>
          </Card>
          <Card className="border-slate-200">
            <CardContent className="p-5">
              <p className="text-xs font-medium text-slate-500 uppercase">Active Pipeline</p>
              <p className="text-2xl font-bold text-slate-900 mt-1">{contacted + inProgress}</p>
              <p className="text-xs text-slate-500 mt-1">{contacted} contacted · {inProgress} in progress</p>
            </CardContent>
          </Card>
        </div>

        {/* Funnel */}
        <Card className="border-slate-200">
          <CardHeader>
            <CardTitle className="text-sm font-medium text-slate-600">Pipeline Funnel</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {[
                { label: 'New Lead', count: newLeads, pct: total > 0 ? (newLeads / total) * 100 : 0, color: 'bg-blue-500' },
                { label: 'Contacted', count: contacted, pct: total > 0 ? (contacted / total) * 100 : 0, color: 'bg-purple-500' },
                { label: 'In Progress', count: inProgress, pct: total > 0 ? (inProgress / total) * 100 : 0, color: 'bg-amber-500' },
                { label: 'Won', count: won, pct: total > 0 ? (won / total) * 100 : 0, color: 'bg-green-500' },
                { label: 'Lost', count: lost, pct: total > 0 ? (lost / total) * 100 : 0, color: 'bg-slate-400' },
              ].map((stage) => (
                <div key={stage.label} className="flex items-center gap-3">
                  <span className="text-xs text-slate-600 w-24">{stage.label}</span>
                  <div className="flex-1 h-5 rounded bg-slate-100 relative overflow-hidden">
                    <div className={`h-full rounded ${stage.color}`} style={{ width: `${stage.pct}%` }} />
                  </div>
                  <span className="text-xs font-medium text-slate-700 w-12 text-right">{stage.count}</span>
                </div>
              ))}
            </div>
            {total === 0 && (
              <p className="text-sm text-slate-500 text-center py-4 mt-4">
                No leads yet. Discover businesses to populate your pipeline.
              </p>
            )}
          </CardContent>
        </Card>

        {/* Distributions */}
        <div className="grid gap-4 md:grid-cols-2">
          <Card className="border-slate-200">
            <CardHeader>
              <CardTitle className="text-sm font-medium text-slate-600">Top Categories</CardTitle>
            </CardHeader>
            <CardContent>
              {topCategories.length > 0 ? (
                <div className="space-y-2">
                  {topCategories.map(([cat, count]) => (
                    <div key={cat} className="flex items-center justify-between">
                      <span className="text-sm text-slate-700">{cat}</span>
                      <span className="text-sm font-medium text-slate-900">{count}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-slate-500">No data yet</p>
              )}
            </CardContent>
          </Card>

          <Card className="border-slate-200">
            <CardHeader>
              <CardTitle className="text-sm font-medium text-slate-600">Top Countries</CardTitle>
            </CardHeader>
            <CardContent>
              {topCountries.length > 0 ? (
                <div className="space-y-2">
                  {topCountries.map(([country, count]) => (
                    <div key={country} className="flex items-center justify-between">
                      <span className="text-sm text-slate-700">{country}</span>
                      <span className="text-sm font-medium text-slate-900">{count}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-slate-500">No data yet</p>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </AppShell>
  );
}