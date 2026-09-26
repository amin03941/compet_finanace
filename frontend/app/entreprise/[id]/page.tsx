"use client";
import * as React from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import useSWR from "swr";
import { motion } from "framer-motion";
import { Building2, CalendarDays, ClipboardCheck, FilePenLine, FileText, Mail, MapPin, ShieldCheck, Users } from "lucide-react";
import { fetcher, type Fiche } from "@/lib/api";
import { CATEGORIES, cn, dateFr, dt, nombre, pct } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge, EtatErreur, Infobulle, Skeleton } from "@/components/ui/misc";
import { BadgeCategorie, JaugeScore } from "@/components/risque/elements";
import { useFilAriane } from "@/components/shell/shell";
import { GraphiqueSources } from "@/components/fiche/graphique-sources";
import { CartesIndices, Neutralisations } from "@/components/fiche/indices";
import { Cascade } from "@/components/fiche/cascade";
import { GrapheReseau } from "@/components/fiche/reseau";
import { DialogueResultat, DonneesBrutes } from "@/components/fiche/donnees-brutes";

function Section({ titre, description, children, className, id }: { titre: string; description?: string; children: React.ReactNode; className?: string; id?: string }) {
  return (
    <Card className={className} id={id}>
      <CardHeader><div><CardTitle>{titre}</CardTitle>{description && <CardDescription>{description}</CardDescription>}</div></CardHeader>
      <CardContent className="pt-4">{children}</CardContent>
    </Card>
  );
}

