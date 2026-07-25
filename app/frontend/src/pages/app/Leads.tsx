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
import { Search, Download, ChevronRight, AlertCircle } from 'lucide-react';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';

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
  created_at: string;
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

export default function AppLeads() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [leads, setLeads] = useState<Lead[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [stageFilter, setStageFilter] = useState('all');
  const [priorityFilter, setPriorityFilter] = useState('all');

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
          <div className="rounded-lg border border-slate-200 overflow-hidden">
            <Table>
              <TableHeader>
                <TableRow className="bg-slate-50">
                  <TableHead className="font-medium text-slate-600">Business</TableHead>
                  <TableHead className="font-medium text-slate-600">Location</TableHead>
                  <TableHead className="font-medium text-slate-600">Stage</TableHead>
                  <TableHead className="font-medium text-slate-600">Priority</TableHead>
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
                    <TableCell className="text-sm text-slate-600">
                      {lead.has_website ? `${lead.website_score}/100` : 'None'}
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