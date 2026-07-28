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
import { ArrowLeft, Globe, Mail, Phone, MapPin, Save, Plus, Sparkles, Loader2 } from 'lucide-react';
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
  /** JSON-encoded Finding[] from services/site_signals.py, or null when this
   *  lead has never been qualified. Null and "[]" mean different things and
   *  must stay distinguishable — see parseFindings below. */
  findings?: string | null;
  qualified_at?: string | null;
  /** JSON-encoded string[] of platforms linked from the site. See parseSocialPlatforms. */
  social_platforms?: string | null;
  /** Street address from the provider; absent on leads saved before migration a2b7c9d4e6f1. */
  address?: string | null;
}

/**
 * Which social platforms the site links to, or null for "nobody has looked".
 *
 * Needs `qualifiedAt` as well as the column because `social_platforms` cannot
 * express the difference on its own: it defaults to '[]' and the save path
 * writes '[]' on create, so an untouched lead is byte-identical to one
 * measured as having no links. `qualified_at` is NULL until a measurement
 * runs, which is the only reliable signal that a page was ever read.
 *
 * Without this gate every un-qualified lead would report "no linked accounts
 * found" — an assertion about a business nobody has looked at.
 */
function parseSocialPlatforms(
  raw: string | null | undefined,
  qualifiedAt: string | null | undefined,
): string[] | null {
  if (!qualifiedAt) return null;
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.filter((p) => typeof p === 'string') : [];
  } catch {
    return [];
  }
}

/** GET /api/v1/outreach/ai/status. `model` names the provider actually in use. */
interface AiStatus {
  available: boolean;
  model: string | null;
}

/** An AI-written opening email held in memory only — never persisted here. */
interface AiPreview {
  subject: string;
  body_text: string;
}

/** One measured defect. `evidence` is the checkable detail behind `label`. */
interface Finding {
  id: string;
  label: string;
  penalty: number;
  evidence: string;
  category: string;
}

/**
 * Decode a lead's stored findings.
 *
 * Returns null for "never measured" and [] for "measured, nothing wrong" —
 * the backend is careful to keep those apart (routers/discover.py only writes
 * findings once a website_score was actually established, so that "[]" never
 * claims a lead was checked when it wasn't), and collapsing them here would
 * throw that distinction away at the last step.
 *
 * Malformed JSON counts as not measured rather than as a clean bill of
 * health. Guessing in this direction is the safe one: it prompts a re-run
 * instead of telling somebody a broken site passed every check.
 */
function parseFindings(raw: string | null | undefined): Finding[] | null {
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? (parsed as Finding[]) : null;
  } catch {
    return null;
  }
}

interface Note {
  id: number;
  content: string;
  created_at: string;
  /** 'ai_angle' marks the machine-written note; anything else is a human's. */
  note_type?: string | null;
}

