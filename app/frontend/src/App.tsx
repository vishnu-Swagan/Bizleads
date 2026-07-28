import { Toaster } from '@/components/ui/sonner';
import { TooltipProvider } from '@/components/ui/tooltip';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter, Routes, Route, Navigate, useParams } from 'react-router-dom';
import { AuthProvider } from './contexts/AuthContext';
import Index from './pages/Index';
import AuthCallback from './pages/AuthCallback';
import AuthError from './pages/AuthError';
import LogoutCallbackPage from './pages/LogoutCallbackPage';
import Pricing from './pages/Pricing';
import Login from './pages/Login';
import Terms from './pages/legal/Terms';
import Privacy from './pages/legal/Privacy';
import Cookies from './pages/legal/Cookies';
import Subprocessors from './pages/legal/Subprocessors';
import AppDashboard from './pages/app/Dashboard';
import AppDiscover from './pages/app/Discover';
import AppLeads from './pages/app/Leads';
import AppLeadDetail from './pages/app/LeadDetail';
import AppPipeline from './pages/app/Pipeline';
import AppAnalytics from './pages/app/Analytics';
import AppAutomations from './pages/app/Automations';
import AppSettings from './pages/app/Settings';

const queryClient = new QueryClient();

/**
 * Redirect /lead/:id to /app/leads/:id, carrying the id.
 *
 * `<Navigate to="/app/leads/:id">` does NOT interpolate route params — it
 * treats the string literally, so every old lead link landed on a URL
 * containing the characters ":id" and 404'd. The bug is invisible in the
 * route table because the two lines look symmetrical with the redirects
 * above, which have no params and are therefore correct.
 */
const RedirectToLead = () => {
  const { id } = useParams();
  return <Navigate to={`/app/leads/${id}`} replace />;
};

const AppRoutes = () => (
  <Routes>
    {/* Public routes */}
    <Route path="/" element={<Index />} />
    <Route path="/pricing" element={<Pricing />} />

    {/* Public policy pages. Reachable without an account on purpose:
        terms nobody can read before signing up are terms nobody agreed to. */}
    <Route path="/terms" element={<Terms />} />
    <Route path="/privacy" element={<Privacy />} />
    <Route path="/cookies" element={<Cookies />} />
    <Route path="/subprocessors" element={<Subprocessors />} />
    <Route path="/login" element={<Login />} />
    <Route path="/signup" element={<Login />} />
    <Route path="/forgot-password" element={<Login />} />
    <Route path="/auth/callback" element={<AuthCallback />} />
    <Route path="/auth/error" element={<AuthError />} />
    <Route path="/logout/callback" element={<LogoutCallbackPage />} />

    {/* App routes (authenticated) */}
    <Route path="/app/dashboard" element={<AppDashboard />} />
    <Route path="/app/discover" element={<AppDiscover />} />
    <Route path="/app/leads" element={<AppLeads />} />
    <Route path="/app/leads/:id" element={<AppLeadDetail />} />
    <Route path="/app/pipeline" element={<AppPipeline />} />
    <Route path="/app/analytics" element={<AppAnalytics />} />
    <Route path="/app/automations" element={<AppAutomations />} />
    <Route path="/app/settings/*" element={<AppSettings />} />

    {/* Redirects from old routes */}
    <Route path="/dashboard" element={<Navigate to="/app/dashboard" replace />} />
    <Route path="/search" element={<Navigate to="/app/discover" replace />} />
    <Route path="/leads" element={<Navigate to="/app/leads" replace />} />
    <Route path="/pipeline" element={<Navigate to="/app/pipeline" replace />} />
    <Route path="/analytics" element={<Navigate to="/app/analytics" replace />} />
    <Route path="/automation" element={<Navigate to="/app/automations" replace />} />
    <Route path="/lead/:id" element={<RedirectToLead />} />
  </Routes>
);

const App = () => (
  <QueryClientProvider client={queryClient}>
    <AuthProvider>
      <TooltipProvider>
        <Toaster />
        <BrowserRouter>
          <AppRoutes />
        </BrowserRouter>
      </TooltipProvider>
    </AuthProvider>
  </QueryClientProvider>
);

export default App;
export { AppRoutes };