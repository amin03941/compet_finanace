/** Client de l'API RASD 360 (FastAPI). */
export const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

export class ErreurApi extends Error {
  constructor(public statut: number, message: string) {
    super(message);
  }
}

export async function api<T>(chemin: string, init?: RequestInit): Promise<T> {
  let r: Response;
  try {
    r = await fetch(`${API_URL}${chemin}`, { ...init, headers: { "Content-Type": "application/json", ...(init?.headers || {}) } });
  } catch {
    throw new ErreurApi(0, "L'API RASD 360 ne répond pas. Lancer scripts\\run_backend.ps1.");
  }
  if (!r.ok) {
    let msg = `Erreur ${r.status}`;
    try {
      const j = await r.json();
      msg = j.detail || msg;
    } catch {}
    throw new ErreurApi(r.status, msg);
  }
  return r.json() as Promise<T>;
}

export const fetcher = <T,>(chemin: string) => api<T>(chemin);

/** Lit un flux NDJSON (streaming du chat et de la génération de dossier). */
export async function* fluxNdjson<T>(chemin: string, corps: unknown, signal?: AbortSignal): AsyncGenerator<T> {
  let r: Response;
  try {
    r = await fetch(`${API_URL}${chemin}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(corps), signal });
  } catch (e) {
    if ((e as Error).name === "AbortError") return;
    throw new ErreurApi(0, "L'API RASD 360 ne répond pas.");
  }
  if (!r.ok || !r.body) throw new ErreurApi(r.status, `Erreur ${r.status}`);
  const lecteur = r.body.getReader();
  const dec = new TextDecoder();
  let tampon = "";
  while (true) {
    const { value, done } = await lecteur.read();
    if (done) break;
    tampon += dec.decode(value, { stream: true });
    let i;
    while ((i = tampon.indexOf("\n")) >= 0) {
      const ligne = tampon.slice(0, i).trim();
      tampon = tampon.slice(i + 1);
      if (ligne) yield JSON.parse(ligne) as T;
    }
  }
  if (tampon.trim()) yield JSON.parse(tampon) as T;
}

// ------------------------------------------------------------------ types
export type Categorie = "rouge" | "orange" | "gris" | "vert";

export interface LigneCiblage {
  id: number;
  rang: number;
  raison_sociale: string;
  matricule_fiscal: string;
  secteur: string;
  secteur_groupe: string;
  gouvernorat: string;
  score: number;
  categorie: Categorie;
  categorie_libelle: string;
  probabilite: number;
  montant_en_jeu: number;
  priorite: number;
  regles: string[];
  premiere_raison: string;
}

export interface Stats {
  kpis: {
    entreprises_analysees: number;
    alertes_rouges: number;
    demandes_justification: number;
    montant_en_jeu: number;
    precision_ciblage: number | null;
    precision_hasard: number | null;
    gain_vs_hasard: number | null;
  };
  categories: { code: Categorie; libelle: string; entreprises: number }[];
  distribution_scores: { tranche: string; entreprises: number }[];
  montant_par_indice: { code: string; libelle: string; niveau: string; entreprises: number; montant: number }[];
  alertes_par_gouvernorat: { gouvernorat: string; rouges: number; oranges: number; entreprises: number }[];
  evolution_mensuelle: { periode: string; entreprises: number; dont_rouges: number }[];
  top5: LigneCiblage[];
  calcule_le: string | null;
}

export interface Indice {
  code: string;
  niveau: "A" | "B" | "C";
  libelle: string;
  formule: string;
  condition: string;
  valeur: number | null;
  seuil: number | null;
  declenchee: boolean;
  force: string;
  montant_en_jeu: number;
  annee: number;
  annees: number[];
  phrase: string | null;
}

export interface Neutralisation {
  cle: string;
  libelle: string;
  statut: "verifie" | "sans_objet" | "manquant";
  detail: string;
}

export interface EtapeCascade {
  libelle: string;
  valeur: number;
  type: "base" | "ia" | "regle" | "anomalie" | "total";
  code?: string;
}

export interface NoeudReseau {
  id: string;
  type: "entreprise" | "personne" | "adresse";
  label: string;
  entreprise_id?: number;
  centrale?: boolean;
  radiee?: boolean;
  redressee?: boolean;
  defaillante?: boolean;
  relation?: string | null;
}

export interface Fiche {
  identite: {
    id: number;
    raison_sociale: string;
    matricule_fiscal: string;
    forme_juridique: string;
    date_creation: string;
    gouvernorat: string;
    delegation: string;
    adresse: string | null;
    secteur: string;
    secteur_nat: string;
    regime_fiscal: string;
    statut_export: string;
    capital: number;
    effectif: number;
    statut_oea: boolean;
    bureau_controle: string;
    statut: string;
    dirigeants: { prenom: string; nom: string; role: string }[];
  };
  score: {
    score: number;
    categorie: Categorie;
    categorie_libelle: string;
    raison_categorie: string;
    probabilite: number;
    anomalie: number;
    force_indices: number;
    montant_en_jeu: number;
    priorite: number;
    rang: number;
    total: number;
  } | null;
  indices: Indice[];
  neutralisations: Neutralisation[];
  cascade: EtapeCascade[];
  facilitation: { criteres: { libelle: string; ok: boolean }[]; eligible: boolean; candidat_oea: boolean; candidat_remboursement_rapide: boolean } | null;
  series: Record<string, number | string>[];
  reseau: { nodes: NoeudReseau[]; edges: { source: string; target: string; label: string; circuit?: boolean }[] };
  donnees_brutes: Record<string, { titre: string; lignes: Record<string, string | number | null>[] }>;
  historique_controles: { annee_controlee: number; date_controle: string; type: string; origine_selection: string; redressement: boolean; montant_redresse: number }[];
  resultats_saisis: { redressement: boolean; montant: number; commentaire: string; agent: string; saisi_le: string }[];
}

export interface Preuves {
  regle: { code: string; niveau: string; libelle: string; formule: string; condition: string };
  source: string;
  colonnes: string[];
  lignes: Record<string, string | number | null>[];
  total: number;
}

export interface SourceRag {
  n: number;
  id: string;
  source_id: string;
  document: string;
  article: string | number | null;
  section: string | null;
  page: number | null;
  locator: string | null;
  chunk_type: string;
  extrait: string;
  extrait_envoye?: string;
  score: number;
  recherche_directe: boolean;
}

export interface LigneEcart {
  cle: string;
  libelle: string;
  montant: number;
  montant_affiche: string;
  formule: string;
  source: string;
  a_verifier?: boolean;
  indicatif?: boolean;
  total?: boolean;
}

export interface ArticleDossier {
  id: string;
  document: string;
  source_id: string;
  article: string;
  section: string;
  page: number;
  locator: string;
  motif: string;
  extrait: string;
  edition: string | null;
  indices: string[];
}

export interface Dossier {
  id: number;
  entreprise_id?: number;
  statut: "brouillon" | "valide";
  agent?: string;
  valide_le?: string | null;
  contenu: {
    entete: {
      raison_sociale: string;
      matricule_fiscal: string;
      forme_juridique: string;
      adresse: string | null;
      gouvernorat: string;
      secteur: string;
      periode: string;
      score: number;
      categorie: Categorie;
      categorie_libelle: string;
      montant_en_jeu: number;
      agent: string;
      statut: string;
      date: string;
      reference?: string;
      entreprise_id: number;
    };
    synthese: string[];
    ecarts: { annee: number; lignes: LigneEcart[]; total_tva: number; total_estime: number; hypotheses: string[]; mention: string };
    indices: { code: string; niveau: string; libelle: string; phrase: string; montant_en_jeu: number }[];
    articles: ArticleDossier[];
    documents: string[];
    lettre: { objet: string; corps: string; delai_jours: number; destinataire: string };
    avertissements: string[];
    generation: { source: string; erreur: string | null; duree_s: number; modele: string | null };
  };
}
