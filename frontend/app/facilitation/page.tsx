"use client";
import * as React from "react";
import Link from "next/link";
import useSWR from "swr";
import { Check, HandCoins, ShieldCheck, X } from "lucide-react";
import { fetcher, type LigneCiblage } from "@/lib/api";
import { cn, nombre } from "@/lib/utils";
import { Card } from "@/components/ui/card";
import { EtatErreur, EtatVide, Infobulle, Skeleton } from "@/components/ui/misc";
import { CarteKpi, EnTetePage, PastilleScore } from "@/components/risque/elements";
import { useFilAriane } from "@/components/shell/shell";

interface Candidat extends LigneCiblage {
  statut_export: string;
  criteres: { libelle: string; ok: boolean }[];
  candidat_oea: boolean;
  candidat_remboursement_rapide: boolean;
}

export default function Facilitation() {
  useFilAriane([{ libelle: "Facilitation" }]);
  const { data, error } = useSWR<{ total: number; candidats_oea: number; candidats_remboursement: number; entreprises: Candidat[] }>("/api/facilitation", fetcher);
  const [filtre, setFiltre] = React.useState<"tous" | "oea" | "remboursement">("tous");
  if (error) return <EtatErreur message={error.message} />;
  const liste = (data?.entreprises || []).filter((e) => filtre === "tous" || (filtre === "oea" ? e.candidat_oea : e.candidat_remboursement_rapide));
  return (
    <div>
      <EnTetePage titre="Facilitation des entreprises fiables"
        sousTitre="Récompenser la conformité : candidates au statut d'opérateur économique agréé (OEA) et au remboursement rapide du crédit de TVA." />
      <div className="mb-5 grid grid-cols-3 gap-4">
        {!data ? Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-[120px]" />) : <>
          <CarteKpi titre="Entreprises fiables" valeur={nombre(data.total)} accent="bg-vert/10 text-vert" icone={<Check className="h-4 w-4" />}
            detail="Tous les critères remplis sur 3 ans" />
          <CarteKpi titre="Candidates OEA" valeur={nombre(data.candidats_oea)} icone={<ShieldCheck className="h-4 w-4" />}
            detail="Importatrices ou exportatrices, non encore agréées" info="Décret gouvernemental n° 2018-612 relatif au statut d'opérateur économique agréé (texte indexé)." />
          <CarteKpi titre="Remboursement rapide de TVA" valeur={nombre(data.candidats_remboursement)} accent="bg-orange/10 text-amber-600" icone={<HandCoins className="h-4 w-4" />}
            detail="Exportatrices au crédit de TVA structurel et justifié" />
        </>}
      </div>
      <div className="mb-3 flex gap-1 rounded-xl bg-survol p-1 text-xs font-medium" style={{ width: "fit-content" }}>
        {([["tous", "Toutes"], ["oea", "Candidates OEA"], ["remboursement", "Remboursement rapide"]] as const).map(([v, l]) => (
          <button key={v} onClick={() => setFiltre(v)} className={cn("rounded-lg px-3 py-1.5", filtre === v ? "bg-carte text-encre shadow-sm" : "text-attenue")}>{l}</button>
        ))}
      </div>
      {!data ? <Skeleton className="h-96" /> : liste.length === 0 ? <EtatVide titre="Aucune entreprise" /> : (
        <Card className="overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-ligne bg-survol/60 text-left text-[11px] font-semibold uppercase tracking-wide text-attenue">
                <th className="px-4 py-3">Entreprise</th><th className="px-3 py-3 text-center">Score</th><th className="px-3 py-3">Critères remplis</th>
                <th className="px-3 py-3">Proposition</th>
              </tr>
            </thead>
            <tbody>
              {liste.slice(0, 200).map((e) => (
                <tr key={e.id} className="border-b border-ligne last:border-0 hover:bg-survol/60">
                  <td className="px-4 py-3">
                    <Link href={`/entreprise/${e.id}`} className="font-medium hover:text-action">{e.raison_sociale}</Link>
                    <p className="text-[11px] text-attenue">{e.secteur} · {e.gouvernorat} · {e.statut_export}</p>
                  </td>
                  <td className="px-3 py-3 text-center"><PastilleScore score={e.score} taille="sm" /></td>
                  <td className="px-3 py-3">
                    <div className="flex flex-wrap gap-1">
                      {e.criteres.map((c) => (
                        <Infobulle key={c.libelle} contenu={c.libelle}>
                          <span className={cn("flex h-6 w-6 items-center justify-center rounded-md", c.ok ? "bg-vert/10 text-vert" : "bg-rouge/10 text-rouge")}>
                            {c.ok ? <Check className="h-3.5 w-3.5" /> : <X className="h-3.5 w-3.5" />}
                          </span>
                        </Infobulle>
                      ))}
                    </div>
                  </td>
                  <td className="px-3 py-3">
                    <div className="flex flex-wrap gap-1.5">
                      {e.candidat_oea && <span className="rounded-full bg-action/10 px-2.5 py-1 text-xs font-medium text-action">Statut OEA</span>}
                      {e.candidat_remboursement_rapide && <span className="rounded-full bg-orange/15 px-2.5 py-1 text-xs font-medium text-amber-700 dark:text-orange">Remboursement rapide</span>}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {liste.length > 200 && <p className="border-t border-ligne px-4 py-2 text-xs text-attenue">200 premières sur {nombre(liste.length)}.</p>}
        </Card>
      )}
      <p className="mt-4 text-xs text-attenue">
        Critères : aucun indice A, B ou C sur 3 ans, déclarations complètes, TVA déposée dans les délais, score &lt; 10, ancienneté ≥ 5 ans,
        aucun redressement antérieur, activité significative. Proposition soumise à l&apos;instruction habituelle du dossier.
      </p>
    </div>
  );
}
