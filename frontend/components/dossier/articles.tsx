"use client";
import * as React from "react";
import useSWR from "swr";
import { toast } from "sonner";
import { BookMarked, ChevronRight, History, Plus, RotateCcw, Search, Trash2 } from "lucide-react";
import { api, fetcher, type ArticleCandidat, type ArticleDossier, type Dossier, type EntreeHistorique, type Partie } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Bulle, EtatVide, Skeleton } from "@/components/ui/misc";
import { Dialogue, Tiroir } from "@/components/ui/sheet";

export const MOTIF_MIN = 10;
export const cleHistorique = (id: number | string) => `/api/dossiers/${id}/historique`;

export function dateHeure(iso: string | undefined | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("fr-FR", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

/** Zone de saisie du motif (obligatoire, 10 caractères au moins). */
function ChampMotif({ valeur, onChange, placeholder }: { valeur: string; onChange: (v: string) => void; placeholder: string }) {
  const n = valeur.trim().length;
  return (
    <div>
      <label className="text-xs font-medium text-encre">Motif (obligatoire)</label>
      <textarea value={valeur} onChange={(e) => onChange(e.target.value)} rows={3} placeholder={placeholder}
        className="mt-1 w-full resize-none rounded-xl border border-ligne bg-carte p-2.5 text-sm text-encre outline-none focus:ring-2 focus:ring-action/30" />
      <p className={cn("mt-0.5 text-[11px]", n >= MOTIF_MIN ? "text-vert" : "text-attenue")}>
        {n >= MOTIF_MIN ? "Motif suffisant" : `Encore ${MOTIF_MIN - n} caractère${MOTIF_MIN - n > 1 ? "s" : ""} au minimum`}
      </p>
    </div>
  );
}

function Citation({ a }: { a: ArticleDossier }) {
  return (
    <Bulle declencheur={
      <button className="inline-flex items-center gap-1.5 whitespace-nowrap rounded-lg border border-action/30 bg-action/5 px-2 py-1 text-xs font-medium text-action hover:bg-action/10">
        <BookMarked className="h-3.5 w-3.5" /> {a.article}
      </button>}>
      <p className="text-xs font-semibold text-marine dark:text-encre">{a.article} — {a.document}</p>
      {a.edition && <p className="text-[11px] text-orange">{a.edition}</p>}
      <p className="mt-1 text-[11px] text-attenue">{a.origine === "agent" ? `Motif de l'agent : ${a.motif}` : a.motif}</p>
      <div className="defilement mt-3 max-h-64 overflow-y-auto whitespace-pre-wrap rounded-xl bg-survol p-3 text-xs leading-relaxed">{a.extrait}</div>
      <p className="mt-2 text-[11px] text-attenue">{a.locator}</p>
    </Bulle>
  );
}

function Etiquettes({ a }: { a: ArticleDossier }) {
  return (
    <span className="inline-flex flex-wrap items-center gap-1">
      {a.origine === "agent"
        ? <span className="rounded bg-violet-100 px-1.5 py-0.5 text-[10px] font-medium text-violet-800">Ajouté par l&apos;agent</span>
        : <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium text-slate-600">Proposé par le système</span>}
      {a.suggestion && <span className="rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-medium text-amber-800">Suggestion automatique, à vérifier</span>}
      {a.indices?.length > 0 && <span className="text-[10px] text-slate-400">Justifié par : {a.indices.join(", ")}</span>}
    </span>
  );
}

type Action = { type: "retrait" | "retablissement"; article: ArticleDossier } | null;

/** Articles applicables d'UNE administration (DGI ou Douane), modifiables par l'agent tant que le dossier n'est pas validé. */
export function SectionArticles({ dossier, partie, valide, agent, onMaj }: {
  dossier: Dossier; partie: Partie; valide: boolean; agent: string; onMaj: (d: Dossier) => void;
}) {
  const c = dossier.contenu;
  const articles = c.articles.filter((a) => (a.partie ?? "dgi") === partie);
  const ecartes = c.articles_ecartes.filter((a) => (a.partie ?? "dgi") === partie);
  const [action, setAction] = React.useState<Action>(null);
  const [motif, setMotif] = React.useState("");
  const [envoi, setEnvoi] = React.useState(false);
  const [ajout, setAjout] = React.useState(false);

  const executer = async () => {
    if (!action) return;
    setEnvoi(true);
    try {
      const d = await api<Dossier>(`/api/dossiers/${dossier.id}/articles/${action.type}`, {
        method: "POST", body: JSON.stringify({ record_id: action.article.id, motif, agent }),
      });
      onMaj(d);
      toast.success(action.type === "retrait" ? `${action.article.article} écarté` : `${action.article.article} rétabli`,
        { description: "Action inscrite dans l'historique du dossier." });
      setAction(null);
      setMotif("");
    } catch (err) {
      toast.error("Action refusée", { description: (err as Error).message });
    } finally {
      setEnvoi(false);
    }
  };

  return (
    <>
      {c.articles_modifies && (
        <p className="mb-2 rounded bg-violet-50 px-2 py-1 text-[11px] font-medium text-violet-800">Liste des articles modifiée par l&apos;agent (voir historique).</p>
      )}
      <p className="mb-2 text-[11px] text-slate-500">Chaque article correspond à un texte réellement retrouvé dans la base ; cliquer pour lire l&apos;extrait exact.</p>
      <div className="space-y-2">
        {articles.length === 0 && <p className="text-[12px] italic text-slate-500">Aucun article retenu.</p>}
        {articles.map((a) => (
          <div key={a.id} className="group flex items-start gap-3">
            <Citation a={a} />
            <div className="flex-1 pt-0.5">
              <p className="text-[12px] text-slate-600">
                {a.origine === "agent" ? <><span className="text-slate-400">Motif de l&apos;agent : </span>{a.motif}</> : a.motif}{" "}
                <span className="text-slate-400">— {a.document.split(",")[0]}{a.edition ? ` (${a.edition})` : ""}</span>
              </p>
              <Etiquettes a={a} />
            </div>
            {!valide && (
              <button onClick={() => { setAction({ type: "retrait", article: a }); setMotif(""); }}
                className="mt-0.5 inline-flex items-center gap-1 rounded-lg px-2 py-1 text-[11px] font-medium text-slate-400 hover:bg-rouge/5 hover:text-rouge">
                <Trash2 className="h-3.5 w-3.5" /> Retirer
              </button>
            )}
          </div>
        ))}
      </div>
      {!valide && (
        <button onClick={() => setAjout(true)}
          className="mt-3 inline-flex items-center gap-1.5 rounded-lg border border-dashed border-action/40 px-3 py-1.5 text-xs font-medium text-action hover:bg-action/5">
          <Plus className="h-3.5 w-3.5" /> Ajouter un article
        </button>
      )}

      {ecartes.length > 0 && (
        <details className="group mt-4 rounded-lg border border-slate-200 bg-slate-50/60">
          <summary className="flex cursor-pointer list-none items-center gap-1.5 px-3 py-2 text-[12px] font-medium text-slate-600">
            <ChevronRight className="h-3.5 w-3.5 transition-transform group-open:rotate-90" />
            Articles écartés par l&apos;agent ({ecartes.length})
          </summary>
          <div className="space-y-2 border-t border-slate-200 px-3 py-2.5">
            {ecartes.map((a) => (
              <div key={a.id} className="flex items-start gap-3">
                <div className="flex-1">
                  <p className="text-[12px] text-slate-500"><span className="font-semibold line-through">{a.article}</span>{" "}
                    <span className="line-through">{a.motif} — {a.document.split(",")[0]}</span></p>
                  <p className="text-[11px] text-slate-600">Motif du retrait : « {a.retrait?.motif} » — {a.retrait?.agent}, le {dateHeure(a.retrait?.le)}</p>
                </div>
                {!valide && (
                  <button onClick={() => { setAction({ type: "retablissement", article: a }); setMotif(""); }}
                    className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-[11px] font-medium text-action hover:bg-action/5">
                    <RotateCcw className="h-3.5 w-3.5" /> Rétablir
                  </button>
                )}
              </div>
            ))}
          </div>
        </details>
      )}

      <Dialogue ouvert={action !== null} onChange={(v) => !v && setAction(null)}
        titre={action?.type === "retrait" ? `Retirer ${action?.article.article}` : `Rétablir ${action?.article.article}`}>
        <p className="mb-3 text-xs text-attenue">
          {action?.type === "retrait"
            ? "L'article ne sera pas effacé : il passera dans « Articles écartés par l'agent », avec votre motif, votre nom et la date."
            : "L'article reviendra dans la liste des articles applicables."} L&apos;action est inscrite dans l&apos;historique du dossier.
        </p>
        <ChampMotif valeur={motif} onChange={setMotif}
          placeholder={action?.type === "retrait" ? "Ex. : texte hors sujet pour ce dossier, …" : "Ex. : article finalement pertinent, …"} />
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="secondaire" taille="sm" onClick={() => setAction(null)}>Annuler</Button>
          <Button variant={action?.type === "retrait" ? "danger" : "primaire"} taille="sm" disabled={envoi || motif.trim().length < MOTIF_MIN} onClick={executer}>
            {action?.type === "retrait" ? <><Trash2 /> Retirer l&apos;article</> : <><RotateCcw /> Rétablir</>}
          </Button>
        </div>
      </Dialogue>

      <AjoutArticle ouvert={ajout} onChange={setAjout} dossierId={dossier.id} partie={partie} agent={agent} onMaj={onMaj} />
    </>
  );
}

/** Tiroir « Ajouter un article » : recherche dans l'index RAG uniquement, extrait visible avant confirmation. */
function AjoutArticle({ ouvert, onChange, dossierId, partie, agent, onMaj }: {
  ouvert: boolean; onChange: (v: boolean) => void; dossierId: number; partie: Partie; agent: string; onMaj: (d: Dossier) => void;
}) {
  const [q, setQ] = React.useState("");
  const [resultats, setResultats] = React.useState<ArticleCandidat[] | null>(null);
  const [choix, setChoix] = React.useState<ArticleCandidat | null>(null);
  const [motif, setMotif] = React.useState("");
  const [charge, setCharge] = React.useState(false);

  React.useEffect(() => {
    if (!ouvert) { setQ(""); setResultats(null); setChoix(null); setMotif(""); }
  }, [ouvert]);

  const chercher = async (ev?: React.FormEvent) => {
    ev?.preventDefault();
    if (q.trim().length < 2) return;
    setCharge(true);
    setChoix(null);
    try {
      setResultats(await api<ArticleCandidat[]>(`/api/dossiers/${dossierId}/articles/recherche?q=${encodeURIComponent(q.trim())}`));
    } catch (err) {
      toast.error("Recherche impossible", { description: (err as Error).message });
    } finally {
      setCharge(false);
    }
  };

  const confirmer = async () => {
    if (!choix) return;
    setCharge(true);
    try {
      const d = await api<Dossier>(`/api/dossiers/${dossierId}/articles`, { method: "POST", body: JSON.stringify({ record_id: choix.id, motif, agent, partie }) });
      onMaj(d);
      toast.success(`${choix.article} ajouté`, { description: "Action inscrite dans l'historique du dossier." });
      onChange(false);
    } catch (err) {
      toast.error("Ajout refusé", { description: (err as Error).message });
    } finally {
      setCharge(false);
    }
  };

  return (
    <Tiroir ouvert={ouvert} onChange={onChange} titre={`Ajouter un article — partie ${partie === "dgi" ? "DGI" : "Douane"}`} largeur="max-w-2xl"
      description="Recherche dans l'index des textes officiels uniquement : aucune saisie libre de numéro d'article.">
      <form onSubmit={chercher} className="flex gap-2">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-attenue" />
          <input value={q} onChange={(e) => setQ(e.target.value)} autoFocus
            placeholder="« article 94 », « article 38 du code des droits et procédures fiscaux » ou mots-clés"
            className="h-10 w-full rounded-xl border border-ligne bg-carte pl-9 pr-3 text-sm text-encre outline-none focus:ring-2 focus:ring-action/30" />
        </div>
        <Button type="submit" taille="md" disabled={charge || q.trim().length < 2}>Rechercher</Button>
      </form>

      {charge && !resultats && <Skeleton className="mt-4 h-40" />}
      {resultats && resultats.length === 0 && <EtatVide className="mt-4" titre="Aucun texte trouvé" texte="Essayez un numéro d'article ou d'autres mots-clés." />}
      {resultats && resultats.length > 0 && !choix && (
        <div className="mt-4 space-y-2">
          {resultats.map((r) => {
            const bloque = r.deja_present || r.ecarte;
            return (
              <button key={r.id} disabled={bloque} onClick={() => { setChoix(r); setMotif(""); }}
                className={cn("w-full rounded-xl border border-ligne p-3 text-left transition-colors", bloque ? "cursor-not-allowed opacity-50" : "hover:border-action/40 hover:bg-action/5")}>
                <div className="flex items-center gap-2">
                  <span className="text-sm font-semibold text-marine dark:text-encre">{r.article}</span>
                  <span className="truncate text-xs text-attenue">{r.document}</span>
                  {r.edition && <span className="rounded bg-orange/15 px-1.5 text-[10px] text-amber-700">{r.edition}</span>}
                  <span className="ml-auto whitespace-nowrap text-[10px] text-attenue">
                    {r.deja_present ? "déjà dans la liste" : r.ecarte ? "écarté : utiliser « Rétablir »" : r.par_numero ? "par numéro" : `pertinence ${r.pertinence?.toFixed(2)}`}
                  </span>
                </div>
                <p className="mt-1 line-clamp-2 text-xs text-attenue">{r.extrait}</p>
              </button>
            );
          })}
        </div>
      )}
      {choix && (
        <div className="mt-4 space-y-3">
          <button onClick={() => setChoix(null)} className="text-xs text-action hover:underline">← Retour aux résultats</button>
          <div className="rounded-xl border border-ligne p-3">
            <p className="text-sm font-semibold text-marine dark:text-encre">{choix.article} — {choix.document}</p>
            {choix.edition && <p className="text-[11px] text-orange">{choix.edition}</p>}
            <p className="mt-2 text-[11px] font-medium text-attenue">Extrait exact de l&apos;index (ce texte sera joint au dossier) :</p>
            <div className="defilement mt-1 max-h-72 overflow-y-auto whitespace-pre-wrap rounded-lg bg-survol p-3 text-xs leading-relaxed">{choix.extrait}</div>
            <p className="mt-1 text-[11px] text-attenue">{choix.locator}</p>
          </div>
          <ChampMotif valeur={motif} onChange={setMotif} placeholder="Pourquoi cet article s'applique à ce dossier…" />
          <div className="flex justify-end gap-2">
            <Button variant="secondaire" taille="sm" onClick={() => onChange(false)}>Annuler</Button>
            <Button taille="sm" disabled={charge || motif.trim().length < MOTIF_MIN} onClick={confirmer}><Plus /> Confirmer l&apos;ajout</Button>
          </div>
        </div>
      )}
    </Tiroir>
  );
}

const COULEURS_ACTIONS: Record<string, string> = {
  generation: "bg-slate-400", ajout_article: "bg-violet-500", retrait_article: "bg-rouge", retablissement_article: "bg-action",
  regeneration_lettre: "bg-orange", validation: "bg-vert", retour_brouillon: "bg-slate-400",
};

/** Onglet « Historique » : journal du dossier, en ajout seulement. */
export function HistoriqueDossier({ id }: { id: number | string }) {
  const { data, error } = useSWR<EntreeHistorique[]>(cleHistorique(id), fetcher);
  if (error) return <p className="text-sm text-rouge">{(error as Error).message}</p>;
  if (!data) return <Skeleton className="h-60" />;
  return (
    <div className="mx-auto max-w-[210mm] rounded-2xl border border-ligne bg-carte p-6 shadow-carte">
      <div className="mb-1 flex items-center gap-2 text-marine dark:text-encre"><History className="h-4 w-4" /><h2 className="text-base font-semibold">Historique du dossier</h2></div>
      <p className="mb-5 text-xs text-attenue">Journal en ajout seulement : aucune entrée ne peut être modifiée ni supprimée.</p>
      {data.length === 0 ? <EtatVide titre="Aucune action enregistrée" /> : (
        <ol className="relative space-y-4 border-l border-ligne pl-5">
          {data.map((l) => (
            <li key={l.id} className="relative">
              <span className={cn("absolute -left-[26px] top-1 h-3 w-3 rounded-full ring-4 ring-carte", COULEURS_ACTIONS[l.action] ?? "bg-slate-400")} />
              <div className="flex flex-wrap items-baseline gap-x-2">
                <p className="text-sm font-medium text-encre">{l.libelle}{l.article ? ` : ${l.article}` : ""}</p>
                <p className="text-xs text-attenue">{dateHeure(l.horodatage)} · {l.agent}</p>
              </div>
              {l.motif && <p className="mt-0.5 text-xs text-attenue">{l.record_id ? `Motif : « ${l.motif} »` : l.motif}</p>}
              {l.record_id && <p className="mt-0.5 font-mono text-[10px] text-slate-400">{l.record_id}</p>}
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
