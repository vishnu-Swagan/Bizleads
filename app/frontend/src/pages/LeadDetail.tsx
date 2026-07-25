import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import AppLayout from '@/components/AppLayout';
import { client } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Skeleton } from '@/components/ui/skeleton';
import { toast } from 'sonner';
import {
  ArrowLeft, Globe, Mail, Phone, MapPin, Building2,
  ExternalLink, Wifi, WifiOff, Save, Trash2, Plus,
  MessageSquare, PhoneCall, Calendar
} from 'lucide-react';

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
  social_platforms: string;
  contact_email: string;
  contact_phone: string;
  pipeline_stage: string;
  priority: string;
  notes_count: number;
  last_contacted: string;
  created_at: string;
  updated_at: string;
}

interface Note {
  id: number;
  lead_id: number;
  content: string;
  note_type: string;
  created_at: string;
}

const STAGE_OPTIONS = [
  { value: 'new_lead', label: 'New Lead' },
  { value: 'contacted', label: 'Contacted' },
  { value: 'in_progress', label: 'In Progress' },
  { value: 'won', label: 'Won' },
  { value: 'lost', label: 'Lost' },
];

const PRIORITY_OPTIONS = [
  { value: 'low', label: 'Low' },
  { value: 'medium', label: 'Medium' },
  { value: 'high', label: 'High' },
];

const NOTE_TYPE_ICONS: Record<string, React.ElementType> = {
  note: MessageSquare,
  call: PhoneCall,
  email: Mail,
  meeting: Calendar,
};

