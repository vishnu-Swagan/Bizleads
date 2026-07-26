import { useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { client } from '@/lib/api';
import { useAuth } from '@/contexts/AuthContext';
import { LogoMark } from '@/components/Logo';

type Mode = 'signin' | 'signup' | 'forgot';

const COPY: Record<Mode, { title: string; action: string; busy: string }> = {
  signin: { title: 'Sign in to BizLeads', action: 'Sign in', busy: 'Signing in…' },
  signup: { title: 'Create your account', action: 'Create account', busy: 'Creating account…' },
  forgot: { title: 'Reset your password', action: 'Send reset link', busy: 'Sending…' },
};

/**
 * Sign in, sign up and password reset in one screen.
 *
 * Kept as a single component because the three states share a form, a layout
 * and an error surface; three files would triplicate all of it to no benefit.
 */
export default function Login() {
  const navigate = useNavigate();
  const { refetch } = useAuth();
  const [params] = useSearchParams();

  const [mode, setMode] = useState<Mode>(params.get('mode') === 'signup' ? 'signup' : 'signin');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const switchMode = (next: Mode) => {
    setMode(next);
    setError(null);
    setNotice(null);
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setNotice(null);

    try {
      if (mode === 'signin') {
        await client.auth.signInWithPassword(email, password);
        await refetch();
        navigate('/app/dashboard');
      } else if (mode === 'signup') {
        await client.auth.signUp(email, password);
        // Email confirmation is enabled on this project, so a new account is
        // not usable until the link is clicked. Say so plainly rather than
        // dropping the user on a dashboard that will reject them.
        setNotice(
          'Account created. Check your email for a confirmation link — you will not be able to sign in until you confirm.',
        );
        setMode('signin');
      } else {
        await client.auth.resetPassword(email);
        // Deliberately the same message whether or not the address exists:
        // a different response would let anyone test which emails have accounts.
        setNotice('If that email has an account, a reset link is on its way.');
      }
    } catch (err) {
      const detail = (err as { data?: { detail?: string }; message?: string });
      setError(detail?.data?.detail ?? detail?.message ?? 'Something went wrong. Please try again.');
    } finally {
      setBusy(false);
    }
  };

  const copy = COPY[mode];

  return (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center px-4 py-12">
      <div className="w-full max-w-md">
        <button
          onClick={() => navigate('/')}
          className="flex items-center gap-2 mx-auto mb-8 cursor-pointer"
          aria-label="BizLeads home"
        >
          <LogoMark className="h-10 w-10" />
          <span className="text-xl font-semibold text-slate-900">BizLeads</span>
        </button>

        <Card className="border-slate-200 shadow-sm">
          <CardHeader>
            <CardTitle className="text-lg text-slate-900">{copy.title}</CardTitle>
          </CardHeader>

          <CardContent>
            <form onSubmit={handleSubmit} className="space-y-4" noValidate>
              <div className="space-y-2">
                <Label htmlFor="email">Email</Label>
                <Input
                  id="email"
                  type="email"
                  autoComplete="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@agency.com"
                  className="border-slate-200"
                />
              </div>

              {mode !== 'forgot' && (
                <div className="space-y-2">
                  <Label htmlFor="password">Password</Label>
                  <Input
                    id="password"
                    type="password"
                    autoComplete={mode === 'signup' ? 'new-password' : 'current-password'}
                    required
                    minLength={8}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder={mode === 'signup' ? 'At least 8 characters' : ''}
                    className="border-slate-200"
                  />
                </div>
              )}

              {/* role=alert so failures are announced, not just shown in red. */}
              {error && (
                <p role="alert" className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-md px-3 py-2">
                  {error}
                </p>
              )}
              {notice && (
                <p role="status" className="text-sm text-slate-700 bg-slate-50 border border-slate-200 rounded-md px-3 py-2">
                  {notice}
                </p>
              )}

              <Button
                type="submit"
                disabled={busy}
                className="w-full bg-indigo-600 hover:bg-indigo-700 cursor-pointer"
              >
                {busy && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                {busy ? copy.busy : copy.action}
              </Button>

              {/*
                Shown at the point of signup, immediately above the action that
                forms the contract. Terms linked only from a footer are hard to
                argue were ever presented; terms sitting on the button the user
                pressed are not. Opens in a new tab so reading them does not
                discard a half-filled form.
              */}
              {mode === 'signup' && (
                <p className="text-xs leading-relaxed text-slate-500 text-center">
                  By creating an account you agree to our{' '}
                  <Link
                    to="/terms"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-indigo-600 underline underline-offset-2"
                  >
                    Terms of Service
                  </Link>{' '}
                  and{' '}
                  <Link
                    to="/privacy"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-indigo-600 underline underline-offset-2"
                  >
                    Privacy Policy
                  </Link>
                  .
                </p>
              )}
            </form>

            <div className="mt-6 space-y-2 text-sm text-center">
              {mode === 'signin' && (
                <>
                  <button onClick={() => switchMode('forgot')} className="text-slate-600 hover:text-indigo-600 cursor-pointer">
                    Forgot your password?
                  </button>
                  <p className="text-slate-600">
                    No account?{' '}
                    <button onClick={() => switchMode('signup')} className="text-indigo-600 font-medium cursor-pointer">
                      Create one
                    </button>
                  </p>
                </>
              )}
              {mode !== 'signin' && (
                <button onClick={() => switchMode('signin')} className="text-slate-600 hover:text-indigo-600 cursor-pointer">
                  Back to sign in
                </button>
              )}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
