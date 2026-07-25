import { useState, useEffect } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import AppShell from '@/components/AppShell';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from '@/components/ui/sheet';
import { Progress } from '@/components/ui/progress';
import { toast } from 'sonner';
import { client } from '@/lib/api';
import {
  Search, Globe, AlertCircle, CreditCard, Info, Save,
  ChevronRight, Loader2, CheckCircle2, XCircle, Clock,
} from 'lucide-react';
import { cn } from '@/lib/utils';

interface ScoreBreakdown {
  score: number;
  factors: Array<{ factor: string; impact: number; source: string }>;
}

interface BusinessResult {
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
  priority_score: number;
  website_state: string;
  scores: {
    need: number;
    buyability: number;
    timing: number;
    reachability: number;
    agency_fit: number;
    confidence: number;
  };
  score_breakdown: Record<string, ScoreBreakdown>;
  score_version: string;
  risk_reasons: string[];
  top_opportunity: string;
  timing_signal: string;
}

interface Filters {
  google_places_connected: boolean;
  countries: string[];
  categories: string[];
  website_states: Array<{ value: string; label: string }>;
  pass_types: Array<{ value: string; label: string; description: string }>;
}

interface Estimate {
  credit_cost: number;
  credits_remaining: number;
  can_afford: boolean;
  estimated_results: number;
  estimated_time_seconds: number;
  providers: string[];
}

