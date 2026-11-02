"""Tri des sujets extraits par Qwen : une ACTION (« Migrer l'ingress controller… ») n'est pas
un concept, elle devient une tâche au lieu d'une note. Qwen classe chaque sujet (`nature`) ;
le code rattrape aussi les titres qui commencent par un verbe d'action (VERBES_ACTION)."""

import unicodedata

from . import config as cfg
from .index import Note, meme_titre

NATURES = ("concept", "projet", "action")


def _sans_accents(mot: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", mot) if not unicodedata.combining(c))


def nature(sujet: dict) -> str:
    """Nature du sujet ; ancien format (`est_projet`) toujours compris."""
    n = str(sujet.get("nature", "")).strip().lower()
    if n in NATURES:
        return n
    return "projet" if sujet.get("est_projet") else "concept"


def est_projet(sujet: dict) -> bool:
    return nature(sujet) == "projet"


def commence_par_un_verbe(titre: str) -> bool:
    mots = titre.strip().split()
    if not mots:
        return False
    premier = _sans_accents(mots[0].lower().strip("«»\"'.,:;!?"))
    return premier in {_sans_accents(v.lower()) for v in cfg.VERBES_ACTION}


def est_action(sujet: dict, ids: dict[str, Note]) -> bool:
    """Action = classée comme telle, ou titre à l'infinitif ; jamais si une note porte déjà
    exactement ce titre (choix fait à la main, respecté)."""
    if meme_titre(sujet.get("titre", ""), ids):
        return False
    return nature(sujet) == "action" or commence_par_un_verbe(sujet.get("titre", ""))


def projet_de_rattachement(sujets: list[dict]) -> str:
    """Titre du sujet auquel rattacher une action : le premier projet, sinon le premier
    concept de l'entrée, sinon « » (→ note du jour)."""
    for voulu in ("projet", "concept"):
        for s in sujets:
            if nature(s) == voulu:
                return s["titre"]
    return ""


def separer_actions(sujets: list[dict], taches: list[dict],
                    ids: dict[str, Note]) -> tuple[list[dict], list[dict], list[str]]:
    """(sujets gardés, tâches complétées des actions converties, titres convertis).
    Une action déjà présente dans les tâches (même texte) n'est pas répétée."""
    gardes = [s for s in sujets if not est_action(s, ids)]
    actions = [s for s in sujets if est_action(s, ids)]
    if not actions:
        return sujets, taches, []
    projet = projet_de_rattachement(gardes)
    deja = {t.get("texte", "").strip().rstrip(".").lower() for t in taches}
    nouvelles = []
    for s in actions:
        texte = s["titre"].strip().rstrip(".")
        if texte.lower() in deja:
            continue
        deja.add(texte.lower())
        nouvelles.append({"texte": texte, "projet": projet, "date": "", "date_limite": False,
                          "en_cours": False})
    return gardes, [*taches, *nouvelles], [s["titre"] for s in actions]
