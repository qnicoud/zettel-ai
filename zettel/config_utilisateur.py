"""Fichier de configuration utilisateur : ~/.config/zettel-ai/config.toml.

Ses valeurs remplacent celles de `zettel/config.py`, sauf les noms propres et les corrections
de transcription, qui s'y AJOUTENT. Toute clé inconnue ou mal typée arrête le programme avec
un message clair (une faute de frappe ne doit pas être ignorée en silence).
Modèle commenté : config.exemple.toml (installé dans /usr/share/doc/zettel-ai/).
"""

import os
import sys
import tomllib
from collections.abc import Callable
from pathlib import Path
from typing import Any

from zettel import config as cfg


class ErreurConfig(ValueError):
    pass


# --- Convertisseurs : (nom complet de la clé, valeur TOML) -> valeur de config ---------------
def _texte(nom: str, v: Any) -> str:
    if not isinstance(v, str):
        raise ErreurConfig(f"{nom} : texte attendu")
    if not v.strip():
        raise ErreurConfig(f"{nom} : ne doit pas être vide")
    return v.strip()


def _booleen(nom: str, v: Any) -> bool:
    if not isinstance(v, bool):
        raise ErreurConfig(f"{nom} : booléen attendu (true ou false)")
    return v


def _entier_positif(nom: str, v: Any) -> int:
    if isinstance(v, bool) or not isinstance(v, int):
        raise ErreurConfig(f"{nom} : entier attendu")
    if v <= 0:
        raise ErreurConfig(f"{nom} : doit être positif")
    return v


def _temperature(nom: str, v: Any) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise ErreurConfig(f"{nom} : nombre attendu")
    if not 0 <= v <= 2:
        raise ErreurConfig(f"{nom} : doit être entre 0 et 2")
    return float(v)


def _url(nom: str, v: Any) -> str:
    v = _texte(nom, v)
    if not v.startswith(("http://", "https://")):
        raise ErreurConfig(f"{nom} : doit commencer par http:// ou https://")
    return v.rstrip("/")


def _chemin(nom: str, v: Any) -> Path:
    return Path(_texte(nom, v)).expanduser()


def _chemins(nom: str, v: Any) -> tuple[Path, ...]:
    if not isinstance(v, list) or not v:
        raise ErreurConfig(f"{nom} : liste non vide de chemins attendue, ex. [\"~/a.md\"]")
    return tuple(_chemin(f"{nom}[{i}]", x) for i, x in enumerate(v))


def _liste(nom: str, v: Any) -> tuple[str, ...]:
    if not isinstance(v, list):
        raise ErreurConfig(f"{nom} : liste de textes attendue, ex. [\"a\", \"b\"]")
    return tuple(_texte(f"{nom}[{i}]", x) for i, x in enumerate(v))


def _table(nom: str, v: Any) -> dict[str, str]:
    if not isinstance(v, dict):
        raise ErreurConfig(f"{nom} : table attendue")
    return {_texte(nom, k): _texte(f"{nom}.{k}", x) for k, x in v.items()}


# --- Fusion avec la valeur intégrée ----------------------------------------------------------
def _remplacer(defaut: Any, nouveau: Any) -> Any:
    return nouveau


def _ajouter_liste(defaut: tuple[str, ...], nouveau: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys((*defaut, *nouveau)))      # ordre gardé, sans doublon


def _ajouter_table(defaut: dict[str, str], nouveau: dict[str, str]) -> dict[str, str]:
    return {**defaut, **nouveau}


Convertir = Callable[[str, Any], Any]
Fusionner = Callable[[Any, Any], Any]

