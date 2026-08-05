import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import AppShell from '@/components/AppShell';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
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
import { useCredits } from '@/contexts/CreditsContext';
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
  // Null when the site could not be read at all — unreachable, blocked or
  // parked. Discovery measures every result, so this is now the exception
  // rather than the norm, but `has_website` is still null — not false — when
  // nothing could be established. Typing these as non-nullable let code like
  // `biz.website_score > 50` compile while silently reading unknown as zero,
  // which is the one claim this product must never make.
  website_score: number | null;
  social_score: number | null;
  has_website: boolean | null;
  contact_email: string;
  contact_phone: string;
  /** Street address as the provider recorded it; '' when it had none. */
  full_address?: string;
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
  data_source?: string;
  /**
   * Measured at discovery, from the business's own page.
   *
   * `findings` is the sellable part — specific, checkable problems with the
   * site. Null when nothing could be read, which is not the same as an empty
   * list ("read it, found nothing wrong").
   */
  findings?: Array<Record<string, unknown>> | null;
  /** ISO timestamp; present only where a website score was established. */
  qualified_at?: string;
  /** Social platforms the site links to. Null when no page could be read. */
  social_platforms?: string[] | null;
  /** Which tier produced the score: heuristic, lighthouse or pagespeed. */
  evidence_tier?: string | null;
}

