import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Target, ArrowRight, Search, BarChart3, Zap, Shield, CheckCircle2, Star } from 'lucide-react';

export default function Index() {
  const { user, login, loading } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    if (user) {
      navigate('/app/dashboard');
    }
  }, [user, navigate]);

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-white">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-indigo-600 border-t-transparent" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-white">
      {/* Header */}
      <header className="border-b border-slate-100">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
          <div className="flex items-center gap-2">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-indigo-600">
              <Target className="h-5 w-5 text-white" />
            </div>
            <span className="font-semibold text-lg text-slate-900">BizLeads</span>
          </div>
          <nav className="hidden md:flex items-center gap-6">
            <button onClick={() => navigate('/pricing')} className="text-sm text-slate-600 hover:text-slate-900 font-medium">
              Pricing
            </button>
          </nav>
          <div className="flex items-center gap-2">
            <Button onClick={login} variant="ghost" size="sm" className="text-slate-700">
              Sign In
            </Button>
            <Button onClick={login} size="sm" className="bg-indigo-600 hover:bg-indigo-700">
              Start Free Trial
            </Button>
          </div>
        </div>
      </header>

      {/* Hero */}
      <section className="relative py-20 sm:py-28">
        <div className="absolute inset-0 bg-gradient-to-b from-indigo-50/50 to-white" />
        <div className="relative mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="mx-auto max-w-3xl text-center">
            <Badge variant="secondary" className="mb-4 bg-indigo-50 text-indigo-700 border-indigo-200">
              Website Opportunity Intelligence
            </Badge>
            <h1 className="text-4xl font-bold tracking-tight text-slate-900 sm:text-5xl lg:text-6xl">
              Find the businesses most likely to{' '}
              <span className="text-indigo-600">buy a better website</span>
            </h1>
            <p className="mt-6 text-lg leading-relaxed text-slate-600 sm:text-xl max-w-2xl mx-auto">
              Not just businesses with bad websites — businesses that are active, growing, 
              and ready to invest. BizLeads scores buyability, timing, and fit so you pitch 
              the right prospect at the right moment.
            </p>
            <div className="mt-10 flex flex-col items-center gap-4 sm:flex-row sm:justify-center">
              <Button onClick={login} size="lg" className="gap-2 px-8 bg-indigo-600 hover:bg-indigo-700">
                Start 7-Day Free Trial
                <ArrowRight className="h-4 w-4" />
              </Button>
              <Button onClick={() => navigate('/pricing')} variant="outline" size="lg" className="gap-2 px-8 border-slate-300">
                View Pricing
              </Button>
            </div>
            <p className="mt-4 text-sm text-slate-500">No credit card required · 25 discovery credits included</p>
          </div>
        </div>
      </section>

      {/* Differentiator */}
      <section className="py-16 border-t border-slate-100">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="mx-auto max-w-2xl text-center mb-12">
            <h2 className="text-2xl font-bold text-slate-900 sm:text-3xl">
              Beyond "bad website" lists
            </h2>
            <p className="mt-3 text-slate-600">
              Other tools find businesses with weak websites. BizLeads finds businesses 
              that will actually buy from you.
            </p>
          </div>

          <div className="grid gap-6 md:grid-cols-3">
            <div className="rounded-xl border border-slate-200 p-6">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-red-50 mb-4">
                <Search className="h-5 w-5 text-red-600" />
              </div>
              <h3 className="font-semibold text-slate-900 mb-2">6-Score Intelligence</h3>
              <p className="text-sm text-slate-600">
                Need, Buyability, Timing, Reachability, Agency Fit, and Evidence Confidence — 
                each with full breakdown and source citations. No unexplained single scores.
              </p>
            </div>

            <div className="rounded-xl border border-slate-200 p-6">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-amber-50 mb-4">
                <Zap className="h-5 w-5 text-amber-600" />
              </div>
              <h3 className="font-semibold text-slate-900 mb-2">Timing Signals</h3>
              <p className="text-sm text-slate-600">
                New locations, review acceleration, expired certificates, active ads with weak 
                landing pages, rebrands, hiring — evidence that now is the moment to pitch.
              </p>
            </div>

            <div className="rounded-xl border border-slate-200 p-6">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-green-50 mb-4">
                <BarChart3 className="h-5 w-5 text-green-600" />
              </div>
              <h3 className="font-semibold text-slate-900 mb-2">Expected Agency Value</h3>
              <p className="text-sm text-slate-600">
                Rank leads by your economics: reply probability × close rate × expected profit. 
                Calibrated by your actual outcomes over time.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* How it works */}
      <section className="py-16 bg-slate-50 border-t border-slate-100">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <h2 className="text-2xl font-bold text-slate-900 text-center mb-12 sm:text-3xl">
            Evidence-to-revenue in 4 steps
          </h2>
          <div className="grid gap-8 md:grid-cols-4">
            {[
              { step: '1', title: 'Discover', desc: 'AI-powered search finds real businesses matching your ideal client profile, scored across 6 dimensions.' },
              { step: '2', title: 'Qualify', desc: 'Deep audit reveals the exact digital gaps, timing signals, and buyability evidence for each prospect.' },
              { step: '3', title: 'Prove', desc: 'Generate a Revenue Gap Twin and shareable Proof Room showing the prospect exactly why they need you now.' },
              { step: '4', title: 'Close', desc: 'Evidence-based outreach with personalized pitches. Track outcomes and calibrate your scoring over time.' },
            ].map((item) => (
              <div key={item.step} className="text-center">
                <div className="mx-auto flex h-10 w-10 items-center justify-center rounded-full bg-indigo-600 text-white font-bold text-sm mb-4">
                  {item.step}
                </div>
                <h3 className="font-semibold text-slate-900 mb-2">{item.title}</h3>
                <p className="text-sm text-slate-600">{item.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Target users */}
      <section className="py-16 border-t border-slate-100">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <h2 className="text-2xl font-bold text-slate-900 text-center mb-8 sm:text-3xl">
            Built for web professionals
          </h2>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4 max-w-4xl mx-auto">
            {[
              'Freelance web designers',
              'WordPress & Webflow builders',
              'Small web design agencies',
              'Local SEO & marketing teams',
              'Shopify & e-commerce studios',
              'CRO & conversion specialists',
              'Framer & no-code builders',
              'Outbound sales teams',
            ].map((item) => (
              <div key={item} className="flex items-center gap-2 text-sm text-slate-700">
                <CheckCircle2 className="h-4 w-4 text-green-600 shrink-0" />
                {item}
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="py-16 bg-indigo-600">
        <div className="mx-auto max-w-3xl px-4 text-center">
          <h2 className="text-2xl font-bold text-white sm:text-3xl">
            Stop guessing. Start closing.
          </h2>
          <p className="mt-4 text-indigo-100">
            7-day free trial with 25 discovery credits. No credit card required.
          </p>
          <Button
            onClick={login}
            size="lg"
            className="mt-8 bg-white text-indigo-700 hover:bg-indigo-50 px-8"
          >
            Start Free Trial
            <ArrowRight className="ml-2 h-4 w-4" />
          </Button>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-slate-200 py-8">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="flex flex-col items-center justify-between gap-4 sm:flex-row">
            <div className="flex items-center gap-2">
              <div className="flex h-7 w-7 items-center justify-center rounded-md bg-indigo-600">
                <Target className="h-3.5 w-3.5 text-white" />
              </div>
              <span className="font-semibold text-sm text-slate-900">BizLeads</span>
            </div>
            <p className="text-xs text-slate-500">
              © 2024 BizLeads. Website Opportunity Intelligence.
            </p>
          </div>
        </div>
      </footer>
    </div>
  );
}