export default function AppDiscover() {
  const { user } = useAuth();
  const [filters, setFilters] = useState<Filters | null>(null);
  const [query, setQuery] = useState('');
  const [country, setCountry] = useState('all');
  const [category, setCategory] = useState('all');
  const [websiteState, setWebsiteState] = useState('all');
  const [passType, setPassType] = useState('quick');
  const [results, setResults] = useState<BusinessResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);
  const [estimate, setEstimate] = useState<Estimate | null>(null);
  const [savingIndex, setSavingIndex] = useState<number | null>(null);
  const [jobStatus, setJobStatus] = useState<string>('');
  const [dataSource, setDataSource] = useState<string>('');

  useEffect(() => {
    if (user) fetchFilters();
  }, [user]);

  const fetchFilters = async () => {
    try {
      const res = await client.apiCall.invoke({ url: '/api/v1/discover/filters', method: 'GET', data: {} });
      setFilters(res.data);
    } catch (err) {
      console.error('Failed to fetch filters:', err);
    }
  };

  const getEstimate = async () => {
    try {
      const res = await client.apiCall.invoke({
        url: '/api/v1/discover/estimate',
        method: 'POST',
        data: {
          query: query || null,
          country: country === 'all' ? null : country,
          category: category === 'all' ? null : category,
          limit: 15,
          pass_type: passType,
        },
      });
      setEstimate(res.data);
    } catch (err) {
      console.error('Estimate failed:', err);
    }
  };

  useEffect(() => {
    if (user && (country !== 'all' || category !== 'all' || query)) {
      const timer = setTimeout(getEstimate, 500);
      return () => clearTimeout(timer);
    }
  }, [country, category, query, passType]);

  const handleSearch = async () => {
    if (!user) return;
    setSearching(true);
    setHasSearched(true);
    setJobStatus('running');
    setResults([]);

    try {
      const res = await client.apiCall.invoke({
        url: '/api/v1/discover/run',
        method: 'POST',
        data: {
          query: query || null,
          country: country === 'all' ? null : country,
          category: category === 'all' ? null : category,
          website_state: websiteState,
          limit: 15,
          pass_type: passType,
        },
        options: { timeout: 120000 },
      });

      setResults(res.data?.results || []);
      setJobStatus('complete');
      setDataSource(res.data?.data_source || 'ai');
      toast.success(`Found ${res.data?.total_results || 0} businesses · ${res.data?.credits_charged || 0} credit(s) used`);
    } catch (err: any) {
      const detail = err?.data?.detail;
      if (detail?.error === 'insufficient_credits') {
        setJobStatus('quota_exceeded');
        toast.error(detail.message);
      } else if (detail?.error === 'discovery_failed') {
        setJobStatus('failed');
        toast.error('Discovery failed. Credits refunded.');
      } else {
        setJobStatus('failed');
        toast.error('Search failed. Please try again.');
      }
    } finally {
      setSearching(false);
    }
  };

  const saveAsLead = async (biz: BusinessResult, index: number) => {
    setSavingIndex(index);
    try {
      await client.entities.leads.create({
        data: {
          business_name: biz.business_name,
          category: biz.category,
          location: biz.location,
          country: biz.country,
          website_url: biz.website_url || '',
          website_score: biz.website_score,
          social_score: biz.social_score,
          has_website: biz.has_website,
          social_platforms: '[]',
          contact_email: biz.contact_email || '',
          contact_phone: biz.contact_phone || '',
          pipeline_stage: 'new_lead',
          priority: biz.priority_score >= 70 ? 'high' : biz.priority_score >= 40 ? 'medium' : 'low',
          notes_count: 0,
          last_contacted: '',
        },
      });
      toast.success(`${biz.business_name} saved as lead!`);
    } catch (err) {
      toast.error('Failed to save lead');
    } finally {
      setSavingIndex(null);
    }
  };

  const getWebsiteStateBadge = (state: string) => {
    const map: Record<string, { label: string; className: string }> = {
      no_website: { label: 'No Website', className: 'bg-red-50 text-red-700 border-red-200' },
      parked: { label: 'Parked', className: 'bg-orange-50 text-orange-700 border-orange-200' },
      weak: { label: 'Weak', className: 'bg-amber-50 text-amber-700 border-amber-200' },
      moderate: { label: 'Moderate', className: 'bg-blue-50 text-blue-700 border-blue-200' },
      healthy: { label: 'Healthy', className: 'bg-green-50 text-green-700 border-green-200' },
      unknown: { label: 'Unknown', className: 'bg-slate-50 text-slate-600 border-slate-200' },
    };
    const info = map[state] || map.unknown;
    return <Badge variant="outline" className={cn('text-xs', info.className)}>{info.label}</Badge>;
  };

  const ScoreBar = ({ label, score, color }: { label: string; score: number; color: string }) => (
    <div className="flex items-center gap-2">
      <span className="text-xs text-slate-500 w-20 shrink-0">{label}</span>
      <div className="flex-1 h-1.5 rounded-full bg-slate-100">
        <div className={cn('h-full rounded-full', color)} style={{ width: `${score}%` }} />
      </div>
      <span className="text-xs font-medium text-slate-700 w-7 text-right">{score}</span>
    </div>
  );

  return (
    <AppShell>
      <div className="space-y-6">
        {/* Header */}
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Discover</h1>
          <p className="text-sm text-slate-500">
            Find businesses scored by need, buyability, timing, and fit
          </p>
        </div>

        {/* Search Filters */}
        <Card className="border-slate-200">
          <CardContent className="p-5">
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <div className="space-y-1.5">
                <Label className="text-xs font-medium text-slate-600">Search Query</Label>
                <Input
                  placeholder="e.g. restaurants without booking..."
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                  className="border-slate-200"
                />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs font-medium text-slate-600">Country</Label>
                <Select value={country} onValueChange={setCountry}>
                  <SelectTrigger className="border-slate-200"><SelectValue placeholder="Any country" /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">Any Country</SelectItem>
                    {filters?.countries.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs font-medium text-slate-600">Category</Label>
                <Select value={category} onValueChange={setCategory}>
                  <SelectTrigger className="border-slate-200"><SelectValue placeholder="Any category" /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">Any Category</SelectItem>
                    {filters?.categories.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs font-medium text-slate-600">Website State</Label>
                <Select value={websiteState} onValueChange={setWebsiteState}>
                  <SelectTrigger className="border-slate-200"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {filters?.website_states.map((ws) => (
                      <SelectItem key={ws.value} value={ws.value}>{ws.label}</SelectItem>
                    )) || <SelectItem value="all">All States</SelectItem>}
                  </SelectContent>
                </Select>
              </div>
            </div>

            {/* Estimate & Action */}
            <div className="mt-4 flex items-center justify-between flex-wrap gap-3">
              <div className="flex items-center gap-4 text-xs text-slate-500">
                {estimate && (
                  <>
                    <span className="flex items-center gap-1">
                      <CreditCard className="h-3 w-3" />
                      {estimate.credit_cost} credit{estimate.credit_cost > 1 ? 's' : ''}
                    </span>
                    <span className="flex items-center gap-1">
                      <Clock className="h-3 w-3" />
                      ~{estimate.estimated_time_seconds}s
                    </span>
                    <span className="flex items-center gap-1">
                      {estimate.can_afford
                        ? <CheckCircle2 className="h-3 w-3 text-green-600" />
                        : <XCircle className="h-3 w-3 text-red-600" />
                      }
                      {estimate.credits_remaining} credits available
                    </span>
                  </>
                )}
              </div>
              <Button
                onClick={handleSearch}
                disabled={searching}
                className="bg-indigo-600 hover:bg-indigo-700 gap-2"
              >
                {searching ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
                {searching ? 'Discovering...' : 'Run Discovery'}
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* Job Status */}
        {searching && (
          <Card className="border-indigo-200 bg-indigo-50">
            <CardContent className="p-5">
              <div className="flex items-center gap-3">
                <Loader2 className="h-5 w-5 animate-spin text-indigo-600" />
                <div className="flex-1">
                  <p className="text-sm font-medium text-indigo-900">AI Discovery Running</p>
                  <p className="text-xs text-indigo-700">Analyzing businesses, scoring buyability and timing signals...</p>
                </div>
              </div>
              <Progress value={45} className="mt-3 h-1.5" />
            </CardContent>
          </Card>
        )}

        {/* Quota exceeded */}
        {jobStatus === 'quota_exceeded' && (
          <Card className="border-amber-200 bg-amber-50">
            <CardContent className="p-5 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <AlertCircle className="h-5 w-5 text-amber-600" />
                <div>
                  <p className="text-sm font-medium text-amber-900">Credits Exhausted</p>
                  <p className="text-xs text-amber-700">Upgrade your plan or purchase a credit top-up to continue.</p>
                </div>
              </div>
              <Button size="sm" variant="outline" className="border-amber-300" onClick={() => window.location.href = '/app/settings/billing'}>
                Upgrade
              </Button>
            </CardContent>
          </Card>
        )}

        {/* Results */}
        {!searching && hasSearched && results.length === 0 && jobStatus !== 'quota_exceeded' && (
          <div className="flex flex-col items-center py-12 text-center">
            <AlertCircle className="mb-3 h-10 w-10 text-slate-300" />
            <p className="text-slate-600 font-medium">No businesses found</p>
            <p className="text-sm text-slate-500 mt-1">Try adjusting your filters or broadening your search.</p>
          </div>
        )}

        {results.length > 0 && (
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <p className="text-sm text-slate-600">
                <span className="font-medium text-slate-900">{results.length}</span> businesses found · sorted by Priority Score
              </p>
              <div className="flex items-center gap-2">
                {filters?.google_places_connected && (
                  <Badge variant="outline" className="text-xs bg-green-50 text-green-700 border-green-200">
                    <Globe className="h-3 w-3 mr-1" />
                    Google Places
                  </Badge>
                )}
                <Badge variant="outline" className="text-xs border-slate-200 text-slate-500">
                  Source: {dataSource === 'google_places' ? 'Google Places API' : 'AI Discovery'}
                </Badge>
              </div>
            </div>

            {results.map((biz, idx) => (
              <Card key={idx} className="border-slate-200 hover:border-indigo-200 transition-colors">
                <CardContent className="p-5">
                  <div className="flex flex-col lg:flex-row lg:items-start gap-4">
                    {/* Main info */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-start gap-3">
                        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-slate-100 text-lg font-bold text-indigo-600">
                          {biz.priority_score}
                        </div>
                        <div className="min-w-0">
                          <h3 className="font-semibold text-slate-900 truncate">{biz.business_name}</h3>
                          <p className="text-sm text-slate-500">{biz.category} · {biz.location}, {biz.country}</p>
                          <div className="flex items-center gap-2 mt-1.5">
                            {getWebsiteStateBadge(biz.website_state)}
                            {biz.timing_signal && (
                              <Badge variant="outline" className="text-xs bg-amber-50 text-amber-700 border-amber-200">
                                ⚡ {biz.timing_signal}
                              </Badge>
                            )}
                          </div>
                        </div>
                      </div>

                      {biz.top_opportunity && (
                        <p className="mt-2 text-xs text-slate-600 bg-slate-50 rounded px-2 py-1">
                          💡 {biz.top_opportunity}
                        </p>
                      )}
                    </div>

                    {/* Scores */}
                    <div className="w-full lg:w-64 shrink-0 space-y-1.5">
                      <ScoreBar label="Need" score={biz.scores.need} color="bg-red-500" />
                      <ScoreBar label="Buyability" score={biz.scores.buyability} color="bg-blue-500" />
                      <ScoreBar label="Timing" score={biz.scores.timing} color="bg-amber-500" />
                      <ScoreBar label="Reachability" score={biz.scores.reachability} color="bg-green-500" />
                      <ScoreBar label="Confidence" score={biz.scores.confidence} color="bg-slate-400" />
                    </div>

                    {/* Actions */}
                    <div className="flex lg:flex-col gap-2 shrink-0">
                      <Button
                        size="sm"
                        onClick={() => saveAsLead(biz, idx)}
                        disabled={savingIndex === idx}
                        className="bg-indigo-600 hover:bg-indigo-700 gap-1"
                      >
                        <Save className="h-3.5 w-3.5" />
                        {savingIndex === idx ? 'Saving...' : 'Save'}
                      </Button>
                      <Sheet>
                        <SheetTrigger asChild>
                          <Button size="sm" variant="outline" className="gap-1 border-slate-200">
                            <Info className="h-3.5 w-3.5" />
                            Scores
                          </Button>
                        </SheetTrigger>
                        <SheetContent className="w-[400px] sm:w-[540px]">
                          <SheetHeader>
                            <SheetTitle>Score Breakdown: {biz.business_name}</SheetTitle>
                          </SheetHeader>
                          <div className="mt-6 space-y-6">
                            {Object.entries(biz.score_breakdown || {}).map(([key, breakdown]) => (
                              <div key={key}>
                                <div className="flex items-center justify-between mb-2">
                                  <h4 className="text-sm font-medium capitalize text-slate-900">{key.replace('_', ' ')} Score</h4>
                                  <span className="text-sm font-bold text-slate-700">{breakdown.score}/100</span>
                                </div>
                                <div className="space-y-1">
                                  {breakdown.factors.map((f, i) => (
                                    <div key={i} className="flex items-start gap-2 text-xs">
                                      <span className={cn(
                                        'font-medium shrink-0',
                                        f.impact > 0 ? 'text-green-600' : f.impact < 0 ? 'text-red-600' : 'text-slate-400'
                                      )}>
                                        {f.impact > 0 ? `+${f.impact}` : f.impact === 0 ? '—' : f.impact}
                                      </span>
                                      <span className="text-slate-600">{f.factor}</span>
                                      <Badge variant="outline" className="text-[10px] ml-auto shrink-0">{f.source}</Badge>
                                    </div>
                                  ))}
                                </div>
                              </div>
                            ))}
                            {biz.risk_reasons.length > 0 && (
                              <div>
                                <h4 className="text-sm font-medium text-red-700 mb-2">Risk Factors</h4>
                                {biz.risk_reasons.map((r, i) => (
                                  <p key={i} className="text-xs text-red-600">⚠️ {r}</p>
                                ))}
                              </div>
                            )}
                            <div className="text-xs text-slate-400 border-t pt-3">
                              Score version: {biz.score_version}
                            </div>
                          </div>
                        </SheetContent>
                      </Sheet>
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}

        {/* Empty state */}
        {!hasSearched && !searching && (
          <div className="flex flex-col items-center py-16 text-center">
            <div className="flex h-16 w-16 items-center justify-center rounded-full bg-indigo-50 mb-4">
              <Globe className="h-8 w-8 text-indigo-400" />
            </div>
            <h3 className="font-semibold text-slate-900 text-lg">Discover business opportunities</h3>
            <p className="mt-2 max-w-md text-sm text-slate-500">
              Use the filters above to find businesses with weak digital presence, 
              scored by their likelihood to buy your services.
            </p>
            <div className="mt-6 grid gap-3 text-left max-w-sm">
              <div className="flex items-start gap-2 text-xs text-slate-600">
                <CheckCircle2 className="h-4 w-4 text-green-600 shrink-0 mt-0.5" />
                <span>6-score intelligence: Need, Buyability, Timing, Reachability, Fit, Confidence</span>
              </div>
              <div className="flex items-start gap-2 text-xs text-slate-600">
                <CheckCircle2 className="h-4 w-4 text-green-600 shrink-0 mt-0.5" />
                <span>Full breakdown with source citations for every score</span>
              </div>
              <div className="flex items-start gap-2 text-xs text-slate-600">
                <CheckCircle2 className="h-4 w-4 text-green-600 shrink-0 mt-0.5" />
                <span>Save qualified businesses directly to your pipeline</span>
              </div>
            </div>
          </div>
        )}
      </div>
    </AppShell>
  );
}