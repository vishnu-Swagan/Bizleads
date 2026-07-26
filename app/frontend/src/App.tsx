import { Toaster } from '@/components/ui/sonner';
import { TooltipProvider } from '@/components/ui/tooltip';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from './contexts/AuthContext';
import Index from './pages/Index';
import AuthCallback from './pages/AuthCallback';
import AuthError from './pages/AuthError';
import LogoutCallbackPage from './pages/LogoutCallbackPage';
import Pricing from './pages/Pricing';
import Login from './pages/Login';
import AppDashboard from './pages/app/Dashboard';
import AppDiscover from './pages/app/Discover';
import AppLeads from './pages/app/Leads';
import AppLeadDetail from './pages/app/LeadDetail';
import AppPipeline from './pages/app/Pipeline';
import AppAnalytics from './pages/app/Analytics';
import AppAutomations from './pages/app/Automations';
import AppSettings from './pages/app/Settings';

const queryClient = new QueryClient();

const AppRoutes = () => (
  <Routes>
    {/* Public routes */}
    <Route path="/" element={<Index />} />
    <Route path="/pricing" element={<Pricing />} />
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
    <Route path="/lead/:id" element={<Navigate to="/app/leads/:id" replace />} />
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