interface Filters {
  google_places_connected: boolean;
  mapbox_connected: boolean;
  discovery_provider: 'google_places' | 'mapbox' | null;
  max_results: number;
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
  const navigate = useNavigate();
  const [filters, setFilters] = useState<Filters | null>(null);
  const [query, setQuery] = useState('');
  const [city, setCity] = useState('');
  const [country, setCountry] = useState('all');
  const [category, setCategory] = useState('all');
  const [websiteState, setWebsiteState] = useState('all');
  const [passType, setPassType] = useState('quick');
  const [results, setResults] = useState<BusinessResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);
  const [estimate, setEstimate] = useState<Estimate | null>(null);
  const [savingIndex, setSavingIndex] = useState<number | null>(null);
  // Indices already written to the CRM. Saving is not idempotent server-side,
  // so a second click would create a duplicate lead; this is what prevents it.
  const [savedIndices, setSavedIndices] = useState<Set<number>>(new Set());
  const [savingAll, setSavingAll] = useState(false);
  const [jobStatus, setJobStatus] = useState<string>('');
  // The server's own wording for an expired trial, kept verbatim so the date
  // shown is the date the block was computed from.
  const [trialMessage, setTrialMessage] = useState<string>('');
  const [dataSource, setDataSource] = useState<string>('');
  const { refresh: refreshCredits } = useCredits();

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
          limit: filters?.max_results ?? 20,
          pass_type: passType,
        },
      });
      setEstimate(res.data);
    } catch (err) {
      console.error('Estimate failed:', err);
    }
  };

  useEffect(() => {
    if (user && (country !== 'all' || category !== 'all' || query || city.trim())) {
      const timer = setTimeout(getEstimate, 500);
      return () => clearTimeout(timer);
    }
  }, [country, category, query, city, passType]);

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
          city: city.trim() || null,
          country: country === 'all' ? null : country,
          category: category === 'all' ? null : category,
          website_state: websiteState,
          limit: filters?.max_results ?? 20,
          pass_type: passType,
        },
        options: { timeout: 120000 },
      });

      const status = res.data?.status;
      // A search charges before it knows how many results it will find, so
      // the balance moves even on "no matches". Refresh regardless of status.
      void refreshCredits();
      setSavedIndices(new Set());
      setResults(res.data?.results || []);
      setDataSource(res.data?.data_source || '');

      if (status === 'provider_unconfigured') {
        setJobStatus('provider_unconfigured');
        toast.error(res.data?.message || 'No discovery provider is connected.');
      } else if (status === 'no_matches') {
        setJobStatus('no_matches');
        toast.info('No businesses matched those filters.');
      } else {
        setJobStatus('complete');
        toast.success(
          `Found ${res.data?.total_results || 0} businesses · ${res.data?.credits_charged || 0} credit(s) used`
        );
      }
    } catch (err: any) {
      const detail = err?.data?.detail;
      if (detail?.error === 'trial_expired') {
        // Distinct from running out of credits: a top-up does not fix this,
        // only a plan does. Carrying the server's own message keeps the date
        // it names identical to the one the block was computed from.
        setJobStatus('trial_expired');
        setTrialMessage(detail.message ?? '');
        toast.error(detail.message ?? 'Your free trial has ended.');
      } else if (detail?.error === 'insufficient_credits') {
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

  const leadPayload = (biz: BusinessResult) => ({
    business_name: biz.business_name,
    category: biz.category,
    location: biz.location,
    country: biz.country,
    website_url: biz.website_url || '',
    // Null stays null. Discovery measures every result, but a site that is
    // unreachable, blocked or parked still yields no score, and coercing that
    // to 0/false would claim a verdict nobody has established.
    website_score: biz.website_score,
    social_score: biz.social_score,
    has_website: biz.has_website,
    // Measured from the links on the business's own page. Falls back to '[]'
    // only when no page could be read — an empty list means "looked, found
    // none", which is a different claim from "never looked".
    social_platforms: JSON.stringify(biz.social_platforms ?? []),
    contact_email: biz.contact_email || '',
    contact_phone: biz.contact_phone || '',
    // The provider has returned this on every POI all along; there was simply
    // no column to keep it in. Undefined rather than '' when absent, so "no
    // address on record" stays distinguishable from an empty one.
    address: biz.full_address || undefined,
    pipeline_stage: 'new_lead',
    priority: biz.priority_score >= 70 ? 'high' : biz.priority_score >= 40 ? 'medium' : 'low',
    notes_count: 0,
    last_contacted: '',
    data_source: biz.data_source || 'provider',
    // The measurement discovery already performed. Without these two the save
    // would throw away the findings the user paid for and the lead would land
    // in the pipeline looking as though it had never been checked.
    //
    // The backend sets qualified_at only where a score was established, so
    // undefined here means genuinely unmeasured rather than measured-and-clean.
    findings: biz.findings ? JSON.stringify(biz.findings) : undefined,
    qualified_at: biz.qualified_at || undefined,
  });

  const saveAsLead = async (biz: BusinessResult, index: number) => {
    if (savedIndices.has(index)) return;
    setSavingIndex(index);
    try {
      await client.entities.leads.create({ data: leadPayload(biz) });
      setSavedIndices((prev) => new Set(prev).add(index));
      toast.success(`${biz.business_name} saved as lead!`);
    } catch (err) {
      toast.error('Failed to save lead');
    } finally {
      setSavingIndex(null);
    }
  };

  /**
   * Save every result not already saved.
   *
   * The search has already cost a credit by the time these are on screen, and
   * they live only in component state — navigating away lost them. Saving one
   * row at a time made a 25-result search 25 clicks, so in practice the work
   * paid for was routinely thrown away.
   *
   * Failures are counted rather than aborting the batch: one bad row should
   * not discard the other twenty-four.
   */
  const saveAllResults = async () => {
    const pending = results
      .map((biz, idx) => ({ biz, idx }))
      .filter(({ idx }) => !savedIndices.has(idx));
    if (!pending.length) return;

    setSavingAll(true);
    const saved = new Set(savedIndices);
    let failed = 0;

    for (const { biz, idx } of pending) {
      try {
        await client.entities.leads.create({ data: leadPayload(biz) });
        saved.add(idx);
      } catch {
        failed += 1;
      }
    }

    setSavedIndices(saved);
    setSavingAll(false);

    const succeeded = pending.length - failed;
    if (failed === 0) {
      toast.success(`Saved ${succeeded} lead${succeeded === 1 ? '' : 's'} to your pipeline`);
    } else if (succeeded === 0) {
      toast.error(`Could not save ${failed} lead${failed === 1 ? '' : 's'}`);
    } else {
      toast.warning(`Saved ${succeeded}, but ${failed} failed`);
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
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
              <div className="space-y-1.5">
                <Label htmlFor="city" className="text-xs font-medium text-slate-600">
                  City or area
                </Label>
                {/*
                  The product searches for LOCAL businesses, but until now the
                  only geography control was a 20-item country dropdown. A user
                  in Nairobi, Manila or Buenos Aires had no way to say where
                  they were, and a country-wide search returns businesses from
                  the geographic middle of a nation — useless for local
                  outreach. Free text works anywhere MapBox can geocode, which
                  is far more of the world than any list we maintain.
                */}
                <Input
                  id="city"
                  placeholder="e.g. Nairobi, Lyon, 90210"
                  value={city}
                  onChange={(e) => setCity(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                  className="border-slate-200"
                />
              </div>
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
                  <p className="text-sm font-medium text-indigo-900">Discovery Running</p>
                  <p className="text-xs text-indigo-700">Analyzing businesses, scoring buyability and timing signals...</p>
                </div>
              </div>
              <Progress value={45} className="mt-3 h-1.5" />
            </CardContent>
          </Card>
        )}

        {/* Quota exceeded */}
        {jobStatus === 'trial_expired' && (
          <Card className="border-amber-200 bg-amber-50">
            <CardContent className="p-5 flex items-center justify-between gap-4">
              <div className="flex items-center gap-3">
                <AlertCircle className="h-5 w-5 text-amber-600 shrink-0" />
                <div>
                  <p className="text-sm font-medium text-amber-900">Free trial ended</p>
                  <p className="text-xs text-amber-700">
                    {trialMessage ||
                      'Upgrade to keep discovering and qualifying leads. Your saved leads stay available.'}
                  </p>
                </div>
              </div>
              <Button
                size="sm"
                variant="outline"
                className="border-amber-300 shrink-0"
                onClick={() => navigate('/app/settings/billing')}
              >
                Upgrade
              </Button>
            </CardContent>
          </Card>
        )}

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
        {!searching &&
          hasSearched &&
          results.length === 0 &&
          jobStatus !== 'quota_exceeded' &&
          jobStatus !== 'trial_expired' &&
          jobStatus !== 'provider_unconfigured' &&
          jobStatus !== 'no_matches' && (
            <div className="flex flex-col items-center py-12 text-center">
              <AlertCircle className="mb-3 h-10 w-10 text-slate-300" />
              <p className="text-slate-600 font-medium">No businesses found</p>
              <p className="text-sm text-slate-500 mt-1">Try adjusting your filters or broadening your search.</p>
            </div>
          )}

        {jobStatus === 'provider_unconfigured' && (
          <Card className="border-amber-200 bg-amber-50/50">
            <CardHeader>
              <CardTitle className="text-base text-slate-900">No discovery provider connected</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {/* This used to say "Add a MapBox access token to enable
                  searching" above a Go to Settings button. Neither was
                  actionable: discovery providers are configured with
                  environment variables on the API service, and the settings
                  page it opened has no such control — so the button was a
                  dead end that implied the customer had done something wrong.
                  It had also gone stale, naming only MapBox after Google
                  Places was added as an alternative. */}
              <p className="text-sm text-slate-600">
                Searching is unavailable right now — no credits were charged. This is a
                configuration issue on our side, not something wrong with your search.
              </p>
              <p className="text-sm text-slate-600">
                Results will never be invented to fill the gap, which is why nothing is shown
                rather than something plausible.
              </p>
            </CardContent>
          </Card>
        )}

        {jobStatus === 'no_matches' && (
          <Card className="border-slate-200">
            <CardHeader>
              <CardTitle className="text-base text-slate-900">No businesses matched</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              <p className="text-sm text-slate-600">
                The provider ran your search and returned nothing. Try widening it:
              </p>
              <ul className="text-sm text-slate-600 list-disc pl-5 space-y-1">
                <li>Remove the category filter, or pick a broader one</li>
                <li>Search a larger city or drop the city entirely</li>
                <li>Set Website State back to “All States”</li>
              </ul>
            </CardContent>
          </Card>
        )}

        {results.length > 0 && (
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <p className="text-sm text-slate-600">
                <span className="font-medium text-slate-900">{results.length}</span> businesses found · sorted by Priority Score
              </p>
              <div className="flex items-center gap-2">
                {results.length > savedIndices.size && (
                  <Button
                    size="sm"
                    onClick={saveAllResults}
                    disabled={savingAll}
                    className="bg-indigo-600 hover:bg-indigo-700 text-white cursor-pointer"
                  >
                    {savingAll
                      ? `Saving ${results.length - savedIndices.size}...`
                      : `Save all ${results.length - savedIndices.size} to pipeline`}
                  </Button>
                )}
                <Badge variant="outline" className="text-xs border-green-200 text-green-700 bg-green-50">
                  Source: {dataSource === 'google_places'
                    ? 'Google Places'
                    : dataSource === 'mapbox'
                    ? 'MapBox Places'
                    : 'Connected provider'}
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
                        disabled={savingIndex === idx || savingAll || savedIndices.has(idx)}
                        className={
                          savedIndices.has(idx)
                            ? 'bg-green-600 hover:bg-green-600 gap-1 cursor-default'
                            : 'bg-indigo-600 hover:bg-indigo-700 gap-1 cursor-pointer'
                        }
                      >
                        <Save className="h-3.5 w-3.5" />
                        {savedIndices.has(idx)
                          ? 'Saved'
                          : savingIndex === idx
                            ? 'Saving...'
                            : 'Save'}
                      </Button>
                      <Sheet>
                        <SheetTrigger asChild>
                          <Button size="sm" variant="outline" className="gap-1 border-slate-200">
                            <Info className="h-3.5 w-3.5" />
                            Scores
                          </Button>
                        </SheetTrigger>
                        <SheetContent className="w-full sm:max-w-[540px] overflow-y-auto">
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