/** Must match services/ai_writer.py::AI_ANGLE_NOTE_TYPE. */
const AI_ANGLE_NOTE_TYPE = 'ai_angle';

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

  // Outreach from this lead's own findings.
  const [aiStatus, setAiStatus] = useState<AiStatus | null>(null);
  const [preview, setPreview] = useState<AiPreview | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [drafting, setDrafting] = useState(false);
  const [queued, setQueued] = useState(false);
  const [suggesting, setSuggesting] = useState(false);

  useEffect(() => {
    if (user && id) fetchLead();
  }, [user, id]);

  useEffect(() => {
    if (!user) return;
    // Never assume available before this resolves — aiReady stays false until
    // the server has actually said so, so the button cannot appear and then
    // fail on click.
    client.apiCall
      .invoke({ url: '/api/v1/outreach/ai/status', method: 'GET', data: {} })
      .then((res) =>
        setAiStatus({
          available: res.data?.available === true,
          model: typeof res.data?.model === 'string' ? res.data.model : null,
        }),
      )
      .catch(() => setAiStatus({ available: false, model: null }));
  }, [user]);

  /**
   * Show what an AI-written opening email would say. Persists nothing.
   *
   * Deliberately separate from "Draft outreach" below, which writes to the
   * approval queue. Conflating the two would mean a click that looks like a
   * preview quietly creates something a human then has to find and discard.
   */
  const previewWithAi = async () => {
    if (!lead) return;
    setPreviewing(true);
    try {
      const res = await client.apiCall.invoke({
        url: '/api/v1/outreach/ai/draft',
        method: 'POST',
        data: { lead_id: lead.id, tone: 'professional' },
        options: { timeout: 60000 },
      });
      setPreview({ subject: res.data?.subject ?? '', body_text: res.data?.body_text ?? '' });
    } catch (err: any) {
      toast.error(err?.data?.detail ?? 'Could not write a preview');
    } finally {
      setPreviewing(false);
    }
  };

  /**
   * Write a draft for this lead into the approval queue.
   *
   * Uses /compose, the deterministic composer, which works whether or not a
   * wording provider is configured and costs no credits — the measurement was
   * already paid for at qualification. Wording help lives in Outreach, where
   * the draft can be polished or rewritten and then actually sent; there is no
   * second half-persisted AI path here.
   */
  /**
   * Write (or rewrite) the internal "how to win this lead" note.
   *
   * The server owns replace-not-stack, so this refetches the notes list
   * afterwards rather than splicing the response in locally — that way the
   * displayed note is the row that actually exists, not an optimistic guess
   * that could disagree with it.
   */
  const suggestAngle = async () => {
    if (!lead) return;
    setSuggesting(true);
    try {
      await client.apiCall.invoke({
        url: '/api/v1/outreach/ai/angle',
        method: 'POST',
        data: { lead_id: lead.id },
        options: { timeout: 60000 },
      });
      const notesRes = await client.entities.lead_notes.query({
        query: { lead_id: lead.id },
        sort: '-created_at',
      });
      setNotes(notesRes.data?.items || []);
      // A plain apostrophe: this is a JS string, not JSX, so an HTML entity
      // here would show up literally in the toast.
      toast.success("Angle written from this lead's findings.");
    } catch (err: any) {
      toast.error(err?.data?.detail ?? 'Could not write an angle');
    } finally {
      setSuggesting(false);
    }
  };

  const draftOutreach = async () => {
    if (!lead) return;
    setDrafting(true);
    try {
      const res = await client.apiCall.invoke({
        url: '/api/v1/outreach/compose',
        method: 'POST',
        data: { lead_ids: [lead.id] },
        options: { timeout: 60000 },
      });
      if ((res.data?.queued ?? 0) > 0) {
        setQueued(true);
        toast.success('Draft added to the approval queue.');
        return;
      }
      // A skipped lead is explained rather than reported as a silent success.
      // `message` is the human sentence ("No contact email on this lead");
      // `reason` beside it is a machine slug like "no_email" and must never
      // reach a toast.
      const skipped = res.data?.skipped?.[0];
      toast.error(skipped?.message ?? 'Nothing could be drafted for this lead.');
    } catch (err: any) {
      toast.error(err?.data?.detail ?? 'Could not draft outreach');
    } finally {
      setDrafting(false);
    }
  };

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

  // Computed after the !lead guard so these are plain values by render time.
  const findings = parseFindings(lead.findings);
  const qualifiedOn = lead.qualified_at
    ? new Date(lead.qualified_at).toLocaleDateString()
    : null;
  const socialPlatforms = parseSocialPlatforms(lead.social_platforms, lead.qualified_at);
  // The server keeps at most one angle note per lead, but take the first
  // rather than assuming exactly one — a stale duplicate should render as one
  // note, not crash the tab.
  const angleNote = notes.find((n) => n.note_type === AI_ANGLE_NOTE_TYPE) ?? null;
  const humanNotes = notes.filter((n) => n.note_type !== AI_ANGLE_NOTE_TYPE);

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
                {/* Was `{lead.social_score}/100`, which rendered as a bare
                    "/100" on every lead: social_score is only ever written by
                    services/google_places.py, which is not wired up, so it is
                    NULL for everything the live provider returns.
                    A follower or engagement score would need platform APIs
                    this product does not have. What it CAN measure, from the
                    page it already fetched, is which platforms the site links
                    to — so that is what it now reports. */}
                <div className="flex items-start justify-between gap-3">
                  <span className="text-sm text-slate-600 shrink-0">Social Media</span>
                  <div className="flex flex-wrap justify-end gap-1.5">
                    {socialPlatforms === null ? (
                      <span className="text-sm text-slate-400">Not measured yet</span>
                    ) : socialPlatforms.length === 0 ? (
                      <span className="text-sm text-slate-500">No linked accounts found</span>
                    ) : (
                      socialPlatforms.map((platform) => (
                        <Badge key={platform} variant="outline" className="text-xs capitalize">
                          {platform}
                        </Badge>
                      ))
                    )}
                  </div>
                </div>
                {socialPlatforms !== null && socialPlatforms.length === 0 && (
                  <p className="text-xs text-slate-400">
                    Nothing on the site links to Facebook, Instagram, LinkedIn, X, TikTok or
                    YouTube — itself worth raising with them.
                  </p>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="evidence" className="space-y-4">
            <Card className="border-slate-200">
              <CardContent className="p-5">
                {findings === null ? (
                  <>
                    <p className="text-sm text-slate-700 font-medium">Not measured yet</p>
                    <p className="text-sm text-slate-500 mt-1">
                      Run <span className="font-medium">Qualify</span> on this lead from the Leads page to
                      measure its site. That costs one credit and produces the specific, checkable problems
                      you can quote back to the business.
                    </p>
                  </>
                ) : findings.length === 0 ? (
                  <>
                    <p className="text-sm text-slate-700 font-medium">Measured — nothing wrong found</p>
                    <p className="text-sm text-slate-500 mt-1">
                      This site passed every check{qualifiedOn ? ` when it was measured on ${qualifiedOn}` : ''}.
                      There is no defect to pitch, which is a finding in itself.
                    </p>
                  </>
                ) : (
                  <>
                    <div className="flex items-baseline justify-between gap-3 mb-4">
                      <p className="text-sm font-medium text-slate-700">
                        {findings.length} issue{findings.length === 1 ? '' : 's'} measured on this site
                      </p>
                      {qualifiedOn && (
                        <span className="text-xs text-slate-500 shrink-0">Measured {qualifiedOn}</span>
                      )}
                    </div>
                    <ul className="space-y-3">
                      {findings.map((finding, i) => (
                        <li
                          key={finding.id || i}
                          className="rounded-lg border border-slate-200 p-3"
                        >
                          <div className="flex items-start justify-between gap-3">
                            <p className="text-sm font-medium text-slate-800">{finding.label}</p>
                            {finding.category && (
                              <Badge variant="outline" className="text-xs shrink-0 capitalize">
                                {finding.category}
                              </Badge>
                            )}
                          </div>
                          {/* The evidence string is the whole point: it is what
                              makes the claim checkable by the prospect, so it is
                              shown verbatim rather than summarised. */}
                          {finding.evidence && (
                            <p className="text-xs text-slate-500 mt-1.5">{finding.evidence}</p>
                          )}
                        </li>
                      ))}
                    </ul>
                    <p className="text-xs text-slate-400 mt-4">
                      Every line above was measured from the live site. Outreach drafted for this lead
                      cites only these findings.
                    </p>
                  </>
                )}
              </CardContent>
            </Card>

            {/* Turning evidence into outreach, at the moment somebody is
                looking at the evidence. Only rendered when there is something
                honest to write from — with no findings there is no email, the
                same rule the composer and the model both work under. */}
            {findings !== null && findings.length > 0 && (
              <Card className="border-slate-200">
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm font-medium text-slate-700">
                    Turn this into outreach
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div className="flex flex-wrap gap-2">
                    <Button onClick={draftOutreach} disabled={drafting} size="sm">
                      {drafting ? (
                        <Loader2 className="h-4 w-4 mr-1.5 animate-spin" />
                      ) : (
                        <Save className="h-4 w-4 mr-1.5" />
                      )}
                      Draft outreach
                    </Button>

                    {/* Only offered once the server has confirmed a provider.
                        aiStatus === null means "not asked yet", which is not
                        the same as unavailable. */}
                    {aiStatus?.available && (
                      <Button
                        onClick={previewWithAi}
                        disabled={previewing}
                        size="sm"
                        variant="outline"
                      >
                        {previewing ? (
                          <Loader2 className="h-4 w-4 mr-1.5 animate-spin" />
                        ) : (
                          <Sparkles className="h-4 w-4 mr-1.5" />
                        )}
                        Preview with AI
                      </Button>
                    )}
                  </div>

                  {queued && (
                    <p className="text-sm text-slate-600">
                      Drafted and waiting for your approval.{' '}
                      <button
                        onClick={() => navigate('/app/automations')}
                        className="text-indigo-600 hover:underline font-medium"
                      >
                        Review in Outreach
                      </button>{' '}
                      — nothing sends until you approve it.
                    </p>
                  )}

                  {preview && (
                    <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
                      <div className="flex items-start justify-between gap-3">
                        <p className="text-sm font-medium text-slate-800">{preview.subject}</p>
                        <Badge variant="outline" className="text-xs shrink-0">
                          Preview
                        </Badge>
                      </div>
                      <p className="text-sm text-slate-600 mt-2 whitespace-pre-wrap">
                        {preview.body_text}
                      </p>
                      <p className="text-xs text-slate-400 mt-3">
                        Written from the findings above and nothing else. Not saved — use
                        Draft outreach to put a draft in the approval queue.
                      </p>
                    </div>
                  )}

                  <p className="text-xs text-slate-400">
                    {aiStatus?.available
                      ? `Wording help is on${aiStatus.model ? ` (${aiStatus.model})` : ''}. It rewrites how the email reads and never adds a claim that isn't measured above.`
                      : 'Drafts are written from the measured findings above.'}
                  </p>
                </CardContent>
              </Card>
            )}
          </TabsContent>

          <TabsContent value="contacts" className="space-y-4">
            <Card className="border-slate-200">
              <CardContent className="p-5 space-y-3">
                {lead.contact_email && (
                  <div className="flex items-center gap-3">
                    <Mail className="h-4 w-4 text-slate-400" />
                    <a
                      href={`mailto:${lead.contact_email}`}
                      className="text-sm text-slate-700 hover:text-indigo-600"
                    >
                      {lead.contact_email}
                    </a>
                  </div>
                )}
                {lead.contact_phone && (
                  <div className="flex items-center gap-3">
                    <Phone className="h-4 w-4 text-slate-400" />
                    <a href={`tel:${lead.contact_phone}`} className="text-sm text-slate-700 hover:text-indigo-600">
                      {lead.contact_phone}
                    </a>
                  </div>
                )}
                {/* The provider returns a street address on every POI and it
                    was discarded until the `address` column existed. Leads
                    saved before that migration have none and cannot have one
                    reconstructed — re-running Discover populates it. */}
                {lead.address && (
                  <div className="flex items-start gap-3">
                    <MapPin className="h-4 w-4 text-slate-400 mt-0.5 shrink-0" />
                    <span className="text-sm text-slate-700">{lead.address}</span>
                  </div>
                )}
                {!lead.contact_email && !lead.contact_phone && !lead.address && (
                  <p className="text-sm text-slate-500">No contact information available.</p>
                )}
                {!lead.contact_email && (lead.contact_phone || lead.address) && (
                  <p className="text-xs text-slate-400 pt-1">
                    No email address found on their site. Outreach cannot be drafted without
                    one — add it here if you find it another way.
                  </p>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="notes" className="space-y-4">
            {/* The machine-written angle is separated from the human notes
                below rather than sorted in among them. It is generated
                automatically on Qualify and replaced on every re-run, so a
                reader has to be able to tell at a glance which note nobody
                typed — and which one will be overwritten. */}
            <Card className={cn('border-slate-200', angleNote && 'border-indigo-200 bg-indigo-50/40')}>
              <CardHeader className="pb-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <CardTitle className="text-sm font-medium text-slate-700 flex items-center gap-1.5">
                    <Sparkles className="h-4 w-4 text-indigo-600" />
                    How to win this lead
                  </CardTitle>
                  {aiStatus?.available && findings !== null && findings.length > 0 && (
                    <Button onClick={suggestAngle} disabled={suggesting} size="sm" variant="outline">
                      {suggesting ? (
                        <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" />
                      ) : (
                        <Sparkles className="h-3.5 w-3.5 mr-1.5" />
                      )}
                      {angleNote ? 'Regenerate' : 'Suggest an angle'}
                    </Button>
                  )}
                </div>
              </CardHeader>
              <CardContent>
                {angleNote ? (
                  <>
                    <p className="text-sm text-slate-700 whitespace-pre-wrap">
                      {angleNote.content}
                    </p>
                    <p className="text-xs text-slate-400 mt-3">
                      Written from this lead&rsquo;s measured findings only. Regenerating
                      replaces it; your own notes below are never touched.
                    </p>
                  </>
                ) : findings === null || findings.length === 0 ? (
                  <p className="text-sm text-slate-500">
                    Qualify this lead first. With nothing measured there is no honest angle to
                    suggest, so none is invented.
                  </p>
                ) : aiStatus?.available ? (
                  <p className="text-sm text-slate-500">
                    No angle written yet — use Suggest an angle above.
                  </p>
                ) : (
                  <p className="text-sm text-slate-500">
                    Wording help is unavailable right now. The measured findings on the
                    Evidence tab are unaffected.
                  </p>
                )}
              </CardContent>
            </Card>

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

            {humanNotes.length > 0 ? (
              <div className="space-y-2">
                {humanNotes.map((note) => (
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