"""Base SQLite (SQLAlchemy Core) : schéma de la section 5.2 + tables applicatives."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pandas as pd
from sqlalchemy import (
    Boolean,
    Column,
    Date,
    Float,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    event,
    text,
)
from sqlalchemy.engine import Engine

from . import config

metadata = MetaData()

entreprises = Table(
    "entreprises", metadata,
    Column("id", Integer, primary_key=True),
    Column("matricule_fiscal", String, unique=True, nullable=False),
    Column("raison_sociale", String, nullable=False),
    Column("forme_juridique", String),
    Column("date_creation", Date),
    Column("gouvernorat", String, index=True),
    Column("delegation", String),
    Column("adresse_id", Integer, ForeignKey("adresses.id")),
    Column("secteur_nat_code", String, index=True),
    Column("secteur_libelle", String),
    Column("secteur_groupe", String, index=True),  # famille de simulation (marges, produits)
    Column("regime_fiscal", String),
    Column("statut_export", String),
    Column("capital", Float),
    Column("effectif", Integer),
    Column("statut_oea", Boolean),
    Column("bureau_controle", String),
    Column("statut", String),
    Column("date_radiation", Date, nullable=True),
)

personnes = Table(
    "personnes", metadata,
    Column("id", Integer, primary_key=True),
    Column("nom", String),
    Column("prenom", String),
)

roles = Table(
    "roles", metadata,
    Column("entreprise_id", Integer, ForeignKey("entreprises.id"), index=True),
    Column("personne_id", Integer, ForeignKey("personnes.id"), index=True),
    Column("role", String),
)

adresses = Table(
    "adresses", metadata,
    Column("id", Integer, primary_key=True),
    Column("adresse", String),
    Column("gouvernorat", String),
)

declarations_douane = Table(
    "declarations_douane", metadata,
    Column("id", Integer, primary_key=True),
    Column("entreprise_id", Integer, ForeignKey("entreprises.id"), index=True),
    Column("numero_declaration", String, index=True),
    Column("date", Date, index=True),
    Column("bureau", String),
    Column("flux", String),
    Column("regime", String),
    Column("code_sh", String, index=True),
    Column("designation", String),
    Column("pays_origine", String),
    Column("fournisseur_etranger", String),
    Column("quantite", Float),
    Column("unite", String),
    Column("poids_kg", Float),
    Column("valeur_fob", Float),
    Column("fret", Float),
    Column("assurance", Float),
    Column("valeur_cif_dt", Float),
    Column("taux_droits", Float),
    Column("droits_douane", Float),
    Column("base_tva", Float),
    Column("tva_import", Float),
    Column("avance_impot_import", Float),
    Column("est_equipement", Boolean),
    Column("circuit", String),
    Column("resultat_controle", String, nullable=True),
)

declarations_tva = Table(
    "declarations_tva", metadata,
    Column("entreprise_id", Integer, ForeignKey("entreprises.id"), index=True),
    Column("annee", Integer),
    Column("mois", Integer),
    Column("date_depot", Date, nullable=True),
    Column("deposee", Boolean),
    Column("ca_local_ht", Float),
    Column("ca_export_ht", Float),
    Column("tva_collectee", Float),
    Column("tva_deductible_import", Float),
    Column("tva_deductible_local", Float),
    Column("tva_deductible_immobilisations", Float),
    Column("credit_reporte", Float),
    Column("tva_due", Float),
    Column("remboursement_demande", Float),
)

declarations_annuelles = Table(
    "declarations_annuelles", metadata,
    Column("entreprise_id", Integer, ForeignKey("entreprises.id"), index=True),
    Column("annee", Integer),
    Column("chiffre_affaires", Float),
    Column("achats_marchandises", Float),
    Column("achats_matieres", Float),
    Column("stock_initial", Float),
    Column("stock_final", Float),
    Column("marge_brute", Float),
    Column("charges_personnel", Float),
    Column("autres_charges", Float),
    Column("resultat_comptable", Float),
    Column("resultat_fiscal", Float),
    Column("impot_du", Float),
    Column("immobilisations_acquises", Float),
)

retenues_source = Table(
    "retenues_source", metadata,
    Column("id", Integer, primary_key=True),
    Column("payeur_id", Integer, ForeignKey("entreprises.id"), index=True),
    Column("beneficiaire_id", Integer, ForeignKey("entreprises.id"), index=True),
    Column("date", Date),
    Column("montant_brut", Float),
    Column("taux", Float),
    Column("montant_retenu", Float),
)

factures_electroniques = Table(
    "factures_electroniques", metadata,
    Column("id", Integer, primary_key=True),
    Column("emetteur_id", Integer, ForeignKey("entreprises.id"), index=True),
    Column("client_id", Integer, ForeignKey("entreprises.id"), index=True),
    Column("date", Date),
    Column("montant_ht", Float),
    Column("tva", Float),
    Column("code_sh_principal", String, nullable=True),
)

encaissements_bancaires = Table(
    "encaissements_bancaires", metadata,
    Column("entreprise_id", Integer, ForeignKey("entreprises.id"), index=True),
    Column("annee", Integer),
    Column("mois", Integer),
    Column("total_encaissements", Float),
)

controles_historiques = Table(
    "controles_historiques", metadata,
    Column("id", Integer, primary_key=True),
    Column("entreprise_id", Integer, ForeignKey("entreprises.id"), index=True),
    Column("annee_controlee", Integer),
    Column("date_controle", Date),
    Column("type", String),
    Column("origine_selection", String),
    Column("redressement", Boolean),
    Column("montant_redresse", Float),
    Column("motif_categorie", String, nullable=True),
)

prix_reference = Table(
    "prix_reference", metadata,
    Column("code_sh", String, index=True),
    Column("pays_origine", String),
    Column("prix_unitaire_median", Float),
    Column("p10", Float),
    Column("p90", Float),
    Column("nb_obs", Integer),
)

parametres = Table(
    "parametres", metadata,
    Column("cle", String, primary_key=True),
    Column("valeur", Float),
    Column("source", String),
    Column("a_verifier", Boolean),
)

secteurs_reference = Table(  # référentiel sectoriel simulé (monographies sectorielles fictives)
    "secteurs_reference", metadata,
    Column("secteur_groupe", String, primary_key=True),
    Column("libelle", String),
    Column("type", String),  # negoce | industrie | services
    Column("marge_mediane", Float),
    Column("marge_sd", Float),
    Column("habituellement_crediteur", Boolean),
    Column("ventes_biens", Boolean),  # False : prestations de services (pas d'exportation en douane)
)

# --- Tables applicatives -------------------------------------------------------
scores = Table(
    "scores", metadata,
    Column("entreprise_id", Integer, ForeignKey("entreprises.id"), primary_key=True),
    Column("score", Float),
    Column("categorie", String, index=True),
    Column("probabilite", Float),
    Column("score_anomalie", Float),
    Column("force_indices", Float),
    Column("montant_en_jeu", Float),
    Column("priorite", Float, index=True),
    Column("rang", Integer),
    Column("regles_declenchees", String),  # JSON : ["A1", "A3", ...]
    Column("premiere_raison", Text),
    Column("details", Text),  # JSON : indices, neutralisations, shap
    Column("facilitation", Boolean),
    Column("score_regles", Float),
    Column("calcule_le", String),
)

dossiers = Table(
    "dossiers", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("entreprise_id", Integer, ForeignKey("entreprises.id"), index=True),
    Column("statut", String),  # brouillon | valide
    Column("agent", String),
    Column("contenu", Text),  # JSON du pré-dossier
    Column("modele_llm", String),
    Column("duree_generation_s", Float),
    Column("cree_le", String),
    Column("modifie_le", String),
    Column("valide_le", String, nullable=True),
)

resultats_controle = Table(
    "resultats_controle", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("entreprise_id", Integer, ForeignKey("entreprises.id"), index=True),
    Column("redressement", Boolean),
    Column("montant", Float),
    Column("commentaire", Text),
    Column("agent", String),
    Column("saisi_le", String),
)

journal_audit = Table(
    "journal_audit", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("horodatage", String),
    Column("agent", String),
    Column("action", String),
    Column("objet", String),
    Column("details", Text),
)

metriques = Table(
    "metriques", metadata,
    Column("cle", String, primary_key=True),
    Column("valeur", Text),  # JSON
    Column("calcule_le", String),
)


def _sqlite_pragmas(dbapi_connection, _record) -> None:
    cur = dbapi_connection.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA synchronous=NORMAL")
    cur.execute("PRAGMA foreign_keys=OFF")
    cur.close()


def make_engine(db_path: Path | None = None) -> Engine:
    path = Path(db_path or config.DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{path.as_posix()}", future=True, connect_args={"check_same_thread": False})
    event.listen(engine, "connect", _sqlite_pragmas)
    return engine


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    return make_engine()


def create_schema(engine: Engine, drop: bool = False) -> None:
    if drop:
        metadata.drop_all(engine)
    metadata.create_all(engine)


def read_sql(query: str, params: dict | None = None, engine: Engine | None = None) -> pd.DataFrame:
    with (engine or get_engine()).connect() as conn:
        return pd.read_sql(text(query), conn, params=params or {})


def db_status(engine: Engine | None = None) -> dict:
    engine = engine or get_engine()
    if not Path(config.DB_PATH).exists() and engine is get_engine():
        return {"status": "absente", "message": "Base non générée : lancer scripts\\reset_demo.ps1"}
    try:
        with engine.connect() as conn:
            n = conn.execute(text("SELECT COUNT(*) FROM entreprises")).scalar()
            n_scores = conn.execute(text("SELECT COUNT(*) FROM scores")).scalar()
        return {"status": "ok" if n else "vide", "entreprises": int(n or 0), "scores": int(n_scores or 0)}
    except Exception as exc:  # noqa: BLE001
        return {"status": "erreur", "message": str(exc)}
