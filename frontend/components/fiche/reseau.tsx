"use client";
import * as React from "react";
import dynamic from "next/dynamic";
import { useRouter } from "next/navigation";
import type { NoeudReseau } from "@/lib/api";
import { useCouleurs } from "@/lib/couleurs";
import { Skeleton } from "@/components/ui/misc";

const ForceGraph2D = dynamic(() => import("./force-graph"), { ssr: false, loading: () => <Skeleton className="h-[340px]" /> });

type N = NoeudReseau & { x?: number; y?: number };

/* eslint-disable @typescript-eslint/no-explicit-any */
/** Réseau : dirigeants, adresses, sociétés liées ; radiées, redressées ou défaillantes en rouge. */
export function GrapheReseau({ nodes, edges }: { nodes: NoeudReseau[]; edges: { source: string; target: string; label: string; circuit?: boolean }[] }) {
  const C = useCouleurs();
  const routeur = useRouter();
  const conteneur = React.useRef<HTMLDivElement>(null);
  const [largeur, setLargeur] = React.useState(600);
  React.useEffect(() => {
    const el = conteneur.current;
    if (!el) return;
    const obs = new ResizeObserver(() => setLargeur(el.clientWidth));
    obs.observe(el);
    return () => obs.disconnect();
  }, []);
  const data = React.useMemo(() => ({
    nodes: nodes.map((n) => ({ ...n })),
    links: edges.map((e) => ({ ...e })),
  }), [nodes, edges]);

  const couleur = (n: N) => {
    if (n.type === "personne") return C.attenue;
    if (n.type === "adresse") return C.gris;
    if (n.centrale) return C.action;
    if (n.radiee || n.redressee || n.defaillante) return C.rouge;
    return C.vert;
  };

  if (nodes.length <= 1) {
    return <p className="rounded-xl bg-survol p-4 text-sm text-attenue">Aucun lien (dirigeant, adresse ou circuit de factures) avec une autre entreprise.</p>;
  }
  return (
    <div>
      <div ref={conteneur} className="overflow-hidden rounded-xl border border-ligne bg-fond">
        <ForceGraph2D graphData={data} width={largeur} height={340} cooldownTicks={120} nodeRelSize={5}
          linkColor={(l: any) => (l.circuit ? C.rouge : C.ligne)} linkWidth={(l: any) => (l.circuit ? 2 : 1.2)}
          linkDirectionalArrowLength={(l: any) => (l.circuit ? 5 : 0)} linkDirectionalArrowRelPos={0.9}
          linkDirectionalParticles={(l: any) => (l.circuit ? 2 : 0)} linkDirectionalParticleColor={() => C.rouge}
          onNodeClick={(n: any) => { if (n.entreprise_id && !n.centrale) routeur.push(`/entreprise/${n.entreprise_id}`); }}
          nodeCanvasObject={(n: any, ctx: CanvasRenderingContext2D, zoom: number) => {
            const r = n.centrale ? 9 : n.type === "entreprise" ? 7 : 5;
            ctx.beginPath();
            if (n.type === "adresse") ctx.rect((n.x ?? 0) - r, (n.y ?? 0) - r, r * 2, r * 2);
            else ctx.arc(n.x ?? 0, n.y ?? 0, r, 0, 2 * Math.PI);
            ctx.fillStyle = couleur(n);
            ctx.fill();
            if (n.centrale) { ctx.lineWidth = 3; ctx.strokeStyle = "rgba(29,78,216,0.25)"; ctx.stroke(); }
            const taille = Math.max(10 / zoom, 3.2);
            ctx.font = `${n.centrale ? 600 : 500} ${taille}px Inter Variable, sans-serif`;
            ctx.textAlign = "center";
            ctx.textBaseline = "top";
            ctx.fillStyle = C.encre;
            const etiquette = n.type === "adresse" ? "Adresse commune" : n.label.length > 30 ? `${n.label.slice(0, 29)}…` : n.label;
            ctx.fillText(etiquette, n.x ?? 0, (n.y ?? 0) + r + 2);
            if (n.radiee || n.redressee || n.defaillante) {
              ctx.font = `${taille * 0.85}px Inter Variable, sans-serif`;
              ctx.fillStyle = C.rouge;
              ctx.fillText(n.radiee ? "radiée" : n.redressee ? "redressée" : "TVA non déposée", n.x ?? 0, (n.y ?? 0) + r + 3 + taille);
            }
          }} />
      </div>
      <div className="mt-2 flex flex-wrap gap-4 text-[11px] text-attenue">
        <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-full" style={{ background: C.action }} />Entreprise analysée</span>
        <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-full" style={{ background: C.rouge }} />Radiée, redressée ou défaillante</span>
        <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-full" style={{ background: C.vert }} />Autre entreprise liée</span>
        <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-full" style={{ background: C.attenue }} />Dirigeant ou associé</span>
        <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5" style={{ background: C.gris }} />Adresse</span>
        <span className="flex items-center gap-1.5"><span className="h-0.5 w-4" style={{ background: C.rouge }} />Circuit de factures</span>
      </div>
    </div>
  );
}
