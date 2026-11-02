"""Routeur : une consigne (« Instruction : … » du journal, ou prompt direct) -> une tâche
choisie dans une liste fermée. Ajouter une tâche = créer son module et l'inscrire ici."""

from ..contexte import Contexte
from ..ollama import llm
from . import (bilan, extraire, fusionner, lier, marquer_fait, preparation, renommer, resume,
               todos)
from .base import Tache

TACHES: dict[str, Tache] = {t.nom: t for t in (
    extraire.TACHE, fusionner.TACHE, renommer.TACHE, lier.TACHE,      # remaniement
    marquer_fait.TACHE, todos.TACHE, resume.TACHE,                    # todos, lecture
    bilan.TACHE, preparation.TACHE)}                                   # journées

PROMPT_ROUTEUR = """Tu reçois une demande adressée à l'assistant d'une base de notes org-roam.
Choisis LA tâche de la liste qui y correspond. Si aucune ne correspond vraiment, réponds
"inconnue" : mieux vaut ne rien faire que faire la mauvaise chose.
sujet = le sujet ou le filtre mentionné dans la demande (ex. « Rust »), vide s'il n'y en a pas."""


def schema_routeur() -> dict:
    return {
        "type": "object",
        "properties": {
            "tache": {"type": "string", "enum": [*TACHES, "inconnue"]},
            "sujet": {"type": "string"},
        },
        "required": ["tache", "sujet"],
    }


def router(consigne: str) -> tuple[Tache | None, str]:
    liste = "\n".join(f"- {t.nom} : {t.description}" for t in TACHES.values())
    d = llm(PROMPT_ROUTEUR, f"Tâches disponibles :\n{liste}\n\nDemande : {consigne}",
            schema_routeur())
    return TACHES.get(d["tache"]), d["sujet"].strip()


def executer_consigne(consigne: str, ctx: Contexte) -> tuple[str, str]:
    """Route puis exécute. Renvoie (nom de la tâche, texte du résultat)."""
    print(f"  ⚙ CONSIGNE : {consigne[:100]}")
    tache, sujet = router(consigne)
    if tache is None:
        msg = ("Demande non comprise ou non prise en charge. Tâches possibles : "
               + ", ".join(TACHES) + ".")
        print(f"    {msg}")
        return "inconnue", msg
    print(f"    → tâche « {tache.nom} »" + (f", sujet « {sujet} »" if sujet else ""))
    if tache.ecrit:
        ctx.lot_notes.commiter()          # ce qui précède dans son propre commit
    try:
        return tache.nom, tache.executer(consigne, sujet, ctx)
    finally:
        if tache.ecrit:
            ctx.lot_remaniement.commiter(ctx.source)
