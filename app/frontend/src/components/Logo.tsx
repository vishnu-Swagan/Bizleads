import { cn } from '@/lib/utils';

/**
 * The BizLeads mark.
 *
 * Three ascending bars are a business's measured web presence; the tallest is
 * held back at 45% opacity — the gap between where a prospect is and where
 * they could be. That gap is what the product sells, so it belongs in the
 * mark.
 *
 * Kept as inline SVG rather than an <img> so it inherits colour, needs no
 * network request, and renders identically wherever it appears. The previous
 * logo was a generic Lucide `Target` icon, and the favicon was a default app
 * logo served from a third-party CDN.
 */

interface LogoMarkProps {
  className?: string;
  /** Renders the mark in a single colour instead of the indigo tile. */
  monochrome?: boolean;
}

export function LogoMark({ className, monochrome = false }: LogoMarkProps) {
  // Unique per instance so multiple marks on one page cannot collide on the
  // gradient id — a duplicate id makes every later instance render blank.
  const gradientId = `bl-tile-${Math.random().toString(36).slice(2, 9)}`;

  return (
    <svg
      viewBox="0 0 32 32"
      className={cn('h-9 w-9', className)}
      role="img"
      aria-label="BizLeads"
      focusable="false"
    >
      {!monochrome && (
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#6366F1" />
            <stop offset="1" stopColor="#4338CA" />
          </linearGradient>
        </defs>
      )}
      <rect
        width="32"
        height="32"
        rx="7"
        fill={monochrome ? 'currentColor' : `url(#${gradientId})`}
      />
      <g fill={monochrome ? '#FFFFFF' : '#FFFFFF'}>
        <rect x="7.5" y="19" width="4.5" height="6.5" rx="1.6" />
        <rect x="13.75" y="14" width="4.5" height="11.5" rx="1.6" />
        <rect x="20" y="7.5" width="4.5" height="18" rx="1.6" opacity="0.45" />
      </g>
    </svg>
  );
}

interface LogoProps {
  className?: string;
  markClassName?: string;
  /** Hides the wordmark, leaving only the tile — for tight or mobile headers. */
  markOnly?: boolean;
}

export default function Logo({ className, markClassName, markOnly = false }: LogoProps) {
  return (
    <span className={cn('inline-flex items-center gap-2.5', className)}>
      <LogoMark className={markClassName} />
      {!markOnly && (
        <span className="font-semibold text-lg tracking-tight text-slate-900">BizLeads</span>
      )}
    </span>
  );
}
