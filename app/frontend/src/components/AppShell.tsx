import { ReactNode, useState } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { CreditsProvider, useCredits } from '@/contexts/CreditsContext';
import { Button } from '@/components/ui/button';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import { Badge } from '@/components/ui/badge';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import {
  Search, LayoutDashboard, LogOut, Menu, X, Target,
  Kanban, List, BarChart3, Zap, Settings, CreditCard,
  ChevronLeft, ChevronRight, Bell, HelpCircle, Coins,
} from 'lucide-react';
import { useNavigate, useLocation } from 'react-router-dom';
import { cn } from '@/lib/utils';
import GuidedTutorial, { useTutorial } from '@/components/GuidedTutorial';
import { LogoMark } from '@/components/Logo';

interface AppShellProps {
  children: ReactNode;
}

const navItems = [
  { path: '/app/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { path: '/app/discover', label: 'Discover', icon: Search },
  { path: '/app/leads', label: 'Leads', icon: List },
  { path: '/app/pipeline', label: 'Pipeline', icon: Kanban },
  { path: '/app/analytics', label: 'Analytics', icon: BarChart3 },
  { path: '/app/automations', label: 'Automations', icon: Zap },
];

const bottomNavItems = [
  { path: '/app/settings/workspace', label: 'Settings', icon: Settings },
  { path: '/app/settings/billing', label: 'Billing', icon: CreditCard },
];

/**
 * Wrapper exists solely so the header below can read the credit balance:
 * a provider rendered inside the component that consumes it would not be in
 * scope. The whole shell sits inside it, so every page gets the same handle.
 */
export default function AppShell({ children }: AppShellProps) {
  return (
    <CreditsProvider>
      <AppShellInner>{children}</AppShellInner>
    </CreditsProvider>
  );
}

function AppShellInner({ children }: AppShellProps) {
  const { user, login, logout, loading } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const tutorial = useTutorial();
  const { credits } = useCredits();

  const isActive = (path: string) => location.pathname.startsWith(path);

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-indigo-600 border-t-transparent" />
      </div>
    );
  }

  if (!user) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center bg-slate-50 p-4">
        <div className="flex items-center gap-2 mb-6">
          <LogoMark className="h-10 w-10" />
          <span className="font-semibold text-xl text-slate-900">BizLeads</span>
        </div>
        <p className="text-slate-600 mb-4">Sign in to access your workspace</p>
        <Button onClick={login} className="bg-indigo-600 hover:bg-indigo-700">Sign In</Button>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen bg-slate-50">
      {/* Sidebar - Desktop */}
      <aside
        className={cn(
          'hidden lg:flex flex-col border-r border-slate-200 bg-white transition-all duration-200',
          collapsed ? 'w-16' : 'w-56'
        )}
      >
        {/* Logo */}
        <div className={cn('flex items-center border-b border-slate-200 h-14 px-3', collapsed ? 'justify-center' : 'gap-2')}>
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-indigo-600">
            <Target className="h-4 w-4 text-white" />
          </div>
          {!collapsed && (
            <span className="font-semibold text-slate-900 text-sm">BizLeads</span>
          )}
        </div>

        {/* Nav Items */}
        <nav className="flex-1 py-3 px-2 space-y-0.5">
          {navItems.map((item) => {
            const active = isActive(item.path);
            const btn = (
              <button
                key={item.path}
                onClick={() => navigate(item.path)}
                className={cn(
                  'flex items-center w-full rounded-md px-2.5 py-2 text-sm font-medium transition-colors',
                  active
                    ? 'bg-indigo-50 text-indigo-700'
                    : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900',
                  collapsed && 'justify-center px-2'
                )}
              >
                <item.icon className={cn('h-4 w-4 shrink-0', !collapsed && 'mr-2.5')} />
                {!collapsed && item.label}
              </button>
            );

            if (collapsed) {
              return (
                <Tooltip key={item.path}>
                  <TooltipTrigger asChild>{btn}</TooltipTrigger>
                  <TooltipContent side="right">{item.label}</TooltipContent>
                </Tooltip>
              );
            }
            return btn;
          })}
        </nav>

        {/* Bottom Nav */}
        <div className="border-t border-slate-200 py-3 px-2 space-y-0.5">
          {bottomNavItems.map((item) => {
            const active = isActive(item.path);
            const btn = (
              <button
                key={item.path}
                onClick={() => navigate(item.path)}
                className={cn(
                  'flex items-center w-full rounded-md px-2.5 py-2 text-sm font-medium transition-colors',
                  active
                    ? 'bg-indigo-50 text-indigo-700'
                    : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900',
                  collapsed && 'justify-center px-2'
                )}
              >
                <item.icon className={cn('h-4 w-4 shrink-0', !collapsed && 'mr-2.5')} />
                {!collapsed && item.label}
              </button>
            );

            if (collapsed) {
              return (
                <Tooltip key={item.path}>
                  <TooltipTrigger asChild>{btn}</TooltipTrigger>
                  <TooltipContent side="right">{item.label}</TooltipContent>
                </Tooltip>
              );
            }
            return btn;
          })}

          {/* Collapse toggle */}
          <button
            onClick={() => setCollapsed(!collapsed)}
            className="flex items-center w-full rounded-md px-2.5 py-2 text-sm text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors justify-center"
          >
            {collapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronLeft className="h-4 w-4" />}
          </button>
        </div>
      </aside>

      {/* Mobile sidebar overlay */}
      {mobileOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div className="absolute inset-0 bg-black/30" onClick={() => setMobileOpen(false)} />
          <aside className="absolute left-0 top-0 h-full w-56 bg-white border-r border-slate-200 flex flex-col">
            <div className="flex items-center justify-between border-b border-slate-200 h-14 px-3">
              <div className="flex items-center gap-2">
                <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-600">
                  <Target className="h-4 w-4 text-white" />
                </div>
                <span className="font-semibold text-slate-900 text-sm">BizLeads</span>
              </div>
              <button onClick={() => setMobileOpen(false)}>
                <X className="h-5 w-5 text-slate-400" />
              </button>
            </div>
            <nav className="flex-1 py-3 px-2 space-y-0.5">
              {navItems.map((item) => (
                <button
                  key={item.path}
                  onClick={() => { navigate(item.path); setMobileOpen(false); }}
                  className={cn(
                    'flex items-center w-full rounded-md px-2.5 py-2 text-sm font-medium transition-colors',
                    isActive(item.path) ? 'bg-indigo-50 text-indigo-700' : 'text-slate-600 hover:bg-slate-100'
                  )}
                >
                  <item.icon className="h-4 w-4 mr-2.5" />
                  {item.label}
                </button>
              ))}
            </nav>
            <div className="border-t border-slate-200 py-3 px-2 space-y-0.5">
              {bottomNavItems.map((item) => (
                <button
                  key={item.path}
                  onClick={() => { navigate(item.path); setMobileOpen(false); }}
                  className={cn(
                    'flex items-center w-full rounded-md px-2.5 py-2 text-sm font-medium transition-colors',
                    isActive(item.path) ? 'bg-indigo-50 text-indigo-700' : 'text-slate-600 hover:bg-slate-100'
                  )}
                >
                  <item.icon className="h-4 w-4 mr-2.5" />
                  {item.label}
                </button>
              ))}
            </div>
          </aside>
        </div>
      )}

      {/* Main content */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Top bar */}
        <header className="sticky top-0 z-40 flex items-center justify-between h-14 border-b border-slate-200 bg-white px-4 lg:px-6">
          <div className="flex items-center gap-3">
            <button className="lg:hidden" onClick={() => setMobileOpen(true)}>
              <Menu className="h-5 w-5 text-slate-600" />
            </button>
          </div>

          <div className="flex items-center gap-2">
            {/* The balance, on every page. Credits were always deducted
                correctly; they were just invisible outside Settings > Billing,
                so spending them looked like nothing had happened. */}
            {credits && (
              <button
                onClick={() => navigate('/app/settings/billing')}
                className="hidden sm:flex items-center gap-1.5 rounded-full border border-slate-200 px-3 py-1 text-xs hover:border-slate-300"
                title={
                  credits.unlimited
                    ? 'This account is not metered'
                    : `${credits.remaining} of ${credits.total} credits left on ${credits.plan_name}`
                }
              >
                {/* An unmetered account shows "Unlimited", not a number that
                    never moves — a static balance reads as a broken counter. */}
                <Coins
                  className={cn(
                    'h-3.5 w-3.5',
                    credits.unlimited ? 'text-indigo-500'
                      : credits.remaining === 0 ? 'text-amber-500' : 'text-slate-400',
                  )}
                />
                {credits.unlimited ? (
                  <span className="font-medium text-indigo-700">Unlimited</span>
                ) : (
                  <>
                    <span className={cn('font-medium', credits.remaining === 0 ? 'text-amber-700' : 'text-slate-700')}>
                      {credits.remaining}
                    </span>
                    <span className="text-slate-400">credits</span>
                  </>
                )}
              </button>
            )}

            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={tutorial.startTutorial}
                  className="relative"
                >
                  <HelpCircle className="h-4 w-4 text-slate-500" />
                </Button>
              </TooltipTrigger>
              <TooltipContent>App Tour</TooltipContent>
            </Tooltip>

            <Button variant="ghost" size="icon" className="relative">
              <Bell className="h-4 w-4 text-slate-500" />
            </Button>

            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="icon" className="rounded-full">
                  <Avatar className="h-8 w-8">
                    <AvatarFallback className="bg-indigo-100 text-indigo-700 text-xs font-medium">
                      {user.email?.charAt(0).toUpperCase() || 'U'}
                    </AvatarFallback>
                  </Avatar>
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-52">
                <div className="px-2 py-1.5">
                  <p className="text-sm font-medium text-slate-900 truncate">{user.email}</p>
                  <p className="text-xs text-slate-500">Workspace Owner</p>
                </div>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={() => navigate('/app/settings/workspace')} className="cursor-pointer">
                  <Settings className="mr-2 h-4 w-4" />
                  Settings
                </DropdownMenuItem>
                <DropdownMenuItem onClick={() => navigate('/app/settings/billing')} className="cursor-pointer">
                  <CreditCard className="mr-2 h-4 w-4" />
                  Billing
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={logout} className="cursor-pointer text-red-600">
                  <LogOut className="mr-2 h-4 w-4" />
                  Sign Out
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </header>

        {/* Page content */}
        <main className="flex-1 overflow-auto p-4 lg:p-6">
          {children}
        </main>
      </div>

      {/* Guided Tutorial Overlay */}
      <GuidedTutorial
        isActive={tutorial.isActive}
        currentStep={tutorial.currentStep}
        totalSteps={tutorial.totalSteps}
        onNext={tutorial.nextStep}
        onPrev={tutorial.prevStep}
        onDismiss={tutorial.dismissTutorial}
        onGoToStep={tutorial.goToStep}
      />
    </div>
  );
}