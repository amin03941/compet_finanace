"use client";
import * as React from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import useSWR from "swr";
import { ChevronLeft, ChevronRight, Download, Search, SlidersHorizontal, X } from "lucide-react";
import { API_URL, fetcher, type LigneCiblage } from "@/lib/api";
import { CATEGORIES, cn, dt, nombre } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EtatErreur, EtatVide, Infobulle, Skeleton } from "@/components/ui/misc";
import { BadgeCategorie, EnTetePage, PastilleScore, PucesIndices } from "@/components/risque/elements";
import { useFilAriane } from "@/components/shell/shell";

interface Referentiels {
  secteurs: { code: string; libelle: string }[];
  gouvernorats: string[];
  regles: { code: string; libelle: string; niveau: string }[];
}

function Selecteur({ valeur, onChange, options, placeholder }: {
  valeur: string; onChange: (v: string) => void; options: { v: string; l: string }[]; placeholder: string;
}) {
  return (
    <select value={valeur} onChange={(e) => onChange(e.target.value)}
      className={cn("h-9 rounded-xl border border-ligne bg-carte px-3 text-sm outline-none focus:ring-2 focus:ring-action/30", !valeur && "text-attenue")}>
      <option value="">{placeholder}</option>
      {options.map((o) => <option key={o.v} value={o.v}>{o.l}</option>)}
    </select>
  );
}

