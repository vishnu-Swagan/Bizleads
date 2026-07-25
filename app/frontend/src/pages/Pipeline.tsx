import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import AppLayout from '@/components/AppLayout';
import { client } from '@/lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { toast } from 'sonner';
import {
  Globe, MapPin, Building2, GripVertical, ArrowRight
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

const PIPELINE_STAGES = [
  { key: 'new_lead', label: 'New Lead', color: 'border-t-blue-500', bgColor: 'bg-blue-50', textColor: 'text-blue-700' },
  { key: 'contacted', label: 'Contacted', color: 'border-t-yellow-500', bgColor: 'bg-yellow-50', textColor: 'text-yellow-700' },
  { key: 'in_progress', label: 'In Progress', color: 'border-t-purple-500', bgColor: 'bg-purple-50', textColor: 'text-purple-700' },
  { key: 'won', label: 'Won', color: 'border-t-green-500', bgColor: 'bg-green-50', textColor: 'text-green-700' },
  { key: 'lost', label: 'Lost', color: 'border-t-red-500', bgColor: 'bg-red-50', textColor: 'text-red-700' },
];

const PRIORITY_COLORS: Record<string, string> = {
  high: 'bg-red-100 text-red-700',
  medium: 'bg-orange-100 text-orange-700',
  low: 'bg-gray-100 text-gray-700',
};

export default function Pipeline() {
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

  const moveToStage = async (leadId: number, newStage: string) => {
    try {
      await client.entities.leads.update({
        id: String(leadId),
        data: { pipeline_stage: newStage },
      });
      setLeads((prev) =>
        prev.map((l) => (l.id === leadId ? { ...l, pipeline_stage: newStage } : l))
      );
      toast.success('Lead moved successfully');
    } catch (err) {
      console.error('Failed to move lead:', err);
      toast.error('Failed to move lead');
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
          <h2 className="font-[Poppins] text-2xl font-semibold">Sign in to view pipeline</h2>
          <p className="mt-2 text-muted-foreground">Manage your leads through pipeline stages.</p>
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
          <h1 className="font-[Poppins] text-2xl font-bold text-foreground">Pipeline</h1>
          <p className="text-sm text-muted-foreground">
            Drag leads through your sales pipeline stages
          </p>
        </div>

        {/* Pipeline Board */}
        {loading ? (
          <div className="grid gap-4 lg:grid-cols-5">
            {[...Array(5)].map((_, i) => (
              <Skeleton key={i} className="h-96 rounded-xl" />
            ))}
          </div>
        ) : (
          <div className="grid gap-4 lg:grid-cols-5">
            {PIPELINE_STAGES.map((stage) => {
              const stageLeads = leads.filter((l) => l.pipeline_stage === stage.key);
              const nextStageIndex = PIPELINE_STAGES.findIndex((s) => s.key === stage.key) + 1;
              const nextStage = PIPELINE_STAGES[nextStageIndex];

              return (
                <div key={stage.key} className="space-y-3">
                  {/* Stage Header */}
                  <Card className={`border-t-4 ${stage.color}`}>
                    <CardHeader className="p-3 pb-1">
                      <div className="flex items-center justify-between">
                        <CardTitle className="text-sm font-semibold">{stage.label}</CardTitle>
                        <Badge variant="secondary" className="text-xs">
                          {stageLeads.length}
                        </Badge>
                      </div>
                    </CardHeader>
                  </Card>

                  {/* Stage Cards */}
                  <div className="space-y-2 min-h-[200px]">
                    {stageLeads.length === 0 ? (
                      <div className="flex items-center justify-center rounded-lg border border-dashed border-border p-6">
                        <p className="text-xs text-muted-foreground">No leads</p>
                      </div>
                    ) : (
                      stageLeads.map((lead) => (
                        <Card
                          key={lead.id}
                          className="cursor-pointer transition-all hover:shadow-md hover:border-primary/30"
                        >
                          <CardContent className="p-3">
                            <div className="flex items-start gap-2">
                              <GripVertical className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground/50" />
                              <div className="flex-1 min-w-0">
                                <p
                                  className="truncate text-sm font-medium text-foreground hover:text-primary cursor-pointer"
                                  onClick={() => navigate(`/lead/${lead.id}`)}
                                >
                                  {lead.business_name}
                                </p>
                                <div className="mt-1 flex items-center gap-1 text-[11px] text-muted-foreground">
                                  <Building2 className="h-3 w-3" />
                                  <span className="truncate">{lead.category}</span>
                                </div>
                                <div className="mt-0.5 flex items-center gap-1 text-[11px] text-muted-foreground">
                                  <MapPin className="h-3 w-3" />
                                  <span className="truncate">{lead.location}</span>
                                </div>
                                <div className="mt-2 flex items-center justify-between">
                                  <Badge
                                    variant="outline"
                                    className={`text-[10px] border-0 ${PRIORITY_COLORS[lead.priority] || ''}`}
                                  >
                                    {lead.priority}
                                  </Badge>
                                  {nextStage && (
                                    <Button
                                      variant="ghost"
                                      size="sm"
                                      className="h-6 px-1.5 text-[10px] gap-0.5"
                                      onClick={(e) => {
                                        e.stopPropagation();
                                        moveToStage(lead.id, nextStage.key);
                                      }}
                                    >
                                      <ArrowRight className="h-3 w-3" />
                                    </Button>
                                  )}
                                </div>
                              </div>
                            </div>
                          </CardContent>
                        </Card>
                      ))
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </AppLayout>
  );
}