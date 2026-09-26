"use client";
import { motion } from "framer-motion";
import type { EtapeCascade } from "@/lib/api";
import { cn, nombre } from "@/lib/utils";

const TYPES: Record<string, string> = { ia: "IA", regle: "Indice", anomalie: "Atypicité", base: "", total: "" };

/** Cascade du score (SHAP) en barres horizontales : niveau moyen, puis contributions, jusqu'au score final. */
export function Cascade({ etapes }: { etapes: EtapeCascade[] }) {
  let cumul = 0;
  const lignes = etapes.map((e) => {
    let debut: number, fin: number;
    if (e.type === "base") { debut = 0; fin = e.valeur; cumul = e.valeur; }
    else if (e.type === "total") { debut = 0; fin = e.valeur; }
    else { debut = cumul; fin = cumul + e.valeur; cumul = fin; }
    return { ...e, debut: Math.min(debut, fin), fin: Math.max(debut, fin) };
  });
  const max = Math.max(100, ...lignes.map((l) => l.fin));
  return (
    <div className="space-y-1.5">
      {lignes.map((l, k) => {
        const hausse = l.valeur > 0;
        const couleur = l.type === "base" ? "bg-gris" : l.type === "total" ? "bg-marine dark:bg-action" : hausse ? "bg-rouge" : "bg-vert";
        return (
          <div key={k} className="grid grid-cols-[minmax(0,42%)_1fr_60px] items-center gap-3 text-xs">
            <span className={cn("truncate", l.type === "total" ? "font-semibold text-encre" : "text-attenue")} title={l.libelle}>
              {TYPES[l.type] && <span className="mr-1 rounded bg-survol px-1 py-0.5 text-[10px] font-medium text-attenue">{TYPES[l.type]}</span>}
              {l.libelle}
            </span>
            <div className="relative h-5 rounded bg-survol/60">
              <motion.div initial={{ width: 0 }} animate={{ width: `${((l.fin - l.debut) / max) * 100}%` }} transition={{ delay: k * 0.03, duration: 0.2 }}
                className={cn("absolute top-0.5 h-4 rounded", couleur, l.type !== "base" && l.type !== "total" && "opacity-85")}
                style={{ left: `${(l.debut / max) * 100}%` }} />
            </div>
            <span className={cn("chiffres text-right font-semibold", l.type === "total" ? "text-encre" : l.type === "base" ? "text-attenue" : hausse ? "text-rouge" : "text-vert")}>
              {l.type === "base" || l.type === "total" ? nombre(l.valeur, 1) : `${hausse ? "+" : "−"}${nombre(Math.abs(l.valeur), 1)}`}
            </span>
          </div>
        );
      })}
      <p className="pt-2 text-[11px] leading-relaxed text-attenue">
        Score = 45 % probabilité calibrée (LightGBM, contributions SHAP) + 40 % force des indices + 15 % atypicité sectorielle (Isolation Forest).
        Rouge : fait monter le score ; vert : le fait baisser.
      </p>
    </div>
  );
}
