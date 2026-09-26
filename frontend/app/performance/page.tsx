"use client";
import * as React from "react";
import useSWR from "swr";
import { toast } from "sonner";
import { Bar, BarChart, CartesianGrid, Cell, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { BrainCircuit, Coins, RefreshCw, ShieldCheck, Target } from "lucide-react";
import { api, fetcher } from "@/lib/api";
import { useCouleurs } from "@/lib/couleurs";
import { cn, dateFr, dt, dtCompact, nombre, pct } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { EtatErreur, Skeleton } from "@/components/ui/misc";
import { CarteKpi, EnTetePage } from "@/components/risque/elements";
import { useFilAriane } from "@/components/shell/shell";

interface Top { n: number; precision: number; rappel: number; montant_detecte: number; pieges_dans_top: number; taux_fausses_alertes_pieges: number }
interface Perf {
  resume: { precision_top100_regles_ia: number; precision_hasard: number; gain_vs_hasard: number; montant_top100_regles: number;
    montant_top100_regles_ia: number; gain_montant_ia_pct: number; taux_redressement_historique: number; fausses_alertes_pieges_outil: number; fausses_alertes_pieges_naif: number };
  methodes: Record<string, { libelle: string; top: Top[] }>;
  categories: Record<string, Record<string, number>>;
  fausses_alertes: { outil: number; outil_rouge: number; naif: number; honnetes_outil: number; honnetes_naif: number };
  schemas: { code: string; libelle: string; n: number; rouge: number; alerte: number; top200_regles_ia: number; top200_regles: number }[];
  auc: Record<string, number>;
  modele: { n_etiquettes: number; taux_redressement: number; auc_validation_croisee: number; brier_validation_croisee: number };
  signaux_faibles: { fraudeurs_sans_alerte: number; dont_atypiques: number; non_fraudeurs_sans_alerte: number; dont_atypiques_non_fraudeurs: number };
  historique: { n_controles: number; taux_par_origine: Record<string, number> };
  population: { entreprises: number; fraudeurs: number; pieges: number; honnetes: number; montant_elude_total: number };
}

const ORDRE = ["hasard", "ecart_brut", "regles", "regles_ia"] as const;
const COURT: Record<string, string> = { hasard: "Hasard", ecart_brut: "Écart brut naïf", regles: "Règles seules", regles_ia: "Règles + IA" };
const INFOBULLE = { contentStyle: { borderRadius: 12, border: "1px solid rgb(var(--ligne))", background: "rgb(var(--carte))", fontSize: 12 } };

export default function Performance() {
  useFilAriane([{ libelle: "Performance" }]);
  const C = useCouleurs();
  const { data, error, mutate } = useSWR<{ performance: Perf; calcule_le: string }>("/api/performance", fetcher);
  const [entrainement, setEntrainement] = React.useState(false);
  const couleurs: Record<string, string> = { hasard: C.gris, ecart_brut: C.orange, regles: C.action2, regles_ia: C.action };
  const AXE = { fontSize: 11, fill: C.attenue };

  const reentrainer = async () => {
    setEntrainement(true);
    try {
      await api("/api/admin/reentrainer", { method: "POST" });
      for (let i = 0; i < 60; i++) {
        await new Promise((r) => setTimeout(r, 2000));
        const t = await api<{ reentrainement: { etat: string; message?: string } }>("/api/admin/taches");
        if (t.reentrainement.etat === "termine") { toast.success("Modèle ré-entraîné", { description: "Scores et métriques recalculés avec les résultats saisis." }); break; }
        if (t.reentrainement.etat === "erreur") { toast.error("Échec du ré-entraînement", { description: t.reentrainement.message }); break; }
      }
      await mutate();
    } catch (e) {
      toast.error("Échec du ré-entraînement", { description: (e as Error).message });
    } finally {
      setEntrainement(false);
    }
  };

  if (error) return <EtatErreur message={error.message} />;
  const p = data?.performance;
  const precision = p ? [50, 100, 200].map((n, i) => ({ n: `${n} premiers`, ...Object.fromEntries(ORDRE.map((m) => [m, p.methodes[m].top[i].precision])) })) : [];
  const montants = p ? ORDRE.map((m) => ({ m, libelle: COURT[m], montant: p.methodes[m].top[1].montant_detecte })) : [];
  const pieges = p ? ORDRE.map((m) => ({ m, libelle: COURT[m], taux: p.methodes[m].top[2].taux_fausses_alertes_pieges })) : [];

  return (
    <div className="space-y-5">
      <EnTetePage titre="Performance du ciblage"
        sousTitre={<>Mesurée sur la vérité terrain de la base fictive, <b>jamais utilisée pour entraîner</b>. Chiffres recalculés à chaque lancement{data ? ` (le ${dateFr(data.calcule_le)})` : ""}.</>}
        actions={<Button variant="secondaire" onClick={reentrainer} disabled={entrainement}><RefreshCw className={cn(entrainement && "animate-spin")} /> {entrainement ? "Ré-entraînement…" : "Ré-entraîner le modèle"}</Button>} />

      <div className="grid grid-cols-4 gap-4">
        {!p ? Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-[126px]" />) : <>
          <CarteKpi titre="Réussite des 100 premiers contrôles" valeur={pct(p.resume.precision_top100_regles_ia, 0)} accent="bg-vert/10 text-vert" icone={<Target className="h-4 w-4" />}
            detail={<>contre {pct(p.resume.precision_hasard, 0)} au hasard et {pct(p.resume.taux_redressement_historique, 0)} pour la sélection historique</>} />
          <CarteKpi titre="Montant détecté · 100 contrôles" valeur={dtCompact(p.resume.montant_top100_regles_ia)} accent="bg-orange/10 text-amber-600" icone={<Coins className="h-4 w-4" />}
            detail={<>+{pct(p.resume.gain_montant_ia_pct, 0)} grâce à l&apos;IA (règles seules : {dtCompact(p.resume.montant_top100_regles)})</>} />
          <CarteKpi titre="Fausses alertes sur les pièges" valeur={pct(p.fausses_alertes.outil)} accent="bg-rouge/10 text-rouge" icone={<ShieldCheck className="h-4 w-4" />}
            detail={<>contre {pct(p.fausses_alertes.naif, 0)} avec l&apos;écart brut (importations &gt; CA)</>}
            info="Pièges : entreprises honnêtes présentant un écart brut réel mais expliqué (stock, équipements, admission temporaire, exportations, secteur à faible marge…)." />
          <CarteKpi titre="Qualité du modèle (AUC)" valeur={nombre(p.auc.score_final, 2)} icone={<BrainCircuit className="h-4 w-4" />}
            detail={<>validation croisée sur {nombre(p.modele.n_etiquettes)} contrôles passés : {nombre(p.modele.auc_validation_croisee, 2)}</>}
            info="AUC du score final sur la vérité terrain (1 = parfait, 0,5 = hasard). La validation croisée sur les étiquettes imparfaites des contrôles passés est plus basse, comme attendu." />
        </>}
      </div>

      <div className="grid grid-cols-3 gap-5">
        <Card className="col-span-2">
          <CardHeader><div><CardTitle>Taux de réussite des contrôles</CardTitle><CardDescription>Part de fraudeurs réels parmi les N premières entreprises de chaque méthode</CardDescription></div></CardHeader>
          <CardContent className="h-[300px] pt-2">
            {!p ? <Skeleton className="h-full" /> : (
              <ResponsiveContainer>
                <BarChart data={precision} margin={{ left: -10, right: 8, top: 8 }}>
                  <CartesianGrid vertical={false} stroke={C.ligne} />
                  <XAxis dataKey="n" tick={AXE} tickLine={false} axisLine={false} />
                  <YAxis tickFormatter={(v) => pct(v, 0)} tick={AXE} tickLine={false} axisLine={false} domain={[0, 1]} />
                  <Tooltip {...INFOBULLE} formatter={(v: number, n) => [pct(v), COURT[n as string]]} />
                  <Legend formatter={(v) => COURT[v]} iconType="circle" wrapperStyle={{ fontSize: 12 }} />
                  {ORDRE.map((m) => <Bar key={m} dataKey={m} fill={couleurs[m]} radius={[5, 5, 0, 0]} />)}
                </BarChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader><div><CardTitle>Montant détecté</CardTitle><CardDescription>Droits éludés réels chez les fraudeurs des 100 premiers contrôles</CardDescription></div></CardHeader>
          <CardContent className="h-[300px] pt-2">
            {!p ? <Skeleton className="h-full" /> : (
              <ResponsiveContainer>
                <BarChart data={montants} layout="vertical" margin={{ left: 12, right: 16 }}>
                  <CartesianGrid horizontal={false} stroke={C.ligne} />
                  <XAxis type="number" tickFormatter={(v) => dtCompact(v).replace(/ DT/, "")} tick={AXE} tickLine={false} axisLine={false} />
                  <YAxis type="category" dataKey="libelle" tick={AXE} width={96} tickLine={false} axisLine={false} />
                  <Tooltip {...INFOBULLE} formatter={(v: number) => [dt(v), "Montant détecté"]} />
                  <Bar dataKey="montant" radius={[0, 6, 6, 0]}>{montants.map((d) => <Cell key={d.m} fill={couleurs[d.m]} />)}</Bar>
                </BarChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-3 gap-5">
        <Card>
          <CardHeader><div><CardTitle>Pièges pris pour des fraudeurs</CardTitle><CardDescription>Part des honnêtes « avec écart expliqué » dans les 200 premiers</CardDescription></div></CardHeader>
          <CardContent className="h-[260px] pt-2">
            {!p ? <Skeleton className="h-full" /> : (
              <ResponsiveContainer>
                <BarChart data={pieges} margin={{ left: -10, right: 8, top: 8 }}>
                  <CartesianGrid vertical={false} stroke={C.ligne} />
                  <XAxis dataKey="libelle" tick={AXE} tickLine={false} axisLine={false} interval={0} />
                  <YAxis tickFormatter={(v) => pct(v, 0)} tick={AXE} tickLine={false} axisLine={false} />
                  <Tooltip {...INFOBULLE} formatter={(v: number) => [pct(v), "Pièges dans le top 200"]} />
                  <Bar dataKey="taux" radius={[5, 5, 0, 0]}>{pieges.map((d) => <Cell key={d.m} fill={couleurs[d.m]} />)}</Bar>
                </BarChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>
        <Card className="col-span-2">
          <CardHeader><div><CardTitle>Détection par schéma de fraude</CardTitle><CardDescription>Part des fraudeurs de chaque schéma signalés (rouge ou orange) et présents dans les 200 premiers</CardDescription></div></CardHeader>
          <CardContent className="pt-3">
            {!p ? <Skeleton className="h-52" /> : (
              <table className="w-full text-sm">
                <thead><tr className="text-left text-[11px] uppercase tracking-wide text-attenue"><th className="py-1.5">Schéma</th><th className="text-right">Entreprises</th><th className="text-right">Signalées</th><th className="text-right">Top 200 · règles</th><th className="text-right">Top 200 · règles + IA</th></tr></thead>
                <tbody>
                  {p.schemas.map((s) => (
                    <tr key={s.code} className="border-t border-ligne">
                      <td className="py-2"><span className="chiffres mr-2 rounded bg-survol px-1.5 py-0.5 text-[11px] font-semibold">{s.code}</span>{s.libelle}</td>
                      <td className="chiffres text-right">{s.n}</td>
                      <td className="chiffres text-right">{pct(s.alerte, 0)}</td>
                      <td className="chiffres text-right text-attenue">{pct(s.top200_regles, 0)}</td>
                      <td className={cn("chiffres text-right font-semibold", s.top200_regles_ia > s.top200_regles ? "text-vert" : s.top200_regles_ia < s.top200_regles ? "text-rouge" : "")}>{pct(s.top200_regles_ia, 0)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-3 gap-5">
        <Card className="col-span-2">
          <CardHeader><div><CardTitle>Méthodologie, simplement</CardTitle><CardDescription>Comment l&apos;agent décide si c&apos;est vraiment une fraude</CardDescription></div></CardHeader>
          <CardContent className="grid grid-cols-3 gap-4 pt-4 text-[13px] leading-relaxed">
            {[
              ["1. Neutraliser", "Avant tout calcul, on retire ce qui explique un écart honnête : variation de stock, décalage de période (comparaison sur 12 et 36 mois), machines (annexe du décret 2017-419), admission temporaire et réexportation, exportations, données manquantes."],
              ["2. Croiser des sources indépendantes", "Les indices les plus forts viennent de tiers que l'entreprise ne contrôle pas : ses clients (TEJ), ses factures électroniques (El Fatoora), la douane, la banque. Chaque règle est explicable et chiffrée."],
              ["3. Apprendre des contrôles passés", "Un modèle LightGBM (contraintes monotones, calibration isotonique) apprend sur 580 contrôles aux étiquettes imparfaites ; une Isolation Forest par secteur repère les signaux faibles. Priorité = probabilité × montant en jeu."],
            ].map(([t, x]) => <div key={t} className="rounded-xl bg-survol p-4"><p className="mb-1 font-semibold text-marine dark:text-encre">{t}</p><p className="text-attenue">{x}</p></div>)}
            <p className="col-span-3 text-xs text-attenue">
              Évaluation : la base fictive contient une vérité terrain cachée (72 % d&apos;honnêtes, 17 % d&apos;honnêtes avec écart expliqué, 11 % de fraudeurs répartis sur 8 schémas).
              Elle ne sert qu&apos;à mesurer ; le modèle n&apos;apprend que des contrôles passés, dont environ 10 % de fraudeurs contrôlés sans redressement (bruit réaliste).
              Pour les entreprises déjà contrôlées, le score est calculé hors échantillon (validation croisée).
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader><div><CardTitle>Ce que l&apos;IA ajoute aux règles</CardTitle></div></CardHeader>
          <CardContent className="space-y-3 pt-3 text-[13px]">
            {!p ? <Skeleton className="h-40" /> : <>
              <p><b className="chiffres">+{pct(p.resume.gain_montant_ia_pct, 0)}</b> de montant détecté pour le même nombre de contrôles : la priorité (probabilité × montant) place d&apos;abord les dossiers les plus lourds.</p>
              <p>Signaux faibles : sur <b className="chiffres">{p.signaux_faibles.fraudeurs_sans_alerte}</b> fraudeurs qu&apos;aucune règle ne signale, <b className="chiffres">{p.signaux_faibles.dont_atypiques}</b> sont repérés comme atypiques par l&apos;Isolation Forest
                (contre {pct(p.signaux_faibles.dont_atypiques_non_fraudeurs / Math.max(1, p.signaux_faibles.non_fraudeurs_sans_alerte), 0)} des non-fraudeurs).</p>
              <p className="text-xs text-attenue">Sélection historique (étiquettes) : {Object.entries(p.historique.taux_par_origine).map(([k, v]) => `${k} ${pct(v, 0)}`).join(" · ")} de redressements.</p>
            </>}
          </CardContent>
        </Card>
      </div>

      {p && (
        <Card>
          <CardHeader><div><CardTitle>Catégorie affichée selon la vérité terrain</CardTitle><CardDescription>{nombre(p.population.entreprises)} entreprises · {nombre(p.population.fraudeurs)} fraudeurs · {nombre(p.population.pieges)} pièges</CardDescription></div></CardHeader>
          <CardContent className="pt-3">
            <table className="w-full text-sm">
              <thead><tr className="text-left text-[11px] uppercase tracking-wide text-attenue"><th className="py-1.5">Vérité terrain</th><th className="text-right">Contrôle recommandé</th><th className="text-right">Demande de justification</th><th className="text-right">Données insuffisantes</th><th className="text-right">Cohérent</th></tr></thead>
              <tbody>
                {[["fraudeur", "Fraudeurs"], ["honnete_ecart_explique", "Honnêtes avec écart expliqué (pièges)"], ["honnete", "Honnêtes cohérents"]].map(([k, l]) => (
                  <tr key={k} className="border-t border-ligne">
                    <td className="py-2">{l}</td>
                    {["rouge", "orange", "gris", "vert"].map((c) => <td key={c} className="chiffres text-right">{nombre(p.categories[k]?.[c] ?? 0)}</td>)}
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
