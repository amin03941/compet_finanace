"use client";
import * as React from "react";
import * as T from "@radix-ui/react-tooltip";
import * as TabsPrimitive from "@radix-ui/react-tabs";
import * as P from "@radix-ui/react-popover";
import { AlertTriangle, Inbox } from "lucide-react";
import { cn } from "@/lib/utils";

// ------------------------------------------------------------------ badge
export function Badge({ className, ...p }: React.HTMLAttributes<HTMLSpanElement>) {
  return (
    <span
      className={cn("inline-flex items-center gap-1 rounded-full border border-ligne bg-survol px-2 py-0.5 text-[11px] font-medium text-attenue", className)}
      {...p}
    />
  );
}

// ------------------------------------------------------------------ squelette de chargement
export function Skeleton({ className }: { className?: string }) {
  return (
    <div className={cn("relative overflow-hidden rounded-xl bg-survol", className)}>
      <div className="absolute inset-0 -translate-x-full animate-[shimmer_1.4s_infinite] bg-gradient-to-r from-transparent via-white/50 to-transparent dark:via-white/5" />
    </div>
  );
}

// ------------------------------------------------------------------ infobulle
export const TooltipProvider = T.Provider;

export function Infobulle({ contenu, children, className, cote = "top" }: {
  contenu: React.ReactNode; children: React.ReactNode; className?: string; cote?: "top" | "bottom" | "left" | "right";
}) {
  return (
    <T.Root delayDuration={150}>
      <T.Trigger asChild>{children}</T.Trigger>
      <T.Portal>
        <T.Content side={cote} sideOffset={6}
          className={cn("z-50 max-w-xs rounded-xl bg-marine px-3 py-2 text-xs leading-relaxed text-white shadow-levee animate-in fade-in-0 zoom-in-95 dark:bg-slate-800", className)}>
          {contenu}
          <T.Arrow className="fill-marine dark:fill-slate-800" />
        </T.Content>
      </T.Portal>
    </T.Root>
  );
}

// ------------------------------------------------------------------ onglets
export const Tabs = TabsPrimitive.Root;
export function TabsList({ className, ...p }: React.ComponentProps<typeof TabsPrimitive.List>) {
  return <TabsPrimitive.List className={cn("inline-flex items-center gap-1 rounded-xl bg-survol p-1", className)} {...p} />;
}
export function TabsTrigger({ className, ...p }: React.ComponentProps<typeof TabsPrimitive.Trigger>) {
  return (
    <TabsPrimitive.Trigger
      className={cn("rounded-lg px-3 py-1.5 text-xs font-medium text-attenue transition-colors data-[state=active]:bg-carte data-[state=active]:text-encre data-[state=active]:shadow-sm", className)}
      {...p}
    />
  );
}
export const TabsContent = TabsPrimitive.Content;

// ------------------------------------------------------------------ bulle (popover)
export function Bulle({ declencheur, children, className }: { declencheur: React.ReactNode; children: React.ReactNode; className?: string }) {
  return (
    <P.Root>
      <P.Trigger asChild>{declencheur}</P.Trigger>
      <P.Portal>
        <P.Content sideOffset={6} className={cn("z-50 w-[420px] max-w-[90vw] rounded-2xl border border-ligne bg-carte p-4 text-sm shadow-levee animate-in fade-in-0 zoom-in-95", className)}>
          {children}
        </P.Content>
      </P.Portal>
    </P.Root>
  );
}

// ------------------------------------------------------------------ états vides et erreurs
export function EtatVide({ titre, texte, className }: { titre: string; texte?: string; className?: string }) {
  return (
    <div className={cn("flex flex-col items-center justify-center rounded-2xl border border-dashed border-ligne px-6 py-12 text-center", className)}>
      <Inbox className="mb-3 h-8 w-8 text-gris" />
      <p className="text-sm font-medium text-encre">{titre}</p>
      {texte && <p className="mt-1 max-w-sm text-xs text-attenue">{texte}</p>}
    </div>
  );
}

export function EtatErreur({ message, className }: { message: string; className?: string }) {
  return (
    <div className={cn("flex items-start gap-3 rounded-2xl border border-rouge/30 bg-rouge/5 px-5 py-4 text-sm", className)}>
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-rouge" />
      <div>
        <p className="font-medium text-rouge">Impossible de charger les données</p>
        <p className="mt-0.5 text-xs text-attenue">{message}</p>
      </div>
    </div>
  );
}
