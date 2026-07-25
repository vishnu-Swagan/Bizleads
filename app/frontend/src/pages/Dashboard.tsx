import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import AppLayout from '@/components/AppLayout';
import GuidedTutorial from '@/components/GuidedTutorial';
import { client } from '@/lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Users, Target, TrendingUp, CheckCircle, Search, Globe,
  ArrowRight, Phone, Mail, Kanban, List, BarChart3, Plus
} from 'lucide-react';

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
  contact_email: string;
  contact_phone: string;
  created_at: string;
}

const STAGE_CONFIG: Record<string, { label: string; color: string }> = {
  new_lead: { label: 'New Lead', color: 'bg-blue-100 text-blue-700' },
  contacted: { label: 'Contacted', color: 'bg-yellow-100 text-yellow-700' },
  in_progress: { label: 'In Progress', color: 'bg-purple-100 text-purple-700' },
  won: { label: 'Won', color: 'bg-green-100 text-green-700' },
  lost: { label: 'Lost', color: 'bg-red-100 text-red-700' },
};

export default function Dashboard() {
  const { user, loading: authLoading, login } = useAuth();
  const navigate = useNavigate();
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
        limit: 200,
      });
      setLeads(response.data?.items || []);
    } catch (err) {
      console.error('Failed to fetch leads:', err);
    } finally {
      setLoading(false);
    }
  };

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
          <h2 className="font-[Poppins] text-2xl font-semibold">Sign in to access your CRM</h2>
          <p className="mt-2 text-muted-foreground">Manage your leads and track your pipeline.</p>
          <Button onClick={login} className="mt-6">
            Sign In
          </Button>
        </div>
      </AppLayout>
    );
  }

  // Calculate metrics
  const totalLeads = leads.length;
  const newLeads = leads.filter((l) => l.pipeline_stage === 'new_lead').length;
  const inProgress = leads.filter((l) => l.pipeline_stage === 'in_progress' || l.pipeline_stage === 'contacted').length;
  const won = leads.filter((l) => l.pipeline_stage === 'won').length;
  const lost = leads.filter((l) => l.pipeline_stage === 'lost').length;
  const closed = won + lost;
  const conversionRate = closed > 0 ? Math.round((won / closed) * 100) : 0;
  const highPriority = leads.filter((l) => l.priority === 'high').length;

  return (
    <AppLayout>
      <div className="space-y-6">
        {/* Page Header */}
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className="font-[Poppins] text-2xl font-bold text-foreground">Dashboard</h1>
            <p className="text-sm text-muted-foreground">Overview of your lead pipeline and performance</p>
          </div>
          <Button onClick={() => navigate('/search')} className="gap-2">
            <Search className="h-4 w-4" />
            Find Businesses
          </Button>
        </div>

        {/* Metrics */}
        {loading ? (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {[...Array(4)].map((_, i) => (
              <Skeleton key={i} className="h-28 rounded-xl" />
            ))}
          </div>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <MetricCard icon={Users} label="Total Leads" value={totalLeads} color="text-primary" />
            <MetricCard icon={Target} label="High Priority" value={highPriority} color="text-red-500" />
            <MetricCard icon={TrendingUp} label="In Progress" value={inProgress} color="text-purple-500" />
            <MetricCard icon={CheckCircle} label="Conversion Rate" value={`${conversionRate}%`} color="text-green-500" />
          </div>
        )}

        {/* Quick Actions */}
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <QuickAction
            icon={Search}
            label="Search Businesses"
            description="Find new leads globally"
            onClick={() => navigate('/search')}
          />
          <QuickAction
            icon={Kanban}
            label="Pipeline View"
            description="Manage lead stages"
            onClick={() => navigate('/pipeline')}
          />
          <QuickAction
            icon={List}
            label="All Leads"
            description="View & filter all leads"
            onClick={() => navigate('/leads')}
          />
          <QuickAction
            icon={BarChart3}
            label="Analytics"
            description="View performance insights"
            onClick={() => navigate('/analytics')}
          />
        </div>

        {/* Guided Tutorial for New Users */}
        <GuidedTutorial onNavigate={(route) => navigate(route)} />

        {/* Recent Leads & Pipeline */}
        <div className="grid gap-6 lg:grid-cols-3">
          {/* Recent Leads */}
          <Card className="lg:col-span-2">
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="font-[Poppins] text-lg">Recent Leads</CardTitle>
              <Button variant="ghost" size="sm" className="text-primary gap-1" onClick={() => navigate('/leads')}>
                View All <ArrowRight className="h-3 w-3" />
              </Button>
            </CardHeader>
            <CardContent>
              {loading ? (
                <div className="space-y-3">
                  {[...Array(5)].map((_, i) => (
                    <Skeleton key={i} className="h-16 rounded-lg" />
                  ))}
                </div>
              ) : leads.length === 0 ? (
                <div className="flex flex-col items-center py-12 text-center">
                  <Search className="mb-3 h-10 w-10 text-muted-foreground/50" />
                  <p className="text-muted-foreground">No leads yet. Start by searching for businesses.</p>
                  <Button onClick={() => navigate('/search')} variant="outline" className="mt-4 gap-2">
                    <Plus className="h-4 w-4" />
                    Search Businesses
                  </Button>
                </div>
              ) : (
                <div className="space-y-2">
                  {leads.slice(0, 6).map((lead) => (
                    <div
                      key={lead.id}
                      className="flex cursor-pointer items-center justify-between rounded-lg border border-border p-3 transition-colors hover:bg-muted/50"
                      onClick={() => navigate(`/lead/${lead.id}`)}
                    >
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <p className="truncate font-medium text-foreground">{lead.business_name}</p>
                          <Badge variant="outline" className="hidden sm:inline-flex text-xs">
                            {lead.category}
                          </Badge>
                        </div>
                        <div className="mt-1 flex items-center gap-3 text-xs text-muted-foreground">
                          <span>{lead.location}</span>
                          {lead.contact_email && (
                            <span className="hidden items-center gap-1 sm:flex">
                              <Mail className="h-3 w-3" />
                              {lead.contact_email}
                            </span>
                          )}
                          {lead.contact_phone && (
                            <span className="hidden items-center gap-1 lg:flex">
                              <Phone className="h-3 w-3" />
                              {lead.contact_phone}
                            </span>
                          )}
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${STAGE_CONFIG[lead.pipeline_stage]?.color || 'bg-gray-100 text-gray-700'}`}>
                          {STAGE_CONFIG[lead.pipeline_stage]?.label || lead.pipeline_stage}
                        </span>
                        <ArrowRight className="h-4 w-4 text-muted-foreground" />
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Pipeline Summary Sidebar */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="font-[Poppins] text-lg">Pipeline Summary</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {loading ? (
                <div className="space-y-3">
                  {[...Array(5)].map((_, i) => (
                    <Skeleton key={i} className="h-10 rounded-lg" />
                  ))}
                </div>
              ) : (
                <>
                  {Object.entries(STAGE_CONFIG).map(([stage, config]) => {
                    const count = leads.filter((l) => l.pipeline_stage === stage).length;
                    const percentage = totalLeads > 0 ? Math.round((count / totalLeads) * 100) : 0;
                    return (
                      <div key={stage} className="space-y-1">
                        <div className="flex items-center justify-between">
                          <span className="text-sm text-muted-foreground">{config.label}</span>
                          <span className="text-sm font-medium">{count}</span>
                        </div>
                        <div className="h-2 w-full rounded-full bg-muted overflow-hidden">
                          <div
                            className={`h-full rounded-full transition-all duration-500 ${
                              stage === 'new_lead' ? 'bg-blue-500' :
                              stage === 'contacted' ? 'bg-yellow-500' :
                              stage === 'in_progress' ? 'bg-purple-500' :
                              stage === 'won' ? 'bg-green-500' : 'bg-red-500'
                            }`}
                            style={{ width: `${Math.max(percentage, 3)}%` }}
                          />
                        </div>
                      </div>
                    );
                  })}
                  <Button
                    variant="outline"
                    size="sm"
                    className="w-full mt-4 gap-2"
                    onClick={() => navigate('/pipeline')}
                  >
                    <Kanban className="h-4 w-4" />
                    Open Pipeline Board
                  </Button>
                </>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </AppLayout>
  );
}

function MetricCard({
  icon: Icon,
  label,
  value,
  color,
}: {
  icon: React.ElementType;
  label: string;
  value: string | number;
  color: string;
}) {
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

function QuickAction({
  icon: Icon,
  label,
  description,
  onClick,
}: {
  icon: React.ElementType;
  label: string;
  description: string;
  onClick: () => void;
}) {
  return (
    <Card
      className="cursor-pointer transition-all hover:border-primary/30 hover:shadow-sm"
      onClick={onClick}
    >
      <CardContent className="flex items-center gap-3 p-4">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10">
          <Icon className="h-4 w-4 text-primary" />
        </div>
        <div className="min-w-0">
          <p className="text-sm font-medium text-foreground">{label}</p>
          <p className="text-xs text-muted-foreground truncate">{description}</p>
        </div>
      </CardContent>
    </Card>
  );
}