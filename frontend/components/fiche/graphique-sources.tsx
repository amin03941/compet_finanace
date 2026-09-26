"use client";
import * as React from "react";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useCouleurs } from "@/lib/couleurs";
import { dt, dtCompact, moisCourt } from "@/lib/utils";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/misc";

/** « Le graphique qui tue » : 4 sources indépendantes sur 36 mois. L'écart qui s'ouvre saute aux yeux. */
export function GraphiqueSources({ series }: { series: Record<string, number | string>[] }) {
  const C = useCouleurs();
  const [mode, setMode] = React.useState<"cumul" | "mensuel">("cumul");
  const p = mode === "cumul" ? "cumul_" : "";
  const lignes = [
    { cle: `${p}importations`, nom: "Importations (douane)", couleur: C.marine === "rgb(5,14,30)" ? C.action2 : C.marine, largeur: 2.5 },
    { cle: `${p}ca_declare`, nom: "Chiffre d'affaires déclaré (impôts)", couleur: C.rouge, largeur: 2.5 },
    { cle: `${p}paiements_tej`, nom: "Paiements attestés par les clients (TEJ)", couleur: C.orange, largeur: 2.5 },
    { cle: `${p}factures_emises`, nom: "Factures émises (El Fatoora)", couleur: C.vert, largeur: 2 },
  ];
  return (
    <div>
      <div className="mb-3 flex items-center justify-between">
        <p className="text-xs text-attenue">{mode === "cumul" ? "Montants cumulés depuis janvier 2023" : "Montants mensuels"} — montants hors taxes, en dinars</p>
        <Tabs value={mode} onValueChange={(v) => setMode(v as "cumul" | "mensuel")}>
          <TabsList>
            <TabsTrigger value="cumul">Cumul</TabsTrigger>
            <TabsTrigger value="mensuel">Mensuel</TabsTrigger>
          </TabsList>
        </Tabs>
      </div>
      <div className="h-[320px]">
        <ResponsiveContainer>
          <LineChart data={series} margin={{ left: 4, right: 12, top: 8 }}>
            <CartesianGrid vertical={false} stroke={C.ligne} />
            <XAxis dataKey="periode" tickFormatter={moisCourt} tick={{ fontSize: 11, fill: C.attenue }} interval={2} tickLine={false} axisLine={false} />
            <YAxis tickFormatter={(v) => dtCompact(v).replace(/ DT/, "")} tick={{ fontSize: 11, fill: C.attenue }} tickLine={false} axisLine={false} width={64} />
            <Tooltip formatter={(v: number, n) => [dt(v), n]} labelFormatter={moisCourt}
              contentStyle={{ borderRadius: 12, border: "1px solid rgb(var(--ligne))", background: "rgb(var(--carte))", fontSize: 12 }} />
            <Legend iconType="plainline" wrapperStyle={{ fontSize: 12, paddingTop: 8 }} />
            {lignes.map((l) => (
              <Line key={l.cle} type={mode === "cumul" ? "monotone" : "linear"} dataKey={l.cle} name={l.nom} stroke={l.couleur}
                strokeWidth={l.largeur} dot={false} activeDot={{ r: 4 }} animationDuration={900} />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
