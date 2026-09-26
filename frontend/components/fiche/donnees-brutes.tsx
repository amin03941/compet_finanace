"use client";
import * as React from "react";
import { toast } from "sonner";
import type { Fiche } from "@/lib/api";
import { api } from "@/lib/api";
import { cn, nombre } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Dialogue } from "@/components/ui/sheet";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/misc";

function cellule(v: string | number | null) {
  if (v === null || v === undefined || v === "") return "—";
  if (typeof v === "number") return nombre(v, Math.abs(v) < 100 && v % 1 ? 2 : 0);
  return v;
}

/** Les 4 sources côte à côte (onglets) : douane, impôts, TEJ, El Fatoora, et les déclarations annuelles. */
export function DonneesBrutes({ donnees }: { donnees: Fiche["donnees_brutes"] }) {
  const cles = Object.keys(donnees);
  return (
    <Tabs defaultValue={cles[0]}>
      <TabsList>
        {cles.map((c) => <TabsTrigger key={c} value={c}>{donnees[c].titre.split(" (")[0]} <span className="ml-1 text-gris">{donnees[c].lignes.length}</span></TabsTrigger>)}
      </TabsList>
      {cles.map((c) => {
        const lignes = donnees[c].lignes;
        const cols = lignes.length ? Object.keys(lignes[0]) : [];
        return (
          <TabsContent key={c} value={c} className="mt-3">
            <p className="mb-2 text-xs text-attenue">{donnees[c].titre}</p>
            {lignes.length === 0 ? <p className="rounded-xl bg-survol p-4 text-sm text-attenue">Aucune ligne pour cette source.</p> : (
              <div className="defilement max-h-[360px] overflow-auto rounded-xl border border-ligne">
                <table className="w-full text-xs">
                  <thead className="sticky top-0 bg-survol"><tr className="text-left text-attenue">{cols.map((k) => <th key={k} className="whitespace-nowrap px-3 py-2 font-medium">{k}</th>)}</tr></thead>
                  <tbody>
                    {lignes.map((l, i) => (
                      <tr key={i} className="border-t border-ligne">
                        {cols.map((k) => <td key={k} className={cn("whitespace-nowrap px-3 py-1.5", typeof l[k] === "number" && "chiffres text-right")}>{cellule(l[k])}</td>)}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </TabsContent>
        );
      })}
    </Tabs>
  );
}

/** Boucle d'apprentissage : l'agent saisit l'issue du contrôle (redressement oui/non, montant). */
export function DialogueResultat({ ouvert, onChange, entrepriseId, onEnregistre }: {
  ouvert: boolean; onChange: (v: boolean) => void; entrepriseId: number; onEnregistre?: () => void;
}) {
  const [redressement, setRedressement] = React.useState<boolean | null>(null);
  const [montant, setMontant] = React.useState("");
  const [commentaire, setCommentaire] = React.useState("");
  const [envoi, setEnvoi] = React.useState(false);
  const enregistrer = async () => {
    if (redressement === null) return;
    setEnvoi(true);
    try {
      const r = await api<{ resultats_en_attente: number }>(`/api/entreprises/${entrepriseId}/resultat-controle`, {
        method: "POST", body: JSON.stringify({ redressement, montant: Number(montant.replace(/\s/g, "")) || 0, commentaire, agent: "agent.demo" }),
      });
      toast.success("Résultat enregistré", { description: `${r.resultats_en_attente} résultat(s) disponible(s) pour le prochain ré-entraînement.` });
      onChange(false);
      onEnregistre?.();
    } catch (e) {
      toast.error("Échec de l'enregistrement", { description: (e as Error).message });
    } finally {
      setEnvoi(false);
    }
  };
  return (
    <Dialogue ouvert={ouvert} onChange={onChange} titre="Résultat du contrôle">
      <p className="mb-4 text-xs text-attenue">L&apos;issue réelle du contrôle alimente l&apos;apprentissage du modèle (bouton « Ré-entraîner » de la page Performance).</p>
      <div className="mb-4 grid grid-cols-2 gap-2">
        {[{ v: true, l: "Redressement" }, { v: false, l: "Sans redressement" }].map((o) => (
          <button key={String(o.v)} onClick={() => setRedressement(o.v)}
            className={cn("rounded-xl border px-3 py-2.5 text-sm font-medium", redressement === o.v ? "border-action bg-action/10 text-action" : "border-ligne hover:bg-survol")}>
            {o.l}
          </button>
        ))}
      </div>
      {redressement && (
        <label className="mb-3 block text-xs font-medium text-attenue">Montant redressé (DT)
          <input value={montant} onChange={(e) => setMontant(e.target.value)} inputMode="numeric" placeholder="ex. 480 000"
            className="mt-1 h-10 w-full rounded-xl border border-ligne bg-carte px-3 text-sm text-encre outline-none focus:ring-2 focus:ring-action/30" />
        </label>
      )}
      <label className="mb-5 block text-xs font-medium text-attenue">Commentaire
        <textarea value={commentaire} onChange={(e) => setCommentaire(e.target.value)} rows={3}
          className="mt-1 w-full rounded-xl border border-ligne bg-carte px-3 py-2 text-sm text-encre outline-none focus:ring-2 focus:ring-action/30" />
      </label>
      <div className="flex justify-end gap-2">
        <Button variant="secondaire" onClick={() => onChange(false)}>Annuler</Button>
        <Button onClick={enregistrer} disabled={redressement === null || envoi}>Enregistrer</Button>
      </div>
    </Dialogue>
  );
}