# (section, clé) -> (attribut de zettel.config, conversion, fusion avec la valeur intégrée)
SCHEMA: dict[tuple[str, str], tuple[str, Convertir, Fusionner]] = {
    ("chemins", "journaux"): ("JOURNAUX", _chemins, _remplacer),
    ("chemins", "base_org_roam"): ("ROAM_DIR", _chemin, _remplacer),
    ("chemins", "dossier_journalier"): ("DAILY_DIR", _texte, _remplacer),
    ("ollama", "url"): ("OLLAMA_BASE", _url, _remplacer),
    ("ollama", "modele"): ("MODEL", _texte, _remplacer),
    ("ollama", "modele_embeddings"): ("EMBED_MODEL", _texte, _remplacer),
    ("ollama", "contexte"): ("NUM_CTX", _entier_positif, _remplacer),
    ("ollama", "temperature"): ("TEMPERATURE", _temperature, _remplacer),
    ("ollama", "think"): ("THINK", _booleen, _remplacer),
    ("notes", "notes_proches"): ("TOP_K", _entier_positif, _remplacer),
    ("notes", "max_liens"): ("MAX_LIENS", _entier_positif, _remplacer),
    ("notes", "verbes_action"): ("VERBES_ACTION", _liste, _ajouter_liste),
    ("transcription", "noms_propres"): ("NOMS_PROPRES", _liste, _ajouter_liste),
    ("transcription", "corrections"): ("CORRECTIONS_TRANSCRIPTION", _table, _ajouter_table),
    ("todo", "mots_ouverts"): ("TODO_OUVERTS", _liste, _remplacer),
    ("todo", "mot_fait"): ("MOT_FAIT", _texte, _remplacer),
    ("todo", "mot_abandon"): ("MOT_ABANDON", _texte, _remplacer),
    ("todo", "mot_en_cours"): ("MOT_EN_COURS", _texte, _remplacer),
    ("git", "branche_principale"): ("BASE_BRANCH", _texte, _remplacer),
    ("git", "branche_relecture"): ("REVIEW_BRANCH", _texte, _remplacer),
    ("hyprwhspr", "gerer"): ("TOGGLE_WHISPER", _booleen, _remplacer),
    ("hyprwhspr", "script"): ("WHISPER_CTL", _texte, _remplacer),
    ("notification", "activer"): ("NOTIFIER", _booleen, _remplacer),
    ("notification", "terminal"): ("TERMINAL", _texte, _remplacer),
}
SECTIONS = sorted({s for s, _ in SCHEMA})


def chemin_config() -> Path:
    """$ZETTEL_AI_CONFIG, sinon $XDG_CONFIG_HOME/zettel-ai/config.toml (~/.config par défaut)."""
    explicite = os.environ.get("ZETTEL_AI_CONFIG")
    if explicite:
        return Path(explicite).expanduser()
    base = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    return Path(base) / "zettel-ai" / "config.toml"


def _verifier_cles(donnees: dict[str, Any]) -> None:
    for section, contenu in donnees.items():
        if section not in SECTIONS:
            raise ErreurConfig(f"« {section} » : section (ou clé hors section) inconnue ; "
                               f"sections possibles : {', '.join(SECTIONS)}")
        if not isinstance(contenu, dict):
            raise ErreurConfig(f"« {section} » doit être une section [{section}]")
        for cle in contenu:
            if (section, cle) not in SCHEMA:
                possibles = ", ".join(c for s, c in SCHEMA if s == section)
                raise ErreurConfig(f"{section}.{cle} : clé inconnue ; possibles : {possibles}")


def lire(chemin: Path) -> dict[str, Any]:
    """Valeurs finales {ATTRIBUT: valeur} définies par le fichier ({} s'il n'existe pas).
    Ne modifie pas zettel.config."""
    if not chemin.is_file():
        return {}
    try:
        donnees = tomllib.loads(chemin.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as e:
        raise ErreurConfig(f"syntaxe TOML invalide : {e}") from e
    _verifier_cles(donnees)
    valeurs = {}
    for section, contenu in donnees.items():
        for cle, brut in contenu.items():
            attribut, convertir, fusionner = SCHEMA[(section, cle)]
            valeurs[attribut] = fusionner(getattr(cfg, attribut),
                                          convertir(f"{section}.{cle}", brut))
    return valeurs


def appliquer(valeurs: dict[str, Any]) -> None:
    for attribut, valeur in valeurs.items():
        setattr(cfg, attribut, valeur)


def charger() -> None:
    """Point d'entrée des commandes : lit et applique, ou s'arrête avec un message clair."""
    chemin = chemin_config()
    try:
        appliquer(lire(chemin))
    except (ErreurConfig, OSError) as e:
        sys.exit(f"Configuration {chemin} : {e}")
