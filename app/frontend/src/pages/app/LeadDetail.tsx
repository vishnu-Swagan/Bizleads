import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import AppShell from '@/components/AppShell';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Skeleton } from '@/components/ui/skeleton';
import { client } from '@/lib/api';
import { toast } from 'sonner';
import { ArrowLeft, Globe, Mail, Phone, Save, Plus } from 'lucide-react';
import { cn } from '@/lib/utils';
import { getDataSourceBadge } from './Leads';

interface Lead {
  id: number;
  business_name: string;
  category: string;
  location: string;
  country: string;
  website_url: string;
  website_score: number;
  social_score: number;
  has_website: boolean;
  contact_email: string;
  contact_phone: string;
  pipeline_stage: string;
  priority: string;
  notes_count: number;
  last_contacted: string;
  data_source?: string | null;
}

interface Note {
  id: number;
  content: string;
  created_at: string;
}

const stages = ['new_lead', 'contacted', 'in_progress', 'won', 'lost'];
const stageLabels: Record<string, string> = {
  new_lead: 'New Lead', contacted: 'Contacted', in_progress: 'In Progress', won: 'Won', lost: 'Lost',
};

export default function AppLeadDetail() {
  const { id } = useParams();
  const { user } = useAuth();
  const navigate = useNavigate();
  const [lead, setLead] = useState<Lead | null>(null);
  const [notes, setNotes] = useState<Note[]>([]);
  const [loading, setLoading] = useState(true);
  const [newNote, setNewNote] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (user && id) fetchLead();
  }, [user, id]);

  const fetchLead = async () => {
    try {
      const res = await client.entities.leads.get({ id: id! });
      setLead(res.data);
      const notesRes = await client.entities.lead_notes.query({ query: { lead_id: parseInt(id!) }, sort: '-created_at' });
      setNotes(notesRes.data?.items || []);
    } catch (err) {
      console.error('Failed to fetch lead:', err);
      toast.error('Lead not found');
    } finally {
      setLoading(false);
    }
  };

  const updateStage = async (stage: string) => {
    if (!lead) return;
    try {
      await client.entities.leads.update({ id: String(lead.id), data: { pipeline_stage: stage } });
      setLead({ ...lead, pipeline_stage: stage });
      toast.success(`Stage updated to ${stageLabels[stage]}`);
    } catch (err) {
      toast.error('Failed to update stage');
    }
  };

  const updatePriority = async (priority: string) => {
    if (!lead) return;
    try {
      await client.entities.leads.update({ id: String(lead.id), data: { priority } });
      setLead({ ...lead, priority });
      toast.success('Priority updated');
    } catch (err) {
      toast.error('Failed to update priority');
    }
  };

  const addNote = async () => {
    if (!lead || !newNote.trim()) return;
    setSaving(true);
    try {
      await client.entities.lead_notes.create({
        data: { lead_id: lead.id, content: newNote.trim() },
      });
      setNewNote('');
      const notesRes = await client.entities.lead_notes.query({ query: { lead_id: lead.id }, sort: '-created_at' });
      setNotes(notesRes.data?.items || []);
      toast.success('Note added');
    } catch (err) {
      toast.error('Failed to add note');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <AppShell>
        <div className="space-y-4">
          <Skeleton className="h-8 w-48" />
          <Skeleton className="h-64 rounded-xl" />
        </div>
      </AppShell>
    );
  }

  if (!lead) {
    return (
      <AppShell>
        <div className="text-center py-12">
          <p className="text-slate-600">Lead not found</p>
          <Button onClick={() => navigate('/app/leads')} className="mt-4">Back to Leads</Button>
        </div>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <div className="space-y-6">
        {/* Header */}
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="icon" onClick={() => navigate('/app/leads')}>
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <div className="flex-1">
            <div className="flex items-center gap-2">
              <h1 className="text-xl font-bold text-slate-900">{lead.business_name}</h1>
              {(() => {
                const badge = getDataSourceBadge(lead?.data_source);
                return (
                  <Badge variant="outline" className={cn('text-xs', badge.className)} title={badge.title}>
                    {badge.label}
                  </Badge>
                );
              })()}
            </div>
            <p className="text-sm text-slate-500">{lead.category} · {lead.location}, {lead.country}</p>
          </div>
        </div>

        <Tabs defaultValue="overview" className="space-y-4">
          <TabsList className="bg-slate-100">
            <TabsTrigger value="overview">Overview</TabsTrigger>
            <TabsTrigger value="evidence">Evidence</TabsTrigger>
            <TabsTrigger value="contacts">Contacts</TabsTrigger>
            <TabsTrigger value="notes">Notes</TabsTrigger>
          </TabsList>

          <TabsContent value="overview" className="space-y-4">
            <div className="grid gap-4 md:grid-cols-2">
              {/* Pipeline */}
              <Card className="border-slate-200">
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm font-medium text-slate-600">Pipeline Stage</CardTitle>
                </CardHeader>
                <CardContent>
                  <Select value={lead.pipeline_stage} onValueChange={updateStage}>
                    <SelectTrigger className="border-slate-200">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {stages.map((s) => <SelectItem key={s} value={s}>{stageLabels[s]}</SelectItem>)}
                    </SelectContent>
                  </Select>
                  <div className="flex gap-1 mt-3">
                    {stages.map((s) => (
                      <div
                        key={s}
                        className={cn(
                          'h-1.5 flex-1 rounded-full',
                          stages.indexOf(s) <= stages.indexOf(lead.pipeline_stage)
                            ? 'bg-indigo-600'
                            : 'bg-slate-200'
                        )}
                      />
                    ))}
                  </div>
                </CardContent>
              </Card>

              {/* Priority */}
              <Card className="border-slate-200">
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm font-medium text-slate-600">Priority</CardTitle>
                </CardHeader>
                <CardContent>
                  <Select value={lead.priority} onValueChange={updatePriority}>
                    <SelectTrigger className="border-slate-200"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="high">High</SelectItem>
                      <SelectItem value="medium">Medium</SelectItem>
                      <SelectItem value="low">Low</SelectItem>
                    </SelectContent>
                  </Select>
                </CardContent>
              </Card>
            </div>

            {/* Digital Presence */}
            <Card className="border-slate-200">
              <CardHeader className="pb-3">
                <CardTitle className="text-sm font-medium text-slate-600">Digital Presence</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-slate-600">Website</span>
                  <div className="flex items-center gap-2">
                    {lead.has_website ? (
                      <>
                        <span className="text-sm font-medium">{lead.website_score}/100</span>
                        {lead.website_url && (
                          <a href={lead.website_url} target="_blank" rel="noopener noreferrer" className="text-indigo-600 hover:underline text-xs">
                            Visit
                          </a>
                        )}
                      </>
                    ) : (
                      <Badge variant="outline" className="text-xs bg-red-50 text-red-700 border-red-200">No Website</Badge>
                    )}
                  </div>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-slate-600">Social Media</span>
                  <span className="text-sm font-medium">{lead.social_score}/100</span>
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="evidence" className="space-y-4">
            <Card className="border-slate-200">
              <CardContent className="p-5">
                <p className="text-sm text-slate-500">
                  Evidence collection requires provider integrations. Configure providers in Settings → Integrations 
                  to enable website audits, screenshots, and detailed analysis.
                </p>
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="contacts" className="space-y-4">
            <Card className="border-slate-200">
              <CardContent className="p-5 space-y-3">
                {lead.contact_email && (
                  <div className="flex items-center gap-3">
                    <Mail className="h-4 w-4 text-slate-400" />
                    <span className="text-sm text-slate-700">{lead.contact_email}</span>
                  </div>
                )}
                {lead.contact_phone && (
                  <div className="flex items-center gap-3">
                    <Phone className="h-4 w-4 text-slate-400" />
                    <span className="text-sm text-slate-700">{lead.contact_phone}</span>
                  </div>
                )}
                {!lead.contact_email && !lead.contact_phone && (
                  <p className="text-sm text-slate-500">No contact information available.</p>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="notes" className="space-y-4">
            <Card className="border-slate-200">
              <CardContent className="p-5">
                <Textarea
                  placeholder="Add a note..."
                  value={newNote}
                  onChange={(e) => setNewNote(e.target.value)}
                  className="border-slate-200 mb-3"
                  rows={3}
                />
                <Button onClick={addNote} disabled={saving || !newNote.trim()} size="sm" className="bg-indigo-600 hover:bg-indigo-700 gap-2">
                  <Plus className="h-3.5 w-3.5" />
                  {saving ? 'Saving...' : 'Add Note'}
                </Button>
              </CardContent>
            </Card>

            {notes.length > 0 ? (
              <div className="space-y-2">
                {notes.map((note) => (
                  <Card key={note.id} className="border-slate-200">
                    <CardContent className="p-4">
                      <p className="text-sm text-slate-700 whitespace-pre-wrap">{note.content}</p>
                      <p className="text-xs text-slate-400 mt-2">
                        {new Date(note.created_at).toLocaleDateString()}
                      </p>
                    </CardContent>
                  </Card>
                ))}
              </div>
            ) : (
              <p className="text-sm text-slate-500 text-center py-4">No notes yet</p>
            )}
          </TabsContent>
        </Tabs>
      </div>
    </AppShell>
  );
}