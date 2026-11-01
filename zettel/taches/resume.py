"""Tâche « resumer » (lecture seule) : bge-m3 trouve les notes du sujet, Qwen les résume
en s'appuyant uniquement sur elles."""

import re

from .. import config as cfg
from ..contexte import Contexte
from ..index import Note, plus_proches
from ..ollama import embed, llm
from .base import Tache

PROMPT_RESUME = """Tu résumes ce que contient une base de notes personnelle sur un sujet.
Appuie-toi UNIQUEMENT sur les notes fournies, n'ajoute aucune connaissance extérieure.
Écris en français, en syntaxe Org (paragraphes, listes « - », jamais de Markdown ni de titres).
Si les notes ne parlent pas du sujet, dis-le simplement.
notes_utilisees : les titres EXACTS des notes sur lesquelles tu t'appuies."""

SCHEMA_RESUME = {
    "type": "object",
    "properties": {
        "resume": {"type": "string"},
        "notes_utilisees": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["resume", "notes_utilisees"],
}


def texte_note(n: Note) -> str:
    txt = n.path.read_text(encoding="utf-8", errors="replace")
    txt = re.sub(r":PROPERTIES:.*?:END:", "", txt, flags=re.S | re.I)
    txt = re.sub(r"(?m)^#\+.*\n?", "", txt)
    return txt.strip()[:cfg.MAX_CARACTERES_NOTE]


def executer(consigne: str, sujet: str, ctx: Contexte) -> str:
    sujet = sujet or consigne
    notes = plus_proches(embed([sujet])[0], ctx.reelles(), cfg.TOP_K_RESUME)
    if not notes:
        return "La base ne contient aucune note."
    blocs = "\n\n".join(f"=== Note « {n.titre} »\n{texte_note(n)}" for n in notes)
    d = llm(PROMPT_RESUME, f"Sujet : {sujet}\n\nNotes :\n\n{blocs}", SCHEMA_RESUME)
    par_titre = {n.titre.lower(): n for n in notes}
    utilisees = {par_titre[t.strip().lower()].id: par_titre[t.strip().lower()]
                 for t in d["notes_utilisees"] if t.strip().lower() in par_titre}
    sources = "\n".join(f"- [[id:{n.id}][{n.titre}]]" for n in utilisees.values())
    return (f"Résumé : {sujet}\n\n{d['resume'].strip()}\n\n"
            f"Notes utilisées :\n{sources or '- (aucune note citée)'}")


TACHE = Tache(
    nom="resumer",
    description="faire un résumé de ce que les notes contiennent sur un sujet",
    executer=executer,
    ecrit=False,
)
