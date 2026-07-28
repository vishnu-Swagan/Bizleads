/**
 * RevenueCat hosted Web Purchase Link integration.
 *
 * RevenueCat identifies a logged-in web customer by appending the App User ID
 * to the purchase-link path. BizLeads uses the authenticated Supabase UUID:
 * it is non-guessable, stable across devices, and is also copied to Stripe
 * Checkout and Subscription metadata by the backend.
 *
 * When VITE_REVENUECAT_PURCHASE_LINK is absent, callers fall back to the
 * existing direct Stripe Checkout endpoint. Never put a sandbox purchase link
 * in the production Vercel environment.
 */

const PURCHASE_LINK = (
  import.meta.env.VITE_REVENUECAT_PURCHASE_LINK ?? ''
).replace(/\/+$/, '');

const PACKAGE_IDS: Record<string, string> = {
  solo: 'solo_monthly',
  pro: 'pro_monthly',
  agency: 'agency_monthly',
};

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
