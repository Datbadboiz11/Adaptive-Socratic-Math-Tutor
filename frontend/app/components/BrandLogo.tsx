/** Original Mở identity, retained at the user's request. */
export function BrandLogo({ compact = false }: { compact?: boolean }) {
  return <span className={compact ? "brand-logo brand-logo-compact" : "brand-logo"} role="img" aria-label="Mở">
    {!compact && <span className="brand-symbol" aria-hidden="true" />}
    <span className="brand-wordmark" aria-hidden="true">mở<span>.</span></span>
  </span>;
}
