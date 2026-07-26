import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import AppShell from '@/components/AppShell';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { client } from '@/lib/api';
import { Search, Download, ChevronRight, AlertCircle, Gauge, Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';

interface Lead {
  id: number;
  business_name: string;
  category: string;
  location: string;
  country: string;
  // Null means nobody has measured this lead yet — distinct from a measured
  // zero, and from has_website: false, which is a verdict Qualify reached.
  // The rendering below already keeps the three states apart; these types
  // now say so, instead of describing a payload the API never sends.
  website_score: number | null;
  social_score: number | null;
  has_website: boolean | null;
  pipeline_stage: string;
  priority: string;
  contact_email: string;
  created_at: string;
  data_source?: string | null;
}

const stageLabels: Record<string, string> = {
  new_lead: 'New',
  contacted: 'Contacted',
  in_progress: 'In Progress',
  won: 'Won',
  lost: 'Lost',
};

const stageBadgeClass: Record<string, string> = {
  new_lead: 'bg-blue-50 text-blue-700 border-blue-200',
  contacted: 'bg-purple-50 text-purple-700 border-purple-200',
  in_progress: 'bg-amber-50 text-amber-700 border-amber-200',
  won: 'bg-green-50 text-green-700 border-green-200',
  lost: 'bg-slate-50 text-slate-500 border-slate-200',
};

const dataSourceBadge: Record<string, { label: string; className: string; title: string }> = {
  provider: {
    label: 'Verified source',
    className: 'bg-green-50 text-green-700 border-green-200',
    title: 'Sourced from a connected data provider.',
  },
  manual: {
    label: 'Added manually',
    className: 'bg-slate-50 text-slate-700 border-slate-200',
    title: 'Entered by a team member.',
  },
  ai_generated: {
    label: 'AI-generated — unverified',
    className: 'bg-red-50 text-red-700 border-red-200',
    title: 'Produced by an AI model. This business may not exist. Verify before contacting.',
  },
  mock: {
    label: 'Sample data',
    className: 'bg-slate-50 text-slate-400 border-slate-200',
    title: 'Seeded demo record, not a real business.',
  },
};

const unverifiedBadge = {
  label: 'Unverified',
  className: 'bg-amber-50 text-amber-700 border-amber-200',
  title: 'Origin unknown — this lead predates provenance tracking. Verify before contacting.',
};

export function getDataSourceBadge(source?: string | null) {
  return (source && dataSourceBadge[source]) || unverifiedBadge;
}

export default function AppLeads() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [leads, setLeads] = useState<Lead[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [stageFilter, setStageFilter] = useState('all');
  const [priorityFilter, setPriorityFilter] = useState('all');
  const [qualifying, setQualifying] = useState<Set<number>>(new Set());

  /** A lead whose web presence has never been measured. */
  const isUnmeasured = (l: Lead) => l.website_score === null && l.has_website === null;

  /**
   * Pass 2. Measures the site behind each lead and ranks it.
   *
   * Costs one credit per lead because it does real work — a DNS lookup, an
   * HTTP fetch, and optionally a Lighthouse audit. The endpoint caps a batch
   * at 10, so the bulk action is chunked rather than sent as one large call.
   */
  const qualify = async (ids: number[]) => {
    if (!ids.length) return;
    setQualifying((prev) => new Set([...prev, ...ids]));

    try {
      const batches: number[][] = [];
      for (let i = 0; i < ids.length; i += 10) batches.push(ids.slice(i, i + 10));

      let measured = 0;
      let topFinding: string | null = null;

      for (const batch of batches) {
        const res = await client.apiCall.invoke({
          url: '/api/v1/discover/qualify',
          method: 'POST',
          data: { lead_ids: batch },
          options: { timeout: 120000 },
        });
        const qualified = res.data?.qualified ?? [];
        measured += qualified.length;
        for (const q of qualified) {
          if (!topFinding && q.findings?.length) {
            topFinding = `${q.business_name}: ${q.findings[0].label}`;
          }
        }
      }

      await fetchLeads();
      toast.success(
        `Measured ${measured} lead${measured === 1 ? '' : 's'}` +
          (topFinding ? ` · ${topFinding}` : ''),
      );
    } catch (err: any) {
      const detail = err?.data?.detail;
      if (detail?.error === 'insufficient_credits') {
        toast.error(detail.message);
      } else {
        toast.error(detail?.message ?? err?.message ?? 'Qualification failed');
      }
    } finally {
      setQualifying((prev) => {
        const next = new Set(prev);
        ids.forEach((id) => next.delete(id));
        return next;
      });
    }
  };

  useEffect(() => {
    if (user) fetchLeads();
  }, [user]);

  const fetchLeads = async () => {
    try {
      const res = await client.entities.leads.query({ query: {}, sort: '-created_at', limit: 200 });
      setLeads(res.data?.items || []);
    } catch (err) {
      console.error('Failed to fetch leads:', err);
    } finally {
      setLoading(false);
    }
  };

  const filtered = leads.filter((l) => {
    if (searchQuery && !l.business_name.toLowerCase().includes(searchQuery.toLowerCase())) return false;
    if (stageFilter !== 'all' && l.pipeline_stage !== stageFilter) return false;
    if (priorityFilter !== 'all' && l.priority !== priorityFilter) return false;
    return true;
  });

  const exportCSV = () => {
    const headers = ['Business Name', 'Category', 'Location', 'Country', 'Stage', 'Priority', 'Email'];
    const rows = filtered.map(l => [l.business_name, l.category, l.location, l.country, l.pipeline_stage, l.priority, l.contact_email]);
    const csv = [headers, ...rows].map(r => r.join(',')).join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'bizleads-export.csv';
    a.click();
    toast.success('Exported to CSV');
  };

  return (
    <AppShell>
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-slate-900">Leads</h1>
            <p className="text-sm text-slate-500">{leads.length} total leads in your workspace</p>
          </div>
          {leads.filter(isUnmeasured).length > 0 && (
            <Button
              variant="outline"
              size="sm"
              disabled={qualifying.size > 0}
              onClick={() => qualify(leads.filter(isUnmeasured).map((l) => l.id))}
              className="gap-2 border-indigo-200 text-indigo-700 cursor-pointer"
              title="Measure every lead that has never been checked (1 credit each)"
            >
              {qualifying.size > 0 ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Gauge className="h-4 w-4" />
              )}
              Qualify {leads.filter(isUnmeasured).length} unmeasured
            </Button>
          )}
          <Button variant="outline" size="sm" onClick={exportCSV} className="gap-2 border-slate-200">
            <Download className="h-4 w-4" />
            Export CSV
          </Button>
        </div>

        {/* Filters */}
        <Card className="border-slate-200">
          <CardContent className="p-4">
            <div className="flex flex-wrap gap-3">
              <div className="flex-1 min-w-[200px]">
                <Input
                  placeholder="Search leads..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="border-slate-200"
                />
              </div>
              <Select value={stageFilter} onValueChange={setStageFilter}>
                <SelectTrigger className="w-[140px] border-slate-200"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Stages</SelectItem>
                  {Object.entries(stageLabels).map(([k, v]) => <SelectItem key={k} value={k}>{v}</SelectItem>)}
                </SelectContent>
              </Select>
              <Select value={priorityFilter} onValueChange={setPriorityFilter}>
                <SelectTrigger className="w-[130px] border-slate-200"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Priority</SelectItem>
                  <SelectItem value="high">High</SelectItem>
                  <SelectItem value="medium">Medium</SelectItem>
                  <SelectItem value="low">Low</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </CardContent>
        </Card>

        {/* Table */}
        {loading ? (
          <div className="space-y-2">
            {[...Array(5)].map((_, i) => <Skeleton key={i} className="h-14 rounded-lg" />)}
          </div>
        ) : filtered.length === 0 ? (
          <div className="flex flex-col items-center py-12 text-center">
            <AlertCircle className="mb-3 h-10 w-10 text-slate-300" />
            <p className="text-slate-600 font-medium">No leads found</p>
            <p className="text-sm text-slate-500 mt-1">
              {leads.length === 0 ? 'Discover businesses and save them as leads.' : 'Try adjusting your filters.'}
            </p>
            {leads.length === 0 && (
              <Button onClick={() => navigate('/app/discover')} className="mt-4 bg-indigo-600 hover:bg-indigo-700">
                Discover Leads
              </Button>
            )}
          </div>
        ) : (
          <div className="rounded-lg border border-slate-200 overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow className="bg-slate-50">
                  <TableHead className="font-medium text-slate-600">Business</TableHead>
                  <TableHead className="font-medium text-slate-600">Location</TableHead>
                  <TableHead className="font-medium text-slate-600">Stage</TableHead>
                  <TableHead className="font-medium text-slate-600">Priority</TableHead>
                  <TableHead className="text-xs font-medium text-slate-600">Source</TableHead>
                  <TableHead className="font-medium text-slate-600">Web Score</TableHead>
                  <TableHead></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filtered.map((lead) => (
                  <TableRow
                    key={lead.id}
                    className="cursor-pointer hover:bg-slate-50"
                    onClick={() => navigate(`/app/leads/${lead.id}`)}
                  >
                    <TableCell>
                      <div>
                        <p className="font-medium text-slate-900 text-sm">{lead.business_name}</p>
                        <p className="text-xs text-slate-500">{lead.category}</p>
                      </div>
                    </TableCell>
                    <TableCell className="text-sm text-slate-600">{lead.location}, {lead.country}</TableCell>
                    <TableCell>
                      <Badge variant="outline" className={cn('text-xs', stageBadgeClass[lead.pipeline_stage] || '')}>
                        {stageLabels[lead.pipeline_stage] || lead.pipeline_stage}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline" className={cn('text-xs capitalize',
                        lead.priority === 'high' ? 'bg-red-50 text-red-700 border-red-200' :
                        lead.priority === 'medium' ? 'bg-amber-50 text-amber-700 border-amber-200' :
                        'bg-slate-50 text-slate-600 border-slate-200'
                      )}>
                        {lead.priority}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      {(() => {
                        const badge = getDataSourceBadge(lead.data_source);
                        return (
                          <Badge variant="outline" className={cn('text-xs', badge.className)} title={badge.title}>
                            {badge.label}
                          </Badge>
                        );
                      })()}
                    </TableCell>
                    <TableCell className="text-sm text-slate-600">
                      {/* Three distinct states. Collapsing them would report an
                          unmeasured lead as one confirmed to have no website. */}
                      {lead.website_score !== null && lead.website_score !== undefined ? (
                        `${lead.website_score}/100`
                      ) : lead.has_website === false ? (
                        <span className="text-slate-700">No website</span>
                      ) : (
                        <Button
                          variant="outline"
                          size="sm"
                          disabled={qualifying.has(lead.id)}
                          className="h-7 border-slate-200 text-xs cursor-pointer"
                          onClick={(e) => {
                            e.stopPropagation();
                            qualify([lead.id]);
                          }}
                          title="Fetch the site and measure its quality (1 credit)"
                        >
                          {qualifying.has(lead.id) ? (
                            <Loader2 className="h-3 w-3 mr-1 animate-spin" />
                          ) : (
                            <Gauge className="h-3 w-3 mr-1" />
                          )}
                          {qualifying.has(lead.id) ? 'Measuring…' : 'Qualify'}
                        </Button>
                      )}
                    </TableCell>
                    <TableCell>
                      <ChevronRight className="h-4 w-4 text-slate-400" />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </div>
    </AppShell>
  );
}