"use client";
import * as React from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import useSWR from "swr";
import { toast } from "sonner";
import { ArrowLeft, BadgeCheck, BookMarked, Download, Pencil, Save, Undo2 } from "lucide-react";
import { API_URL, api, fetcher, type ArticleDossier, type Dossier } from "@/lib/api";
import { cn, dt, nombre } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Bulle, EtatErreur, Infobulle, Skeleton } from "@/components/ui/misc";
import { BadgeCategorie, FORCES } from "@/components/risque/elements";
import { useFilAriane } from "@/components/shell/shell";
import { LogoRadar } from "@/components/shell/logo";

function Titre({ n, children, id }: { n: number; children: React.ReactNode; id?: string }) {
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

function Citation({ a }: { a: ArticleDossier }) {
  return (
    <Bulle declencheur={
      <button className="inline-flex items-center gap-1.5 rounded-lg border border-action/30 bg-action/5 px-2 py-1 text-xs font-medium text-action hover:bg-action/10">
        <BookMarked className="h-3.5 w-3.5" /> {a.article}
      </button>}>
      <p className="text-xs font-semibold text-marine dark:text-encre">{a.article} — {a.document}</p>
      {a.edition && <p className="text-[11px] text-orange">{a.edition}</p>}
      <p className="mt-1 text-[11px] text-attenue">{a.motif}</p>
      <div className="defilement mt-3 max-h-64 overflow-y-auto whitespace-pre-wrap rounded-xl bg-survol p-3 text-xs leading-relaxed">{a.extrait}</div>
      <p className="mt-2 text-[11px] text-attenue">{a.locator}</p>
    </Bulle>
  );
}

export default function PageDossier() {
  const { id } = useParams<{ id: string }>();
  const { data, error, mutate } = useSWR<Dossier>(`/api/dossiers/${id}`, fetcher);
  const [brouillon, setBrouillon] = React.useState<Dossier["contenu"] | null>(null);
  const [agent, setAgent] = React.useState("agent.demo");
  const [modifie, setModifie] = React.useState(false);
  const [envoi, setEnvoi] = React.useState(false);
  React.useEffect(() => {
    if (data) {
      setBrouillon(structuredClone(data.contenu));
      setAgent(data.contenu.entete.agent || "agent.demo");
      setModifie(false);
    }
  }, [data]);
  React.useEffect(() => {
    if (data && typeof window !== "undefined" && window.location.hash) {
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
  const maj = (f: (c: Dossier["contenu"]) => void) => {
    const c = structuredClone(brouillon);
    f(c);
    setBrouillon(c);
    setModifie(true);
  };
  const enregistrer = async (statut?: "valide" | "brouillon") => {
    setEnvoi(true);
    try {
      await api(`/api/dossiers/${id}`, { method: "PUT", body: JSON.stringify({
        synthese: brouillon.synthese, documents: brouillon.documents, lettre: { objet: brouillon.lettre.objet, corps: brouillon.lettre.corps },
        agent, ...(statut ? { statut } : {}),
      }) });
      await mutate();
      toast.success(statut === "valide" ? "Dossier validé" : statut === "brouillon" ? "Dossier repassé en brouillon" : "Modifications enregistrées",
        { description: statut === "valide" ? "La validation est tracée dans le journal d'audit." : undefined });
    } catch (err) {
      toast.error("Échec de l'enregistrement", { description: (err as Error).message });
    } finally {
      setEnvoi(false);
    }
  };
  const gen = brouillon.generation;

  return (
    <div>
      {/* ------------------------------------------------ barre d'outils */}
      <div className="sticky top-[84px] z-10 mx-auto mb-5 flex max-w-[210mm] flex-wrap items-center gap-2 rounded-2xl border border-ligne bg-carte/95 p-3 shadow-carte backdrop-blur">
        <Button variant="fantome" taille="sm" asChild><Link href={`/entreprise/${e.entreprise_id}`}><ArrowLeft /> Fiche</Link></Button>
        <span className={cn("rounded-full px-2.5 py-1 text-xs font-semibold", valide ? "bg-vert/10 text-vert" : "bg-orange/15 text-amber-700 dark:text-orange")}>
          {valide ? "Validé" : "Brouillon"}
        </span>
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

      {/* ------------------------------------------------ feuille A4 */}
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

        <h1 className="mt-5 text-xl font-semibold text-[#0B2545]">Pré-dossier de contrôle fiscal</h1>
        <p className="text-[12px] text-slate-500">Exercice {e.periode} · généré automatiquement, à valider par l&apos;agent</p>

        <div className="mt-4 grid grid-cols-2 gap-x-6 gap-y-1.5 rounded-lg border border-slate-200 bg-slate-50 p-3 text-[12px]">
          <p><span className="text-slate-500">Entreprise :</span> <b>{e.raison_sociale}</b> ({e.forme_juridique})</p>
          <p><span className="text-slate-500">Matricule :</span> <span className="chiffres">{e.matricule_fiscal}</span> <span className="rounded bg-amber-100 px-1 text-[10px] text-amber-800">fictif</span></p>
          <p><span className="text-slate-500">Adresse :</span> {e.adresse}</p>
          <p><span className="text-slate-500">Secteur :</span> {e.secteur}</p>
          <p className="flex items-center gap-2"><span className="text-slate-500">Score :</span> <b className="chiffres">{Math.round(e.score)}/100</b> <BadgeCategorie categorie={e.categorie} court /></p>
          <p><span className="text-slate-500">Montant estimé en jeu :</span> <b className="chiffres">{dt(brouillon.ecarts.total_estime)}</b></p>
          <p><span className="text-slate-500">Agent :</span> {agent}</p>
          <p><span className="text-slate-500">Rédaction :</span> {gen.modele ? `modèle local ${gen.modele} (${nombre(gen.duree_s, 1)} s)` : "modèle déterministe de secours"}</p>
        </div>

        <Titre n={1}>Synthèse</Titre>
        <ul className="list-disc space-y-1 pl-5">
          {brouillon.synthese.map((l, i) => (
            <li key={i}><Editable valeur={l} actif={!valide} onChange={(v) => maj((c) => { c.synthese[i] = v; })} /></li>
          ))}
        </ul>
        {!valide && <p className="mt-1 flex items-center gap-1 text-[10px] text-slate-400"><Pencil className="h-3 w-3" /> Les textes sont modifiables : cliquer pour éditer.</p>}

        <Titre n={2}>Tableau des écarts</Titre>
        <table className="w-full border-collapse text-[12px]">
          <thead><tr className="bg-slate-100 text-left"><th className="border border-slate-200 px-2 py-1.5">Poste</th><th className="border border-slate-200 px-2 py-1.5 text-right">Montant</th><th className="border border-slate-200 px-2 py-1.5">Formule et hypothèse</th></tr></thead>
          <tbody>
            {brouillon.ecarts.lignes.map((l) => (
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
        <ul className="mt-2 space-y-0.5 text-[10.5px] text-slate-500">{brouillon.ecarts.hypotheses.map((h, i) => <li key={i}>* {h}</li>)}</ul>
        <p className="mt-2 text-[12px] font-semibold text-[#0B2545]">{brouillon.ecarts.mention}</p>

        <Titre n={3}>Faisceau d&apos;indices</Titre>
        <div className="space-y-2">
          {brouillon.indices.map((i) => (
            <div key={i.code} className="flex items-start gap-3 rounded-lg border border-slate-200 p-2.5">
              <span className={cn("chiffres mt-0.5 rounded border px-1.5 py-0.5 text-[11px] font-bold", FORCES[i.niveau]?.classe)}>{i.code}</span>
              <div className="flex-1"><p className="font-medium text-[#0B2545]">{i.libelle}</p><p className="text-[12px] text-slate-600">{i.phrase}</p></div>
              {i.montant_en_jeu > 0 && <span className="chiffres whitespace-nowrap text-[12px] font-semibold">{dt(i.montant_en_jeu)}</span>}
            </div>
          ))}
          <p className="text-[10.5px] text-slate-500">Les preuves (déclarations en douane, certificats TEJ, factures) sont consultables dans la fiche 360.</p>
        </div>

        <Titre n={4}>Articles applicables</Titre>
        <p className="mb-2 text-[11px] text-slate-500">Chaque article correspond à un texte réellement retrouvé dans la base ; cliquer pour lire l&apos;extrait exact.</p>
        <div className="space-y-2">
          {brouillon.articles.map((a) => (
            <div key={a.id} className="flex items-start gap-3">
              <Citation a={a} />
              <p className="pt-1 text-[12px] text-slate-600">{a.motif} <span className="text-slate-400">— {a.document.split(",")[0]}{a.edition ? ` (${a.edition})` : ""}</span></p>
            </div>
          ))}
        </div>

        <Titre n={5}>Documents à demander</Titre>
        <ul className="space-y-1">
          {brouillon.documents.map((d, i) => (
            <li key={i} className="flex items-start gap-2"><span className="mt-0.5 text-slate-400">☐</span>
              <Editable valeur={d} actif={!valide} onChange={(v) => maj((c) => { c.documents[i] = v; })} className="flex-1" /></li>
          ))}
        </ul>

        <Titre n={6} id="lettre">Projet de lettre de demande de justification</Titre>
        <div className="rounded-lg border border-slate-200 p-4">
          <p className="text-[11px] text-slate-500">Destinataire : {brouillon.lettre.destinataire}</p>
          <div className="mt-1 flex gap-1 font-semibold text-[#0B2545]">Objet :
            <Editable valeur={brouillon.lettre.objet} actif={!valide} onChange={(v) => maj((c) => { c.lettre.objet = v; })} className="flex-1" />
          </div>
          <Editable valeur={brouillon.lettre.corps} actif={!valide} multiligne onChange={(v) => maj((c) => { c.lettre.corps = v; })} className="mt-3 text-[12.5px]" />
          <p className="mt-4 text-[12px]">L&apos;agent : {agent}</p>
        </div>

        <Titre n={7}>Avertissements</Titre>
        <ul className="list-disc space-y-0.5 pl-5 text-[11.5px] text-slate-600">{brouillon.avertissements.map((a, i) => <li key={i}>{a}</li>)}</ul>
        {gen.erreur && <p className="mt-2 text-[10.5px] text-slate-400">Note technique : {gen.erreur}</p>}
      </article>
    </div>
  );
}
