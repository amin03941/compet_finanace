"use client";
import * as React from "react";
import useSWR from "swr";
import { toast } from "sonner";
import { AnimatePresence, motion } from "framer-motion";
import { AlertTriangle, BookOpen, Copy, Languages, Loader2, SendHorizonal, ShieldAlert, Sparkles, Square, UserRound } from "lucide-react";
import { fetcher, fluxNdjson, type SourceRag } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Infobulle, Skeleton } from "@/components/ui/misc";
import { EnTetePage } from "@/components/risque/elements";
import { useFilAriane } from "@/components/shell/shell";
import { LogoRadar } from "@/components/shell/logo";

type Mode = "contribuable" | "agent";
type Langue = "fr" | "ar" | "tn";
interface Message {
  role: "user" | "assistant";
  contenu: string;
  langue: Langue;
  sources?: SourceRag[];
  reformulation?: string | null;
  avertissement?: string | null;
  abstention?: boolean;
  suggestions?: string[];
  chiffres_non_verifies?: string[];
  erreur?: string;
  enCours?: boolean;
  duree?: number;
}
type Ev =
  | { type: "meta"; reformulation: string | null; abstention: boolean; avertissement: string | null }
  | { type: "sources"; sources: SourceRag[] }
  | { type: "token"; t: string }
  | { type: "fin"; texte: string; abstention: boolean; suggestions?: string[]; chiffres_non_verifies?: string[]; duree_s: number }
  | { type: "erreur"; message: string };

const LANGUES: { v: Langue; l: string }[] = [{ v: "fr", l: "Français" }, { v: "ar", l: "عربي" }, { v: "tn", l: "Tounsi" }];
const rtl = (l: Langue) => l !== "fr";

/** Rendu léger : paragraphes, listes, gras, et citations [n] cliquables. */
function Rendu({ texte, onCitation, langue }: { texte: string; onCitation: (n: number) => void; langue: Langue }) {
  const enLigne = (s: string, k: string) => {
    const morceaux = s.split(/(\*\*[^*]+\*\*|\[\d+\])/g);
    return morceaux.map((m, i) => {
      if (/^\*\*[^*]+\*\*$/.test(m)) return <strong key={`${k}-${i}`}>{m.slice(2, -2)}</strong>;
      const c = m.match(/^\[(\d+)\]$/);
      if (c) return (
        <button key={`${k}-${i}`} onClick={() => onCitation(Number(c[1]))}
          className="chiffres mx-0.5 inline-flex h-5 min-w-5 items-center justify-center rounded-md bg-action/10 px-1 text-[11px] font-semibold text-action align-baseline hover:bg-action/20">{c[1]}</button>
      );
      return <React.Fragment key={`${k}-${i}`}>{m}</React.Fragment>;
    });
  };
  const blocs: React.ReactNode[] = [];
  let liste: string[] = [];
  const viderListe = (k: number) => {
    if (liste.length) {
      blocs.push(<ul key={`ul${k}`} className={cn("my-1.5 space-y-1", rtl(langue) ? "pr-5" : "pl-5", "list-disc")}>{liste.map((l, i) => <li key={i}>{enLigne(l, `l${k}-${i}`)}</li>)}</ul>);
      liste = [];
    }
  };
  texte.split("\n").forEach((ligne, k) => {
    const t = ligne.trim();
    if (/^[-•*]\s+/.test(t)) { liste.push(t.replace(/^[-•*]\s+/, "")); return; }
    viderListe(k);
    if (!t) return;
    const titre = /^(\*\*)?(Détails|التفاصيل)(\*\*)?\s*:?\s*$/.test(t);
    blocs.push(<p key={k} className={cn("my-1.5", titre && "mt-3 font-semibold text-marine dark:text-encre")}>{enLigne(t.replace(/^\*\*(.+)\*\*$/, "$1"), `p${k}`)}</p>);
  });
  viderListe(9999);
  return <div className="text-[14px] leading-relaxed">{blocs}</div>;
}

function Surligne({ texte, passage }: { texte: string; passage?: string }) {
  if (!passage) return <>{texte}</>;
  const morceaux = passage.split("[…]").map((m) => m.trim()).filter((m) => m.length > 40);
  let html: React.ReactNode[] = [texte];
  for (const m of morceaux) {
    const suivant: React.ReactNode[] = [];
    html.forEach((n, i) => {
      if (typeof n !== "string" || !n.includes(m)) { suivant.push(n); return; }
      const [avant, ...apres] = n.split(m);
      suivant.push(avant, <mark key={`${m.slice(0, 12)}${i}`} className="surlignage">{m}</mark>, apres.join(m));
    });
    html = suivant;
  }
  return <>{html}</>;
}

