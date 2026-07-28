import { useState, useEffect, useCallback } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import {
  Search, LayoutDashboard, List, Kanban, BarChart3,
  Zap, Settings, CreditCard, X, ChevronRight, ChevronLeft,
  CheckCircle2, Sparkles, Target, ArrowRight,
} from 'lucide-react';
import { cn } from '@/lib/utils';

interface TutorialStep {
  id: string;
  title: string;
  description: string;
  icon: React.ElementType;
  targetPath: string;
  tip: string;
  highlight?: string;
}

const tutorialSteps: TutorialStep[] = [
  {
    id: 'dashboard',
    title: 'Dashboard',
    description: 'Your command center. See credits, lead stats, pipeline overview, and quick actions at a glance.',
    icon: LayoutDashboard,
    targetPath: '/app/dashboard',
    tip: 'Start here each day to check your credit balance and see new opportunities.',
    highlight: 'Credits remaining, lead metrics, and quick-action cards',
  },
  {
    id: 'discover',
    title: 'Discover',
    description: 'Find businesses with weak digital presence using MapBox place search. Each result is scored across 6 dimensions.',
    icon: Search,
    targetPath: '/app/discover',
    tip: 'Use specific categories and locations for the best results. Click "Scores" on any result to see the full breakdown.',
    highlight: '6-score intelligence: Need, Buyability, Timing, Reachability, Fit, Confidence',
  },
  {
    id: 'leads',
    title: 'Leads',
    description: 'All your saved prospects in one place. Search, filter by stage or priority, and export to CSV.',
    icon: List,
    targetPath: '/app/leads',
    tip: 'Click any lead to see full details, add notes, and update their pipeline stage.',
    highlight: 'Table view with search, filters, and bulk export',
  },
  {
    id: 'pipeline',
    title: 'Pipeline',
    description: 'Visual Kanban board showing leads across stages: New → Contacted → In Progress → Won / Lost.',
    icon: Kanban,
    targetPath: '/app/pipeline',
    tip: 'Drag and drop leads between columns to update their stage instantly.',
    highlight: 'Drag-and-drop stage management',
  },
  {
    id: 'analytics',
    title: 'Analytics',
    description: 'Track your conversion funnel, win rates, and lead distribution by category and country.',
    icon: BarChart3,
    targetPath: '/app/analytics',
    tip: 'Use these insights to refine your discovery filters and focus on high-converting categories.',
    highlight: 'Funnel metrics, win rates, and distribution charts',
  },
  {
    id: 'automations',
    title: 'Automations',
    description: 'Generate evidence-based outreach drafts. All messages require your review before sending.',
    icon: Zap,
    targetPath: '/app/automations',
    tip: 'Connect an email sender in Settings to enable outreach delivery.',
    highlight: 'Draft-only mode with human review required',
  },
  {
    id: 'settings',
    title: 'Settings & Billing',
    description: 'Configure your Offer Profile for better Fit scoring, set up the account your outreach sends from, and handle your subscription.',
    icon: Settings,
    targetPath: '/app/settings/workspace',
    tip: 'Set up your services and target categories to improve Agency Fit scoring for discovered leads.',
    highlight: 'Offer Profile, sending account, and plan management',
  },
];

const TUTORIAL_STORAGE_KEY = 'bizleads_tutorial_completed';
const TUTORIAL_STEP_KEY = 'bizleads_tutorial_step';

export function useTutorial() {
  const [isActive, setIsActive] = useState(false);
  const [currentStep, setCurrentStep] = useState(0);
  const [completed, setCompleted] = useState(false);

  useEffect(() => {
    const done = localStorage.getItem(TUTORIAL_STORAGE_KEY);
    if (done === 'true') {
      setCompleted(true);
    } else {
      // Auto-show for new users
      setIsActive(true);
    }
    const savedStep = localStorage.getItem(TUTORIAL_STEP_KEY);
    if (savedStep) {
      setCurrentStep(parseInt(savedStep, 10));
    }
  }, []);

  const startTutorial = useCallback(() => {
    setIsActive(true);
    setCurrentStep(0);
    setCompleted(false);
    localStorage.removeItem(TUTORIAL_STORAGE_KEY);
    localStorage.setItem(TUTORIAL_STEP_KEY, '0');
  }, []);

  const dismissTutorial = useCallback(() => {
    setIsActive(false);
    localStorage.setItem(TUTORIAL_STORAGE_KEY, 'true');
    setCompleted(true);
  }, []);

  const nextStep = useCallback(() => {
    if (currentStep < tutorialSteps.length - 1) {
      const next = currentStep + 1;
      setCurrentStep(next);
      localStorage.setItem(TUTORIAL_STEP_KEY, String(next));
    } else {
      dismissTutorial();
    }
  }, [currentStep, dismissTutorial]);

  const prevStep = useCallback(() => {
    if (currentStep > 0) {
      const prev = currentStep - 1;
      setCurrentStep(prev);
      localStorage.setItem(TUTORIAL_STEP_KEY, String(prev));
    }
  }, [currentStep]);

  const goToStep = useCallback((index: number) => {
    setCurrentStep(index);
    localStorage.setItem(TUTORIAL_STEP_KEY, String(index));
  }, []);

  return {
    isActive,
    currentStep,
    completed,
    startTutorial,
    dismissTutorial,
    nextStep,
    prevStep,
    goToStep,
    totalSteps: tutorialSteps.length,
    steps: tutorialSteps,
  };
}

