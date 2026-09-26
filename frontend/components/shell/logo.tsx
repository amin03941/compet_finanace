/** Logo RASD 360 (radar stylisé) — création originale, aucun logo institutionnel. */
export function LogoRadar({ className = "h-8 w-8" }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden="true">
      <circle cx="16" cy="16" r="14.5" fill="none" stroke="currentColor" strokeOpacity="0.35" strokeWidth="1.5" />
      <circle cx="16" cy="16" r="9.5" fill="none" stroke="currentColor" strokeOpacity="0.55" strokeWidth="1.5" />
      <circle cx="16" cy="16" r="4.5" fill="none" stroke="currentColor" strokeOpacity="0.8" strokeWidth="1.5" />
      <path d="M16 16 L27 8.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      <path d="M16 16 L27 8.5 A13 13 0 0 1 29 16 Z" fill="currentColor" fillOpacity="0.18" />
      <circle cx="22.5" cy="11.5" r="1.8" fill="#F59E0B" />
      <circle cx="16" cy="16" r="1.6" fill="currentColor" />
    </svg>
  );
}