export default function Assistant() {
  useFilAriane([{ libelle: "Assistant réglementaire" }]);
  const [mode, setMode] = React.useState<Mode>("contribuable");
  const [langue, setLangue] = React.useState<Langue>("fr");
  const [messages, setMessages] = React.useState<Message[]>([]);
  const [saisie, setSaisie] = React.useState("");
  const [source, setSource] = React.useState<SourceRag | null>(null);
  const [enCours, setEnCours] = React.useState(false);
  const arret = React.useRef<AbortController | null>(null);
  const bas = React.useRef<HTMLDivElement>(null);
  const { data: exemples } = useSWR<{ question: string; langue: Langue; mode: Mode; persona?: string }[]>("/api/chat/exemples", fetcher);
  const { data: base } = useSWR<{ sources: { source_id: string; titre: string; records: number; note: string | null }[]; non_couverts: string[] }>("/api/rag/sources", fetcher);

  React.useEffect(() => { bas.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [messages]);

  const envoyer = async (question: string, m: Mode = mode, l: Langue = langue) => {
    if (!question.trim() || enCours) return;
    const historique = messages.filter((x) => !x.erreur).slice(-4).map((x) => ({ role: x.role, content: x.contenu }));
    setMessages((prev) => [...prev, { role: "user", contenu: question, langue: l }, { role: "assistant", contenu: "", langue: l, enCours: true }]);
    setSaisie("");
    setEnCours(true);
    const ctrl = new AbortController();
    arret.current = ctrl;
    const majDernier = (f: (x: Message) => Message) => setMessages((prev) => [...prev.slice(0, -1), f(prev[prev.length - 1])]);
    try {
      for await (const ev of fluxNdjson<Ev>("/api/chat", { question, mode: m, langue: l, historique, stream: true }, ctrl.signal)) {
        if (ev.type === "meta") majDernier((x) => ({ ...x, reformulation: ev.reformulation, avertissement: ev.avertissement }));
        else if (ev.type === "sources") {
          majDernier((x) => ({ ...x, sources: ev.sources }));
          if (ev.sources[0]) setSource(ev.sources[0]);
        } else if (ev.type === "token") majDernier((x) => ({ ...x, contenu: x.contenu + ev.t }));
        else if (ev.type === "fin") majDernier((x) => ({ ...x, contenu: ev.texte, enCours: false, abstention: ev.abstention, suggestions: ev.suggestions, chiffres_non_verifies: ev.chiffres_non_verifies, duree: ev.duree_s }));
        else if (ev.type === "erreur") majDernier((x) => ({ ...x, enCours: false, erreur: ev.message }));
      }
    } catch (e) {
      majDernier((x) => ({ ...x, enCours: false, erreur: (e as Error).message }));
    } finally {
      majDernier((x) => ({ ...x, enCours: false }));
      setEnCours(false);
    }
  };

  const citer = (msg: Message, n: number) => {
    const s = msg.sources?.find((x) => x.n === n);
    if (s) setSource(s);
  };

  return (
    <div>
      <EnTetePage titre="Assistant réglementaire"
        sousTitre="Réponses sourcées : l'article exact et son texte, en français, en arabe ou en dialecte tunisien."
        actions={
          <div className="flex items-center gap-3">
            <div className="flex rounded-xl bg-survol p-1 text-xs font-medium">
              {(["contribuable", "agent"] as Mode[]).map((m) => (
                <button key={m} onClick={() => setMode(m)} className={cn("rounded-lg px-3 py-1.5", mode === m ? "bg-carte text-encre shadow-sm" : "text-attenue")}>
                  {m === "contribuable" ? "Mode contribuable" : "Mode agent"}
                </button>
              ))}
            </div>
            <div className="flex items-center rounded-xl bg-survol p-1 text-xs font-medium">
              <Languages className="mx-1.5 h-3.5 w-3.5 text-attenue" />
              {LANGUES.map((l) => (
                <button key={l.v} onClick={() => setLangue(l.v)} className={cn("rounded-lg px-3 py-1.5", langue === l.v ? "bg-carte text-encre shadow-sm" : "text-attenue", l.v !== "fr" && "font-arabe")}>
                  {l.l}
                </button>
              ))}
            </div>
          </div>
        } />

      <div className="grid h-[calc(100vh-230px)] min-h-[560px] grid-cols-[1fr_440px] gap-5">
        {/* ------------------------------------------------ conversation */}
        <Card className="flex min-h-0 flex-col">
          <div className="defilement flex-1 space-y-5 overflow-y-auto p-6">
            {messages.length === 0 && (
              <div className="mx-auto max-w-2xl pt-6 text-center">
                <LogoRadar className="mx-auto h-12 w-12 text-action" />
                <p className="mt-3 text-lg font-semibold text-marine dark:text-encre">Posez une question sur vos droits et obligations</p>
                <p className="mt-1 text-sm text-attenue">L&apos;assistant répond uniquement à partir des textes de la base et cite chaque article.</p>
                <div className="mt-6 grid grid-cols-2 gap-2 text-left">
                  {!exemples ? Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-16" />) : exemples.map((ex) => (
                    <button key={ex.question} onClick={() => { setLangue(ex.langue); setMode(ex.mode); envoyer(ex.question, ex.mode, ex.langue); }}
                      className="group rounded-xl border border-ligne p-3 text-sm transition-colors hover:border-action/40 hover:bg-action/5" dir={rtl(ex.langue) ? "rtl" : "ltr"}>
                      {ex.persona && <span className="mb-1 block text-[11px] font-medium text-action" dir="ltr">{ex.persona}</span>}
                      <span className={cn(rtl(ex.langue) && "font-arabe")}>{ex.question}</span>
                    </button>
                  ))}
                </div>
              </div>
            )}
            <AnimatePresence initial={false}>
              {messages.map((m, i) => (
                <motion.div key={i} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.15 }}
                  className={cn("flex gap-3", m.role === "user" && "flex-row-reverse")}>
                  <span className={cn("mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-full", m.role === "user" ? "bg-survol text-attenue" : "bg-action/10 text-action")}>
                    {m.role === "user" ? <UserRound className="h-4 w-4" /> : <Sparkles className="h-4 w-4" />}
                  </span>
                  <div className={cn("max-w-[82%] rounded-2xl px-4 py-3", m.role === "user" ? "bg-action text-white" : "border border-ligne bg-carte")}
                    dir={rtl(m.langue) ? "rtl" : "ltr"}>
                    {m.role === "user" ? <p className={cn("text-[14px]", rtl(m.langue) && "font-arabe")}>{m.contenu}</p> : (
                      <>
                        {m.avertissement && (
                          <p className="mb-2 flex items-center gap-2 rounded-lg bg-orange/10 px-2.5 py-1.5 text-xs text-amber-800 dark:text-orange" dir="ltr">
                            <ShieldAlert className="h-3.5 w-3.5" /> {m.avertissement}
                          </p>
                        )}
                        {m.enCours && !m.contenu ? (
                          <p className="flex items-center gap-2 text-sm text-attenue" dir="ltr"><Loader2 className="h-4 w-4 animate-spin" />
                            {m.sources ? "Rédaction à partir des textes retrouvés…" : "Recherche dans les textes…"}</p>
                        ) : (
                          <div className={cn(rtl(m.langue) && "font-arabe")}><Rendu texte={m.contenu} langue={m.langue} onCitation={(n) => citer(m, n)} /></div>
                        )}
                        {m.erreur && <p className="mt-2 flex items-start gap-2 text-xs text-rouge" dir="ltr"><AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />{m.erreur}</p>}
                        {!!m.chiffres_non_verifies?.length && (
                          <p className="mt-2 flex items-start gap-2 rounded-lg bg-rouge/5 px-2.5 py-1.5 text-xs text-rouge" dir="ltr">
                            <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                            À vérifier : {m.chiffres_non_verifies.join(", ")} ne figure dans aucun des textes fournis.
                          </p>
                        )}
                        {m.abstention && m.suggestions && (
                          <div className="mt-3 space-y-1.5" dir="ltr">
                            <p className="text-xs font-medium text-attenue">Essayez plutôt :</p>
                            {m.suggestions.map((s) => (
                              <button key={s} onClick={() => envoyer(s, mode, "fr")} className="block w-full rounded-lg border border-ligne px-3 py-1.5 text-left text-xs hover:bg-survol">{s}</button>
                            ))}
                          </div>
                        )}
                        {!m.enCours && !!m.sources?.length && (
                          <div className="mt-3 border-t border-ligne pt-2.5" dir="ltr">
                            <div className="mb-1.5 flex items-center justify-between">
                              <p className="text-[11px] font-semibold uppercase tracking-wide text-attenue">Sources</p>
                              <div className="flex items-center gap-2">
                                {m.duree && <span className="chiffres text-[11px] text-gris">{m.duree.toFixed(1).replace(".", ",")} s</span>}
                                <Infobulle contenu="Copier la réponse">
                                  <button onClick={() => { navigator.clipboard.writeText(m.contenu); toast.success("Réponse copiée"); }} className="rounded-md p-1 text-attenue hover:bg-survol"><Copy className="h-3.5 w-3.5" /></button>
                                </Infobulle>
                              </div>
                            </div>
                            <div className="flex flex-wrap gap-1.5">
                              {m.sources.map((s) => (
                                <button key={s.id} onClick={() => setSource(s)}
                                  className={cn("rounded-lg border px-2 py-1 text-left text-[11px] transition-colors", source?.id === s.id ? "border-action bg-action/10 text-action" : "border-ligne hover:bg-survol")}>
                                  <span className="chiffres font-semibold">[{s.n}]</span> {s.article ? (String(s.article).toLowerCase().startsWith("art") ? s.article : `Article ${s.article}`) : "Extrait"} · {s.document.split(",")[0].slice(0, 38)} · p. {s.page}
                                </button>
                              ))}
                            </div>
                            {m.reformulation && <p className="mt-2 text-[11px] text-gris">Recherche : « {m.reformulation} »</p>}
                          </div>
                        )}
                      </>
                    )}
                  </div>
                </motion.div>
              ))}
            </AnimatePresence>
            <div ref={bas} />
          </div>
          <form onSubmit={(e) => { e.preventDefault(); envoyer(saisie); }} className="border-t border-ligne p-4">
            <div className="flex items-end gap-2 rounded-2xl border border-ligne bg-fond p-2 focus-within:ring-2 focus-within:ring-action/30">
              <textarea value={saisie} onChange={(e) => setSaisie(e.target.value)} rows={1} dir={rtl(langue) ? "rtl" : "ltr"}
                onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); envoyer(saisie); } }}
                placeholder={langue === "fr" ? "Votre question (ex. : dans quel délai dois-je répondre à une demande de l'administration ?)" : "اكتب سؤالك هنا…"}
                className={cn("max-h-32 min-h-[40px] flex-1 resize-none bg-transparent px-2 py-2 text-sm outline-none", rtl(langue) && "font-arabe")} />
              {enCours ? <Button type="button" variant="secondaire" taille="icone" onClick={() => arret.current?.abort()} aria-label="Arrêter"><Square /></Button>
                : <Button type="submit" taille="icone" disabled={!saisie.trim()} aria-label="Envoyer"><SendHorizonal /></Button>}
            </div>
            <p className="mt-2 text-center text-[11px] text-gris">Information, pas un conseil juridique. {mode === "agent" ? "Mode agent : réponses techniques." : "Mode contribuable : langage simple."}</p>
          </form>
        </Card>

        {/* ------------------------------------------------ panneau des sources */}
        <Card className="flex min-h-0 flex-col">
          <div className="border-b border-ligne px-5 py-4">
            <p className="flex items-center gap-2 text-sm font-semibold text-marine dark:text-encre"><BookOpen className="h-4 w-4" /> Texte exact de la source</p>
            <p className="mt-0.5 text-xs text-attenue">Cliquez sur une citation [n] pour afficher l&apos;article ; le passage transmis au modèle est surligné.</p>
          </div>
          <div className="defilement flex-1 overflow-y-auto px-5 py-4">
            {source ? (
              <div>
                <p className="text-xs font-medium text-action">[{source.n}] {source.document}</p>
                <p className="mt-1 text-base font-semibold text-marine dark:text-encre">{source.article ? (String(source.article).toLowerCase().startsWith("art") ? source.article : `Article ${source.article}`) : "Extrait"}</p>
                {source.source_id === "code_douanes_2016" && <p className="mt-1 rounded-md bg-orange/10 px-2 py-1 text-[11px] text-amber-800 dark:text-orange">Code des douanes, édition 2016</p>}
                <p className="mt-1 text-[11px] leading-relaxed text-attenue">{source.section}</p>
                <div className="mt-3 whitespace-pre-wrap rounded-xl bg-survol p-4 text-[13px] leading-relaxed">
                  <Surligne texte={source.extrait} passage={source.extrait_envoye} />
                </div>
                <p className="mt-2 text-[11px] text-attenue">{source.locator}</p>
              </div>
            ) : (
              <div className="space-y-3 text-xs text-attenue">
                <p className="font-medium text-encre">Textes de la base</p>
                {!base ? <Skeleton className="h-40" /> : base.sources.map((s) => (
                  <div key={s.source_id} className="flex items-start justify-between gap-3 rounded-lg border border-ligne p-2.5">
                    <span>{s.titre}{s.note && <span className="block text-[11px] text-orange">{s.note}</span>}</span>
                    <span className="chiffres shrink-0 text-gris">{s.records}</span>
                  </div>
                ))}
                {base && <p className="rounded-lg bg-orange/10 p-2.5 text-amber-800 dark:text-orange">Pas encore couverts : {base.non_couverts.join(", ")}. L&apos;assistant le signale au lieu de répondre de mémoire.</p>}
              </div>
            )}
          </div>
        </Card>
      </div>
    </div>
  );
}
