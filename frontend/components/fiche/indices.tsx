"use client";
import * as React from "react";
import useSWR from "swr";
import { motion } from "framer-motion";
import { CheckCircle2, CircleDashed, FileSearch, TriangleAlert } from "lucide-react";
import { fetcher, type Indice, type Neutralisation, type Preuves } from "@/lib/api";
import { cn, dt, nombre, pct } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { EtatErreur, Infobulle, Skeleton } from "@/components/ui/misc";
import { Tiroir } from "@/components/ui/sheet";
import { FORCES } from "@/components/risque/elements";

function valeurLisible(i: Indice): string {
  if (i.valeur === null || i.valeur === undefined) return "—";
  if (["A1", "A2", "A3", "A4", "B4"].includes(i.code)) return `ratio ${nombre(i.valeur, 2)} (seuil ${nombre(i.seuil ?? 0, 2)})`;
  if (i.code === "B1") return `marge ${pct(i.valeur)} (seuil ${pct(i.seuil ?? 0)})`;
  if (i.code === "B2") return `${pct(i.valeur, 0)} du prix de référence (seuil 70 %)`;
  if (i.code === "A5") return `${nombre(i.valeur)} mois (seuil 3)`;
  if (i.code === "C3") return `${nombre(i.valeur)} mois en crédit (seuil 10)`;
  if (i.code === "C1") return `${nombre(i.valeur)} déclarations en 7 jours (seuil 5)`;
  return "";
}

export function CartesIndices({ entrepriseId, indices }: { entrepriseId: number; indices: Indice[] }) {
  const [ouvert, setOuvert] = React.useState<Indice | null>(null);
  const declenches = indices.filter((i) => i.declenchee).sort((a, b) => a.niveau.localeCompare(b.niveau) || b.montant_en_jeu - a.montant_en_jeu);
  const autres = indices.filter((i) => !i.declenchee);
  return (
    <div>
      {declenches.length === 0 ? (
        <div className="flex items-center gap-3 rounded-2xl border border-vert/30 bg-vert/5 p-4 text-sm">
          <CheckCircle2 className="h-5 w-5 text-vert" />
          <span>Aucun indice déclenché : les données des différentes sources sont cohérentes entre elles.</span>
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-3">
          {declenches.map((i, k) => (
            <motion.div key={i.code} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: k * 0.04, duration: 0.18 }}
              className={cn("flex flex-col rounded-2xl border bg-carte p-4 shadow-carte", i.niveau === "A" ? "border-rouge/30" : i.niveau === "B" ? "border-orange/40" : "border-ligne")}>
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-center gap-2">
                  <span className={cn("chiffres rounded-lg border px-2 py-0.5 text-xs font-bold", FORCES[i.niveau].classe)}>{i.code}</span>
                  <Infobulle contenu={<><p className="font-semibold">{FORCES[i.niveau].libelle}</p><p className="mt-1">Formule : {i.formule}</p><p className="mt-1">Déclenché si : {i.condition}</p></>}>
                    <p className="cursor-help text-sm font-semibold leading-snug text-marine dark:text-encre">{i.libelle}</p>
                  </Infobulle>
                </div>
                {i.montant_en_jeu > 0 && <span className="chiffres whitespace-nowrap text-sm font-semibold text-encre">{dt(i.montant_en_jeu)}</span>}
              </div>
              <p className="mt-3 flex-1 text-[13px] leading-relaxed text-encre/90">{i.phrase}</p>
              <div className="mt-3 flex items-center justify-between gap-2 border-t border-ligne pt-3">
                <span className="text-[11px] text-attenue">{valeurLisible(i)}{i.annees.length > 1 ? ` · ${i.annees.join(", ")}` : ""}</span>
                <Button variant="secondaire" taille="sm" onClick={() => setOuvert(i)}><FileSearch /> Voir les preuves</Button>
              </div>
            </motion.div>
          ))}
        </div>
      )}
      <div className="mt-4 flex flex-wrap items-center gap-1.5">
        <span className="mr-1 text-[11px] font-medium uppercase tracking-wide text-attenue">Contrôlés sans alerte</span>
        {autres.map((i) => (
          <Infobulle key={i.code} contenu={<><p className="font-semibold">{i.code} — {i.libelle}</p><p className="mt-1">{i.condition}</p>{valeurLisible(i) && <p className="mt-1">Valeur : {valeurLisible(i)}</p>}</>}>
            <span className="chiffres cursor-help rounded-md border border-ligne px-1.5 py-0.5 text-[11px] text-gris">{i.code}</span>
          </Infobulle>
        ))}
      </div>
      {ouvert && <TiroirPreuves entrepriseId={entrepriseId} indice={ouvert} onClose={() => setOuvert(null)} />}
    </div>
  );
}

function cellule(v: string | number | null) {
  if (v === null || v === undefined) return "—";
  if (typeof v === "number") return Math.abs(v) >= 100 ? nombre(v, 0) : nombre(v, v % 1 ? 3 : 0);
  return v;
}

function TiroirPreuves({ entrepriseId, indice, onClose }: { entrepriseId: number; indice: Indice; onClose: () => void }) {
  const { data, error } = useSWR<Preuves>(`/api/entreprises/${entrepriseId}/preuves/${indice.code}`, fetcher);
  return (
    <Tiroir ouvert onChange={(v) => !v && onClose()} titre={<>Preuves · {indice.code} — {indice.libelle}</>}
      description={data?.source || "Lignes sources de l'indice"}>
      {indice.phrase && <p className="mb-4 rounded-xl bg-survol p-3 text-sm">{indice.phrase}</p>}
      {error ? <EtatErreur message={error.message} /> : !data ? <Skeleton className="h-64" /> : (
        <>
          <p className="chiffres mb-2 text-xs text-attenue">{nombre(data.total)} ligne{data.total > 1 ? "s" : ""} source{data.total > 1 ? "s" : ""}{data.total > data.lignes.length ? ` (${data.lignes.length} affichées)` : ""}</p>
          <div className="overflow-hidden rounded-xl border border-ligne">
            <table className="w-full text-xs">
              <thead><tr className="bg-survol text-left text-attenue">{data.colonnes.map((c) => <th key={c} className="px-3 py-2 font-medium">{c}</th>)}</tr></thead>
              <tbody>
                {data.lignes.map((l, k) => (
                  <tr key={k} className="border-t border-ligne">
                    {data.colonnes.map((c) => <td key={c} className={cn("px-3 py-2", typeof l[c] === "number" && "chiffres text-right")}>{cellule(l[c])}</td>)}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </Tiroir>
  );
}

const ICONES = {
  verifie: <CheckCircle2 className="h-4 w-4 text-vert" />,
  sans_objet: <CircleDashed className="h-4 w-4 text-gris" />,
  manquant: <TriangleAlert className="h-4 w-4 text-orange" />,
};

export function Neutralisations({ items }: { items: Neutralisation[] }) {
  return (
    <ul className="space-y-2.5">
      {items.map((n) => (
        <li key={n.cle} className="flex items-start gap-3">
          <span className="mt-0.5">{ICONES[n.statut]}</span>
          <div>
            <p className="text-sm font-medium">{n.libelle} {n.statut === "verifie" && <span className="text-vert">✔</span>}</p>
            <p className="text-xs leading-relaxed text-attenue">{n.detail}</p>
          </div>
        </li>
      ))}
    </ul>
  );
}
