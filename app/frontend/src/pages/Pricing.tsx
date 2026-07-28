import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { CheckCircle2, ArrowRight } from 'lucide-react';
import { cn } from '@/lib/utils';
import { LogoMark } from '@/components/Logo';
import SiteFooter from '@/components/SiteFooter';

// Tiers differ by discovery volume only. Team seats were advertised here until
// it became clear nothing enforces or even offers them: `max_seats` is written
// by the billing webhook and displayed back, but read as a limit nowhere, and
// there is no invite flow — so an Agency customer could not add the ten people
// the page promised. Selling a seat count nobody can use is the same class of
// mistake as the fabricated leads this product was built to avoid. Put the
// lines back only once workspace-scoped tenancy and an invite flow ship.
const plans = [
  {
    id: 'solo',
    name: 'Solo',
    price: 29,
    description: 'For freelance web designers getting started',
    credits: '300',
    features: [
      '300 monthly discovery credits',
      'Website audit: HTTPS, mobile, titles, meta, structured data, tap-to-call',
      'Lead pipeline & CRM',
      'Analytics dashboard',
      'Email support',
    ],
    popular: false,
  },
  {
    id: 'pro',
    name: 'Pro',
    price: 79,
    description: 'For studios running outreach at a steady clip',
    credits: '1,500',
    features: [
      '1,500 monthly discovery credits',
      'Website audit: HTTPS, mobile, titles, meta, structured data, tap-to-call',
      'Lead pipeline & CRM',
      'Analytics dashboard',
      'Priority support',
    ],
    popular: true,
  },
  {
    id: 'agency',
    name: 'Agency',
    price: 199,
    description: 'For agencies prospecting across many markets',
    credits: '5,000',
    features: [
      '5,000 monthly discovery credits',
      'Website audit: HTTPS, mobile, titles, meta, structured data, tap-to-call',
      'Lead pipeline & CRM',
      'Analytics dashboard',
      'Dedicated support',
    ],
    popular: false,
  },
];

export default function Pricing() {
  const { login } = useAuth();
  const navigate = useNavigate();

  return (
    <div className="min-h-screen bg-white">
      {/* Header */}
      <header className="border-b border-slate-100">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
          <div className="flex items-center gap-2 min-w-0 cursor-pointer" onClick={() => navigate('/')}>
            <LogoMark className="h-9 w-9 shrink-0" />
            <span className="font-semibold text-lg text-slate-900 hidden xs:inline">BizLeads</span>
          </div>
          <div className="flex items-center gap-1.5 sm:gap-2 shrink-0">
            <Button onClick={login} variant="ghost" size="sm" className="hidden xs:inline-flex">Sign In</Button>
            <Button onClick={login} size="sm" className="bg-indigo-600 hover:bg-indigo-700 whitespace-nowrap">
              <span className="sm:hidden">Try free</span>
              <span className="hidden sm:inline">Start Free Trial</span>
            </Button>
          </div>
        </div>
      </header>

      {/* Pricing */}
      <section className="py-16 sm:py-20">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-12">
            <h1 className="text-3xl font-bold text-slate-900 sm:text-4xl">
              Simple, transparent pricing
            </h1>
            <p className="mt-4 text-lg text-slate-600 max-w-2xl mx-auto">
              Start with a free 7-day trial. No credit card required.
              All plans include the full 6-score intelligence system.
            </p>
            <p className="mt-3 text-sm text-slate-500 max-w-2xl mx-auto">
              All prices are in US dollars (USD). If you're outside the United States, your bank
              or card network will convert the charge to your local currency at their exchange
              rate, and any applicable tax is calculated at checkout.
            </p>
          </div>

          {/* Trial banner */}
          <div className="mx-auto max-w-3xl mb-12 rounded-xl border border-indigo-200 bg-indigo-50 p-5 text-center">
            <p className="font-medium text-indigo-900">
              🚀 Free Trial: 7 days, 25 credits, full scoring — no card required
            </p>
            <p className="text-sm text-indigo-700 mt-1">
              25 discovery credits and the full toolset. No card required.
            </p>
          </div>

          {/* Plan cards */}
          <div className="grid gap-6 lg:grid-cols-3 max-w-5xl mx-auto">
            {plans.map((plan) => (
              <div
                key={plan.id}
                className={cn(
                  'relative rounded-xl border p-6 flex flex-col',
                  plan.popular ? 'border-indigo-300 shadow-lg shadow-indigo-100' : 'border-slate-200'
                )}
              >
                {plan.popular && (
                  <Badge className="absolute -top-2.5 left-1/2 -translate-x-1/2 bg-indigo-600">
                    Most Popular
                  </Badge>
                )}
                <div className="mb-4">
                  <h3 className="font-semibold text-lg text-slate-900">{plan.name}</h3>
                  <p className="text-sm text-slate-500 mt-1">{plan.description}</p>
                </div>
                <div className="mb-6">
                  <span className="text-4xl font-bold text-slate-900">${plan.price}</span>
                  <span className="text-slate-500 ml-1">USD</span>
                  <span className="text-slate-500">/month</span>
                </div>
                <div className="flex-1 mb-6">
                  <div className="flex items-center gap-2 mb-3 text-sm font-medium text-slate-700">
                    <span>{plan.credits} credits/mo</span>
                  </div>
                  <ul className="space-y-2.5">
                    {plan.features.map((feature) => (
                      <li key={feature} className="flex items-start gap-2 text-sm text-slate-600">
                        <CheckCircle2 className="h-4 w-4 text-green-600 shrink-0 mt-0.5" />
                        {feature}
                      </li>
                    ))}
                  </ul>
                </div>
                <Button
                  onClick={login}
                  className={cn(
                    'w-full',
                    plan.popular ? 'bg-indigo-600 hover:bg-indigo-700' : ''
                  )}
                  variant={plan.popular ? 'default' : 'outline'}
                >
                  Start Free Trial
                  <ArrowRight className="ml-2 h-4 w-4" />
                </Button>
              </div>
            ))}
          </div>

          {/* Credit packs */}
          <div className="mt-12 text-center">
            <p className="text-sm text-slate-600">
              Need more credits? One-time credit packs available from your billing settings.
            </p>
          </div>
        </div>
      </section>

      <SiteFooter />
    </div>
  );
}
