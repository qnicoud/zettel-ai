"""
Journal dicté (Markdown) -> notes org-roam, avec un LLM local (Ollama).

Pipeline guidé (le LLM décide, le script exécute et vérifie) :
  1. Découpe ~/Documents/journal-dictee.md en entrées (une ligne hyprwhspr « - [horodatage] »
     ou un titre # / ##) et ne garde que celles jamais traitées.
  2. Indexe les notes org-roam (ID, titre, alias, tags, extrait) + embeddings en cache.
  3. Entrée ordinaire : Qwen en extrait les sujets (concepts), puis pour chacun décide
     de créer une note, compléter une note existante ou ignorer, avec des liens validés.
  4. Entrée « Instruction : … » : un routeur choisit une tâche dans une liste fermée
     (extraire, lister_todos, resumer, voir zettel/taches/) et l'exécute.
  5. Tout ce qui est écrit va dans un worktree séparé, commité sur la branche « zettel-ai ».
     Rien n'arrive sur main tant que tu ne fusionnes pas toi-même.
  6. Les résultats sont réunis dans ~/.local/state/zettel_ai/rapports/*.org + notification.

hyprwhspr est coupé pendant le traitement puis relancé (s'il tournait).
Réglages : ~/.config/zettel-ai/config.toml (valeurs par défaut : zettel/config.py) ; relecture : zettel-valider

Dépendances : sudo pacman -S python-requests ollama-cuda
              ollama pull hf.co/bartowski/Qwen_Qwen3.5-9B-GGUF:Q5_K_M
              ollama pull bge-m3
Usage       : zettel-ai [--dry-run] [--force]        # traite le journal
              zettel-ai --lister                     # entrées et statut
              zettel-ai [--dry-run] --entree 4 --entree "2026-11-01 14:59"
              zettel-ai [--dry-run] "liste mes todos Rust"   # demande directe
"""

import argparse
import signal
import sys
import time
from datetime import datetime

from zettel import config as cfg
from zettel.config_utilisateur import charger
from zettel.contexte import Contexte
from zettel.index import indexer
from zettel.journal import (charger_etat, corriger_transcription, entrees_journal, est_traitee,
                            lister, selectionner)
from zettel.ollama import decharger_modeles
from zettel.pipeline import traiter_journal
from zettel.rapport import Rapport
from zettel.relecture import MSG_NOTES, MSG_REMANIEMENT, LotCommit, preparer_branche
from zettel.taches import executer_consigne
from zettel.validation import en_attente
from zettel.whisper import whisper, whisper_actif


def arguments():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0].strip())
    ap.add_argument("demande", nargs="?",
                    help="demande directe (ex. « résume mes notes sur Rust ») ; "
                         "sans elle, le journal est traité")
    ap.add_argument("--dry-run", action="store_true", help="affiche les décisions sans rien écrire")
    ap.add_argument("--force", action="store_true", help="retraite aussi les entrées déjà traitées")
    ap.add_argument("--lister", action="store_true",
                    help="liste les entrées du journal (numéro, horodatage, statut) et s'arrête")
    ap.add_argument("--entree", action="append", metavar="N|HORODATAGE",
                    help="(re)traite seulement cette entrée : numéro de --lister ou début "
                         "d'horodatage (« 2026-11-01 14:59 »). Répétable. Attention : une "
                         "entrée déjà traitée peut produire des compléments en double.")
    return ap.parse_args()


def journal_complet() -> tuple[list[str], set]:
    if not cfg.JOURNAL.exists():
        sys.exit(f"Introuvable : {cfg.JOURNAL}")
    return entrees_journal(cfg.JOURNAL.read_text(encoding="utf-8")), charger_etat()


def entrees_a_traiter(args) -> tuple[list[str], set]:
    entrees, etat = journal_complet()
    if args.entree:
        try:
            return selectionner(entrees, args.entree), etat
        except ValueError as e:
            sys.exit(str(e))
    return [e for e in entrees if args.force or not est_traitee(e, etat)], etat


def main():
    args = arguments()
    charger()                       # ~/.config/zettel-ai/config.toml
    if args.lister:
        print(lister(*journal_complet()) or "Journal vide")
        return
    if not cfg.ROAM_DIR.is_dir():
        sys.exit(f"Introuvable : {cfg.ROAM_DIR}")
    entrees, etat = ([], set()) if args.demande else entrees_a_traiter(args)
    if not args.demande and not entrees:
        print("Aucune nouvelle entrée dans le journal")
        return
    if not args.demande:
        print(f"{len(entrees)} entrée(s) à traiter" + (" (simulation)" if args.dry_run else ""))
    preparer_branche()

    signal.signal(signal.SIGTERM, lambda *_: sys.exit(1))
    relancer = cfg.TOGGLE_WHISPER and whisper_actif()
    if relancer:
        whisper("stop")
        time.sleep(cfg.VRAM_RELEASE_DELAY)

    lot_notes, lot_remaniement = LotCommit(MSG_NOTES), LotCommit(MSG_REMANIEMENT)
    rapport = Rapport()
    try:
        notes = indexer()
        ctx = Contexte(notes, {n.id: n for n in notes}, args.dry_run, lot_notes, lot_remaniement)
        if args.demande:
            ctx.source = f"Demande directe du {datetime.now():%Y-%m-%d %H:%M}"
            _, resultat = executer_consigne(corriger_transcription(args.demande), ctx)
            print(f"\n{resultat}")
        else:
            traiter_journal(entrees, etat, ctx, rapport)
    finally:
        decharger_modeles()
        if relancer:
            time.sleep(cfg.VRAM_RELEASE_DELAY)
            whisper("start")
        lot_notes.commiter()          # même en cas d'erreur en route, on commit ce qui a été écrit
        lot_remaniement.commiter()
        if not args.dry_run:          # vide (donc rien) en mode demande directe
            rapport.publier(a_valider=len(en_attente()))


if __name__ == "__main__":
    main()
