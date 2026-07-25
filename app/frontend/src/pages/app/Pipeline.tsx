import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import AppShell from '@/components/AppShell';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { client } from '@/lib/api';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';

interface Lead {
  id: number;
  business_name: string;
  category: string;
  location: string;
  country: string;
  pipeline_stage: string;
  priority: string;
  website_score: number;
  has_website: boolean;
}

const stages = [
  { id: 'new_lead', label: 'New Lead', color: 'border-t-blue-500' },
  { id: 'contacted', label: 'Contacted', color: 'border-t-purple-500' },
  { id: 'in_progress', label: 'In Progress', color: 'border-t-amber-500' },
  { id: 'won', label: 'Won', color: 'border-t-green-500' },
  { id: 'lost', label: 'Lost', color: 'border-t-slate-400' },
];

export default function AppPipeline() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [leads, setLeads] = useState<Lead[]>([]);
  const [loading, setLoading] = useState(true);
  const [draggedLead, setDraggedLead] = useState<Lead | null>(null);

  useEffect(() => {
    if (user) fetchLeads();
  }, [user]);

  const fetchLeads = async () => {
    try {
      const res = await client.entities.leads.query({ query: {}, limit: 200 });
      setLeads(res.data?.items || []);
    } catch (err) {
      console.error('Failed to fetch leads:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleDrop = async (stageId: string) => {
    if (!draggedLead || draggedLead.pipeline_stage === stageId) {
      setDraggedLead(null);
      return;
    }
    try {
      await client.entities.leads.update({
        id: String(draggedLead.id),
        data: { pipeline_stage: stageId },
      });
      setLeads(leads.map(l => l.id === draggedLead.id ? { ...l, pipeline_stage: stageId } : l));
      toast.success(`Moved to ${stages.find(s => s.id === stageId)?.label}`);
    } catch (err) {
      toast.error('Failed to update stage');
    } finally {
      setDraggedLead(null);
    }
  };

  if (loading) {
    return (
      <AppShell>
        <div className="space-y-4">
          <Skeleton className="h-8 w-48" />
          <div className="grid grid-cols-5 gap-4">
            {[...Array(5)].map((_, i) => <Skeleton key={i} className="h-96 rounded-xl" />)}
          </div>
        </div>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Pipeline</h1>
          <p className="text-sm text-slate-500">Drag leads between stages to update their status</p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-5 gap-4 min-h-[500px]">
          {stages.map((stage) => {
            const stageLeads = leads.filter(l => l.pipeline_stage === stage.id);
            return (
              <div
                key={stage.id}
                className={cn('rounded-xl border border-slate-200 bg-slate-50/50 p-3 border-t-4', stage.color)}
                onDragOver={(e) => e.preventDefault()}
                onDrop={() => handleDrop(stage.id)}
              >
                <div className="flex items-center justify-between mb-3">
                  <h3 className="text-xs font-semibold text-slate-700 uppercase tracking-wide">{stage.label}</h3>
                  <Badge variant="secondary" className="text-xs bg-white">{stageLeads.length}</Badge>
                </div>
                <div className="space-y-2">
                  {stageLeads.map((lead) => (
                    <Card
                      key={lead.id}
                      className="border-slate-200 cursor-grab active:cursor-grabbing hover:border-indigo-200 transition-colors"
                      draggable
                      onDragStart={() => setDraggedLead(lead)}
                      onClick={() => navigate(`/app/leads/${lead.id}`)}
                    >
                      <CardContent className="p-3">
                        <p className="text-sm font-medium text-slate-900 truncate">{lead.business_name}</p>
                        <p className="text-xs text-slate-500 truncate">{lead.category}</p>
                        <div className="flex items-center justify-between mt-2">
                          <span className="text-xs text-slate-400">{lead.location}</span>
                          <Badge variant="outline" className={cn('text-[10px]',
                            lead.priority === 'high' ? 'border-red-200 text-red-600' :
                            lead.priority === 'medium' ? 'border-amber-200 text-amber-600' :
                            'border-slate-200 text-slate-500'
                          )}>
                            {lead.priority}
                          </Badge>
                        </div>
                      </CardContent>
                    </Card>
                  ))}
                  {stageLeads.length === 0 && (
                    <p className="text-xs text-slate-400 text-center py-4">No leads</p>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </AppShell>
  );
}