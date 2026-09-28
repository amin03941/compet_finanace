import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

const NBSP = " ";

/** Montant en dinars : 1 234 567 DT (espace insécable). */
export function dt(x: number | null | undefined, decimales = 0): string {
  if (x === null || x === undefined || Number.isNaN(x)) return "—";
  const s = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: decimales, minimumFractionDigits: decimales })
    .format(x)
    .replace(/[   ]/g, NBSP);
  return `${s}${NBSP}DT`;
}

/** Montant compact pour les graphiques : 1,2 M DT, 340 k DT. */
export function dtCompact(x: number): string {
  if (Math.abs(x) >= 1e6) return `${(x / 1e6).toLocaleString("fr-FR", { maximumFractionDigits: 1 })}${NBSP}M${NBSP}DT`;
  if (Math.abs(x) >= 1e3) return `${Math.round(x / 1e3).toLocaleString("fr-FR")}${NBSP}k${NBSP}DT`;
  return dt(x);
}

export function nombre(x: number | null | undefined, decimales = 0): string {
  if (x === null || x === undefined || Number.isNaN(x)) return "—";
  return new Intl.NumberFormat("fr-FR", { maximumFractionDigits: decimales, minimumFractionDigits: decimales })
    .format(x)
    .replace(/[  ]/g, NBSP);
}

/** Pourcentage avec 1 décimale : 12,5 %. */
export function pct(x: number | null | undefined, decimales = 1): string {
  if (x === null || x === undefined || Number.isNaN(x) || !Number.isFinite(x)) return "—";
  return `${(x * 100).toLocaleString("fr-FR", { minimumFractionDigits: decimales, maximumFractionDigits: decimales })}${NBSP}%`;
}

/** Date jj/mm/aaaa. */
export function dateFr(d: string | Date | null | undefined): string {
  if (!d) return "—";
  const x = typeof d === "string" ? new Date(d.length === 10 ? `${d}T00:00:00` : d) : d;
  if (Number.isNaN(x.getTime())) return String(d);
  return x.toLocaleDateString("fr-FR", { day: "2-digit", month: "2-digit", year: "numeric" });
}

export function moisCourt(periode: string): string {
  const [a, m] = periode.split("-").map(Number);
  return new Date(a, m - 1, 1).toLocaleDateString("fr-FR", { month: "short", year: "2-digit" }).replace(".", "");
}

export const CATEGORIES: Record<string, { libelle: string; court: string; couleur: string; fond: string; texte: string; point: string }> = {
  rouge: { libelle: "Contrôle recommandé", court: "Contrôle", couleur: "rgb(var(--rouge))", fond: "bg-rouge/10", texte: "text-rouge", point: "bg-rouge" },
  orange: { libelle: "Demande de justification", court: "Justification", couleur: "rgb(var(--orange))", fond: "bg-orange/10", texte: "text-orange", point: "bg-orange" },
  gris: { libelle: "Données insuffisantes", court: "Données", couleur: "rgb(var(--gris))", fond: "bg-gris/15", texte: "text-attenue", point: "bg-gris" },
  vert: { libelle: "Cohérent", court: "Cohérent", couleur: "rgb(var(--vert))", fond: "bg-vert/10", texte: "text-vert", point: "bg-vert" },
};

/** Type de dossier selon l'administration compétente (déduit des indices déclenchés). */
export const TYPES_DOSSIER: Record<string, { libelle: string; detail: string; classe: string }> = {
  fiscal: { libelle: "Fiscal", detail: "Dossier de la DGI (impôts)", classe: "border-action/30 bg-action/10 text-action" },
  douanier: { libelle: "Douanier", detail: "Dossier de la Douane (contrôle a posteriori)", classe: "border-teal-500/30 bg-teal-500/10 text-teal-700 dark:text-teal-300" },
  conjoint: { libelle: "Conjoint", detail: "Deux parties : DGI et Douane, avec fiche de transmission", classe: "border-violet-500/30 bg-violet-500/10 text-violet-700 dark:text-violet-300" },
};
