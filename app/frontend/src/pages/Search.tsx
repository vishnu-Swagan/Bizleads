import { useState, useEffect } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { useNavigate } from 'react-router-dom';
import AppLayout from '@/components/AppLayout';
import { client } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Skeleton } from '@/components/ui/skeleton';
import { toast } from 'sonner';
import {
  Search as SearchIcon, Globe, Wifi, WifiOff, Plus,
  MapPin, Building2, ExternalLink, AlertCircle
} from 'lucide-react';

interface BusinessResult {
  business_name: string;
  category: string;
  location: string;
  country: string;
  website_url: string;
  website_score: number;
  social_score: number;
  has_website: boolean;
  social_platforms: string[];
  contact_email: string;
  contact_phone: string;
}

interface Filters {
  categories: string[];
  countries: string[];
  web_presence_options: { value: string; label: string }[];
}

export default function Search() {
  const { user, loading: authLoading, login } = useAuth();
  const navigate = useNavigate();
  const [query, setQuery] = useState('');
  const [country, setCountry] = useState('');
  const [category, setCategory] = useState('');
  const [webPresence, setWebPresence] = useState('all');
  const [results, setResults] = useState<BusinessResult[]>([]);
  const [filters, setFilters] = useState<Filters | null>(null);
  const [searching, setSearching] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);
  const [savingIndex, setSavingIndex] = useState<number | null>(null);

  useEffect(() => {
    if (user) {
      fetchFilters();
    }
  }, [user]);

  const fetchFilters = async () => {
    try {
      const response = await client.apiCall.invoke({
        url: '/api/v1/search/filters',
        method: 'GET',
        data: {},
      });
      setFilters(response.data);
    } catch (err) {
      console.error('Failed to fetch filters:', err);
    }
  };

  const handleSearch = async () => {
    if (!user) return;
    setSearching(true);
    setHasSearched(true);
    try {
      const response = await client.apiCall.invoke({
        url: '/api/v1/search/businesses',
        method: 'POST',
        data: {
          query: query || null,
          country: (country && country !== 'all_countries') ? country : null,
          category: (category && category !== 'all_categories') ? category : null,
          web_presence: webPresence || 'all',
          limit: 20,
        },
        options: { timeout: 600_000 },
      });
      setResults(response.data?.results || []);
    } catch (err) {
      console.error('Search failed:', err);
      toast.error('Search failed. Please try again.');
    } finally {
      setSearching(false);
    }
  };

  const saveAsLead = async (business: BusinessResult, index: number) => {
    setSavingIndex(index);
    try {
      await client.entities.leads.create({
        data: {
          business_name: business.business_name,
          category: business.category,
          location: business.location,
          country: business.country,
          website_url: business.website_url || '',
          website_score: business.website_score,
          social_score: business.social_score,
          has_website: business.has_website,
          social_platforms: JSON.stringify(business.social_platforms),
          contact_email: business.contact_email || '',
          contact_phone: business.contact_phone || '',
          pipeline_stage: 'new_lead',
          priority: business.website_score === 0 && business.social_score < 20 ? 'high' : 'medium',
          notes_count: 0,
          last_contacted: '',
        },
      });
      toast.success(`${business.business_name} saved as a lead!`);
    } catch (err) {
      console.error('Failed to save lead:', err);
      toast.error('Failed to save lead. Please try again.');
    } finally {
      setSavingIndex(null);
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
          <h2 className="font-[Poppins] text-2xl font-semibold">Sign in to search businesses</h2>
          <p className="mt-2 text-muted-foreground">Find businesses with weak digital presence worldwide.</p>
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
          <h1 className="font-[Poppins] text-2xl font-bold text-foreground">AI Business Discovery</h1>
          <p className="text-sm text-muted-foreground">
            AI-powered discovery of real businesses worldwide with weak digital presence
          </p>
        </div>

        {/* Search Filters */}
        <Card>
          <CardContent className="p-5">
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <div className="space-y-1.5">
                <Label htmlFor="query" className="text-sm font-medium">Search Query</Label>
                <Input
                  id="query"
                  placeholder="Business name, keyword..."
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                />
              </div>

              <div className="space-y-1.5">
                <Label className="text-sm font-medium">Country</Label>
                <Select value={country} onValueChange={setCountry}>
                  <SelectTrigger>
                    <SelectValue placeholder="All Countries" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all_countries">All Countries</SelectItem>
                    {filters?.countries.map((c) => (
                      <SelectItem key={c} value={c}>{c}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-1.5">
                <Label className="text-sm font-medium">Category</Label>
                <Select value={category} onValueChange={setCategory}>
                  <SelectTrigger>
                    <SelectValue placeholder="All Categories" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all_categories">All Categories</SelectItem>
                    {filters?.categories.map((c) => (
                      <SelectItem key={c} value={c}>{c}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-1.5">
                <Label className="text-sm font-medium">Web Presence</Label>
                <Select value={webPresence} onValueChange={setWebPresence}>
                  <SelectTrigger>
                    <SelectValue placeholder="All" />
                  </SelectTrigger>
                  <SelectContent>
                    {filters?.web_presence_options.map((opt) => (
                      <SelectItem key={opt.value} value={opt.value}>{opt.label}</SelectItem>
                    )) || (
                      <>
                        <SelectItem value="all">All Weak Presence</SelectItem>
                        <SelectItem value="no_website">No Website</SelectItem>
                        <SelectItem value="weak_website">Weak Website</SelectItem>
                        <SelectItem value="weak_social">Weak Social Media</SelectItem>
                      </>
                    )}
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="mt-4 flex items-center justify-between">
              <p className="text-xs text-muted-foreground">
                🤖 AI analyzes real market data to find businesses needing digital services
              </p>
              <Button onClick={handleSearch} disabled={searching} className="gap-2">
                <SearchIcon className="h-4 w-4" />
                {searching ? 'AI Discovering...' : 'Discover Businesses'}
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* Results */}
        {searching ? (
          <div className="space-y-4">
            <div className="flex items-center justify-center gap-3 rounded-lg border border-dashed p-6">
              <div className="h-5 w-5 animate-spin rounded-full border-2 border-primary border-t-transparent" />
              <p className="text-sm text-muted-foreground">
                AI is analyzing real businesses in the target market... This may take 15-30 seconds.
              </p>
            </div>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {[...Array(6)].map((_, i) => (
                <Skeleton key={i} className="h-48 rounded-xl" />
              ))}
            </div>
          </div>
        ) : hasSearched && results.length === 0 ? (
          <div className="flex flex-col items-center py-12 text-center">
            <AlertCircle className="mb-3 h-10 w-10 text-muted-foreground/50" />
            <p className="text-muted-foreground">No businesses found. Try adjusting your filters.</p>
          </div>
        ) : results.length > 0 ? (
          <>
            <div className="flex items-center justify-between">
              <p className="text-sm text-muted-foreground">
                Found <span className="font-medium text-foreground">{results.length}</span> businesses
              </p>
            </div>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {results.map((business, index) => (
                <BusinessCard
                  key={index}
                  business={business}
                  onSave={() => saveAsLead(business, index)}
                  saving={savingIndex === index}
                />
              ))}
            </div>
          </>
        ) : (
          <div className="flex flex-col items-center py-16 text-center">
            <Globe className="mb-4 h-16 w-16 text-muted-foreground/30" />
            <h3 className="font-[Poppins] text-lg font-semibold text-foreground">
              Search for businesses worldwide
            </h3>
            <p className="mt-2 max-w-md text-sm text-muted-foreground">
              Use the filters above to find local businesses with weak digital presence. 
              Save promising results as leads to your CRM pipeline.
            </p>
          </div>
        )}
      </div>
    </AppLayout>
  );
}

function BusinessCard({
  business,
  onSave,
  saving,
}: {
  business: BusinessResult;
  onSave: () => void;
  saving: boolean;
}) {
  const getPresenceLevel = (score: number) => {
    if (score === 0) return { label: 'None', color: 'bg-red-100 text-red-700' };
    if (score < 25) return { label: 'Very Weak', color: 'bg-orange-100 text-orange-700' };
    if (score < 50) return { label: 'Weak', color: 'bg-yellow-100 text-yellow-700' };
    return { label: 'Moderate', color: 'bg-green-100 text-green-700' };
  };

  const webLevel = getPresenceLevel(business.website_score);
  const socialLevel = getPresenceLevel(business.social_score);

  return (
    <Card className="flex flex-col transition-shadow hover:shadow-md">
      <CardContent className="flex flex-1 flex-col p-5">
        <div className="flex-1">
          {/* Header */}
          <div className="flex items-start justify-between gap-2">
            <h3 className="font-[Poppins] font-semibold text-foreground leading-tight">
              {business.business_name}
            </h3>
            {business.has_website ? (
              <Wifi className="h-4 w-4 shrink-0 text-yellow-500" />
            ) : (
              <WifiOff className="h-4 w-4 shrink-0 text-red-500" />
            )}
          </div>

          {/* Meta */}
          <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            <span className="flex items-center gap-1">
              <Building2 className="h-3 w-3" />
              {business.category}
            </span>
            <span className="flex items-center gap-1">
              <MapPin className="h-3 w-3" />
              {business.location}
            </span>
          </div>

          {/* Scores */}
          <div className="mt-3 flex flex-wrap gap-2">
            <Badge variant="outline" className={`text-xs ${webLevel.color} border-0`}>
              Web: {webLevel.label}
            </Badge>
            <Badge variant="outline" className={`text-xs ${socialLevel.color} border-0`}>
              Social: {socialLevel.label}
            </Badge>
          </div>

          {/* Social Platforms */}
          {business.social_platforms.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1">
              {business.social_platforms.map((platform) => (
                <span key={platform} className="rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground capitalize">
                  {platform}
                </span>
              ))}
            </div>
          )}

          {/* Website Link */}
          {business.website_url && (
            <a
              href={business.website_url}
              target="_blank"
              rel="noopener noreferrer"
              className="mt-2 inline-flex items-center gap-1 text-xs text-primary hover:underline"
            >
              <ExternalLink className="h-3 w-3" />
              {business.website_url.replace(/^https?:\/\//, '')}
            </a>
          )}
        </div>

        {/* Action */}
        <Button
          onClick={onSave}
          disabled={saving}
          size="sm"
          className="mt-4 w-full gap-2"
          variant="outline"
        >
          <Plus className="h-4 w-4" />
          {saving ? 'Saving...' : 'Save as Lead'}
        </Button>
      </CardContent>
    </Card>
  );
}