import { useState, useEffect } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import AppLayout from '@/components/AppLayout';
import { client } from '@/lib/api';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { toast } from 'sonner';
import {
  Bot, Sparkles, Mail, FileText, Globe, Zap,
  CheckCircle2, AlertTriangle, ArrowRight, Copy, Send,
  RefreshCw, Target, TrendingUp, Users, Clock,
  Filter, History, BarChart3, Building2, Signal,
  Calendar, DollarSign, UserCheck
} from 'lucide-react';

interface GeneratedLead {
  business_name: string;
  category: string;
  location: string;
  country: string;
  contact_email: string;
  website_score: number;
  social_score: number;
  has_website: boolean;
  notes: string;
  priority: string;
  estimated_employees?: number;
  years_operating?: number;
  opportunity_score?: number;
}

interface FollowUpEmail {
  subject: string;
  body: string;
  suggested_action: string;
  lead_name: string;
}

interface DailyReport {
  summary: string;
  metrics: Record<string, any>;
  action_items: string[];
  urgent_leads: string[];
  recommendations: string[];
  generated_at: string;
  raw_stats: {
    total_leads: number;
    by_stage: Record<string, number>;
    by_priority: Record<string, number>;
    conversion_rate?: number;
  };
}

interface InteractionLog {
  id: number;
  action_type: string;
  input_summary: string;
  output_summary: string;
  status: string;
  lead_id: number | null;
  duration_ms: number;
  created_at: string;
}

