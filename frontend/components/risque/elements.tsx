"use client";
import * as React from "react";
import { motion, useMotionValue, useTransform, animate } from "framer-motion";
import { CATEGORIES, TYPES_DOSSIER, cn } from "@/lib/utils";
import { Infobulle } from "@/components/ui/misc";
import type { Categorie } from "@/lib/api";

export const LIBELLES_REGLES: Record<string, string> = {
  A1: "Paiements attestés par les clients (TEJ) supérieurs au chiffre d'affaires",
  A2: "Factures électroniques émises supérieures au chiffre d'affaires",
  A3: "TVA déduite à l'import supérieure à la TVA payée en douane",
  A4: "Exportations déclarées supérieures aux exportations en douane",
  A5: "Défaut de déclaration de TVA malgré une activité",
  B1: "Marge implicite impossible (après neutralisation)",
  B2: "Sous-évaluation en douane répétée",
  B3: "Carrousel de TVA (circuit fermé de factures)",
  B4: "Encaissements bancaires très supérieurs au CA",
  C1: "Fractionnement des déclarations en douane",
  C2: "Détournement d'avantage fiscal (équipements revendus)",
  C3: "Crédit de TVA structurel",
  C4: "Réseau à risque (dirigeant, adresse)",
  C5: "Productivité anormale",
};

export const FORCES: Record<string, { libelle: string; classe: string }> = {
  A: { libelle: "Niveau A — contradiction avec des données de tiers (quasi-preuve)", classe: "bg-rouge/10 text-rouge border-rouge/25" },
  B: { libelle: "Niveau B — anomalie économique forte après neutralisation", classe: "bg-orange/10 text-amber-700 border-orange/30 dark:text-orange" },
  C: { libelle: "Niveau C — signal de contexte (ne suffit jamais seul)", classe: "bg-slate-500/10 text-slate-600 border-slate-400/30 dark:text-slate-300" },
};

/** Score (chiffre) coloré selon la CATÉGORIE décidée par les règles : la couleur, c'est la décision ; le chiffre, l'ordre. */
export function PastilleScore({ score, categorie, taille = "md" }: { score: number; categorie: Categorie; taille?: "sm" | "md" | "lg" }) {
  const c = CATEGORIES[categorie].couleur;
  return (
    <span
      className={cn("chiffres inline-flex items-center justify-center rounded-full font-semibold",
        taille === "sm" && "h-7 min-w-[2.6rem] px-2 text-xs", taille === "md" && "h-8 min-w-[3rem] px-2.5 text-sm",
        taille === "lg" && "h-10 min-w-[3.6rem] px-3 text-base")}
      style={{ color: c, backgroundColor: `color-mix(in srgb, ${c} 12%, transparent)`, boxShadow: `inset 0 0 0 1px color-mix(in srgb, ${c} 30%, transparent)` }}
    >
      {Math.round(score)}
    </span>
  );
}

export function BadgeCategorie({ categorie, court = false, className }: { categorie: Categorie; court?: boolean; className?: string }) {
  const c = CATEGORIES[categorie];
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium", c.fond, c.texte, className)}>
      <span className={cn("h-1.5 w-1.5 rounded-full", c.point)} />
      {court ? c.court : c.libelle}
    </span>
  );
}

export function BadgeTypeDossier({ type, className }: { type: string | null | undefined; className?: string }) {
  if (!type || !TYPES_DOSSIER[type]) return null;
  const t = TYPES_DOSSIER[type];
  return (
    <Infobulle contenu={t.detail}>
      <span className={cn("inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium", t.classe, className)}>{t.libelle}</span>
    </Infobulle>
  );
}

export function PuceIndice({ code }: { code: string }) {
  const niveau = code[0];
  return (
    <Infobulle contenu={<><p className="font-semibold">{code} · {FORCES[niveau]?.libelle.split(" — ")[0]}</p><p>{LIBELLES_REGLES[code]}</p></>}>
      <span className={cn("chiffres inline-flex h-6 items-center rounded-md border px-1.5 text-[11px] font-semibold", FORCES[niveau]?.classe)}>{code}</span>
    </Infobulle>
  );
}

export function PucesIndices({ codes, max = 6 }: { codes: string[]; max?: number }) {
  if (!codes.length) return <span className="text-xs text-gris">—</span>;
  return (
    <div className="flex flex-wrap gap-1">
      {codes.slice(0, max).map((c) => <PuceIndice key={c} code={c} />)}
      {codes.length > max && <span className="text-xs text-attenue">+{codes.length - max}</span>}
    </div>
  );
}

/** Jauge semi-circulaire animée (0-100), à la couleur de la CATÉGORIE décidée par les règles (gris compris). */
export function JaugeScore({ score, categorie, taille = 180 }: { score: number; categorie: Categorie; taille?: number }) {
  const r = taille / 2 - 14;
  const long = Math.PI * r;
  const mv = useMotionValue(0);
  const offset = useTransform(mv, (v) => long * (1 - v / 100));
  const [affiche, setAffiche] = React.useState(0);
  React.useEffect(() => {
    const ctrl = animate(mv, score, { duration: 0.9, ease: [0.22, 1, 0.36, 1], onUpdate: (v) => setAffiche(v) });
    return () => ctrl.stop();
  }, [score, mv]);
  const c = CATEGORIES[categorie].couleur;
  const cx = taille / 2;
  const cy = taille / 2;
  return (
    <div className="relative" style={{ width: taille, height: taille / 2 + 22 }}>
      <svg width={taille} height={taille / 2 + 12} viewBox={`0 0 ${taille} ${taille / 2 + 12}`}>
        <path d={`M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`} fill="none" stroke="rgb(var(--ligne))" strokeWidth={14} strokeLinecap="round" />
        <motion.path d={`M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`} fill="none" stroke={c} strokeWidth={14} strokeLinecap="round"
          strokeDasharray={long} style={{ strokeDashoffset: offset }} />
      </svg>
      <div className="absolute inset-x-0 bottom-1 text-center">
        <span className="chiffres text-4xl font-semibold tracking-tight" style={{ color: c }}>{Math.round(affiche)}</span>
        <span className="text-sm text-attenue">/100</span>
      </div>
    </div>
  );
}

export function CarteKpi({ titre, valeur, detail, icone, accent, info }: {
  titre: string; valeur: React.ReactNode; detail?: React.ReactNode; icone: React.ReactNode; accent?: string; info?: string;
}) {
  const contenu = (
    <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.2 }}
      className="rounded-2xl border border-ligne bg-carte p-5 shadow-carte">
      <div className="flex items-start justify-between">
        <p className="text-xs font-medium uppercase tracking-wide text-attenue">{titre}</p>
        <span className={cn("rounded-xl p-2", accent || "bg-action/10 text-action")}>{icone}</span>
      </div>
      <p className="chiffres mt-2 text-[28px] font-semibold leading-tight tracking-tight text-marine dark:text-encre">{valeur}</p>
      {detail && <p className="mt-1 text-xs text-attenue">{detail}</p>}
    </motion.div>
  );
  return info ? <Infobulle contenu={info}><div>{contenu}</div></Infobulle> : contenu;
}

export function EnTetePage({ titre, sousTitre, actions }: { titre: string; sousTitre?: React.ReactNode; actions?: React.ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-marine dark:text-encre">{titre}</h1>
        {sousTitre && <p className="mt-1 text-sm text-attenue">{sousTitre}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}