interface GuidedTutorialProps {
  isActive: boolean;
  currentStep: number;
  totalSteps: number;
  onNext: () => void;
  onPrev: () => void;
  onDismiss: () => void;
  onGoToStep: (index: number) => void;
}

export default function GuidedTutorial({
  isActive,
  currentStep,
  totalSteps,
  onNext,
  onPrev,
  onDismiss,
  onGoToStep,
}: GuidedTutorialProps) {
  const navigate = useNavigate();
  const location = useLocation();

  if (!isActive) return null;

  const step = tutorialSteps[currentStep];
  const isLastStep = currentStep === totalSteps - 1;
  const isFirstStep = currentStep === 0;
  const Icon = step.icon;

  const handleNavigate = () => {
    navigate(step.targetPath);
  };

  const isOnTargetPage = location.pathname.startsWith(step.targetPath);

  return (
    <>
      {/* Overlay backdrop */}
      <div className="fixed inset-0 z-[60] bg-black/20 backdrop-blur-[1px]" onClick={onDismiss} />

      {/* Tutorial card */}
      <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-[70] w-full max-w-lg px-4">
        <Card className="border-indigo-200 shadow-xl shadow-indigo-100/50 bg-white">
          <CardContent className="p-5">
            {/* Header */}
            <div className="flex items-start justify-between mb-3">
              <div className="flex items-center gap-2">
                <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-50">
                  <Sparkles className="h-4 w-4 text-indigo-600" />
                </div>
                <div>
                  <p className="text-xs font-medium text-indigo-600 uppercase tracking-wide">
                    Getting Started · Step {currentStep + 1} of {totalSteps}
                  </p>
                </div>
              </div>
              <button
                onClick={onDismiss}
                className="text-slate-400 hover:text-slate-600 transition-colors"
                aria-label="Dismiss tutorial"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            {/* Progress dots */}
            <div className="flex gap-1 mb-4">
              {tutorialSteps.map((_, idx) => (
                <button
                  key={idx}
                  onClick={() => onGoToStep(idx)}
                  className={cn(
                    'h-1.5 rounded-full transition-all',
                    idx === currentStep ? 'w-6 bg-indigo-600' : 'w-1.5 bg-slate-200 hover:bg-slate-300',
                    idx < currentStep && 'bg-indigo-300'
                  )}
                />
              ))}
            </div>

            {/* Step content */}
            <div className="flex items-start gap-3 mb-4">
              <div className={cn(
                'flex h-10 w-10 shrink-0 items-center justify-center rounded-lg',
                isOnTargetPage ? 'bg-green-50' : 'bg-slate-100'
              )}>
                <Icon className={cn('h-5 w-5', isOnTargetPage ? 'text-green-600' : 'text-slate-600')} />
              </div>
              <div>
                <h3 className="font-semibold text-slate-900 flex items-center gap-2">
                  {step.title}
                  {isOnTargetPage && (
                    <Badge variant="outline" className="text-[10px] bg-green-50 text-green-700 border-green-200">
                      You're here
                    </Badge>
                  )}
                </h3>
                <p className="text-sm text-slate-600 mt-1">{step.description}</p>
                {step.highlight && (
                  <p className="text-xs text-indigo-600 mt-1.5 font-medium">
                    ✨ {step.highlight}
                  </p>
                )}
              </div>
            </div>

            {/* Tip */}
            <div className="bg-slate-50 rounded-lg px-3 py-2 mb-4">
              <p className="text-xs text-slate-600">
                <span className="font-medium text-slate-700">💡 Tip:</span> {step.tip}
              </p>
            </div>

            {/* Actions */}
            <div className="flex items-center justify-between">
              <div className="flex gap-2">
                {!isFirstStep && (
                  <Button variant="ghost" size="sm" onClick={onPrev} className="gap-1 text-slate-600">
                    <ChevronLeft className="h-3.5 w-3.5" />
                    Back
                  </Button>
                )}
              </div>

              <div className="flex gap-2">
                {!isOnTargetPage && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleNavigate}
                    className="gap-1 border-indigo-200 text-indigo-700 hover:bg-indigo-50"
                  >
                    Go to {step.title}
                    <ArrowRight className="h-3.5 w-3.5" />
                  </Button>
                )}
                <Button
                  size="sm"
                  onClick={onNext}
                  className="gap-1 bg-indigo-600 hover:bg-indigo-700"
                >
                  {isLastStep ? (
                    <>
                      <CheckCircle2 className="h-3.5 w-3.5" />
                      Finish Tour
                    </>
                  ) : (
                    <>
                      Next
                      <ChevronRight className="h-3.5 w-3.5" />
                    </>
                  )}
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </>
  );
}