export default function Automation() {
  const { user, loading: authLoading, login } = useAuth();

  // Lead generation state
  const [genCountry, setGenCountry] = useState('');
  const [genCategory, setGenCategory] = useState('');
  const [genCount, setGenCount] = useState(5);
  const [generating, setGenerating] = useState(false);
  const [generatedLeads, setGeneratedLeads] = useState<GeneratedLead[]>([]);
  // Advanced targeting
  const [businessSize, setBusinessSize] = useState('');
  const [yearsInBusiness, setYearsInBusiness] = useState('');
  const [targetRevenue, setTargetRevenue] = useState('');
  const [intentSignals, setIntentSignals] = useState<string[]>([]);
  const [showAdvanced, setShowAdvanced] = useState(false);

  // Follow-up email state
  const [leadId, setLeadId] = useState('');
  const [emailTone, setEmailTone] = useState('');
  const [customMessage, setCustomMessage] = useState('');
  const [generatingEmail, setGeneratingEmail] = useState(false);
  const [followUpEmail, setFollowUpEmail] = useState<FollowUpEmail | null>(null);
  const [sendingEmail, setSendingEmail] = useState(false);

  // Daily report state
  const [generatingReport, setGeneratingReport] = useState(false);
  const [dailyReport, setDailyReport] = useState<DailyReport | null>(null);

  // Interaction logs state
  const [logs, setLogs] = useState<InteractionLog[]>([]);
  const [logsLoading, setLogsLoading] = useState(false);
  const [logsTotal, setLogsTotal] = useState(0);
  const [logFilter, setLogFilter] = useState('');

  const handleGenerateLeads = async () => {
    setGenerating(true);
    setGeneratedLeads([]);
    try {
      const response = await client.apiCall.invoke({
        url: '/api/v1/automation/generate-leads',
        method: 'POST',
        data: {
          country: genCountry || null,
          category: genCategory || null,
          count: genCount,
          business_size: businessSize || null,
          years_in_business: yearsInBusiness || null,
          target_revenue: targetRevenue || null,
          intent_signals: intentSignals.length > 0 ? intentSignals : null,
        },
        options: { timeout: 600_000 },
      });
      setGeneratedLeads(response.data?.leads || []);
      toast.success(`${response.data?.leads_generated || 0} new leads generated and saved!`);
      fetchLogs();
    } catch (err: any) {
      const msg = err?.data?.detail || err?.message || 'Failed to generate leads';
      toast.error(msg);
    } finally {
      setGenerating(false);
    }
  };

  const handleGenerateEmail = async () => {
    if (!leadId) {
      toast.error('Please enter a lead ID');
      return;
    }
    setGeneratingEmail(true);
    setFollowUpEmail(null);
    try {
      const response = await client.apiCall.invoke({
        url: '/api/v1/automation/follow-up-email',
        method: 'POST',
        data: {
          lead_id: parseInt(leadId),
          tone: emailTone || null,
          custom_message: customMessage || null,
        },
        options: { timeout: 600_000 },
      });
      setFollowUpEmail(response.data);
      toast.success('Follow-up email generated!');
      fetchLogs();
    } catch (err: any) {
      const msg = err?.data?.detail || err?.message || 'Failed to generate email';
      toast.error(msg);
    } finally {
      setGeneratingEmail(false);
    }
  };

  const handleSendEmail = async () => {
    if (!leadId || !followUpEmail) return;
    setSendingEmail(true);
    try {
      const response = await client.apiCall.invoke({
        url: '/api/v1/automation/send-email',
        method: 'POST',
        data: {
          lead_id: parseInt(leadId),
          subject: followUpEmail.subject,
          body: followUpEmail.body,
        },
        options: { timeout: 600_000 },
      });
      if (response.data?.status === 'queued') {
        toast.success(`Email sent to ${response.data.to}! Delivery: ${response.data.delivery_estimate}`);
      } else {
        toast.error(response.data?.error || 'Failed to send email');
      }
      fetchLogs();
    } catch (err: any) {
      const msg = err?.data?.detail || err?.message || 'Failed to send email';
      toast.error(msg);
    } finally {
      setSendingEmail(false);
    }
  };

  const handleGenerateReport = async () => {
    setGeneratingReport(true);
    setDailyReport(null);
    try {
      const response = await client.apiCall.invoke({
        url: '/api/v1/automation/daily-report',
        method: 'GET',
        data: {},
        options: { timeout: 600_000 },
      });
      setDailyReport(response.data);
      toast.success('Daily report generated!');
      fetchLogs();
    } catch (err: any) {
      const msg = err?.data?.detail || err?.message || 'Failed to generate report';
      toast.error(msg);
    } finally {
      setGeneratingReport(false);
    }
  };

  const fetchLogs = async () => {
    setLogsLoading(true);
    try {
      const params: any = { page: 1, per_page: 20 };
      if (logFilter) params.action_type = logFilter;
      const response = await client.apiCall.invoke({
        url: '/api/v1/automation/interaction-logs',
        method: 'GET',
        data: params,
        options: { timeout: 30_000 },
      });
      setLogs(response.data?.logs || []);
      setLogsTotal(response.data?.total || 0);
    } catch {
      // Silent fail for logs
    } finally {
      setLogsLoading(false);
    }
  };

  useEffect(() => {
    if (user) fetchLogs();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user, logFilter]);

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    toast.success('Copied to clipboard!');
  };

  const toggleIntentSignal = (signal: string) => {
    setIntentSignals(prev =>
      prev.includes(signal)
        ? prev.filter(s => s !== signal)
        : [...prev, signal]
    );
  };

  const getActionIcon = (type: string) => {
    switch (type) {
      case 'generate_leads': return <Sparkles className="h-3.5 w-3.5 text-purple-500" />;
      case 'follow_up_email': return <Mail className="h-3.5 w-3.5 text-blue-500" />;
      case 'send_email': return <Send className="h-3.5 w-3.5 text-green-500" />;
      case 'daily_report': return <FileText className="h-3.5 w-3.5 text-orange-500" />;
      default: return <Bot className="h-3.5 w-3.5 text-gray-500" />;
    }
  };

  const formatDuration = (ms: number) => {
    if (ms < 1000) return `${ms}ms`;
    return `${(ms / 1000).toFixed(1)}s`;
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
          <Bot className="mb-4 h-12 w-12 text-muted-foreground" />
          <h2 className="font-[Poppins] text-2xl font-semibold">Sign in to access AI Automation</h2>
          <p className="mt-2 text-muted-foreground">Automate lead generation, follow-ups, and reporting.</p>
          <Button onClick={login} className="mt-6">Sign In</Button>
        </div>
      </AppLayout>
    );
  }

  return (
    <AppLayout>
      <div className="space-y-6">
        {/* Header */}
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-gradient-to-br from-purple-500 to-blue-600">
              <Bot className="h-5 w-5 text-white" />
            </div>
            <div>
              <h1 className="font-[Poppins] text-2xl font-bold text-foreground">AI Automation Center</h1>
              <p className="text-sm text-muted-foreground">
                Intelligent lead discovery, outreach, and reporting powered by AI
              </p>
            </div>
          </div>
          {logsTotal > 0 && (
            <Badge variant="secondary" className="gap-1.5 self-start">
              <History className="h-3.5 w-3.5" />
              {logsTotal} AI interactions
            </Badge>
          )}
        </div>

        <Tabs defaultValue="generate" className="space-y-4">
          <TabsList className="grid w-full grid-cols-4">
            <TabsTrigger value="generate" className="gap-1.5 text-xs sm:text-sm">
              <Sparkles className="h-4 w-4" />
              <span className="hidden sm:inline">Generate</span> Leads
            </TabsTrigger>
            <TabsTrigger value="followup" className="gap-1.5 text-xs sm:text-sm">
              <Mail className="h-4 w-4" />
              <span className="hidden sm:inline">Follow-Up</span> Emails
            </TabsTrigger>
            <TabsTrigger value="report" className="gap-1.5 text-xs sm:text-sm">
              <FileText className="h-4 w-4" />
              <span className="hidden sm:inline">Daily</span> Report
            </TabsTrigger>
            <TabsTrigger value="logs" className="gap-1.5 text-xs sm:text-sm">
              <History className="h-4 w-4" />
              <span className="hidden sm:inline">Activity</span> Log
            </TabsTrigger>
          </TabsList>

          {/* ═══════════════ AUTO LEAD GENERATION TAB ═══════════════ */}
          <TabsContent value="generate" className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 font-[Poppins]">
                  <Sparkles className="h-5 w-5 text-purple-500" />
                  AI Lead Generator
                </CardTitle>
                <CardDescription>
                  Discover businesses with weak digital presence using AI-powered targeting.
                  Advanced filters help you find the most qualified leads for your services.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                {/* Basic Filters */}
                <div className="grid gap-4 sm:grid-cols-3">
                  <div>
                    <label className="mb-1.5 block text-sm font-medium">Country</label>
                    <Input
                      placeholder="e.g., United States, Germany"
                      value={genCountry}
                      onChange={(e) => setGenCountry(e.target.value)}
                    />
                  </div>
                  <div>
                    <label className="mb-1.5 block text-sm font-medium">Industry Category</label>
                    <Input
                      placeholder="e.g., Restaurant, Dentistry"
                      value={genCategory}
                      onChange={(e) => setGenCategory(e.target.value)}
                    />
                  </div>
                  <div>
                    <label className="mb-1.5 block text-sm font-medium">Number of Leads</label>
                    <Select value={String(genCount)} onValueChange={(v) => setGenCount(Number(v))}>
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="3">3 leads</SelectItem>
                        <SelectItem value="5">5 leads</SelectItem>
                        <SelectItem value="10">10 leads</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>

                {/* Advanced Targeting Toggle */}
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setShowAdvanced(!showAdvanced)}
                  className="gap-2"
                >
                  <Filter className="h-4 w-4" />
                  {showAdvanced ? 'Hide' : 'Show'} Advanced Targeting
                </Button>

                {/* Advanced Filters */}
                {showAdvanced && (
                  <div className="space-y-4 rounded-lg border border-dashed border-purple-200 bg-purple-50/50 p-4 dark:border-purple-800 dark:bg-purple-950/20">
                    <p className="text-xs font-medium text-purple-700 dark:text-purple-300">
                      🎯 Advanced Targeting — Find higher-quality leads
                    </p>
                    <div className="grid gap-4 sm:grid-cols-3">
                      <div>
                        <label className="mb-1.5 flex items-center gap-1.5 text-sm font-medium">
                          <Building2 className="h-3.5 w-3.5" /> Business Size
                        </label>
                        <Select value={businessSize} onValueChange={setBusinessSize}>
                          <SelectTrigger>
                            <SelectValue placeholder="Any size" />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="any">Any size</SelectItem>
                            <SelectItem value="small">Small (1-10 employees)</SelectItem>
                            <SelectItem value="medium">Medium (11-50)</SelectItem>
                            <SelectItem value="large">Large (50+)</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>
                      <div>
                        <label className="mb-1.5 flex items-center gap-1.5 text-sm font-medium">
                          <Calendar className="h-3.5 w-3.5" /> Years in Business
                        </label>
                        <Select value={yearsInBusiness} onValueChange={setYearsInBusiness}>
                          <SelectTrigger>
                            <SelectValue placeholder="Any age" />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="any">Any age</SelectItem>
                            <SelectItem value="new">New (0-2 years)</SelectItem>
                            <SelectItem value="established">Established (3-10)</SelectItem>
                            <SelectItem value="veteran">Veteran (10+)</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>
                      <div>
                        <label className="mb-1.5 flex items-center gap-1.5 text-sm font-medium">
                          <DollarSign className="h-3.5 w-3.5" /> Target Revenue
                        </label>
                        <Select value={targetRevenue} onValueChange={setTargetRevenue}>
                          <SelectTrigger>
                            <SelectValue placeholder="Any revenue" />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="any">Any revenue</SelectItem>
                            <SelectItem value="under_100k">Under $100K</SelectItem>
                            <SelectItem value="100k_500k">$100K - $500K</SelectItem>
                            <SelectItem value="500k_1m">$500K - $1M</SelectItem>
                            <SelectItem value="over_1m">Over $1M</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>
                    </div>

                    {/* Intent Signals */}
                    <div>
                      <label className="mb-2 flex items-center gap-1.5 text-sm font-medium">
                        <Signal className="h-3.5 w-3.5" /> Intent Signals
                        <span className="text-xs font-normal text-muted-foreground">(select all that apply)</span>
                      </label>
                      <div className="flex flex-wrap gap-2">
                        {[
                          { value: 'hiring', label: '🧑‍💼 Hiring', desc: 'Currently hiring' },
                          { value: 'expanding', label: '📈 Expanding', desc: 'Growing services' },
                          { value: 'rebranding', label: '🎨 Rebranding', desc: 'New look/identity' },
                          { value: 'new_location', label: '📍 New Location', desc: 'Opening new spot' },
                        ].map(signal => (
                          <Button
                            key={signal.value}
                            variant={intentSignals.includes(signal.value) ? 'default' : 'outline'}
                            size="sm"
                            onClick={() => toggleIntentSignal(signal.value)}
                            className="gap-1.5 text-xs"
                          >
                            {signal.label}
                          </Button>
                        ))}
                      </div>
                    </div>
                  </div>
                )}

                <Button
                  onClick={handleGenerateLeads}
                  disabled={generating}
                  className="gap-2"
                  size="lg"
                >
                  {generating ? (
                    <>
                      <RefreshCw className="h-4 w-4 animate-spin" />
                      AI is discovering leads...
                    </>
                  ) : (
                    <>
                      <Zap className="h-4 w-4" />
                      Generate New Leads
                    </>
                  )}
                </Button>
              </CardContent>
            </Card>

            {/* Generated leads results */}
            {generatedLeads.length > 0 && (
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-base font-[Poppins]">
                    <CheckCircle2 className="h-5 w-5 text-green-500" />
                    {generatedLeads.length} Leads Generated & Saved to CRM
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-3">
                    {generatedLeads.map((lead, idx) => (
                      <div key={idx} className="rounded-lg border p-4 transition-colors hover:bg-muted/30">
                        <div className="flex items-start justify-between gap-3">
                          <div className="flex-1">
                            <div className="flex items-center gap-2">
                              <p className="font-medium text-foreground">{lead.business_name}</p>
                              {lead.opportunity_score && lead.opportunity_score >= 7 && (
                                <Badge className="bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300 text-[10px]">
                                  🔥 High Opportunity
                                </Badge>
                              )}
                            </div>
                            <p className="text-sm text-muted-foreground">
                              {lead.category} • {lead.location}
                            </p>
                            {lead.contact_email && (
                              <p className="mt-0.5 text-xs text-muted-foreground">
                                ✉️ {lead.contact_email}
                              </p>
                            )}
                            {lead.notes && (
                              <p className="mt-1.5 text-xs text-muted-foreground/80 italic leading-relaxed">
                                💡 {lead.notes}
                              </p>
                            )}
                            <div className="mt-2 flex flex-wrap gap-2">
                              {lead.estimated_employees && (
                                <span className="text-[10px] text-muted-foreground">
                                  👥 ~{lead.estimated_employees} employees
                                </span>
                              )}
                              {lead.years_operating && (
                                <span className="text-[10px] text-muted-foreground">
                                  📅 ~{lead.years_operating} years
                                </span>
                              )}
                            </div>
                          </div>
                          <div className="flex flex-col items-end gap-1.5">
                            <Badge variant="outline" className="text-xs">
                              Web: {lead.website_score}/100
                            </Badge>
                            <Badge variant="outline" className="text-xs">
                              Social: {lead.social_score}/100
                            </Badge>
                            <Badge
                              className={`text-[10px] ${
                                lead.priority === 'high'
                                  ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300'
                                  : lead.priority === 'medium'
                                  ? 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-300'
                                  : 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300'
                              }`}
                            >
                              {lead.priority}
                            </Badge>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            )}
          </TabsContent>

          {/* ═══════════════ FOLLOW-UP EMAIL TAB ═══════════════ */}
          <TabsContent value="followup" className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 font-[Poppins]">
                  <Mail className="h-5 w-5 text-blue-500" />
                  AI Follow-Up Email & Direct Send
                </CardTitle>
                <CardDescription>
                  Generate personalized follow-up emails and send them directly to leads.
                  AI adapts tone and content based on pipeline stage and digital gaps.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid gap-4 sm:grid-cols-2">
                  <div>
                    <label className="mb-1.5 block text-sm font-medium">Lead ID</label>
                    <Input
                      placeholder="Enter lead ID number"
                      value={leadId}
                      onChange={(e) => setLeadId(e.target.value)}
                      type="number"
                    />
                  </div>
                  <div>
                    <label className="mb-1.5 block text-sm font-medium">Email Tone</label>
                    <Select value={emailTone} onValueChange={setEmailTone}>
                      <SelectTrigger>
                        <SelectValue placeholder="Auto (based on stage)" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="auto">Auto (based on stage)</SelectItem>
                        <SelectItem value="professional">Professional & Formal</SelectItem>
                        <SelectItem value="friendly">Friendly & Warm</SelectItem>
                        <SelectItem value="urgent">Urgent & Action-Oriented</SelectItem>
                        <SelectItem value="casual">Casual & Relaxed</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>
                <div>
                  <label className="mb-1.5 block text-sm font-medium">Custom Context (optional)</label>
                  <Textarea
                    placeholder="Add any specific context, talking points, or offers to include..."
                    value={customMessage}
                    onChange={(e) => setCustomMessage(e.target.value)}
                    rows={2}
                  />
                </div>
                <div className="flex gap-3">
                  <Button
                    onClick={handleGenerateEmail}
                    disabled={generatingEmail || !leadId}
                    className="gap-2"
                  >
                    {generatingEmail ? (
                      <>
                        <RefreshCw className="h-4 w-4 animate-spin" />
                        Generating...
                      </>
                    ) : (
                      <>
                        <Sparkles className="h-4 w-4" />
                        Generate Email
                      </>
                    )}
                  </Button>
                </div>
                <p className="text-xs text-muted-foreground">
                  💡 Tip: Find lead IDs on the All Leads or Lead Detail pages.
                </p>
              </CardContent>
            </Card>

            {/* Generated email result */}
            {followUpEmail && (
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-base font-[Poppins]">
                    <CheckCircle2 className="h-5 w-5 text-green-500" />
                    Email for {followUpEmail.lead_name}
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div>
                    <label className="mb-1 block text-sm font-medium text-muted-foreground">Subject</label>
                    <div className="flex items-center gap-2">
                      <p className="flex-1 rounded-md border bg-muted/30 px-3 py-2 text-sm font-medium">
                        {followUpEmail.subject}
                      </p>
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => copyToClipboard(followUpEmail.subject)}
                      >
                        <Copy className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                  <div>
                    <label className="mb-1 block text-sm font-medium text-muted-foreground">Body</label>
                    <div className="relative">
                      <pre className="whitespace-pre-wrap rounded-md border bg-muted/30 p-4 text-sm leading-relaxed">
                        {followUpEmail.body}
                      </pre>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="absolute right-2 top-2"
                        onClick={() => copyToClipboard(followUpEmail.body)}
                      >
                        <Copy className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 rounded-md bg-blue-50 p-3 dark:bg-blue-950/30">
                    <ArrowRight className="h-4 w-4 text-blue-600" />
                    <p className="text-sm text-blue-700 dark:text-blue-300">
                      <strong>Next step:</strong> {followUpEmail.suggested_action}
                    </p>
                  </div>

                  {/* Send Email Button */}
                  <div className="flex gap-3 border-t pt-4">
                    <Button
                      onClick={handleSendEmail}
                      disabled={sendingEmail}
                      className="gap-2 bg-green-600 hover:bg-green-700"
                    >
                      {sendingEmail ? (
                        <>
                          <RefreshCw className="h-4 w-4 animate-spin" />
                          Sending...
                        </>
                      ) : (
                        <>
                          <Send className="h-4 w-4" />
                          Send Email Directly
                        </>
                      )}
                    </Button>
                    <Button
                      variant="outline"
                      onClick={() => copyToClipboard(`Subject: ${followUpEmail.subject}\n\n${followUpEmail.body}`)}
                      className="gap-2"
                    >
                      <Copy className="h-4 w-4" />
                      Copy Full Email
                    </Button>
                  </div>
                </CardContent>
              </Card>
            )}
          </TabsContent>

          {/* ═══════════════ DAILY REPORT TAB ═══════════════ */}
          <TabsContent value="report" className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 font-[Poppins]">
                  <FileText className="h-5 w-5 text-orange-500" />
                  AI Daily Report
                </CardTitle>
                <CardDescription>
                  Get an AI-generated executive summary with actionable insights,
                  conversion metrics, and strategic recommendations.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <Button
                  onClick={handleGenerateReport}
                  disabled={generatingReport}
                  className="gap-2"
                  size="lg"
                >
                  {generatingReport ? (
                    <>
                      <RefreshCw className="h-4 w-4 animate-spin" />
                      Analyzing your pipeline...
                    </>
                  ) : (
                    <>
                      <BarChart3 className="h-4 w-4" />
                      Generate Daily Report
                    </>
                  )}
                </Button>
              </CardContent>
            </Card>

            {/* Report result */}
            {dailyReport && (
              <div className="space-y-4">
                {/* Summary */}
                <Card>
                  <CardHeader className="pb-3">
                    <CardTitle className="text-base font-[Poppins]">Executive Summary</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <p className="text-sm leading-relaxed text-foreground">{dailyReport.summary}</p>
                  </CardContent>
                </Card>

                {/* Metrics */}
                <div className="grid gap-4 sm:grid-cols-4">
                  <Card>
                    <CardContent className="flex items-center gap-3 p-4">
                      <Users className="h-8 w-8 text-primary" />
                      <div>
                        <p className="text-2xl font-bold">{dailyReport.raw_stats.total_leads}</p>
                        <p className="text-xs text-muted-foreground">Total Leads</p>
                      </div>
                    </CardContent>
                  </Card>
                  <Card>
                    <CardContent className="flex items-center gap-3 p-4">
                      <Target className="h-8 w-8 text-green-500" />
                      <div>
                        <p className="text-2xl font-bold">{dailyReport.raw_stats.by_stage?.won || 0}</p>
                        <p className="text-xs text-muted-foreground">Won</p>
                      </div>
                    </CardContent>
                  </Card>
                  <Card>
                    <CardContent className="flex items-center gap-3 p-4">
                      <TrendingUp className="h-8 w-8 text-purple-500" />
                      <div>
                        <p className="text-2xl font-bold">{dailyReport.raw_stats.by_stage?.in_progress || 0}</p>
                        <p className="text-xs text-muted-foreground">In Progress</p>
                      </div>
                    </CardContent>
                  </Card>
                  <Card>
                    <CardContent className="flex items-center gap-3 p-4">
                      <UserCheck className="h-8 w-8 text-blue-500" />
                      <div>
                        <p className="text-2xl font-bold">{dailyReport.raw_stats.conversion_rate || 0}%</p>
                        <p className="text-xs text-muted-foreground">Conversion</p>
                      </div>
                    </CardContent>
                  </Card>
                </div>

                {/* Action Items */}
                <Card>
                  <CardHeader className="pb-3">
                    <CardTitle className="flex items-center gap-2 text-base font-[Poppins]">
                      <Zap className="h-4 w-4 text-yellow-500" />
                      Action Items for Today
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <ul className="space-y-2">
                      {dailyReport.action_items.map((item, idx) => (
                        <li key={idx} className="flex items-start gap-2 text-sm">
                          <CheckCircle2 className="mt-0.5 h-4 w-4 flex-shrink-0 text-green-500" />
                          <span>{item}</span>
                        </li>
                      ))}
                    </ul>
                  </CardContent>
                </Card>

                {/* Urgent Leads */}
                {dailyReport.urgent_leads.length > 0 && (
                  <Card>
                    <CardHeader className="pb-3">
                      <CardTitle className="flex items-center gap-2 text-base font-[Poppins]">
                        <AlertTriangle className="h-4 w-4 text-red-500" />
                        Leads Requiring Attention
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="flex flex-wrap gap-2">
                        {dailyReport.urgent_leads.map((name, idx) => (
                          <Badge key={idx} variant="destructive" className="text-xs">
                            {name}
                          </Badge>
                        ))}
                      </div>
                    </CardContent>
                  </Card>
                )}

                {/* Recommendations */}
                <Card>
                  <CardHeader className="pb-3">
                    <CardTitle className="flex items-center gap-2 text-base font-[Poppins]">
                      <Globe className="h-4 w-4 text-blue-500" />
                      Strategic Recommendations
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <ul className="space-y-2">
                      {dailyReport.recommendations.map((rec, idx) => (
                        <li key={idx} className="flex items-start gap-2 text-sm">
                          <ArrowRight className="mt-0.5 h-4 w-4 flex-shrink-0 text-blue-500" />
                          <span>{rec}</span>
                        </li>
                      ))}
                    </ul>
                  </CardContent>
                </Card>
              </div>
            )}
          </TabsContent>

          {/* ═══════════════ ACTIVITY LOG TAB ═══════════════ */}
          <TabsContent value="logs" className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 font-[Poppins]">
                  <History className="h-5 w-5 text-indigo-500" />
                  AI Interaction History
                </CardTitle>
                <CardDescription>
                  Track all your AI-powered actions — lead generation, email creation,
                  email sends, and report generation with timing and status.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex items-center gap-3">
                  <Select value={logFilter} onValueChange={setLogFilter}>
                    <SelectTrigger className="w-[200px]">
                      <SelectValue placeholder="All actions" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">All actions</SelectItem>
                      <SelectItem value="generate_leads">Generate Leads</SelectItem>
                      <SelectItem value="follow_up_email">Follow-Up Emails</SelectItem>
                      <SelectItem value="send_email">Sent Emails</SelectItem>
                      <SelectItem value="daily_report">Daily Reports</SelectItem>
                    </SelectContent>
                  </Select>
                  <Button variant="outline" size="sm" onClick={fetchLogs} className="gap-1.5">
                    <RefreshCw className="h-3.5 w-3.5" />
                    Refresh
                  </Button>
                  <span className="text-xs text-muted-foreground">
                    {logsTotal} total interactions
                  </span>
                </div>

                {logsLoading ? (
                  <div className="flex items-center justify-center py-8">
                    <RefreshCw className="h-5 w-5 animate-spin text-muted-foreground" />
                  </div>
                ) : logs.length === 0 ? (
                  <div className="flex flex-col items-center justify-center py-8 text-center">
                    <History className="mb-2 h-8 w-8 text-muted-foreground/50" />
                    <p className="text-sm text-muted-foreground">No interactions yet</p>
                    <p className="text-xs text-muted-foreground/70">
                      Use the AI features above to start building your activity log
                    </p>
                  </div>
                ) : (
                  <div className="space-y-2">
                    {logs.map((log) => (
                      <div
                        key={log.id}
                        className="flex items-start gap-3 rounded-lg border p-3 transition-colors hover:bg-muted/30"
                      >
                        <div className="mt-0.5">
                          {getActionIcon(log.action_type)}
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-medium capitalize">
                              {log.action_type.replace(/_/g, ' ')}
                            </span>
                            <Badge
                              variant={log.status === 'success' ? 'default' : 'destructive'}
                              className="text-[10px]"
                            >
                              {log.status}
                            </Badge>
                          </div>
                          <p className="mt-0.5 truncate text-xs text-muted-foreground">
                            {log.input_summary}
                          </p>
                          {log.output_summary && (
                            <p className="mt-0.5 truncate text-xs text-muted-foreground/70">
                              → {log.output_summary}
                            </p>
                          )}
                        </div>
                        <div className="flex flex-col items-end gap-1 text-[10px] text-muted-foreground">
                          <span className="flex items-center gap-1">
                            <Clock className="h-3 w-3" />
                            {formatDuration(log.duration_ms)}
                          </span>
                          <span>
                            {log.created_at ? new Date(log.created_at).toLocaleDateString() : ''}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </div>
    </AppLayout>
  );
}