import {
  ErrorCode,
  Purchases,
  PurchasesError,
  type PaywallPurchaseResult,
} from '@revenuecat/purchases-js';

/**
 * RevenueCat Web SDK and hosted Web Purchase Link integration.
 *
 * RevenueCat identifies a logged-in web customer by appending the App User ID
 * to the purchase-link path. BizLeads uses the authenticated Supabase UUID:
 * it is non-guessable, stable across devices, and is also copied to Stripe
 * Checkout and Subscription metadata by the backend.
 *
 * VITE_REVENUECAT_PUBLIC_API_KEY is a public Web Billing SDK key, not a secret
 * RevenueCat API key. Production and preview must use their matching live and
 * sandbox values. The hosted purchase link and direct Stripe Checkout remain
 * progressively safer fallbacks when the SDK or remote paywall is unavailable.
 */

const PUBLIC_API_KEY = (
  import.meta.env.VITE_REVENUECAT_PUBLIC_API_KEY ?? ''
).trim();

const PURCHASE_LINK = (
  import.meta.env.VITE_REVENUECAT_PURCHASE_LINK ?? ''
).replace(/\/+$/, '');

const PACKAGE_IDS: Record<string, string> = {
  solo: 'solo_monthly',
  pro: 'pro_monthly',
  agency: 'agency_monthly',
};

/**
 * Configures exactly one RevenueCat SDK instance for the authenticated
 * Supabase UUID. Returning null is intentional when the public key is absent:
 * it lets local development and older deployments keep using the existing
 * hosted-link/direct-Stripe fallback.
 */
export async function initializeRevenueCat(
  userId: string,
): Promise<Purchases | null> {
  if (!PUBLIC_API_KEY || !userId) return null;

  const purchases = Purchases.isConfigured()
    ? Purchases.getSharedInstance()
    : Purchases.configure({
        apiKey: PUBLIC_API_KEY,
        appUserId: userId,
      });

  if (purchases.getAppUserId() !== userId) {
    await purchases.changeUser(userId);
  }

  return purchases;
}

/**
 * Presents the published RevenueCat paywall as a full-screen overlay. The
 * result only resolves after a completed purchase; dismissing it produces the
 * SDK's user-cancelled error.
 */
export async function presentRevenueCatPaywall({
  userId,
  email,
}: {
  userId: string;
  email?: string;
}): Promise<PaywallPurchaseResult | null> {
  const purchases = await initializeRevenueCat(userId);
  if (!purchases) return null;

  return purchases.presentPaywall({
    customerEmail: email,
  });
}

export function isRevenueCatUserCancellation(error: unknown): boolean {
  return (
    error instanceof PurchasesError &&
    error.errorCode === ErrorCode.UserCancelledError
  );
}

export function revenueCatPurchaseUrl({
  userId,
  email,
  plan,
}: {
  userId: string;
  email?: string;
  plan: string;
}): string | null {
  if (!PURCHASE_LINK || !userId) return null;

  const packageId = PACKAGE_IDS[plan];
  if (!packageId) return null;

  const url = new URL(`${PURCHASE_LINK}/${encodeURIComponent(userId)}`);
  if (email) url.searchParams.set('email', email);
  url.searchParams.set('package_id', packageId);
  url.searchParams.set('hide_back_button', 'true');
  url.searchParams.set('skip_purchase_success', 'true');
  return url.toString();
}