export default function LeadDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { user, loading: authLoading } = useAuth();
  const [lead, setLead] = useState<Lead | null>(null);
  const [notes, setNotes] = useState<Note[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [newNote, setNewNote] = useState('');
  const [noteType, setNoteType] = useState('note');
  const [addingNote, setAddingNote] = useState(false);

  useEffect(() => {
    if (user && id) {
      fetchLead();
      fetchNotes();
    }
  }, [user, id]);

  const fetchLead = async () => {
    try {
      setLoading(true);
      const response = await client.entities.leads.get({ id: id! });
      setLead(response.data);
    } catch (err) {
      console.error('Failed to fetch lead:', err);
      toast.error('Lead not found');
      navigate('/dashboard');
    } finally {
      setLoading(false);
    }
  };

  const fetchNotes = async () => {
    try {
      const response = await client.entities.lead_notes.query({
        query: { lead_id: Number(id) },
        sort: '-created_at',
        limit: 50,
      });
      setNotes(response.data?.items || []);
    } catch (err) {
      console.error('Failed to fetch notes:', err);
    }
  };

  const updateLead = async (field: string, value: string) => {
    if (!lead) return;
    setSaving(true);
    try {
      const response = await client.entities.leads.update({
        id: String(lead.id),
        data: { [field]: value },
      });
      setLead(response.data);
      toast.success('Lead updated');
    } catch (err) {
      console.error('Failed to update lead:', err);
      toast.error('Failed to update lead');
    } finally {
      setSaving(false);
    }
  };

  const addNote = async () => {
    if (!newNote.trim() || !lead) return;
    setAddingNote(true);
    try {
      await client.entities.lead_notes.create({
        data: {
          lead_id: lead.id,
          content: newNote.trim(),
          note_type: noteType,
        },
      });
      setNewNote('');
      setNoteType('note');
      fetchNotes();
      // Update notes count
      await client.entities.leads.update({
        id: String(lead.id),
        data: { notes_count: (lead.notes_count || 0) + 1 },
      });
      toast.success('Note added');
    } catch (err) {
      console.error('Failed to add note:', err);
      toast.error('Failed to add note');
    } finally {
      setAddingNote(false);
    }
  };

  const deleteLead = async () => {
    if (!lead) return;
    if (!confirm('Are you sure you want to delete this lead?')) return;
    try {
      await client.entities.leads.delete({ id: String(lead.id) });
      toast.success('Lead deleted');
      navigate('/dashboard');
    } catch (err) {
      console.error('Failed to delete lead:', err);
      toast.error('Failed to delete lead');
    }
  };

  if (authLoading || loading) {
    return (
      <AppLayout>
        <div className="space-y-6">
          <Skeleton className="h-8 w-48" />
          <div className="grid gap-6 lg:grid-cols-3">
            <div className="lg:col-span-2 space-y-4">
              <Skeleton className="h-64 rounded-xl" />
              <Skeleton className="h-48 rounded-xl" />
            </div>
            <Skeleton className="h-80 rounded-xl" />
          </div>
        </div>
      </AppLayout>
    );
  }

  if (!lead) {
    return (
      <AppLayout>
        <div className="flex flex-col items-center py-20 text-center">
          <Globe className="mb-4 h-12 w-12 text-muted-foreground" />
          <p className="text-muted-foreground">Lead not found</p>
          <Button onClick={() => navigate('/dashboard')} variant="outline" className="mt-4">
            Back to Dashboard
          </Button>
        </div>
      </AppLayout>
    );
  }

  const socialPlatforms = (() => {
    try {
      return JSON.parse(lead.social_platforms || '[]');
    } catch {
      return [];
    }
  })();

  const getScoreColor = (score: number) => {
    if (score === 0) return 'text-red-500';
    if (score < 25) return 'text-orange-500';
    if (score < 50) return 'text-yellow-500';
    return 'text-green-500';
  };

  return (
    <AppLayout>
      <div className="space-y-6">
        {/* Back button & Header */}
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-3">
            <Button variant="ghost" size="icon" onClick={() => navigate('/dashboard')}>
              <ArrowLeft className="h-5 w-5" />
            </Button>
            <div>
              <h1 className="font-[Poppins] text-2xl font-bold text-foreground">{lead.business_name}</h1>
              <p className="text-sm text-muted-foreground">{lead.category} • {lead.location}</p>
            </div>
          </div>
          <Button variant="destructive" size="sm" onClick={deleteLead} className="gap-2">
            <Trash2 className="h-4 w-4" />
            Delete Lead
          </Button>
        </div>

        <div className="grid gap-6 lg:grid-cols-3">
          {/* Main Content */}
          <div className="space-y-6 lg:col-span-2">
            {/* Business Info */}
            <Card>
              <CardHeader>
                <CardTitle className="font-[Poppins] text-lg">Business Information</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid gap-4 sm:grid-cols-2">
                  <InfoRow icon={Building2} label="Category" value={lead.category} />
                  <InfoRow icon={MapPin} label="Location" value={lead.location} />
                  <InfoRow icon={Mail} label="Email" value={lead.contact_email || 'Not available'} />
                  <InfoRow icon={Phone} label="Phone" value={lead.contact_phone || 'Not available'} />
                </div>

                {/* Website Info */}
                <div className="rounded-lg border border-border p-4">
                  <div className="flex items-center gap-2 mb-3">
                    {lead.has_website ? (
                      <Wifi className="h-4 w-4 text-yellow-500" />
                    ) : (
                      <WifiOff className="h-4 w-4 text-red-500" />
                    )}
                    <span className="font-medium text-sm">
                      {lead.has_website ? 'Has Website' : 'No Website'}
                    </span>
                  </div>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <div>
                      <p className="text-xs text-muted-foreground">Website Score</p>
                      <p className={`text-lg font-bold ${getScoreColor(lead.website_score)}`}>
                        {lead.website_score}/100
                      </p>
                    </div>
                    <div>
                      <p className="text-xs text-muted-foreground">Social Score</p>
                      <p className={`text-lg font-bold ${getScoreColor(lead.social_score)}`}>
                        {lead.social_score}/100
                      </p>
                    </div>
                  </div>
                  {lead.website_url && (
                    <a
                      href={lead.website_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="mt-3 inline-flex items-center gap-1 text-sm text-primary hover:underline"
                    >
                      <ExternalLink className="h-3 w-3" />
                      {lead.website_url}
                    </a>
                  )}
                  {socialPlatforms.length > 0 && (
                    <div className="mt-3 flex flex-wrap gap-1.5">
                      {socialPlatforms.map((platform: string) => (
                        <Badge key={platform} variant="secondary" className="text-xs capitalize">
                          {platform}
                        </Badge>
                      ))}
                    </div>
                  )}
                </div>
              </CardContent>
            </Card>

            {/* Notes */}
            <Card>
              <CardHeader>
                <CardTitle className="font-[Poppins] text-lg">Notes & Activity</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                {/* Add Note */}
                <div className="space-y-3 rounded-lg border border-border p-4">
                  <div className="flex gap-2">
                    <Select value={noteType} onValueChange={setNoteType}>
                      <SelectTrigger className="w-32">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="note">Note</SelectItem>
                        <SelectItem value="call">Call</SelectItem>
                        <SelectItem value="email">Email</SelectItem>
                        <SelectItem value="meeting">Meeting</SelectItem>
                      </SelectContent>
                    </Select>
                    <Button onClick={addNote} disabled={addingNote || !newNote.trim()} size="sm" className="gap-1">
                      <Plus className="h-4 w-4" />
                      Add
                    </Button>
                  </div>
                  <Textarea
                    placeholder="Add a note about this lead..."
                    value={newNote}
                    onChange={(e) => setNewNote(e.target.value)}
                    rows={3}
                  />
                </div>

                {/* Notes List */}
                {notes.length === 0 ? (
                  <p className="py-4 text-center text-sm text-muted-foreground">
                    No notes yet. Add your first note above.
                  </p>
                ) : (
                  <div className="space-y-3">
                    {notes.map((note) => {
                      const NoteIcon = NOTE_TYPE_ICONS[note.note_type] || MessageSquare;
                      return (
                        <div key={note.id} className="flex gap-3 rounded-lg border border-border p-3">
                          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-muted">
                            <NoteIcon className="h-4 w-4 text-muted-foreground" />
                          </div>
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2">
                              <Badge variant="outline" className="text-[10px] capitalize">
                                {note.note_type}
                              </Badge>
                              <span className="text-xs text-muted-foreground">
                                {new Date(note.created_at).toLocaleDateString()}
                              </span>
                            </div>
                            <p className="mt-1 text-sm text-foreground whitespace-pre-wrap">{note.content}</p>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </CardContent>
            </Card>
          </div>

          {/* Sidebar - Pipeline & Priority */}
          <div className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle className="font-[Poppins] text-lg">Pipeline Status</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-1.5">
                  <Label className="text-sm font-medium">Stage</Label>
                  <Select
                    value={lead.pipeline_stage}
                    onValueChange={(val) => updateLead('pipeline_stage', val)}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {STAGE_OPTIONS.map((opt) => (
                        <SelectItem key={opt.value} value={opt.value}>{opt.label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-1.5">
                  <Label className="text-sm font-medium">Priority</Label>
                  <Select
                    value={lead.priority}
                    onValueChange={(val) => updateLead('priority', val)}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {PRIORITY_OPTIONS.map((opt) => (
                        <SelectItem key={opt.value} value={opt.value}>{opt.label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                {saving && (
                  <p className="text-xs text-muted-foreground flex items-center gap-1">
                    <Save className="h-3 w-3 animate-spin" />
                    Saving...
                  </p>
                )}
              </CardContent>
            </Card>

            {/* Quick Stats */}
            <Card>
              <CardHeader>
                <CardTitle className="font-[Poppins] text-lg">Quick Stats</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="flex justify-between text-sm">
                  <span className="text-muted-foreground">Website Score</span>
                  <span className={`font-medium ${getScoreColor(lead.website_score)}`}>
                    {lead.website_score}/100
                  </span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-muted-foreground">Social Score</span>
                  <span className={`font-medium ${getScoreColor(lead.social_score)}`}>
                    {lead.social_score}/100
                  </span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-muted-foreground">Notes</span>
                  <span className="font-medium">{notes.length}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-muted-foreground">Added</span>
                  <span className="font-medium">
                    {new Date(lead.created_at).toLocaleDateString()}
                  </span>
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    </AppLayout>
  );
}

function InfoRow({ icon: Icon, label, value }: { icon: React.ElementType; label: string; value: string }) {
  return (
    <div className="flex items-center gap-3">
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-muted">
        <Icon className="h-4 w-4 text-muted-foreground" />
      </div>
      <div className="min-w-0">
        <p className="text-xs text-muted-foreground">{label}</p>
        <p className="truncate text-sm font-medium text-foreground">{value}</p>
      </div>
    </div>
  );
}