function Ciblage() {
  useFilAriane([{ libelle: "Ciblage" }]);
  const routeur = useRouter();
  const params = useSearchParams();
  const [categories, setCategories] = React.useState<string[]>(params.get("categorie")?.split(",").filter(Boolean) ?? []);
  const [secteur, setSecteur] = React.useState(params.get("secteur") ?? "");
  const [gouvernorat, setGouvernorat] = React.useState(params.get("gouvernorat") ?? "");
  const [regle, setRegle] = React.useState(params.get("regle") ?? "");
  const [montant, setMontant] = React.useState(params.get("montant_min") ?? "");
  const [saisie, setSaisie] = React.useState(params.get("q") ?? "");
  const [q, setQ] = React.useState(saisie);
  const [page, setPage] = React.useState(1);
  React.useEffect(() => {
    const t = setTimeout(() => setQ(saisie), 250);
    return () => clearTimeout(t);
  }, [saisie]);
  React.useEffect(() => setPage(1), [categories, secteur, gouvernorat, regle, montant, q]);

  const filtres = new URLSearchParams();
  if (categories.length) filtres.set("categorie", categories.join(","));
  if (secteur) filtres.set("secteur", secteur);
  if (gouvernorat) filtres.set("gouvernorat", gouvernorat);
  if (regle) filtres.set("regle", regle);
  if (montant) filtres.set("montant_min", montant);
  if (q) filtres.set("q", q);
  const cle = filtres.toString();
  React.useEffect(() => {
    routeur.replace(cle ? `/ciblage?${cle}` : "/ciblage", { scroll: false });
  }, [cle, routeur]);

  const { data: ref } = useSWR<Referentiels>("/api/referentiels", fetcher);
  const { data, error, isLoading } = useSWR<{ total: number; resultats: LigneCiblage[] }>(
    `/api/entreprises?${cle}&page=${page}&taille=50`, fetcher, { keepPreviousData: true });
  const nbFiltres = [categories.length > 0, secteur, gouvernorat, regle, montant, q].filter(Boolean).length;
  const pages = data ? Math.max(1, Math.ceil(data.total / 50)) : 1;

  const reinitialiser = () => {
    setCategories([]); setSecteur(""); setGouvernorat(""); setRegle(""); setMontant(""); setSaisie("");
  };

  return (
    <div>
      <EnTetePage titre="Ciblage des contrôles"
        sousTitre="Entreprises classées par priorité = probabilité qu'un contrôle soit utile × montant en jeu estimé."
        actions={
          <Button variant="secondaire" asChild>
            <a href={`${API_URL}/api/entreprises.csv?${cle}`}><Download /> Exporter en CSV</a>
          </Button>
        } />

      <Card className="mb-4 p-4">
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative mr-1 min-w-[260px] flex-1">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gris" />
            <input value={saisie} onChange={(e) => setSaisie(e.target.value)} placeholder="Rechercher une entreprise ou un matricule…"
              className="h-9 w-full rounded-xl border border-ligne bg-carte pl-9 pr-3 text-sm outline-none focus:ring-2 focus:ring-action/30" />
          </div>
          {(["rouge", "orange", "gris", "vert"] as const).map((c) => {
            const actif = categories.includes(c);
            return (
              <button key={c} onClick={() => setCategories(actif ? categories.filter((x) => x !== c) : [...categories, c])}
                className={cn("flex h-9 items-center gap-2 rounded-xl border px-3 text-xs font-medium transition-colors",
                  actif ? `${CATEGORIES[c].fond} ${CATEGORIES[c].texte} border-transparent ring-1 ring-current/20` : "border-ligne bg-carte text-attenue hover:bg-survol")}>
                <span className={cn("h-2 w-2 rounded-full", CATEGORIES[c].point)} /> {CATEGORIES[c].libelle}
              </button>
            );
          })}
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <SlidersHorizontal className="h-4 w-4 text-gris" />
          <Selecteur valeur={secteur} onChange={setSecteur} placeholder="Tous les secteurs" options={(ref?.secteurs || []).map((s) => ({ v: s.code, l: s.libelle }))} />
          <Selecteur valeur={gouvernorat} onChange={setGouvernorat} placeholder="Tous les gouvernorats" options={(ref?.gouvernorats || []).map((g) => ({ v: g, l: g }))} />
          <Selecteur valeur={regle} onChange={setRegle} placeholder="Tous les indices" options={(ref?.regles || []).map((r) => ({ v: r.code, l: `${r.code} — ${r.libelle}` }))} />
          <Selecteur valeur={montant} onChange={setMontant} placeholder="Tout montant en jeu"
            options={[{ v: "20000", l: "> 20 000 DT" }, { v: "100000", l: "> 100 000 DT" }, { v: "250000", l: "> 250 000 DT" }]} />
          {nbFiltres > 0 && <Button variant="fantome" taille="sm" onClick={reinitialiser}><X /> Réinitialiser ({nbFiltres})</Button>}
          <span className="chiffres ml-auto text-xs text-attenue">{data ? `${nombre(data.total)} entreprise${data.total > 1 ? "s" : ""}` : ""}</span>
        </div>
      </Card>

      {error ? <EtatErreur message={error.message} /> : (
        <Card className="overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-ligne bg-survol/60 text-left text-[11px] font-semibold uppercase tracking-wide text-attenue">
                  <th className="w-14 px-4 py-3 text-center">Rang</th>
                  <th className="px-3 py-3">Entreprise</th>
                  <th className="px-3 py-3">Secteur · gouvernorat</th>
                  <th className="px-3 py-3 text-center">Score</th>
                  <th className="px-3 py-3">Catégorie</th>
                  <th className="px-3 py-3">Indices</th>
                  <th className="px-3 py-3 text-right">Montant en jeu</th>
                  <th className="w-[26%] px-4 py-3">Première raison</th>
                </tr>
              </thead>
              <tbody>
                {isLoading && !data ? Array.from({ length: 10 }).map((_, i) => (
                  <tr key={i} className="border-b border-ligne"><td colSpan={8} className="px-4 py-2.5"><Skeleton className="h-9" /></td></tr>
                )) : data && data.resultats.length === 0 ? (
                  <tr><td colSpan={8} className="p-6"><EtatVide titre="Aucune entreprise ne correspond aux filtres" texte="Modifiez ou réinitialisez les filtres." /></td></tr>
                ) : data?.resultats.map((e) => (
                  <tr key={e.id} onClick={() => routeur.push(`/entreprise/${e.id}`)}
                    className="group cursor-pointer border-b border-ligne transition-colors last:border-0 hover:bg-survol/70">
                    <td className="chiffres px-4 py-3 text-center font-semibold text-gris">{e.rang}</td>
                    <td className="px-3 py-3">
                      <Link href={`/entreprise/${e.id}`} className="font-medium text-encre group-hover:text-action" onClick={(ev) => ev.stopPropagation()}>{e.raison_sociale}</Link>
                      <p className="chiffres text-[11px] text-attenue">{e.matricule_fiscal} <span className="rounded bg-survol px-1 text-[10px]">fictif</span></p>
                    </td>
                    <td className="px-3 py-3 text-xs text-attenue"><p className="text-encre">{e.secteur}</p>{e.gouvernorat}</td>
                    <td className="px-3 py-3 text-center"><PastilleScore score={e.score} taille="sm" /></td>
                    <td className="px-3 py-3"><BadgeCategorie categorie={e.categorie} court /></td>
                    <td className="px-3 py-3"><PucesIndices codes={e.regles} max={4} /></td>
                    <td className="chiffres px-3 py-3 text-right font-medium">{e.montant_en_jeu > 0 ? dt(e.montant_en_jeu) : <span className="text-gris">—</span>}</td>
                    <td className="px-4 py-3">
                      <Infobulle contenu={e.premiere_raison}>
                        <p className="line-clamp-2 text-xs text-attenue">{e.premiere_raison}</p>
                      </Infobulle>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {data && data.total > 50 && (
            <div className="flex items-center justify-between border-t border-ligne px-4 py-3 text-xs text-attenue">
              <span className="chiffres">Page {page} sur {pages}</span>
              <div className="flex gap-2">
                <Button variant="secondaire" taille="sm" disabled={page <= 1} onClick={() => setPage(page - 1)}><ChevronLeft /> Précédente</Button>
                <Button variant="secondaire" taille="sm" disabled={page >= pages} onClick={() => setPage(page + 1)}>Suivante <ChevronRight /></Button>
              </div>
            </div>
          )}
        </Card>
      )}
    </div>
  );
}

export default function PageCiblage() {
  return (
    <React.Suspense fallback={<Skeleton className="h-96" />}>
      <Ciblage />
    </React.Suspense>
  );
}
