"use client";
import { ArrowRight, Database, FileText, Landmark, MessagesSquare, Network, Scale, ShieldCheck } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EnTetePage } from "@/components/risque/elements";
import { useFilAriane } from "@/components/shell/shell";

const SOURCES = [
  { nom: "Douane", detail: "Déclarations en détail (SINDA 2)", icone: Landmark },
  { nom: "Impôts", detail: "TVA mensuelle, déclarations annuelles", icone: Scale },
  { nom: "TEJ", detail: "Retenues à la source des clients", icone: FileText },
  { nom: "El Fatoora", detail: "Factures électroniques", icone: FileText },
  { nom: "Banque", detail: "Encaissements agrégés", icone: Database },
];

function Boite({ titre, lignes, accent }: { titre: string; lignes: string[]; accent?: string }) {
  return (
    <div className={`rounded-2xl border p-4 ${accent || "border-ligne bg-carte"}`}>
      <p className="text-sm font-semibold text-marine dark:text-encre">{titre}</p>
      <ul className="mt-1.5 space-y-0.5 text-xs text-attenue">{lignes.map((l) => <li key={l}>{l}</li>)}</ul>
    </div>
  );
}

export default function APropos() {
  useFilAriane([{ libelle: "À propos" }]);
  return (
    <div className="space-y-5">
      <EnTetePage titre="À propos de RASD 360" sousTitre="رصد — veille, surveillance. Radar fiscal et douanier : impôts et douane ensemble, sur toute l'année." />

      <Card className="bg-marine text-white">
        <CardContent className="p-7">
          <p className="text-xl font-medium leading-relaxed">
            « La douane a déjà une IA qui contrôle chaque déclaration. Personne ne regarde l&apos;entreprise en entier, impôts et douane ensemble,
            sur toute l&apos;année. C&apos;est là que la fraude se cache. »
          </p>
          <div className="mt-5 grid grid-cols-4 gap-4 text-sm text-sky-100/80">
            <p><b className="text-white">Données cloisonnées :</b> chaque administration voit sa partie ; les échanges se font au cas par cas.</p>
            <p><b className="text-white">Peu d&apos;agents :</b> le choix des contrôles repose sur l&apos;expérience ou des listes.</p>
            <p><b className="text-white">Des jours de préparation :</b> rassembler, calculer, trouver les articles, rédiger.</p>
            <p><b className="text-white">Des règles dispersées :</b> plusieurs codes, difficiles à consulter pour tous.</p>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Architecture</CardTitle></CardHeader>
        <CardContent className="pt-4">
          <div className="grid grid-cols-[1fr_auto_1.3fr_auto_1fr] items-center gap-3">
            <div className="space-y-2">
              {SOURCES.map(({ nom, detail, icone: I }) => (
                <div key={nom} className="flex items-center gap-2.5 rounded-xl border border-ligne bg-carte px-3 py-2">
                  <I className="h-4 w-4 text-action" /><div><p className="text-sm font-medium">{nom}</p><p className="text-[11px] text-attenue">{detail}</p></div>
                </div>
              ))}
              <p className="text-center text-[11px] text-attenue">Base SQLite fictive (seed 42)</p>
            </div>
            <ArrowRight className="h-5 w-5 text-gris" />
            <div className="space-y-3">
              <Boite titre="Moteur de ciblage (T20)" accent="border-action/30 bg-action/5"
                lignes={["Neutralisation des explications légitimes", "14 règles A/B/C chiffrées et testées", "LightGBM calibré + Isolation Forest par secteur", "SHAP : explication de chaque score"]} />
              <Boite titre="Dossier de contrôle (T3)" lignes={["calc.py : montants déterministes", "Articles retrouvés et vérifiés par identifiant", "Rédaction par LLM local, sortie JSON validée", "Export PDF, validation par l'agent"]} />
              <Boite titre="Assistant réglementaire (T9)" lignes={["Recherche hybride bge-m3 + BM25 (fusion RRF)", "Index FAISS de 4 523 extraits de textes", "Qwen3 8B local (Ollama), citations vérifiées"]} />
            </div>
            <ArrowRight className="h-5 w-5 text-gris" />
            <div className="space-y-2">
              {[["Service de programmation", "Liste priorisée, preuves, montants", Network], ["Vérificateur", "Pré-dossier en quelques secondes", FileText],
                ["Contribuable et agent", "Réponses sourcées FR / AR / dialecte", MessagesSquare], ["Direction", "Facilitation : OEA, remboursement rapide", ShieldCheck]].map(([t, d, I]) => {
                const Icone = I as typeof Network;
                return (
                  <div key={t as string} className="flex items-center gap-2.5 rounded-xl border border-ligne bg-carte px-3 py-2.5">
                    <Icone className="h-4 w-4 text-vert" /><div><p className="text-sm font-medium">{t as string}</p><p className="text-[11px] text-attenue">{d as string}</p></div>
                  </div>
                );
              })}
            </div>
          </div>
          <p className="mt-4 text-xs text-attenue">Tout tourne en local : FastAPI (Python 3.11), SQLite, Next.js 14 ; aucun envoi de données vers un service externe.</p>
        </CardContent>
      </Card>

      <div className="grid grid-cols-2 gap-5">
        <Card>
          <CardHeader><CardTitle>Données fictives</CardTitle></CardHeader>
          <CardContent className="space-y-2 pt-3 text-[13px] leading-relaxed text-attenue">
            <p>2 000 entreprises inventées sur 2023–2025 (secteurs de la nomenclature NAT 2009), environ 61 000 lignes de déclarations en douane, 71 000 déclarations
              de TVA mensuelles, 6 000 déclarations annuelles, 146 000 factures électroniques et des certificats de retenue à la source, cohérents comptablement.</p>
            <p>Une vérité terrain cachée : 72 % d&apos;honnêtes, 17 % d&apos;honnêtes avec un écart brut expliqué (pièges), 11 % de fraudeurs répartis sur 8 schémas.
              Environ 600 contrôles passés aux étiquettes imparfaites servent à l&apos;apprentissage.</p>
            <p>Noms, matricules et personnes sont générés ; aucune donnée réelle, aucun numéro d&apos;identité (loi organique 2004-63, INPDP).</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>Modèles et ressources pré-existantes</CardTitle></CardHeader>
          <CardContent className="pt-3 text-[13px] text-attenue">
            <ul className="space-y-1.5">
              <li><b className="text-encre">Index RAG</b> construit avant le hackathon par l&apos;équipe (filtré et complété pendant l&apos;événement) : CDPF 2024, Code des douanes 2016,
                Code de l&apos;enregistrement et du timbre 2025, décret OEA 2018-612, loi 2017-8, décrets 2017-418 et 2017-419.</li>
              <li><b className="text-encre">BAAI/bge-m3</b> (embeddings, CPU) · <b className="text-encre">Qwen3 8B</b> via Ollama (rédaction, local)</li>
              <li><b className="text-encre">LightGBM, scikit-learn, SHAP, FAISS, NetworkX, rank-bm25</b>, FastAPI, ReportLab</li>
              <li><b className="text-encre">Next.js, Tailwind, Radix UI, Recharts, framer-motion, react-force-graph</b></li>
            </ul>
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-2 gap-5">
        <Card>
          <CardHeader><CardTitle>Limites</CardTitle></CardHeader>
          <CardContent className="pt-3">
            <ul className="list-disc space-y-1.5 pl-5 text-[13px] text-attenue">
              <li>Données synthétiques : les performances mesurées valent pour ce jeu fictif et doivent être revalidées sur données réelles.</li>
              <li>Le Code de la TVA et le Code de l&apos;IRPP et de l&apos;IS ne sont pas encore indexés : les taux correspondants sont des paramètres « à vérifier ».</li>
              <li>Le Code des douanes indexé est l&apos;édition 2016.</li>
              <li>Le LLM local (8 milliards de paramètres) peut mal formuler : citations et chiffres sont vérifiés automatiquement et l&apos;agent valide toujours.</li>
              <li>Aucune sanction automatique : le score est une aide à la programmation, dans le respect de la procédure contradictoire.</li>
            </ul>
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>Perspectives</CardTitle></CardHeader>
          <CardContent className="pt-3">
            <ul className="list-disc space-y-1.5 pl-5 text-[13px] text-attenue">
              <li>Entraînement sur l&apos;historique réel des contrôles de la DGI, avec suivi des performances et de l&apos;équité.</li>
              <li>Connexion aux systèmes existants : SINDA 2 (douane), TEJ, El Fatoora ; on ne remplace rien, on se branche.</li>
              <li>Compléter l&apos;index : Code de la TVA, Code de l&apos;IRPP et de l&apos;IS, Code des douanes à jour.</li>
              <li>Brancher le moteur réglementaire derrière El Diwani, l&apos;assistant de la douane.</li>
              <li>Hébergement souverain, gestion des habilitations et journal d&apos;audit centralisé.</li>
            </ul>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
