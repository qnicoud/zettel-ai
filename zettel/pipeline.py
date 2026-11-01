"""Traitement des entrées du journal : contenu ordinaire ou consigne « Instruction : … »."""

from datetime import datetime

from .contenu import traiter_entree
from .contexte import Contexte
from .journal import (cle_entree, consigne_instruction, corriger_transcription, date_entree,
                      sauver_etat, source_entree, texte_entree)
from .rapport import Rapport
from .taches import executer_consigne


def indenter(texte: str) -> str:
    return "    " + texte.replace("\n", "\n    ")


def traiter_journal(entrees: list[str], etat: set, ctx: Contexte, rapport: Rapport):
    for entree in entrees:
        source = source_entree(entree)
        texte = corriger_transcription(texte_entree(entree))
        ctx.source = f"Journal dicté, {source}"
        ctx.quand = date_entree(entree) or datetime.now()
        print(f"\n=== Entrée {source} : {texte[:70]}…")
        if (consigne := consigne_instruction(texte)) is not None:
            nom, resultat = executer_consigne(consigne, ctx)
            print(indenter(resultat))
            rapport.ajouter(f"Instruction du {source} ({nom})",
                            f"Demande : {consigne}\n\n{resultat}")
        else:
            actions = traiter_entree(texte, ctx)
            rapport.ajouter(f"Entrée du {source}", "\n".join(f"- {a}" for a in actions))
        if not ctx.dry_run:
            ctx.lot_notes.commiter(source)   # un commit par entrée : validée ou refusée seule
            etat.add(cle_entree(entree))
            sauver_etat(etat)            # une entrée finie n'est jamais retraitée
