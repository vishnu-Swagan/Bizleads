import React from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import { useCredits } from '@/contexts/CreditsContext';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Shield, User, LogIn } from 'lucide-react';

interface ProtectedAdminRouteProps {
  children: React.ReactNode;
}

const ProtectedAdminRoute: React.FC<ProtectedAdminRouteProps> = ({
  children,
}) => {
  const { user, loading, isAdmin: isAdminByRole, login } = useAuth();
  const { credits, loaded, refresh } = useCredits();
  const location = useLocation();

  // Two sources, either sufficient. useAuth reads role=admin off the token,
  // which the original single-admin bootstrap produces. The server's answer
  // additionally covers the ADMIN_EMAILS allowlist, where an operator still
  // carries role="user" — checking only the role would lock out precisely the
  // team this console was built for.
  const isAdmin = isAdminByRole || credits?.isAdmin === true;

  // Wait on `loaded`, never on `credits` being non-null. Those look
  // interchangeable and are not: credits is null before the first fetch AND
  // after a failed one, so gating on it meant a failed request produced a
  // permanent "Verifying permissions" with no error and no way out. Render's
  // free tier sleeps, so the first call after an idle period routinely takes
  // long enough to fail — this was reachable in normal use, not an edge case.
  const stillResolving = !loaded && !isAdminByRole;

  // Loaded, but we never heard back. Not the same as "you are not an admin",
  // and must not be reported as one: telling somebody they lack permission
  // when the truth is the server did not answer sends them to ask for access
  // they already have.
  const checkFailed = loaded && credits === null && !isAdminByRole;

  // Loading state
  if (loading || stillResolving) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4"></div>
          <p className="text-gray-600">Verifying permissions...</p>
        </div>
      </div>
    );
  }

  // If the user is not logged in, redirect to the login page
  if (!user) {
    return <Navigate to="/" replace />;
  }

  if (checkFailed) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <Card className="w-full max-w-md mx-4">
          <CardHeader className="text-center">
            <div className="mx-auto w-16 h-16 bg-amber-100 rounded-full flex items-center justify-center mb-4">
              <Shield className="h-8 w-8 text-amber-600" />
            </div>
            <CardTitle className="text-xl text-gray-900">
              Could not verify your access
            </CardTitle>
          </CardHeader>
          <CardContent className="text-center space-y-4">
            <p className="text-gray-600 text-sm">
              The server did not answer when we asked whether this account is an
              administrator. This is usually the API waking up after a quiet period —
              trying again normally works.
            </p>
            <Button onClick={() => void refresh()} className="w-full">
              Try again
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  // If the user is not an admin, show an insufficient-permissions page
  if (!isAdmin) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <Card className="w-full max-w-md mx-4">
          <CardHeader className="text-center">
            <div className="mx-auto w-16 h-16 bg-red-100 rounded-full flex items-center justify-center mb-4">
              <Shield className="h-8 w-8 text-red-600" />
            </div>
            <CardTitle className="text-xl text-gray-900">
              Insufficient Permissions
            </CardTitle>
          </CardHeader>
          <CardContent className="text-center space-y-4">
            <div className="text-gray-600">
              <p className="mb-2">
                The account you are using does not have administrator rights.
              </p>
              <div className="bg-gray-100 rounded-lg p-3 mb-4">
                <div className="flex items-center justify-center space-x-2 text-sm">
                  <User className="h-4 w-4 text-gray-500" />
                  <span className="text-gray-700">
                    Current account: {user.email}
                  </span>
                </div>
                <div className="text-xs text-gray-500 mt-1">
                  Role: {user.role === 'user' ? 'Regular user' : user.role}
                </div>
              </div>
              <p className="text-sm">
                Please log in with an account that has administrator rights.
              </p>
            </div>

            <div className="space-y-3">
              <Button onClick={login} className="w-full" variant="outline">
                <LogIn className="h-4 w-4 mr-2" />
                Switch account
              </Button>

              <Button
                onClick={() => window.history.back()}
                className="w-full"
                variant="ghost"
              >
                Go back
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  // If the user is an admin, render the child components
  return <>{children}</>;
};

export default ProtectedAdminRoute;
