/**
 * The credit balance, shared by the shell that displays it and the pages that
 * spend it.
 *
 * Credits were always deducted correctly server-side — Discover and Qualify
 * both charge, and the backend has tests asserting the workspace row moves.
 * The balance was simply invisible: nothing outside Settings > Billing showed
 * it, so a user clicking Qualify saw no change anywhere and reasonably
 * concluded nothing had been charged.
 *
 * Spending happens on Discover and Leads, while the number is rendered in the
 * shell's header, so the two need a shared handle on the same value. This
 * context is that handle: `refresh()` after anything that spends, and the
 * header updates.
 *
 * Deliberately no optimistic decrement. The server is authoritative about how
 * many credits a call actually cost — a batch qualify charges per lead
 * measured, not per lead requested, and leads that could not be measured are
 * not charged for. Guessing locally would show a number that quietly
 * disagrees with the invoice.
 */
import { createContext, useCallback, useContext, useEffect, useState, ReactNode } from 'react';
import { client } from '@/lib/api';

interface Credits {
  remaining: number;
  total: number;
  plan_name: string;
  trial_expired: boolean;
  /** Exempt from metering. The balance is then meaningless, not zero. */
  unlimited: boolean;
  /**
   * May reach the operators' console.
   *
   * Comes from the server, not from the JWT role: an operator admitted by
   * the ADMIN_EMAILS allowlist still carries role="user", so deciding this
   * client-side would hide the console from the people it exists for. Used
   * only to choose what to render — every admin route re-checks server-side.
   */
  isAdmin: boolean;
}

interface CreditsContextValue {
  credits: Credits | null;
  /**
   * Whether the first fetch has finished, however it finished.
   *
   * `credits` alone cannot answer this: it is null before the first request
   * AND after a failed one. Anything waiting on "have we heard back yet"
   * therefore waited forever whenever the call failed — which is what left
   * the admin console stuck on "Verifying permissions" with no error and no
   * way out. Loading and failure are different states and now say so.
   */
  loaded: boolean;
  /** Re-read the balance from the server. Call after anything that spends. */
  refresh: () => Promise<void>;
}

const CreditsContext = createContext<CreditsContextValue>({
  credits: null,
  // True in the default so a consumer rendered outside any provider is not
  // left waiting on a fetch that will never happen.
  loaded: true,
  refresh: async () => {},
});

export function CreditsProvider({ children }: { children: ReactNode }) {
  const [credits, setCredits] = useState<Credits | null>(null);
  const [loaded, setLoaded] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const res = await client.apiCall.invoke({
        url: '/api/v1/billing/usage', method: 'GET', data: {},
        // The client defaults to 30s. The API sleeps when idle and takes
        // around 50s to wake, so the first call after a quiet period reliably
        // timed out — and this call decides whether the admin console opens
        // at all, so losing it is not a cosmetic failure. Long enough to
        // outlast a cold start, still bounded.
        options: { timeout: 75000 },
      });
      setCredits({
        remaining: res.data?.credits_remaining ?? 0,
        total: res.data?.credits_total ?? 0,
        plan_name: res.data?.plan_name ?? '',
        trial_expired: res.data?.trial_expired === true,
        unlimited: res.data?.unlimited_credits === true,
        isAdmin: res.data?.is_admin === true,
      });
    } catch {
      // Left null so the header renders nothing rather than a zero. Showing
      // "0 credits" because a request failed would send someone to the
      // billing page to fix a problem they do not have.
      setCredits(null);
    } finally {
      // In `finally`, so a failure ends the wait exactly as a success does.
      // This is the whole fix: anything gating on "have we heard back" must
      // be released by an error too, or an error becomes an infinite spinner.
      setLoaded(true);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return (
    <CreditsContext.Provider value={{ credits, loaded, refresh }}>
      {children}
    </CreditsContext.Provider>
  );
}

export function useCredits() {
  return useContext(CreditsContext);
}
