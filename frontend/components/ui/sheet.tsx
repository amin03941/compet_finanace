"use client";
import * as React from "react";
import * as D from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";

/** Tiroir latéral (preuves, sources). */
export function Tiroir({ ouvert, onChange, titre, description, children, largeur = "max-w-3xl" }: {
  ouvert: boolean; onChange: (v: boolean) => void; titre: React.ReactNode; description?: React.ReactNode;
  children: React.ReactNode; largeur?: string;
}) {
  return (
    <D.Root open={ouvert} onOpenChange={onChange}>
      <D.Portal>
        <D.Overlay className="fixed inset-0 z-40 bg-slate-950/40 backdrop-blur-[2px] data-[state=open]:animate-in data-[state=open]:fade-in-0" />
        <D.Content className={cn("fixed inset-y-0 right-0 z-50 flex w-full flex-col border-l border-ligne bg-carte shadow-levee duration-200 data-[state=open]:animate-in data-[state=open]:slide-in-from-right", largeur)}>
          <div className="flex items-start justify-between gap-4 border-b border-ligne px-6 py-5">
            <div>
              <D.Title className="text-base font-semibold text-marine dark:text-encre">{titre}</D.Title>
              {description ? <D.Description className="mt-1 text-xs text-attenue">{description}</D.Description> : <D.Description className="sr-only">Détail</D.Description>}
            </div>
            <D.Close className="rounded-lg p-1.5 text-attenue hover:bg-survol" aria-label="Fermer"><X className="h-4 w-4" /></D.Close>
          </div>
          <div className="defilement flex-1 overflow-y-auto px-6 py-5">{children}</div>
        </D.Content>
      </D.Portal>
    </D.Root>
  );
}

/** Boîte de dialogue centrée. */
export function Dialogue({ ouvert, onChange, titre, children }: { ouvert: boolean; onChange: (v: boolean) => void; titre: string; children: React.ReactNode }) {
  return (
    <D.Root open={ouvert} onOpenChange={onChange}>
      <D.Portal>
        <D.Overlay className="fixed inset-0 z-40 bg-slate-950/40 data-[state=open]:animate-in data-[state=open]:fade-in-0" />
        <D.Content className="fixed left-1/2 top-1/2 z-50 w-full max-w-md -translate-x-1/2 -translate-y-1/2 rounded-2xl border border-ligne bg-carte p-6 shadow-levee data-[state=open]:animate-in data-[state=open]:zoom-in-95">
          <D.Title className="mb-4 text-base font-semibold text-marine dark:text-encre">{titre}</D.Title>
          <D.Description className="sr-only">{titre}</D.Description>
          {children}
          <D.Close className="absolute right-4 top-4 rounded-lg p-1.5 text-attenue hover:bg-survol" aria-label="Fermer"><X className="h-4 w-4" /></D.Close>
        </D.Content>
      </D.Portal>
    </D.Root>
  );
}
