"""Tâche « bilan_journee » (lecture seule) : bilan d'une journée passée (ou du jour).
Les listes (rendez-vous, tâches, notes, suivi) sont lues de façon déterministe ; Qwen n'écrit
que le résumé, à partir des seules dictées de ce jour-là et du journal de la note du jour."""

import re
from datetime import date

from .. import config as cfg
from ..contexte import Contexte
from ..dates import nom_jour
from ..journal import (
    chemins_journaux,
    consigne_instruction,
    corriger_transcription,
    date_entree,
    lire_journaux,
    texte_entree,
)
from ..ollama import llm
from .agenda import (
    creees_le,
    lire_base,
    note_du_jour,
    notes_du_jour,
    rendez_vous,
    section,
    suivi_du_jour,
    taches_org,
)
from .base import Tache, refus
from .jour import assembler, bloc, journee_demandee

PROMPT_BILAN = """Tu rédiges pour moi le résumé d'une de mes journées, à partir de mes dictées
de ce jour-là et des lignes du journal de ma note du jour. Appuie-toi UNIQUEMENT sur ce qui est
fourni : n'invente rien, n'ajoute aucune connaissance extérieure.
Quelques phrases courtes (5 au plus), en français, à la deuxième personne (« tu as… »).
Syntaxe Org : paragraphes simples, jamais de titre (ligne commençant par « * »), jamais de
Markdown. Ignore ce qui parle de la dictée elle-même (« ceci est un test »)."""

SCHEMA_BILAN = {
    "type": "object",
    "properties": {"resume": {"type": "string"}},
    "required": ["resume"],
}


def dictees_du_jour(j: date) -> list[str]:
    """Dictées ordinaires du jour (pas les consignes), « HH:MM texte », transcription corrigée."""
    entrees, _ = lire_journaux(chemins_journaux())
    res = []
    for e in entrees:
        quand, texte = date_entree(e), texte_entree(e).strip()
        if quand is None or quand.date() != j or consigne_instruction(texte) is not None:
            continue
        res.append(f"{quand:%H:%M} {corriger_transcription(texte)}")
    return res


def resumer(j: date, dictees: list[str], journal: list[str]) -> str:
    """Résumé par Qwen ; « » sans aucune matière (pas d'appel au LLM)."""
    if not dictees and not journal:
        return ""
    matiere = "\n\n".join(p for p in (
        "Dictées :\n" + "\n".join(f"- {d}" for d in dictees) if dictees else "",
        "Journal de la note du jour :\n" + "\n".join(journal) if journal else "") if p)
    r = llm(PROMPT_BILAN, f"Journée : {nom_jour(j)}\n\n{matiere[:cfg.MAX_CARACTERES_BILAN]}",
            SCHEMA_BILAN)["resume"].strip()
    return re.sub(r"(?m)^\*+\s+", "", r)          # garde-fou : jamais de titre Org


def executer(consigne: str, sujet: str, ctx: Contexte) -> str:
    j = journee_demandee(consigne, ctx, sens=-1)
    if j is None:
        return refus("journée non reconnue ou trop lointaine")
    base = lire_base()
    taches = taches_org(base)
    journal = section(note_du_jour(base, j), "Journal")
    dictees = dictees_du_jour(j)
    print(f"    {nom_jour(j)} : {len(dictees)} dictée(s), {len(journal)} ligne(s) de journal")
    return assembler(
        f"Bilan du {nom_jour(j)}",
        resumer(j, dictees, journal),
        bloc("Rendez-vous", [r.org() for r in rendez_vous(base, j)]),
        bloc("Journal du jour", journal),
        bloc("Tâches créées", [t.org() for t in creees_le(taches, j)]),
        bloc("Tâches prévues ou à rendre ce jour-là",
             [t.org() for t in taches if j in (t.prevue, t.limite)]),
        bloc("Tâches terminées", [t.org() for t in taches if t.faite == j]),
        bloc("Notes créées ou complétées",
             [f"- {f.lien()} : {', '.join(n)}" for f, n in notes_du_jour(base, j)]),
        bloc("Suivi des projets", [f"- {f.titre} : {s}" for f, s in suivi_du_jour(base, j)]),
        vide="Rien de noté pour cette journée.",
    )


TACHE = Tache(
    nom="bilan_journee",
    description="faire le bilan d'une journée passée ou de celle d'aujourd'hui (« bilan "
                "d'hier », « qu'est-ce que j'ai fait lundi ») : résumé des dictées du jour, "
                "rendez-vous, tâches créées, prévues ou terminées, notes modifiées",
    executer=executer,
    ecrit=False,
)
