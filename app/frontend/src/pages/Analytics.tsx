import { useEffect, useState, useMemo } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import AppLayout from '@/components/AppLayout';
import { client } from '@/lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { Globe, TrendingUp, Users, Target, MapPin, Building2, Wifi, WifiOff } from 'lucide-react';

interface Lead {
  id: number;
  business_name: string;
  category: string;
  location: string;
  country: string;
  website_score: number;
  social_score: number;
  has_website: boolean;
  pipeline_stage: string;
  priority: string;
  created_at: string;
}

const STAGE_COLORS: Record<string, string> = {
  new_lead: 'bg-blue-500',
  contacted: 'bg-yellow-500',
  in_progress: 'bg-purple-500',
  won: 'bg-green-500',
  lost: 'bg-red-500',
};

const STAGE_LABELS: Record<string, string> = {
  new_lead: 'New Lead',
  contacted: 'Contacted',
  in_progress: 'In Progress',
  won: 'Won',
  lost: 'Lost',
};

export default function Analytics() {
  const { user, loading: authLoading, login } = useAuth();
  const [leads, setLeads] = useState<Lead[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!authLoading && user) {
      fetchLeads();
    }
  }, [user, authLoading]);

  const fetchLeads = async () => {
    try {
      setLoading(true);
      const response = await client.entities.leads.query({
        sort: '-created_at',
        limit: 500,
      });
      setLeads(response.data?.items || []);
    } catch (err) {
      console.error('Failed to fetch leads:', err);
    } finally {
      setLoading(false);
    }
  };

  const analytics = useMemo(() => {
    if (leads.length === 0) return null;

    // Pipeline distribution
    const pipelineDistribution = Object.entries(STAGE_LABELS).map(([key, label]) => ({
      stage: key,
      label,
      count: leads.filter((l) => l.pipeline_stage === key).length,
      percentage: Math.round((leads.filter((l) => l.pipeline_stage === key).length / leads.length) * 100),
    }));

    // Category breakdown
    const categoryMap = new Map<string, number>();
    leads.forEach((l) => {
      categoryMap.set(l.category, (categoryMap.get(l.category) || 0) + 1);
    });
    const topCategories = Array.from(categoryMap.entries())
      .sort((a, b) => b[1] - a[1])
      .slice(0, 8);

    // Country breakdown
    const countryMap = new Map<string, number>();
    leads.forEach((l) => {
      countryMap.set(l.country, (countryMap.get(l.country) || 0) + 1);
    });
    const topCountries = Array.from(countryMap.entries())
      .sort((a, b) => b[1] - a[1])
      .slice(0, 8);

    // Web presence stats
    const noWebsite = leads.filter((l) => !l.has_website).length;
    const weakWebsite = leads.filter((l) => l.has_website && l.website_score < 40).length;
    const weakSocial = leads.filter((l) => l.social_score < 25).length;

    // Average scores
    const avgWebScore = Math.round(leads.reduce((sum, l) => sum + l.website_score, 0) / leads.length);
    const avgSocialScore = Math.round(leads.reduce((sum, l) => sum + l.social_score, 0) / leads.length);

    // Priority breakdown
    const highPriority = leads.filter((l) => l.priority === 'high').length;
    const mediumPriority = leads.filter((l) => l.priority === 'medium').length;
    const lowPriority = leads.filter((l) => l.priority === 'low').length;

    // Conversion rate
    const won = leads.filter((l) => l.pipeline_stage === 'won').length;
    const lost = leads.filter((l) => l.pipeline_stage === 'lost').length;
    const closed = won + lost;
    const conversionRate = closed > 0 ? Math.round((won / closed) * 100) : 0;

    return {
      pipelineDistribution,
      topCategories,
      topCountries,
      noWebsite,
      weakWebsite,
      weakSocial,
      avgWebScore,
      avgSocialScore,
      highPriority,
      mediumPriority,
      lowPriority,
      conversionRate,
      totalLeads: leads.length,
      won,
    };
  }, [leads]);

  if (authLoading) {
    return (
      <AppLayout>
        <div className="flex items-center justify-center py-20">
          <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
        </div>
      </AppLayout>
    );
  }

  if (!user) {
    return (
      <AppLayout>
        <div className="flex flex-col items-center justify-center py-20 text-center">
          <Globe className="mb-4 h-12 w-12 text-muted-foreground" />
          <h2 className="font-[Poppins] text-2xl font-semibold">Sign in to view analytics</h2>
          <Button onClick={login} className="mt-6">Sign In</Button>
        </div>
      </AppLayout>
    );
  }

  return (
    <AppLayout>
      <div className="space-y-6">
        {/* Page Header */}
        <div>
          <h1 className="font-[Poppins] text-2xl font-bold text-foreground">Analytics</h1>
          <p className="text-sm text-muted-foreground">
            Insights into your lead pipeline and business opportunities
          </p>
        </div>

        {loading ? (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {[...Array(8)].map((_, i) => (
              <Skeleton key={i} className="h-32 rounded-xl" />
            ))}
          </div>
        ) : !analytics ? (
          <div className="flex flex-col items-center py-16 text-center">
            <TrendingUp className="mb-4 h-12 w-12 text-muted-foreground/30" />
            <p className="text-muted-foreground">No data yet. Start by adding leads.</p>
          </div>
        ) : (
          <>
            {/* Key Metrics */}
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <MetricCard icon={Users} label="Total Leads" value={analytics.totalLeads} color="text-primary" />
              <MetricCard icon={Target} label="Conversion Rate" value={`${analytics.conversionRate}%`} color="text-green-500" />
              <MetricCard icon={Wifi} label="Avg Web Score" value={`${analytics.avgWebScore}/100`} color="text-orange-500" />
              <MetricCard icon={TrendingUp} label="Deals Won" value={analytics.won} color="text-green-600" />
            </div>

            {/* Pipeline Distribution */}
            <Card>
              <CardHeader>
                <CardTitle className="font-[Poppins] text-lg">Pipeline Distribution</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  {analytics.pipelineDistribution.map((item) => (
                    <div key={item.stage} className="flex items-center gap-3">
                      <span className="w-24 text-sm text-muted-foreground">{item.label}</span>
                      <div className="flex-1">
                        <div className="h-6 w-full rounded-full bg-muted overflow-hidden">
                          <div
                            className={`h-full rounded-full ${STAGE_COLORS[item.stage]} transition-all duration-500`}
                            style={{ width: `${Math.max(item.percentage, 2)}%` }}
                          />
                        </div>
                      </div>
                      <span className="w-16 text-right text-sm font-medium">
                        {item.count} ({item.percentage}%)
                      </span>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>

            <div className="grid gap-6 lg:grid-cols-2">
              {/* Web Presence Breakdown */}
              <Card>
                <CardHeader>
                  <CardTitle className="font-[Poppins] text-lg">Digital Presence Breakdown</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <PresenceRow
                    icon={WifiOff}
                    label="No Website"
                    count={analytics.noWebsite}
                    total={analytics.totalLeads}
                    color="bg-red-500"
                  />
                  <PresenceRow
                    icon={Wifi}
                    label="Weak Website (Score < 40)"
                    count={analytics.weakWebsite}
                    total={analytics.totalLeads}
                    color="bg-orange-500"
                  />
                  <PresenceRow
                    icon={Globe}
                    label="Weak Social Media"
                    count={analytics.weakSocial}
                    total={analytics.totalLeads}
                    color="bg-yellow-500"
                  />
                  <div className="mt-4 rounded-lg bg-muted p-3">
                    <div className="flex justify-between text-sm">
                      <span className="text-muted-foreground">Avg Website Score</span>
                      <span className="font-medium">{analytics.avgWebScore}/100</span>
                    </div>
                    <div className="mt-2 flex justify-between text-sm">
                      <span className="text-muted-foreground">Avg Social Score</span>
                      <span className="font-medium">{analytics.avgSocialScore}/100</span>
                    </div>
                  </div>
                </CardContent>
              </Card>

              {/* Priority Breakdown */}
              <Card>
                <CardHeader>
                  <CardTitle className="font-[Poppins] text-lg">Priority Distribution</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <PriorityRow label="High Priority" count={analytics.highPriority} total={analytics.totalLeads} color="bg-red-500" />
                  <PriorityRow label="Medium Priority" count={analytics.mediumPriority} total={analytics.totalLeads} color="bg-orange-500" />
                  <PriorityRow label="Low Priority" count={analytics.lowPriority} total={analytics.totalLeads} color="bg-gray-400" />
                </CardContent>
              </Card>

              {/* Top Categories */}
              <Card>
                <CardHeader>
                  <CardTitle className="font-[Poppins] text-lg flex items-center gap-2">
                    <Building2 className="h-5 w-5 text-muted-foreground" />
                    Top Categories
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-2">
                    {analytics.topCategories.map(([category, count]) => (
                      <div key={category} className="flex items-center justify-between rounded-lg p-2 hover:bg-muted/50">
                        <span className="text-sm text-foreground">{category}</span>
                        <span className="text-sm font-medium text-muted-foreground">{count}</span>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>

              {/* Top Countries */}
              <Card>
                <CardHeader>
                  <CardTitle className="font-[Poppins] text-lg flex items-center gap-2">
                    <MapPin className="h-5 w-5 text-muted-foreground" />
                    Top Countries
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-2">
                    {analytics.topCountries.map(([country, count]) => (
                      <div key={country} className="flex items-center justify-between rounded-lg p-2 hover:bg-muted/50">
                        <span className="text-sm text-foreground">{country}</span>
                        <span className="text-sm font-medium text-muted-foreground">{count}</span>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            </div>
          </>
        )}
      </div>
    </AppLayout>
  );
}

function MetricCard({ icon: Icon, label, value, color }: { icon: React.ElementType; label: string; value: string | number; color: string }) {
  return (
    <Card>
      <CardContent className="flex items-center gap-4 p-5">
        <div className={`flex h-11 w-11 items-center justify-center rounded-lg bg-muted ${color}`}>
          <Icon className="h-5 w-5" />
        </div>
        <div>
          <p className="text-sm text-muted-foreground">{label}</p>
          <p className="text-2xl font-bold text-foreground">{value}</p>
        </div>
      </CardContent>
    </Card>
  );
}

function PresenceRow({ icon: Icon, label, count, total, color }: { icon: React.ElementType; label: string; count: number; total: number; color: string }) {
  const percentage = total > 0 ? Math.round((count / total) * 100) : 0;
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Icon className="h-4 w-4 text-muted-foreground" />
          <span className="text-sm">{label}</span>
        </div>
        <span className="text-sm font-medium">{count} ({percentage}%)</span>
      </div>
      <div className="h-2 w-full rounded-full bg-muted overflow-hidden">
        <div className={`h-full rounded-full ${color} transition-all duration-500`} style={{ width: `${Math.max(percentage, 2)}%` }} />
      </div>
    </div>
  );
}

function PriorityRow({ label, count, total, color }: { label: string; count: number; total: number; color: string }) {
  const percentage = total > 0 ? Math.round((count / total) * 100) : 0;
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between">
        <span className="text-sm">{label}</span>
        <span className="text-sm font-medium">{count} ({percentage}%)</span>
      </div>
      <div className="h-2 w-full rounded-full bg-muted overflow-hidden">
        <div className={`h-full rounded-full ${color} transition-all duration-500`} style={{ width: `${Math.max(percentage, 2)}%` }} />
      </div>
    </div>
  );
}