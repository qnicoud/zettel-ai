"""Définition d'une tâche que le routeur peut choisir + outils communes aux tâches."""

from dataclasses import dataclass
from typing import Callable

from .. import config as cfg
from ..contexte import Contexte
from ..index import Note, plus_proches


def candidats(consigne: str, vec, ctx: Contexte, k: int | None = None) -> list[Note]:
    """Notes citées par leur titre (ou alias) dans la consigne + les plus proches
    (hors notes simulées). Le LLM ne peut choisir que parmi elles."""
    reelles, bas = ctx.reelles(), consigne.lower()
    cites = [n for n in reelles if any(t.lower() in bas for t in [n.titre, *n.alias] if len(t) >= 3)]
    proches = plus_proches(vec, reelles, k or cfg.TOP_K_INSTRUCTION)
    return list({n.id: n for n in cites + proches}.values())


def liste_notes(notes: list[Note]) -> str:
    return "\n".join(f"- id: {n.id} | titre: {n.titre} | extrait: {n.extrait[:150]}"
                     for n in notes)


def note_reelle(ctx: Contexte, nid: str) -> Note | None:
    n = ctx.ids.get(nid.strip())
    return n if n is not None and n.path is not None else None


def refus(raison: str) -> str:
    print(f"    refusé : {raison}")
    return f"Refusé : {raison}. Rien n'a été modifié."


@dataclass(frozen=True)
class Tache:
    nom: str                 # identifiant proposé au routeur (enum du schéma JSON)
    description: str         # ce que le routeur lit pour choisir
    executer: Callable[[str, str, Contexte], str]   # (consigne, sujet, ctx) -> texte du résultat
    ecrit: bool              # True = modifie des notes (commit séparé sur la branche de relecture)
