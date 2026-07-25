import { useEffect, useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import AppLayout from '@/components/AppLayout';
import { client } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow
} from '@/components/ui/table';
import { toast } from 'sonner';
import {
  Globe, Search, Trash2, ArrowUpDown, Filter, Download,
  Mail, Phone, ExternalLink
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

const PRIORITY_COLORS: Record<string, string> = {
  high: 'bg-red-100 text-red-700',
  medium: 'bg-orange-100 text-orange-700',
  low: 'bg-gray-100 text-gray-700',
};

export default function AllLeads() {
  const { user, loading: authLoading, login } = useAuth();
  const navigate = useNavigate();
  const [leads, setLeads] = useState<Lead[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [stageFilter, setStageFilter] = useState('all');
  const [priorityFilter, setPriorityFilter] = useState('all');
  const [categoryFilter, setCategoryFilter] = useState('all');
  const [countryFilter, setCountryFilter] = useState('all');
  const [sortField, setSortField] = useState<'business_name' | 'created_at' | 'website_score' | 'social_score'>('created_at');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');
  const [selectedLeads, setSelectedLeads] = useState<Set<number>>(new Set());

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

  const filteredLeads = useMemo(() => {
    let filtered = [...leads];

    // Text search
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      filtered = filtered.filter(
        (l) =>
          l.business_name.toLowerCase().includes(q) ||
          l.category.toLowerCase().includes(q) ||
          l.location.toLowerCase().includes(q) ||
          l.country.toLowerCase().includes(q)
      );
    }

    // Stage filter
    if (stageFilter !== 'all') {
      filtered = filtered.filter((l) => l.pipeline_stage === stageFilter);
    }

    // Priority filter
    if (priorityFilter !== 'all') {
      filtered = filtered.filter((l) => l.priority === priorityFilter);
    }

    // Category filter
    if (categoryFilter !== 'all') {
      filtered = filtered.filter((l) => l.category === categoryFilter);
    }

    // Country filter
    if (countryFilter !== 'all') {
      filtered = filtered.filter((l) => l.country === countryFilter);
    }

    // Sort
    filtered.sort((a, b) => {
      let valA: string | number = a[sortField];
      let valB: string | number = b[sortField];
      if (typeof valA === 'string') valA = valA.toLowerCase();
      if (typeof valB === 'string') valB = valB.toLowerCase();
      if (valA < valB) return sortDir === 'asc' ? -1 : 1;
      if (valA > valB) return sortDir === 'asc' ? 1 : -1;
      return 0;
    });

    return filtered;
  }, [leads, searchQuery, stageFilter, priorityFilter, categoryFilter, countryFilter, sortField, sortDir]);

  const uniqueCategories = useMemo(() => {
    const cats = [...new Set(leads.map((l) => l.category))].filter(Boolean).sort();
    return cats;
  }, [leads]);

  const uniqueCountries = useMemo(() => {
    const countries = [...new Set(leads.map((l) => l.country))].filter(Boolean).sort();
    return countries;
  }, [leads]);

  const toggleSort = (field: typeof sortField) => {
    if (sortField === field) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortField(field);
      setSortDir('desc');
    }
  };

  const toggleSelect = (id: number) => {
    setSelectedLeads((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleSelectAll = () => {
    if (selectedLeads.size === filteredLeads.length) {
      setSelectedLeads(new Set());
    } else {
      setSelectedLeads(new Set(filteredLeads.map((l) => l.id)));
    }
  };

  const bulkDelete = async () => {
    if (selectedLeads.size === 0) return;
    if (!confirm(`Delete ${selectedLeads.size} leads?`)) return;
    try {
      for (const id of selectedLeads) {
        await client.entities.leads.delete({ id: String(id) });
      }
      toast.success(`Deleted ${selectedLeads.size} leads`);
      setSelectedLeads(new Set());
      fetchLeads();
    } catch (err) {
      console.error('Bulk delete failed:', err);
      toast.error('Failed to delete some leads');
    }
  };

  const bulkUpdateStage = async (stage: string) => {
    if (selectedLeads.size === 0) return;
    try {
      for (const id of selectedLeads) {
        await client.entities.leads.update({
          id: String(id),
          data: { pipeline_stage: stage },
        });
      }
      toast.success(`Updated ${selectedLeads.size} leads to ${STAGE_CONFIG[stage]?.label || stage}`);
      setSelectedLeads(new Set());
      fetchLeads();
    } catch (err) {
      console.error('Bulk update failed:', err);
      toast.error('Failed to update some leads');
    }
  };

  const exportCSV = () => {
    const headers = ['Business Name', 'Category', 'Location', 'Country', 'Website', 'Website Score', 'Social Score', 'Stage', 'Priority', 'Email', 'Phone'];
    const rows = filteredLeads.map((l) => [
      l.business_name, l.category, l.location, l.country,
      l.website_url, l.website_score, l.social_score,
      STAGE_CONFIG[l.pipeline_stage]?.label || l.pipeline_stage,
      l.priority, l.contact_email, l.contact_phone,
    ]);
    const csv = [headers.join(','), ...rows.map((r) => r.map((v) => `"${v}"`).join(','))].join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'leads_export.csv';
    a.click();
    URL.revokeObjectURL(url);
    toast.success('Leads exported as CSV');
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
          <h2 className="font-[Poppins] text-2xl font-semibold">Sign in to view leads</h2>
          <Button onClick={login} className="mt-6">Sign In</Button>
        </div>
      </AppLayout>
    );
  }

  return (
    <AppLayout>
      <div className="space-y-6">
        {/* Page Header */}
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className="font-[Poppins] text-2xl font-bold text-foreground">All Leads</h1>
            <p className="text-sm text-muted-foreground">
              {filteredLeads.length} of {leads.length} leads
            </p>
          </div>
          <div className="flex gap-2">
            <Button onClick={exportCSV} variant="outline" size="sm" className="gap-2">
              <Download className="h-4 w-4" />
              Export CSV
            </Button>
            <Button onClick={() => navigate('/search')} size="sm" className="gap-2">
              <Search className="h-4 w-4" />
              Find More
            </Button>
          </div>
        </div>

        {/* Filters */}
        <Card>
          <CardContent className="p-4">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
              <div className="relative flex-1">
                <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  placeholder="Search leads..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="pl-9"
                />
              </div>
              <div className="flex gap-2">
                <Select value={stageFilter} onValueChange={setStageFilter}>
                  <SelectTrigger className="w-36">
                    <Filter className="mr-2 h-3 w-3" />
                    <SelectValue placeholder="Stage" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Stages</SelectItem>
                    {Object.entries(STAGE_CONFIG).map(([key, cfg]) => (
                      <SelectItem key={key} value={key}>{cfg.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Select value={priorityFilter} onValueChange={setPriorityFilter}>
                  <SelectTrigger className="w-32">
                    <SelectValue placeholder="Priority" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Priority</SelectItem>
                    <SelectItem value="high">High</SelectItem>
                    <SelectItem value="medium">Medium</SelectItem>
                    <SelectItem value="low">Low</SelectItem>
                  </SelectContent>
                </Select>
                <Select value={categoryFilter} onValueChange={setCategoryFilter}>
                  <SelectTrigger className="w-40">
                    <SelectValue placeholder="Category" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Categories</SelectItem>
                    {uniqueCategories.map((cat) => (
                      <SelectItem key={cat} value={cat}>{cat}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Select value={countryFilter} onValueChange={setCountryFilter}>
                  <SelectTrigger className="w-36">
                    <SelectValue placeholder="Country" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Countries</SelectItem>
                    {uniqueCountries.map((c) => (
                      <SelectItem key={c} value={c}>{c}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Bulk Actions */}
        {selectedLeads.size > 0 && (
          <Card className="border-primary/30 bg-primary/5">
            <CardContent className="flex items-center justify-between p-3">
              <span className="text-sm font-medium">
                {selectedLeads.size} lead{selectedLeads.size > 1 ? 's' : ''} selected
              </span>
              <div className="flex gap-2">
                <Select onValueChange={bulkUpdateStage}>
                  <SelectTrigger className="h-8 w-36 text-xs">
                    <SelectValue placeholder="Move to..." />
                  </SelectTrigger>
                  <SelectContent>
                    {Object.entries(STAGE_CONFIG).map(([key, cfg]) => (
                      <SelectItem key={key} value={key}>{cfg.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Button variant="destructive" size="sm" onClick={bulkDelete} className="gap-1">
                  <Trash2 className="h-3 w-3" />
                  Delete
                </Button>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Table */}
        {loading ? (
          <div className="space-y-2">
            {[...Array(8)].map((_, i) => (
              <Skeleton key={i} className="h-14 rounded-lg" />
            ))}
          </div>
        ) : filteredLeads.length === 0 ? (
          <div className="flex flex-col items-center py-16 text-center">
            <Search className="mb-3 h-10 w-10 text-muted-foreground/50" />
            <p className="text-muted-foreground">No leads match your filters.</p>
          </div>
        ) : (
          <Card>
            <CardContent className="p-0">
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="w-10">
                        <input
                          type="checkbox"
                          checked={selectedLeads.size === filteredLeads.length && filteredLeads.length > 0}
                          onChange={toggleSelectAll}
                          className="rounded border-border"
                        />
                      </TableHead>
                      <TableHead>
                        <button onClick={() => toggleSort('business_name')} className="flex items-center gap-1 hover:text-foreground">
                          Business <ArrowUpDown className="h-3 w-3" />
                        </button>
                      </TableHead>
                      <TableHead className="hidden md:table-cell">Location</TableHead>
                      <TableHead className="hidden lg:table-cell">
                        <button onClick={() => toggleSort('website_score')} className="flex items-center gap-1 hover:text-foreground">
                          Web Score <ArrowUpDown className="h-3 w-3" />
                        </button>
                      </TableHead>
                      <TableHead className="hidden lg:table-cell">
                        <button onClick={() => toggleSort('social_score')} className="flex items-center gap-1 hover:text-foreground">
                          Social Score <ArrowUpDown className="h-3 w-3" />
                        </button>
                      </TableHead>
                      <TableHead>Stage</TableHead>
                      <TableHead className="hidden sm:table-cell">Priority</TableHead>
                      <TableHead className="hidden xl:table-cell">Contact</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {filteredLeads.map((lead) => (
                      <TableRow
                        key={lead.id}
                        className="cursor-pointer hover:bg-muted/50"
                      >
                        <TableCell onClick={(e) => e.stopPropagation()}>
                          <input
                            type="checkbox"
                            checked={selectedLeads.has(lead.id)}
                            onChange={() => toggleSelect(lead.id)}
                            className="rounded border-border"
                          />
                        </TableCell>
                        <TableCell onClick={() => navigate(`/lead/${lead.id}`)}>
                          <div>
                            <p className="font-medium text-foreground hover:text-primary">
                              {lead.business_name}
                            </p>
                            <p className="text-xs text-muted-foreground">{lead.category}</p>
                          </div>
                        </TableCell>
                        <TableCell className="hidden md:table-cell text-sm text-muted-foreground" onClick={() => navigate(`/lead/${lead.id}`)}>
                          {lead.location}
                        </TableCell>
                        <TableCell className="hidden lg:table-cell" onClick={() => navigate(`/lead/${lead.id}`)}>
                          <span className={`text-sm font-medium ${lead.website_score === 0 ? 'text-red-500' : lead.website_score < 30 ? 'text-orange-500' : 'text-yellow-500'}`}>
                            {lead.website_score}
                          </span>
                        </TableCell>
                        <TableCell className="hidden lg:table-cell" onClick={() => navigate(`/lead/${lead.id}`)}>
                          <span className={`text-sm font-medium ${lead.social_score === 0 ? 'text-red-500' : lead.social_score < 30 ? 'text-orange-500' : 'text-yellow-500'}`}>
                            {lead.social_score}
                          </span>
                        </TableCell>
                        <TableCell onClick={() => navigate(`/lead/${lead.id}`)}>
                          <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${STAGE_CONFIG[lead.pipeline_stage]?.color || ''}`}>
                            {STAGE_CONFIG[lead.pipeline_stage]?.label || lead.pipeline_stage}
                          </span>
                        </TableCell>
                        <TableCell className="hidden sm:table-cell" onClick={() => navigate(`/lead/${lead.id}`)}>
                          <Badge variant="outline" className={`text-xs border-0 ${PRIORITY_COLORS[lead.priority] || ''}`}>
                            {lead.priority}
                          </Badge>
                        </TableCell>
                        <TableCell className="hidden xl:table-cell">
                          <div className="flex items-center gap-2">
                            {lead.contact_email && (
                              <a href={`mailto:${lead.contact_email}`} onClick={(e) => e.stopPropagation()} className="text-muted-foreground hover:text-primary">
                                <Mail className="h-4 w-4" />
                              </a>
                            )}
                            {lead.contact_phone && (
                              <a href={`tel:${lead.contact_phone}`} onClick={(e) => e.stopPropagation()} className="text-muted-foreground hover:text-primary">
                                <Phone className="h-4 w-4" />
                              </a>
                            )}
                            {lead.website_url && (
                              <a href={lead.website_url} target="_blank" rel="noopener noreferrer" onClick={(e) => e.stopPropagation()} className="text-muted-foreground hover:text-primary">
                                <ExternalLink className="h-4 w-4" />
                              </a>
                            )}
                          </div>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </CardContent>
          </Card>
        )}
      </div>
    </AppLayout>
  );
}