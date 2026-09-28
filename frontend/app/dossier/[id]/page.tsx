"use client";
import * as React from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import useSWR, { useSWRConfig } from "swr";
import { toast } from "sonner";
import { AlertTriangle, ArrowLeft, ArrowRightLeft, BadgeCheck, Download, Pencil, RefreshCw, Save, Undo2 } from "lucide-react";
import { API_URL, api, fetcher, type Dossier, type FicheTransmission, type Partie } from "@/lib/api";
import { cn, dt, nombre } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { EtatErreur, Infobulle, Skeleton, Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/misc";
import { Dialogue } from "@/components/ui/sheet";
import { HistoriqueDossier, SectionArticles, cleHistorique } from "@/components/dossier/articles";
import { BadgeCategorie, BadgeTypeDossier, FORCES } from "@/components/risque/elements";
import { useFilAriane } from "@/components/shell/shell";
import { LogoRadar } from "@/components/shell/logo";

const NOMS_PARTIES: Record<Partie, string> = { dgi: "DGI — Direction générale des impôts", douane: "Douane — Direction générale des douanes" };
const COURTS: Record<Partie, string> = { dgi: "DGI", douane: "Douane" };
const SENS: Record<FicheTransmission["sens"], string> = { douane_vers_dgi: "Douane → DGI", dgi_vers_douane: "DGI → Douane" };

function Titre({ n, children, id }: { n: number | string; children: React.ReactNode; id?: string }) {
  return <h2 id={id} className="mb-3 mt-8 scroll-mt-28 border-b border-ligne pb-1.5 text-[15px] font-semibold text-marine dark:text-encre">{n}. {children}</h2>;
}

/** Texte modifiable en place (désactivé une fois le dossier validé). */
function Editable({ valeur, onChange, actif, className, multiligne = false }: {
  valeur: string; onChange: (v: string) => void; actif: boolean; className?: string; multiligne?: boolean;
}) {
  return (
    <div contentEditable={actif} suppressContentEditableWarning
      onBlur={(e) => onChange(multiligne ? e.currentTarget.innerText : e.currentTarget.textContent || "")}
      className={cn("editable", actif && "cursor-text rounded-md hover:bg-action/5", multiligne && "whitespace-pre-wrap", className)}>
      {valeur}
    </div>
  );
}

function FicheDeTransmission({ t }: { t: FicheTransmission }) {
  return (
    <div className="mt-4 rounded-lg border-2 border-dashed border-violet-300 p-4">
      <p className="flex items-center gap-2 text-[14px] font-semibold text-[#0B2545]"><ArrowRightLeft className="h-4 w-4 text-violet-600" /> Fiche de transmission — {SENS[t.sens]}</p>
      <p className="text-[11px] font-medium text-violet-800">{t.mention}</p>
      <div className="mt-3 grid grid-cols-2 gap-x-6 gap-y-1 text-[12px]">
        <p><span className="text-slate-500">Émetteur :</span> {t.emetteur}</p>
        <p><span className="text-slate-500">Destinataire :</span> {t.destinataire}</p>
        <p><span className="text-slate-500">Entreprise :</span> {t.entreprise.raison_sociale} <span className="chiffres text-slate-500">({t.entreprise.matricule_fiscal})</span></p>
        <p><span className="text-slate-500">Date :</span> {t.date} · <span className="text-slate-500">Agent :</span> {t.agent}</p>
      </div>
      <p className="mt-3 text-[12px] font-semibold text-[#0B2545]">Indices concernés</p>
      <ul className="text-[12px]">{t.indices.map((i) => <li key={i.code}>• <b>{i.code}</b> — {i.libelle}</li>)}</ul>
      <p className="mt-2 text-[12px] font-semibold text-[#0B2545]">Pièces transmises</p>
      <ul className="text-[12px]">{t.pieces.map((p) => <li key={p}>☐ {p}</li>)}</ul>
      <p className="mt-2 text-[12px] font-semibold text-[#0B2545]">Base légale : {t.base_legale.article} du code des droits et procédures fiscaux</p>
      <div className="defilement mt-1 max-h-48 overflow-y-auto whitespace-pre-wrap rounded bg-slate-50 p-2.5 text-[11px] leading-relaxed text-slate-700">{t.base_legale.extrait}</div>
      <p className="mt-1 text-[10px] text-slate-400">Extrait exact de la base ({t.base_legale.record_id})</p>
    </div>
  );
}

export default function PageDossier() {
  const { id } = useParams<{ id: string }>();
  const { data, error, mutate } = useSWR<Dossier>(`/api/dossiers/${id}`, fetcher);
  const [brouillon, setBrouillon] = React.useState<Dossier["contenu"] | null>(null);
  const [agent, setAgent] = React.useState("agent.demo");
  const [modifie, setModifie] = React.useState(false);
  const [envoi, setEnvoi] = React.useState(false);
  const [confirmLettre, setConfirmLettre] = React.useState(false);
  const [onglet, setOnglet] = React.useState("dossier");
  React.useEffect(() => { if (window.location.hash === "#historique") setOnglet("historique"); }, []);
  const { mutate: rafraichir } = useSWRConfig();
  // après une action sur les articles ou les lettres, on fusionne sans perdre les textes modifiés et non enregistrés
  const fusion = React.useRef<null | "articles" | "lettres">(null);
  React.useEffect(() => {
    if (!data) return;
    const mode = fusion.current;
    fusion.current = null;
    setBrouillon((prec) => {
      if (!mode || !prec) return structuredClone(data.contenu);
      const n = structuredClone(prec);
      n.articles = data.contenu.articles;
      n.articles_ecartes = data.contenu.articles_ecartes;
      n.articles_modifies = data.contenu.articles_modifies;
      for (const p of Object.keys(data.contenu.lettres) as Partie[]) {
        const serveur = data.contenu.lettres[p]!;
        n.lettres[p] = mode === "lettres" ? structuredClone(serveur) : { ...n.lettres[p]!, articles_ids: serveur.articles_ids };
      }
      return n;
    });
    if (!mode) {
      setAgent(data.contenu.entete.agent || "agent.demo");
      setModifie(false);
    }
  }, [data]);
  React.useEffect(() => {
    if (data && typeof window !== "undefined" && window.location.hash && window.location.hash !== "#historique") {
      setTimeout(() => document.getElementById(window.location.hash.slice(1))?.scrollIntoView({ behavior: "smooth" }), 250);
    }
  }, [data]);
  useFilAriane([{ libelle: "Ciblage", href: "/ciblage" },
    { libelle: data?.contenu.entete.raison_sociale ?? "Entreprise", href: data ? `/entreprise/${data.contenu.entete.entreprise_id}` : undefined },
    { libelle: "Pré-dossier" }]);

  if (error) return <EtatErreur message={error.message} />;
  if (!data || !brouillon) return <Skeleton className="mx-auto h-[80vh] max-w-4xl" />;
  const valide = data.statut === "valide";
  const e = brouillon.entete;
  const parties = e.parties;
  const conjoint = e.type_dossier === "conjoint";
  const maj = (f: (c: Dossier["contenu"]) => void) => {
    const c = structuredClone(brouillon);
    f(c);
    setBrouillon(c);
    setModifie(true);
  };
  const enregistrer = async (statut?: "valide" | "brouillon") => {
    setEnvoi(true);
    try {
      const lettres = Object.fromEntries(parties.map((p) => [p, { objet: brouillon.lettres[p]!.objet, corps: brouillon.lettres[p]!.corps }]));
      await api(`/api/dossiers/${id}`, { method: "PUT", body: JSON.stringify({
        synthese: brouillon.synthese, documents: brouillon.documents, lettres, agent, ...(statut ? { statut } : {}),
      }) });
      await mutate();
      rafraichir(cleHistorique(id));
      toast.success(statut === "valide" ? "Dossier validé" : statut === "brouillon" ? "Dossier repassé en brouillon" : "Modifications enregistrées",
        { description: statut === "valide" ? "La validation est tracée dans le journal d'audit." : undefined });
    } catch (err) {
      toast.error("Échec de l'enregistrement", { description: (err as Error).message });
    } finally {
      setEnvoi(false);
    }
  };
  const gen = brouillon.generation;
  const appliquer = (d: Dossier, mode: "articles" | "lettres" = "articles") => {
    fusion.current = mode;
    mutate(d, { revalidate: false });
    rafraichir(cleHistorique(id));
  };
  const regenererLettres = async () => {
    setEnvoi(true);
    try {
      const d = await api<Dossier>(`/api/dossiers/${id}/lettre/regeneration`, { method: "POST", body: JSON.stringify({ agent }) });
      appliquer(d, "lettres");
      const sources = Object.values(d.contenu.lettres).map((l) => l?.source).filter(Boolean);
      toast.success(parties.length > 1 ? "Lettres régénérées avec la liste finale des articles" : "Lettre régénérée avec la liste finale des articles",
        { description: sources.every((s) => s === "modele_de_secours") ? "Rédaction par le modèle déterministe." : `Rédaction : ${sources.join(", ")}` });
      setConfirmLettre(false);
    } catch (err) {
      toast.error("Régénération impossible", { description: (err as Error).message });
    } finally {
      setEnvoi(false);
    }
  };
  const etat = data.etat_articles;
  const transmissions = brouillon.transmissions ?? [];

  /** Sections d'une administration : écarts, indices, articles, pièces, lettre (numérotées à partir de n). */
  const partie = (p: Partie, n: number) => {
    const lignes = brouillon.ecarts.lignes.filter((l) => (l.partie ?? "dgi") === p);
    const indices = brouillon.indices.filter((i) => (i.parties ?? ["dgi"]).includes(p));
    const hypotheses = brouillon.ecarts.hypotheses_par_partie?.[p] ?? (conjoint ? [] : brouillon.ecarts.hypotheses);
    const docs = brouillon.documents[p] ?? [];
    const lettre = brouillon.lettres[p]!;
    const etatP = etat.par_partie?.[p] ?? { lettre_a_regenerer: etat.lettre_a_regenerer, articles_hors_liste: etat.articles_hors_liste_lettre };
    const pre = conjoint ? `${COURTS[p]} — ` : "";
    return (
      <React.Fragment key={p}>
        {conjoint && (
          <div className={cn("mt-10 rounded-lg px-3 py-2 text-[14px] font-semibold", p === "dgi" ? "bg-blue-50 text-[#1D4ED8]" : "bg-teal-50 text-teal-800")}>
            Partie {NOMS_PARTIES[p]}
            <span className="ml-2 text-[11px] font-normal text-slate-500">destinataire : {e.destinataires.find((d) => d.partie === p)?.service}</span>
          </div>
        )}
        <Titre n={n}>{pre}Tableau des écarts</Titre>
        {lignes.length === 0 ? <p className="text-[12px] italic text-slate-500">Aucun montant chiffré pour cette administration.</p> : (
          <table className="w-full border-collapse text-[12px]">
            <thead><tr className="bg-slate-100 text-left"><th className="border border-slate-200 px-2 py-1.5">Poste</th><th className="border border-slate-200 px-2 py-1.5 text-right">Montant</th><th className="border border-slate-200 px-2 py-1.5">Formule et hypothèse</th></tr></thead>
            <tbody>
              {lignes.map((l) => (
                <tr key={l.cle} className={cn(l.total && "bg-blue-50 font-semibold", l.indicatif && "text-slate-500")}>
                  <td className="border border-slate-200 px-2 py-1.5">
                    {l.libelle}
                    {l.a_verifier && <Infobulle contenu={`Paramètre à vérifier : ${l.source}`}><span className="ml-1 cursor-help rounded bg-amber-100 px-1 text-[10px] font-medium text-amber-800">à vérifier</span></Infobulle>}
                  </td>
                  <td className="chiffres whitespace-nowrap border border-slate-200 px-2 py-1.5 text-right">{l.montant_affiche}</td>
                  <td className="border border-slate-200 px-2 py-1.5 text-[11px] text-slate-600">{l.formule}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <ul className="mt-2 space-y-0.5 text-[10.5px] text-slate-500">{hypotheses.map((h, i) => <li key={i}>* {h}</li>)}</ul>
        <p className="mt-2 text-[12px] font-semibold text-[#0B2545]">{brouillon.ecarts.mention}</p>

        <Titre n={n + 1}>{pre}Faisceau d&apos;indices</Titre>
        <div className="space-y-2">
          {indices.map((i) => (
            <div key={i.code} className="flex items-start gap-3 rounded-lg border border-slate-200 p-2.5">
              <span className={cn("chiffres mt-0.5 rounded border px-1.5 py-0.5 text-[11px] font-bold", FORCES[i.niveau]?.classe)}>{i.code}</span>
              <div className="flex-1"><p className="font-medium text-[#0B2545]">{i.libelle}</p><p className="text-[12px] text-slate-600">{i.phrase}</p></div>
              {i.montant_en_jeu > 0 && <span className="chiffres whitespace-nowrap text-[12px] font-semibold">{dt(i.montant_en_jeu)}</span>}
            </div>
          ))}
          <p className="text-[10.5px] text-slate-500">Les preuves (déclarations en douane, certificats TEJ, factures) sont consultables dans la fiche 360.</p>
        </div>

        <Titre n={n + 2}>{pre}Articles applicables</Titre>
        {brouillon.notes_articles?.[p] && <p className="mb-2 rounded bg-slate-50 px-2 py-1 text-[11px] text-slate-600">{brouillon.notes_articles[p]}</p>}
        <SectionArticles dossier={{ ...data, contenu: brouillon }} partie={p} valide={valide} agent={agent} onMaj={(d) => appliquer(d)} />

        <Titre n={n + 3}>{pre}Documents à demander</Titre>
        <ul className="space-y-1">
          {docs.map((d, i) => (
            <li key={i} className="flex items-start gap-2"><span className="mt-0.5 text-slate-400">☐</span>
              <Editable valeur={d} actif={!valide} onChange={(v) => maj((c) => { c.documents[p]![i] = v; })} className="flex-1" /></li>
          ))}
        </ul>

        <Titre n={n + 4} id={p === parties[0] ? "lettre" : `lettre-${p}`}>{pre}Projet de lettre de demande de justification</Titre>
        {!valide && etatP.lettre_a_regenerer && (
          <div className="mb-3 flex flex-wrap items-center gap-3 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-[12px] text-amber-900">
            <RefreshCw className="h-4 w-4 shrink-0" />
            <span className="flex-1">La liste des articles a changé : régénérer la lettre ?</span>
            <Button taille="sm" variant="secondaire" disabled={envoi} onClick={() => setConfirmLettre(true)}><RefreshCw /> Régénérer la lettre</Button>
          </div>
        )}
        {etatP.articles_hors_liste.length > 0 && (
          <div className="mb-3 flex items-start gap-2 rounded-lg border border-rouge/30 bg-rouge/5 px-3 py-2 text-[12px] text-rouge">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            <span>La lettre cite {etatP.articles_hors_liste.length > 1 ? "les articles" : "l’article"} {etatP.articles_hors_liste.join(", ")}, absent{etatP.articles_hors_liste.length > 1 ? "s" : ""} de la liste finale des articles applicables.</span>
          </div>
        )}
        <div className="rounded-lg border border-slate-200 p-4">
          <p className="text-[11px] text-slate-500">Émetteur : {lettre.emetteur ?? NOMS_PARTIES[p]} · Destinataire : {lettre.destinataire}</p>
          <div className="mt-1 flex gap-1 font-semibold text-[#0B2545]">Objet :
            <Editable valeur={lettre.objet} actif={!valide} onChange={(v) => maj((c) => { c.lettres[p]!.objet = v; })} className="flex-1" />
          </div>
          <Editable valeur={lettre.corps} actif={!valide} multiligne onChange={(v) => maj((c) => { c.lettres[p]!.corps = v; })} className="mt-3 text-[12.5px]" />
          <p className="mt-4 text-[12px]">L&apos;agent : {agent}</p>
        </div>
      </React.Fragment>
    );
  };
  let numero = 2;
  const sections = parties.map((p) => { const s = partie(p, numero); numero += 5; return s; });

  return (
    <Tabs value={onglet} onValueChange={setOnglet}>
      {/* ------------------------------------------------ barre d'outils */}
      <div className="sticky top-[84px] z-10 mx-auto mb-5 flex max-w-[210mm] flex-wrap items-center gap-2 rounded-2xl border border-ligne bg-carte/95 p-3 shadow-carte backdrop-blur">
        <Button variant="fantome" taille="sm" asChild><Link href={`/entreprise/${e.entreprise_id}`}><ArrowLeft /> Fiche</Link></Button>
        <span className={cn("rounded-full px-2.5 py-1 text-xs font-semibold", valide ? "bg-vert/10 text-vert" : "bg-orange/15 text-amber-700 dark:text-orange")}>
          {valide ? "Validé" : "Brouillon"}
        </span>
        <BadgeTypeDossier type={e.type_dossier} />
        <TabsList className="ml-1">
          <TabsTrigger value="dossier">Dossier</TabsTrigger>
          <TabsTrigger value="historique">Historique</TabsTrigger>
        </TabsList>
        <label className="ml-2 flex items-center gap-2 text-xs text-attenue">Agent
          <input value={agent} disabled={valide} onChange={(ev) => { setAgent(ev.target.value); setModifie(true); }}
            className="h-8 w-40 rounded-lg border border-ligne bg-carte px-2 text-xs text-encre outline-none focus:ring-2 focus:ring-action/30" />
        </label>
        <div className="ml-auto flex items-center gap-2">
          {!valide && <Button variant="secondaire" taille="sm" disabled={!modifie || envoi} onClick={() => enregistrer()}><Save /> Enregistrer</Button>}
          {!valide ? <Button variant="succes" taille="sm" disabled={envoi} onClick={() => enregistrer("valide")}><BadgeCheck /> Valider le dossier</Button>
            : <Button variant="secondaire" taille="sm" disabled={envoi} onClick={() => enregistrer("brouillon")}><Undo2 /> Repasser en brouillon</Button>}
          <Button taille="sm" asChild><a href={`${API_URL}/api/dossiers/${id}/pdf`}><Download /> Exporter en PDF</a></Button>
        </div>
      </div>

      <TabsContent value="historique"><HistoriqueDossier id={id} /></TabsContent>

      {/* ------------------------------------------------ feuille A4 */}
      <TabsContent value="dossier" forceMount className="data-[state=inactive]:hidden">
      <article className="feuille-a4 relative mx-auto overflow-hidden rounded-sm border border-ligne bg-white px-[16mm] py-[14mm] text-[13px] leading-relaxed text-slate-800 shadow-levee dark:bg-slate-50">
        {!valide && <div aria-hidden className="pointer-events-none absolute left-1/2 top-[40%] -translate-x-1/2 -rotate-[30deg] select-none text-[110px] font-bold tracking-widest text-rouge/[0.06]">BROUILLON</div>}
        <div className="mb-3 rounded bg-amber-100 px-3 py-1 text-center text-[10px] font-semibold uppercase tracking-wide text-amber-900">Prototype — données entièrement fictives — aide à la décision, sans valeur juridique</div>
        <header className="flex items-start justify-between border-b border-slate-200 pb-4">
          <div className="flex items-center gap-2 text-[#1D4ED8]">
            <LogoRadar className="h-9 w-9" />
            <div><p className="text-base font-semibold text-[#0B2545]">RASD 360</p><p className="text-[10px] text-slate-500">Radar fiscal et douanier</p></div>
          </div>
          <div className="text-right text-[11px] text-slate-500">
            <p className="chiffres">Réf. {e.reference}</p><p>{e.date}</p>
            <p>Statut : <span className={valide ? "font-semibold text-green-700" : "font-semibold text-amber-700"}>{valide ? "VALIDÉ" : "BROUILLON"}</span></p>
          </div>
        </header>

        <h1 className="mt-5 text-xl font-semibold text-[#0B2545]">{e.titre}</h1>
        <p className="text-[12px] text-slate-500">Exercice {e.periode} · généré automatiquement, à valider par l&apos;agent</p>

        <div className="mt-4 grid grid-cols-2 gap-x-6 gap-y-1.5 rounded-lg border border-slate-200 bg-slate-50 p-3 text-[12px]">
          <p><span className="text-slate-500">Entreprise :</span> <b>{e.raison_sociale}</b> ({e.forme_juridique})</p>
          <p><span className="text-slate-500">Matricule :</span> <span className="chiffres">{e.matricule_fiscal}</span> <span className="rounded bg-amber-100 px-1 text-[10px] text-amber-800">fictif</span></p>
          <p><span className="text-slate-500">Adresse :</span> {e.adresse}</p>
          <p><span className="text-slate-500">Secteur :</span> {e.secteur}</p>
          <p className="flex items-center gap-2"><span className="text-slate-500">Score :</span> <b className="chiffres">{Math.round(e.score)}/100</b> <BadgeCategorie categorie={e.categorie} court /></p>
          <p className="flex items-center gap-2"><span className="text-slate-500">Type :</span> <BadgeTypeDossier type={e.type_dossier} />
            {e.preuve_douaniere && !conjoint && <span className="text-[11px] text-slate-500">preuve douanière</span>}</p>
          <p className="col-span-2"><span className="text-slate-500">Destinataire{e.destinataires.length > 1 ? "s" : ""} :</span>{" "}
            {e.destinataires.map((d) => `${d.administration} — ${d.service}`).join(" ; ")}</p>
          <p><span className="text-slate-500">Montant estimé en jeu :</span> <b className="chiffres">{dt(brouillon.ecarts.total_estime)}</b>
            {conjoint && <span className="chiffres text-[11px] text-slate-500"> (DGI {dt(brouillon.ecarts.total_dgi ?? 0)} · Douane {dt(brouillon.ecarts.total_douane ?? 0)})</span>}</p>
          <p><span className="text-slate-500">Agent :</span> {agent}</p>
          <p className="col-span-2"><span className="text-slate-500">Rédaction :</span> {gen.modele ? `modèle local ${gen.modele} (${nombre(gen.duree_s, 1)} s)` : "modèle déterministe de secours"}</p>
        </div>

        <Titre n={1}>Synthèse</Titre>
        <ul className="list-disc space-y-1 pl-5">
          {brouillon.synthese.map((l, i) => (
            <li key={i}><Editable valeur={l} actif={!valide} onChange={(v) => maj((c) => { c.synthese[i] = v; })} /></li>
          ))}
        </ul>
        {!valide && <p className="mt-1 flex items-center gap-1 text-[10px] text-slate-400"><Pencil className="h-3 w-3" /> Les textes sont modifiables : cliquer pour éditer.</p>}

        {sections}

        {transmissions.length > 0 && (
          <>
            <Titre n={numero} id="transmission">Fiche{transmissions.length > 1 ? "s" : ""} de transmission</Titre>
            {transmissions.map((t) => <FicheDeTransmission key={t.sens} t={t} />)}
          </>
        )}

        <Titre n={transmissions.length > 0 ? numero + 1 : numero}>Avertissements</Titre>
        <ul className="list-disc space-y-0.5 pl-5 text-[11.5px] text-slate-600">{brouillon.avertissements.map((a, i) => <li key={i}>{a}</li>)}</ul>
        {gen.erreur && <p className="mt-2 text-[10.5px] text-slate-400">Note technique : {gen.erreur}</p>}
      </article>
      </TabsContent>

      <Dialogue ouvert={confirmLettre} onChange={setConfirmLettre} titre={parties.length > 1 ? "Régénérer les lettres" : "Régénérer la lettre"}>
        <p className="text-sm text-attenue">{parties.length > 1 ? "Chaque lettre (DGI et Douane) sera rédigée" : "La lettre sera rédigée"} à nouveau avec la liste finale des articles, puis contrôlée (montants et articles cités).
          Les lettres actuelles, y compris vos retouches, seront remplacées. La synthèse est conservée.</p>
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="secondaire" taille="sm" onClick={() => setConfirmLettre(false)}>Annuler</Button>
          <Button taille="sm" disabled={envoi} onClick={regenererLettres}><RefreshCw className={envoi ? "animate-spin" : undefined} /> {envoi ? "Rédaction en cours…" : "Régénérer"}</Button>
        </div>
      </Dialogue>
    </Tabs>
  );
}
