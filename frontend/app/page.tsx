"use client";
import Link from "next/link";
import useSWR from "swr";
import { ArrowRight, Building2, Coins, Siren, Target } from "lucide-react";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { fetcher, type Stats } from "@/lib/api";
import { useCouleurs } from "@/lib/couleurs";
import { dt, dtCompact, moisCourt, nombre, pct } from "@/lib/utils";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { EtatErreur, Skeleton } from "@/components/ui/misc";
import { BadgeCategorie, BadgeTypeDossier, CarteKpi, EnTetePage, PastilleScore, PucesIndices } from "@/components/risque/elements";
import { useFilAriane } from "@/components/shell/shell";

const INFOBULLE = {
  contentStyle: { borderRadius: 12, border: "1px solid rgb(var(--ligne))", background: "rgb(var(--carte))", fontSize: 12 },
  labelStyle: { color: "rgb(var(--encre))", fontWeight: 600 },
};

export default function TableauDeBord() {
  useFilAriane([{ libelle: "Tableau de bord" }]);
  const { data, error } = useSWR<Stats>("/api/stats", fetcher);
  const C = useCouleurs();
  const AXE = { fontSize: 11, fill: C.attenue };
  if (error) return <EtatErreur message={error.message} />;
  const k = data?.kpis;
  return (
    <div className="space-y-6">
      <EnTetePage titre="Tableau de bord" sousTitre="Vue d'ensemble du ciblage : impôts et douane croisés, sur 3 ans (2023–2025)." />

      <div className="grid grid-cols-4 gap-4">
        {!k ? Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-[126px]" />) : <>
          <CarteKpi titre="Entreprises analysées" valeur={nombre(k.entreprises_analysees)} icone={<Building2 className="h-4 w-4" />}
            detail="Croisement douane, TVA, TEJ, El Fatoora, banque" />
          <CarteKpi titre="Alertes rouges" valeur={nombre(k.alertes_rouges)} accent="bg-rouge/10 text-rouge" icone={<Siren className="h-4 w-4" />}
            detail={`+ ${nombre(k.demandes_justification)} demandes de justification`}
            info="Contrôle recommandé : au moins un indice A (> 20 000 DT en jeu), deux indices B concordants, ou un B et deux C." />
          <CarteKpi titre="Montant en jeu estimé" valeur={dtCompact(k.montant_en_jeu)} accent="bg-orange/10 text-amber-600" icone={<Coins className="h-4 w-4" />}
            detail="Alertes rouges et orange, estimation indicative" info={`Total exact : ${dt(k.montant_en_jeu)}. Montants à confirmer par la procédure contradictoire.`} />
          <CarteKpi titre="Réussite du ciblage" valeur={pct(k.precision_ciblage, 0)} accent="bg-vert/10 text-vert" icone={<Target className="h-4 w-4" />}
            detail={<>contre {pct(k.precision_hasard, 0)} au hasard (× {nombre(k.gain_vs_hasard, 1)}) · 100 premiers</>}
            info="Part de fraudeurs réels parmi les 100 premières entreprises de la liste, mesurée sur la vérité terrain de la base fictive (jamais utilisée pour entraîner)." />
        </>}
      </div>

      <div className="grid grid-cols-3 gap-4">
        <Card className="col-span-2">
          <CardHeader>
            <div>
              <CardTitle>Évolution mensuelle des signaux</CardTitle>
              <CardDescription>Entreprises présentant au moins un signal dans le mois (défaut de dépôt, TVA déduite en trop, factures &gt; CA, sous-évaluation)</CardDescription>
            </div>
          </CardHeader>
          <CardContent className="h-[390px] pt-2">
            {!data ? <Skeleton className="h-full" /> : (
              <ResponsiveContainer>
                <AreaChart data={data.evolution_mensuelle} margin={{ left: -18, right: 8, top: 8 }}>
                  <defs>
                    <linearGradient id="gSignal" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor={C.action} stopOpacity={0.25} />
                      <stop offset="100%" stopColor={C.action} stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid vertical={false} stroke={C.ligne} />
                  <XAxis dataKey="periode" tickFormatter={moisCourt} tick={AXE} interval={2} tickLine={false} axisLine={false} />
                  <YAxis tick={AXE} tickLine={false} axisLine={false} />
                  <Tooltip {...INFOBULLE} labelFormatter={moisCourt} />
                  <Area type="monotone" dataKey="entreprises" name="Entreprises avec signal" stroke={C.action} fill="url(#gSignal)" strokeWidth={2} />
                  <Area type="monotone" dataKey="dont_rouges" name="dont alertes rouges" stroke={C.rouge} fill="transparent" strokeWidth={2} />
                  <Legend iconType="circle" wrapperStyle={{ fontSize: 12 }} />
                </AreaChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <div><CardTitle>Top 5 à contrôler ce mois</CardTitle><CardDescription>Classés par priorité = probabilité × montant en jeu</CardDescription></div>
            <Link href="/ciblage" className="flex items-center gap-1 text-xs font-medium text-action hover:underline">Tout voir <ArrowRight className="h-3 w-3" /></Link>
          </CardHeader>
          <CardContent className="space-y-2 pt-3">
            {!data ? Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-14" />) :
              data.top5.map((e) => (
                <Link key={e.id} href={`/entreprise/${e.id}`} className="flex items-center gap-3 rounded-xl border border-transparent p-2.5 transition-colors hover:border-ligne hover:bg-survol">
                  <span className="chiffres w-5 text-center text-sm font-semibold text-gris">{e.rang}</span>
                  <PastilleScore score={e.score} categorie={e.categorie} taille="sm" />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium">{e.raison_sociale}</p>
                    <div className="mt-0.5 flex items-center gap-2"><PucesIndices codes={e.regles} max={4} /></div>
                  </div>
                  <span className="chiffres text-right text-xs font-medium text-encre">{dtCompact(e.montant_en_jeu)}</span>
                </Link>
              ))}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader><div><CardTitle>Alertes par administration compétente</CardTitle>
          <CardDescription>Type de pré-dossier déduit des indices : fiscal (DGI), douanier (Douane) ou conjoint (les deux, avec fiche de transmission)</CardDescription></div></CardHeader>
        <CardContent className="grid grid-cols-3 gap-3 pt-2">
          {!data ? Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-24" />) :
            data.alertes_par_administration.map((a) => (
              <Link key={a.type} href={`/ciblage?type=${a.type}`} className="rounded-xl border border-ligne p-4 transition-colors hover:border-action/40 hover:bg-survol">
                <div className="flex items-center justify-between"><BadgeTypeDossier type={a.type} /><ArrowRight className="h-3.5 w-3.5 text-gris" /></div>
                <p className="chiffres mt-2 text-2xl font-semibold text-marine dark:text-encre">{nombre(a.rouges + a.oranges)}</p>
                <p className="chiffres text-xs text-attenue"><span className="text-rouge">{nombre(a.rouges)} rouges</span> · <span className="text-amber-600">{nombre(a.oranges)} orange</span> · {dtCompact(a.montant)}</p>
              </Link>
            ))}
        </CardContent>
      </Card>

      <div className="grid grid-cols-2 gap-4">
        <Card>
          <CardHeader><div><CardTitle>Montant associé à chaque indice</CardTitle><CardDescription>Alertes rouges et orange (non additif : un enjeu peut être signalé par plusieurs indices)</CardDescription></div></CardHeader>
          <CardContent className="h-[300px] pt-2">
            {!data ? <Skeleton className="h-full" /> : (
              <ResponsiveContainer>
                <BarChart data={data.montant_par_indice.filter((x) => x.montant > 0)} layout="vertical" margin={{ left: 0, right: 16 }}>
                  <CartesianGrid horizontal={false} stroke={C.ligne} />
                  <XAxis type="number" tickFormatter={(v) => dtCompact(v).replace(/ DT/, "")} tick={AXE} tickLine={false} axisLine={false} />
                  <YAxis type="category" dataKey="code" tick={{ ...AXE, fontWeight: 600 }} width={34} tickLine={false} axisLine={false} />
                  <Tooltip {...INFOBULLE} formatter={(v: number, _n, p) => [dt(v), p.payload.libelle]} />
                  <Bar dataKey="montant" radius={[0, 6, 6, 0]}>
                    {data.montant_par_indice.filter((x) => x.montant > 0).map((d) => (
                      <Cell key={d.code} fill={d.niveau === "A" ? C.rouge : d.niveau === "B" ? C.orange : C.gris} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader><div><CardTitle>Alertes par gouvernorat</CardTitle><CardDescription>Dix gouvernorats les plus concernés</CardDescription></div></CardHeader>
          <CardContent className="h-[300px] pt-2">
            {!data ? <Skeleton className="h-full" /> : (
              <ResponsiveContainer>
                <BarChart data={data.alertes_par_gouvernorat.slice(0, 10)} layout="vertical" margin={{ left: 8, right: 16 }}>
                  <CartesianGrid horizontal={false} stroke={C.ligne} />
                  <XAxis type="number" tick={AXE} tickLine={false} axisLine={false} allowDecimals={false} />
                  <YAxis type="category" dataKey="gouvernorat" tick={AXE} width={72} tickLine={false} axisLine={false} />
                  <Tooltip {...INFOBULLE} />
                  <Bar dataKey="rouges" name="Contrôle recommandé" stackId="a" fill={C.rouge} />
                  <Bar dataKey="oranges" name="Demande de justification" stackId="a" fill={C.orange} radius={[0, 6, 6, 0]} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>
      </div>

      {data && (
        <div className="flex flex-wrap items-center gap-2 text-xs text-attenue">
          {data.categories.map((c) => <span key={c.code} className="flex items-center gap-2"><BadgeCategorie categorie={c.code} court /> {nombre(c.entreprises)}</span>)}
          <span className="ml-auto">Scores pré-calculés le {data.calcule_le ? new Date(data.calcule_le).toLocaleString("fr-FR") : "—"}</span>
        </div>
      )}
    </div>
  );
}
