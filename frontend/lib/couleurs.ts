"use client";
import * as React from "react";

const TOKENS = ["fond", "carte", "encre", "attenue", "ligne", "marine", "action", "action2", "rouge", "orange", "vert", "gris", "survol"] as const;
export type Couleurs = Record<(typeof TOKENS)[number], string>;

const DEFAUT: Couleurs = {
  fond: "#F6F8FB", carte: "#FFFFFF", encre: "#0F172A", attenue: "#64748B", ligne: "#E2E8F0", marine: "#0B2545",
  action: "#1D4ED8", action2: "#13315C", rouge: "#DC2626", orange: "#F59E0B", vert: "#16A34A", gris: "#94A3B8", survol: "#F1F5F9",
};

function lire(): Couleurs {
  if (typeof window === "undefined") return DEFAUT;
  const s = getComputedStyle(document.documentElement);
  const out = { ...DEFAUT };
  for (const t of TOKENS) {
    const v = s.getPropertyValue(`--${t}`).trim();
    if (v) out[t] = `rgb(${v.split(/\s+/).join(",")})`;
  }
  return out;
}

/** Couleurs du design system résolues (les attributs SVG n'acceptent pas var()). Suit le mode sombre. */
export function useCouleurs(): Couleurs {
  const [c, setC] = React.useState<Couleurs>(DEFAUT);
  React.useEffect(() => {
    setC(lire());
    const obs = new MutationObserver(() => setC(lire()));
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
    return () => obs.disconnect();
  }, []);
  return c;
}

export function alpha(couleur: string, a: number): string {
  return couleur.startsWith("rgb(") ? couleur.replace("rgb(", "rgba(").replace(")", `,${a})`) : couleur;
}
