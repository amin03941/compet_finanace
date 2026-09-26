"use client";
import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import useSWR from "swr";
import { motion } from "framer-motion";
import { BookOpenText, ChevronRight, Crosshair, FlaskConical, Gauge, HandCoins, Info, Moon, Sun, TriangleAlert } from "lucide-react";
import { Toaster } from "sonner";
import { fetcher } from "@/lib/api";
import { cn, nombre } from "@/lib/utils";
import { Infobulle, TooltipProvider } from "@/components/ui/misc";
import { LogoRadar } from "./logo";

const NAV = [
  { href: "/", libelle: "Tableau de bord", icone: Gauge },
  { href: "/ciblage", libelle: "Ciblage", icone: Crosshair, sous: "T20" },
  { href: "/assistant", libelle: "Assistant", icone: BookOpenText, sous: "T9" },
  { href: "/facilitation", libelle: "Facilitation", icone: HandCoins, sous: "T4" },
  { href: "/performance", libelle: "Performance", icone: FlaskConical },
  { href: "/a-propos", libelle: "À propos", icone: Info },
];

type Fil = { libelle: string; href?: string }[];
const FilContexte = React.createContext<{ fil: Fil; setFil: (f: Fil) => void }>({ fil: [], setFil: () => {} });

/** Les pages déclarent leur fil d'Ariane. */
export function useFilAriane(fil: Fil) {
  const { setFil } = React.useContext(FilContexte);
  const cle = JSON.stringify(fil);
  React.useEffect(() => {
    setFil(JSON.parse(cle));
  }, [cle, setFil]);
}

function Sidebar() {
  const chemin = usePathname();
  return (
    <aside className="fixed inset-y-0 left-0 z-30 flex w-64 flex-col bg-marine text-white">
      <div className="flex items-center gap-3 px-6 pb-6 pt-11">
        <LogoRadar className="h-9 w-9 text-sky-300" />
        <div>
          <p className="text-[17px] font-semibold tracking-tight">RASD 360</p>
          <p className="text-[11px] text-sky-100/70">Radar fiscal et douanier</p>
        </div>
      </div>
      <nav className="flex-1 space-y-1 px-3">
        {NAV.map(({ href, libelle, icone: Icone, sous }) => {
          const actif = href === "/" ? chemin === "/" : chemin.startsWith(href) ||
            (href === "/ciblage" && (chemin.startsWith("/entreprise") || chemin.startsWith("/dossier")));
          return (
            <Link key={href} href={href}
              className={cn("group relative flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm transition-colors",
                actif ? "text-white" : "text-sky-100/70 hover:bg-white/5 hover:text-white")}>
              {actif && <motion.span layoutId="nav-actif" className="absolute inset-0 rounded-xl bg-white/10" transition={{ duration: 0.18 }} />}
              <Icone className="relative h-[18px] w-[18px]" />
              <span className="relative flex-1">{libelle}</span>
              {sous && <span className="relative rounded-md bg-white/10 px-1.5 py-0.5 text-[10px] font-medium text-sky-100/80">{sous}</span>}
            </Link>
          );
        })}
      </nav>
      <div className="m-3 rounded-xl bg-white/5 p-3 text-[11px] leading-relaxed text-sky-100/70">
        <p className="font-medium text-sky-50">Aide à la décision</p>
        Le score mesure la probabilité qu&apos;un contrôle soit utile, pas la culpabilité. L&apos;agent décide toujours.
      </div>
    </aside>
  );
}

interface Sante {
  status: string;
  index: { status: string; ntotal?: number };
  embeddings: { status: string };
  ollama: { status: string; modele_par_defaut?: string };
  base: { status: string; entreprises?: number };
}

function IndicateurSante() {
  const { data, error } = useSWR<Sante>("/api/health", fetcher, { refreshInterval: 30000 });
  const points = [
    { nom: "API", ok: !error && !!data },
    { nom: data?.index?.ntotal ? `Index RAG ${nombre(data.index.ntotal)}` : "Index RAG", ok: data?.index?.status === "ok" },
    { nom: "Embeddings", ok: data?.embeddings?.status === "ready", attente: data?.embeddings?.status === "loading" },
    { nom: data?.ollama?.modele_par_defaut ? `LLM ${data.ollama.modele_par_defaut}` : "LLM local", ok: data?.ollama?.status === "ok" },
  ];
  return (
    <Infobulle cote="bottom" contenu={
      <div className="space-y-1">
        {points.map((p) => <div key={p.nom}>{p.ok ? "✓" : p.attente ? "…" : "✗"} {p.nom}</div>)}
        {data?.ollama?.status !== "ok" && <div className="pt-1 text-amber-200">Sans LLM : scores, preuves et graphiques restent disponibles.</div>}
      </div>
    }>
      <button className="flex items-center gap-1.5 rounded-lg px-2 py-1 text-[11px] text-attenue hover:bg-survol">
        {points.map((p) => (
          <span key={p.nom} className={cn("h-2 w-2 rounded-full", p.ok ? "bg-vert" : p.attente ? "animate-pulse bg-orange" : "bg-rouge")} />
        ))}
        <span className="ml-1">État des services</span>
      </button>
    </Infobulle>
  );
}

function BasculeTheme() {
  const [sombre, setSombre] = React.useState(false);
  React.useEffect(() => {
    let v = false;
    try { v = localStorage.getItem("rasd-theme") === "sombre"; } catch {}
    setSombre(v);
    document.documentElement.classList.toggle("dark", v);
  }, []);
  const basculer = () => {
    const v = !sombre;
    setSombre(v);
    document.documentElement.classList.toggle("dark", v);
    try { localStorage.setItem("rasd-theme", v ? "sombre" : "clair"); } catch {}
  };
  return (
    <button onClick={basculer} className="rounded-lg p-2 text-attenue hover:bg-survol hover:text-encre" aria-label="Changer de thème">
      {sombre ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
    </button>
  );
}

export function Shell({ children }: { children: React.ReactNode }) {
  const [fil, setFil] = React.useState<Fil>([]);
  return (
    <FilContexte.Provider value={{ fil, setFil }}>
      <TooltipProvider>
        <div className="fixed inset-x-0 top-0 z-40 flex h-7 items-center justify-center gap-2 bg-amber-100 text-[11px] font-semibold uppercase tracking-wide text-amber-900 dark:bg-amber-900/60 dark:text-amber-100">
          <TriangleAlert className="h-3.5 w-3.5" /> Prototype — données entièrement fictives
        </div>
        <Sidebar />
        <div className="pl-64 pt-7">
          <header className="sticky top-7 z-20 flex h-14 items-center justify-between border-b border-ligne bg-fond/85 px-8 backdrop-blur">
            <nav className="flex items-center gap-1.5 text-sm text-attenue" aria-label="Fil d'Ariane">
              <Link href="/" className="hover:text-encre">Accueil</Link>
              {fil.map((f, i) => (
                <React.Fragment key={i}>
                  <ChevronRight className="h-3.5 w-3.5 text-gris" />
                  {f.href && i < fil.length - 1 ? <Link href={f.href} className="hover:text-encre">{f.libelle}</Link>
                    : <span className={cn(i === fil.length - 1 && "font-medium text-encre")}>{f.libelle}</span>}
                </React.Fragment>
              ))}
            </nav>
            <div className="flex items-center gap-2">
              <IndicateurSante />
              <BasculeTheme />
            </div>
          </header>
          <main className="mx-auto max-w-[1360px] px-8 py-7">{children}</main>
        </div>
        <Toaster position="bottom-right" richColors closeButton />
      </TooltipProvider>
    </FilContexte.Provider>
  );
}