export default function FicheEntreprise() {
  const { id } = useParams<{ id: string }>();
  const routeur = useRouter();
  const { data, error, mutate } = useSWR<Fiche>(`/api/entreprises/${id}`, fetcher);
  const [resultat, setResultat] = React.useState(false);
  useFilAriane([{ libelle: "Ciblage", href: "/ciblage" }, { libelle: data?.identite.raison_sociale ?? "Fiche entreprise" }]);

  if (error) return <EtatErreur message={error.message} />;
  if (!data) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-44" />
        <div className="grid grid-cols-3 gap-4"><Skeleton className="col-span-2 h-96" /><Skeleton className="h-96" /></div>
      </div>
    );
  }
  const { identite: e, score: s } = data;
  const cat = s ? CATEGORIES[s.categorie] : null;

  return (
    <div className="space-y-5">
      {/* ------------------------------------------------ en-tête */}
      <Card className="overflow-hidden">
        <div className="h-1.5" style={{ background: cat?.couleur }} />
        <div className="grid grid-cols-[1fr_auto_auto] items-center gap-8 p-6">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-2xl font-semibold tracking-tight text-marine dark:text-encre">{e.raison_sociale}</h1>
              {e.statut_oea && <Badge className="border-vert/30 bg-vert/10 text-vert"><ShieldCheck className="h-3 w-3" /> Opérateur économique agréé</Badge>}
              {e.statut !== "active" && <Badge className="border-rouge/30 bg-rouge/10 text-rouge">{e.statut}</Badge>}
            </div>
            <p className="mt-1 flex flex-wrap items-center gap-x-2 text-sm text-attenue">
              <span className="chiffres">Matricule {e.matricule_fiscal}</span>
              <Infobulle contenu="Matricule généré aléatoirement : aucune entreprise réelle."><span className="cursor-help rounded-md bg-amber-100 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-amber-800 dark:bg-amber-900/50 dark:text-amber-100">fictif</span></Infobulle>
              <span>· {e.forme_juridique}</span>
            </p>
            <div className="mt-4 grid grid-cols-2 gap-x-6 gap-y-2 text-[13px] text-encre/90 xl:grid-cols-3">
              <span className="flex items-center gap-2"><Building2 className="h-4 w-4 text-gris" />{e.secteur}</span>
              <span className="flex items-center gap-2"><MapPin className="h-4 w-4 text-gris" />{e.delegation}, {e.gouvernorat}</span>
              <span className="flex items-center gap-2"><CalendarDays className="h-4 w-4 text-gris" />Créée le {e.date_creation}</span>
              <span className="flex items-center gap-2"><Users className="h-4 w-4 text-gris" />{nombre(e.effectif)} salarié{e.effectif > 1 ? "s" : ""} · capital {dt(e.capital)}</span>
              <span className="col-span-2 truncate text-xs text-attenue" title={e.secteur_nat}>NAT {e.secteur_nat} · {e.statut_export}</span>
            </div>
          </div>
          {s && (
            <div className="flex flex-col items-center">
              <JaugeScore score={s.score} />
              <p className="-mt-1 text-[11px] text-attenue">Probabilité qu&apos;un contrôle soit utile</p>
            </div>
          )}
          {s && (
            <div className="w-[300px] space-y-3">
              <div>
                <BadgeCategorie categorie={s.categorie} className="text-sm" />
                <p className="mt-1.5 text-xs text-attenue">{s.raison_categorie}</p>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div className="rounded-xl bg-survol p-2.5">
                  <p className="text-[10px] uppercase tracking-wide text-attenue">Montant en jeu</p>
                  <p className="chiffres text-base font-semibold">{dt(s.montant_en_jeu)}</p>
                </div>
                <div className="rounded-xl bg-survol p-2.5">
                  <p className="text-[10px] uppercase tracking-wide text-attenue">Priorité</p>
                  <p className="chiffres text-base font-semibold">{nombre(s.rang)}<span className="text-xs font-normal text-attenue"> / {nombre(s.total)}</span></p>
                </div>
              </div>
              <div className="flex flex-col gap-2">
                <Button variant="marine" onClick={() => routeur.push(`/dossier/nouveau?entreprise=${e.id}`)} disabled={s.categorie === "vert" && s.montant_en_jeu === 0 && false}>
                  <FileText /> Préparer le dossier
                </Button>
                <div className="grid grid-cols-2 gap-2">
                  <Button variant="secondaire" taille="sm" onClick={() => routeur.push(`/dossier/nouveau?entreprise=${e.id}&section=lettre`)}><Mail /> Demande de justification</Button>
                  <Button variant="secondaire" taille="sm" onClick={() => setResultat(true)}><ClipboardCheck /> Résultat du contrôle</Button>
                </div>
              </div>
            </div>
          )}
        </div>
        <div className="border-t border-ligne bg-survol/50 px-6 py-2 text-[11px] text-attenue">
          Un écart ne prouve pas une fraude : le score mesure la probabilité qu&apos;un contrôle soit fructueux, à partir d&apos;un faisceau d&apos;indices.
          L&apos;entreprise peut s&apos;expliquer (procédure contradictoire). Aucune sanction automatique.
        </div>
      </Card>

      {/* ------------------------------------------------ graphique + neutralisations */}
      <div className="grid grid-cols-3 gap-5">
        <Section className="col-span-2" titre="Quatre sources indépendantes, une seule entreprise"
          description="Importations (douane), chiffre d'affaires déclaré (impôts), paiements attestés par les clients (TEJ), factures émises (El Fatoora)">
          <GraphiqueSources series={data.series} />
        </Section>
        <Section titre="Explications légitimes vérifiées" description="Neutralisées avant tout calcul, pour éliminer les faux positifs">
          <Neutralisations items={data.neutralisations} />
        </Section>
      </div>

      {/* ------------------------------------------------ indices */}
      <Section titre="Faisceau d'indices" description="A : contradiction avec des données de tiers · B : anomalie économique forte · C : signal de contexte (jamais suffisant seul)">
        <CartesIndices entrepriseId={e.id} indices={data.indices} />
      </Section>

      {/* ------------------------------------------------ SHAP + réseau */}
      <div className="grid grid-cols-2 gap-5">
        <Section titre="Pourquoi ce score ?" description={s ? `Probabilité calibrée ${pct(s.probabilite)} · force des indices ${pct(s.force_indices)} · atypicité ${pct(s.anomalie)}` : ""}>
          {data.cascade?.length ? <Cascade etapes={data.cascade} /> : <p className="text-sm text-attenue">Score non disponible.</p>}
        </Section>
        <Section titre="Réseau" description="Dirigeants, adresses et sociétés liées ; cliquer sur une société pour ouvrir sa fiche">
          <GrapheReseau nodes={data.reseau.nodes} edges={data.reseau.edges} />
        </Section>
      </div>

      {/* ------------------------------------------------ données brutes + historique */}
      <div className="grid grid-cols-3 gap-5">
        <Section className="col-span-2" titre="Données brutes" description="Les sources, côte à côte (dernières lignes)">
          <DonneesBrutes donnees={data.donnees_brutes} />
        </Section>
        <Section titre="Historique des contrôles">
          {data.historique_controles.length === 0 && data.resultats_saisis.length === 0 ? (
            <p className="text-sm text-attenue">Aucun contrôle passé enregistré pour cette entreprise.</p>
          ) : (
            <ul className="space-y-2.5">
              {data.historique_controles.map((h, i) => (
                <li key={i} className="rounded-xl border border-ligne p-3 text-xs">
                  <p className="font-medium text-encre">Exercice {h.annee_controlee} · {h.type}</p>
                  <p className="text-attenue">{dateFr(h.date_controle)} · sélection : {h.origine_selection}</p>
                  <p className={cn("mt-1 font-medium", h.redressement ? "text-rouge" : "text-vert")}>
                    {h.redressement ? `Redressement de ${dt(h.montant_redresse)}` : "Sans redressement"}
                  </p>
                </li>
              ))}
              {data.resultats_saisis.map((r, i) => (
                <li key={`r${i}`} className="rounded-xl border border-action/30 bg-action/5 p-3 text-xs">
                  <p className="font-medium text-encre">Résultat saisi par {r.agent}</p>
                  <p className="text-attenue">{dateFr(r.saisi_le)} · {r.redressement ? `redressement ${dt(r.montant)}` : "sans redressement"}</p>
                  {r.commentaire && <p className="mt-1 text-attenue">{r.commentaire}</p>}
                </li>
              ))}
            </ul>
          )}
          <Link href={`/dossier/nouveau?entreprise=${e.id}`} className="mt-4 flex items-center gap-2 text-xs font-medium text-action hover:underline">
            <FilePenLine className="h-3.5 w-3.5" /> Préparer un pré-dossier de contrôle
          </Link>
        </Section>
      </div>

      <DialogueResultat ouvert={resultat} onChange={setResultat} entrepriseId={e.id} onEnregistre={() => mutate()} />
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="pb-4 text-center text-[11px] text-attenue">
        Données entièrement fictives et synthétiques · aucune donnée réelle d&apos;entreprise ou de personne
      </motion.div>
    </div>
  );
}
