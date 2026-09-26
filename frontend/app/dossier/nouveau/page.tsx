"use client";
import * as React from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { motion } from "framer-motion";
import { Check, Loader2 } from "lucide-react";
import { fluxNdjson, type Dossier } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Card } from "@/components/ui/card";
import { EtatErreur, Skeleton } from "@/components/ui/misc";
import { useFilAriane } from "@/components/shell/shell";
import { LogoRadar } from "@/components/shell/logo";

const ETAPES = [
  { cle: "collecte", libelle: "Collecte des données…", detail: "Douane, déclarations de TVA et annuelles, TEJ, El Fatoora, banque" },
  { cle: "calcul", libelle: "Calcul des écarts…", detail: "Calculs déterministes : le modèle de langage ne calcule jamais" },
  { cle: "articles", libelle: "Recherche des articles…", detail: "Textes retrouvés dans la base et vérifiés un par un" },
  { cle: "redaction", libelle: "Rédaction…", detail: "Synthèse et projet de lettre, à partir des seuls montants calculés" },
];

type Evenement = { type: "etape"; etape: string; libelle: string } | { type: "dossier"; dossier: Dossier } | { type: "erreur"; message: string };

function Generation() {
  const params = useSearchParams();
  const routeur = useRouter();
  const entreprise = params.get("entreprise");
  const section = params.get("section");
  const [courante, setCourante] = React.useState(-1);
  const [erreur, setErreur] = React.useState<string | null>(null);
  const [debut] = React.useState(() => Date.now());
  const [ecoule, setEcoule] = React.useState(0);
  const lance = React.useRef(false);
  useFilAriane([{ libelle: "Ciblage", href: "/ciblage" }, { libelle: "Fiche", href: `/entreprise/${entreprise}` }, { libelle: "Préparation du dossier" }]);

  React.useEffect(() => {
    const t = setInterval(() => setEcoule((Date.now() - debut) / 1000), 100);
    return () => clearInterval(t);
  }, [debut]);

  React.useEffect(() => {
    if (!entreprise || lance.current) return;
    lance.current = true;
    (async () => {
      try {
        for await (const ev of fluxNdjson<Evenement>(`/api/entreprises/${entreprise}/dossier`, { agent: "agent.demo", stream: true })) {
          if (ev.type === "etape") setCourante(ETAPES.findIndex((e) => e.cle === ev.etape));
          if (ev.type === "erreur") setErreur(ev.message);
          if (ev.type === "dossier") {
            setCourante(ETAPES.length);
            setTimeout(() => routeur.replace(`/dossier/${ev.dossier.id}${section ? `#${section}` : ""}`), 450);
          }
        }
      } catch (e) {
        setErreur((e as Error).message);
      }
    })();
  }, [entreprise, section, routeur]);

  if (!entreprise) return <EtatErreur message="Entreprise non précisée." />;
  return (
    <div className="flex min-h-[70vh] items-center justify-center">
      <Card className="w-full max-w-xl p-8">
        <div className="mb-6 flex items-center gap-3">
          <LogoRadar className="h-10 w-10 animate-[spin_6s_linear_infinite] text-action" />
          <div>
            <h1 className="text-lg font-semibold text-marine dark:text-encre">Préparation du pré-dossier de contrôle</h1>
            <p className="chiffres text-xs text-attenue">{ecoule.toFixed(1).replace(".", ",")} s</p>
          </div>
        </div>
        {erreur ? <EtatErreur message={erreur} /> : (
          <ol className="space-y-4">
            {ETAPES.map((e, i) => {
              const fait = i < courante;
              const encours = i === courante;
              return (
                <motion.li key={e.cle} initial={{ opacity: 0.4 }} animate={{ opacity: i <= courante ? 1 : 0.45 }} transition={{ duration: 0.2 }} className="flex items-start gap-3">
                  <span className={cn("mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full border",
                    fait ? "border-vert bg-vert text-white" : encours ? "border-action text-action" : "border-ligne text-gris")}>
                    {fait ? <Check className="h-3.5 w-3.5" /> : encours ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <span className="text-[11px]">{i + 1}</span>}
                  </span>
                  <div>
                    <p className={cn("text-sm font-medium", fait || encours ? "text-encre" : "text-attenue")}>{e.libelle}</p>
                    <p className="text-xs text-attenue">{e.detail}</p>
                  </div>
                </motion.li>
              );
            })}
          </ol>
        )}
        <p className="mt-6 border-t border-ligne pt-4 text-[11px] text-attenue">
          Aide à la décision : l&apos;agent reste seul décisionnaire. Montants indicatifs, à confirmer par la procédure contradictoire.
        </p>
      </Card>
    </div>
  );
}

export default function PageGeneration() {
  return (
    <React.Suspense fallback={<Skeleton className="h-96" />}>
      <Generation />
    </React.Suspense>
  );
}
