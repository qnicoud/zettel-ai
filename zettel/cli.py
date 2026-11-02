"""
Journal dicté (Markdown) -> notes org-roam, avec un LLM local (Ollama).

Pipeline guidé (le LLM décide, le script exécute et vérifie) :
  1. Découpe les journaux dictés (JOURNAUX, ~/Documents/journal-dictee.md par défaut) en
     entrées (une ligne hyprwhspr « - [horodatage] » ou un titre # / ##), fusionnées par ordre
     chronologique, et ne garde que celles jamais traitées.
  2. Indexe les notes org-roam (ID, titre, alias, tags, extrait) + embeddings en cache.
  3. Entrée ordinaire : Qwen en extrait les sujets (concepts), puis pour chacun décide
     de créer une note, compléter une note existante ou ignorer, avec des liens validés.
  4. Entrée « Instruction : … » : un routeur choisit une tâche dans une liste fermée
     (extraire, lister_todos, resumer, voir zettel/taches/) et l'exécute.
  5. Tout ce qui est écrit va dans un worktree séparé, commité sur la branche « zettel-ai ».
     Rien n'arrive sur main tant que tu ne fusionnes pas toi-même.
  6. Les résultats sont réunis dans ~/.local/state/zettel_ai/rapports/*.org + notification.

hyprwhspr est coupé pendant le traitement puis relancé (s'il tournait).
Un seul traitement à la fois (verrou dans ~/.local/state/zettel_ai) : sinon arrêt, code 75.
Réglages : ~/.config/zettel-ai/config.toml (valeurs par défaut : zettel/config.py) ; relecture : zettel-valider

Dépendances : sudo pacman -S python-requests ollama-cuda
              ollama pull hf.co/bartowski/Qwen_Qwen3.5-9B-GGUF:Q5_K_M
              ollama pull bge-m3
Usage       : zettel-ai [--dry-run] [--force]        # traite le journal
              zettel-ai --lister                     # entrées et statut
              zettel-ai [--dry-run] --entree 4 --entree "2026-11-01 14:59"
              zettel-ai [--dry-run] "liste mes todos Rust"   # demande directe
              zettel-ai "résume Rust" --sortie res.org       # résultat seul dans un fichier
"""

import argparse
import signal
import sys
import time
from datetime import datetime
from pathlib import Path

from zettel import config as cfg
from zettel.config_utilisateur import charger
from zettel.contexte import Contexte
from zettel.index import indexer
from zettel.journal import (charger_etat, chemins_journaux, corriger_transcription, est_traitee,
                            horodatages_en_double, lire_journaux, lister, selectionner)
from zettel.ollama import decharger_modeles
from zettel.pipeline import traiter_journal
from zettel.rapport import Rapport, commande_validation, notifier
from zettel.relecture import MSG_NOTES, MSG_REMANIEMENT, LotCommit, preparer_branche
from zettel.taches import TACHES, executer_consigne
from zettel.validation import en_attente
from zettel.verrou import DejaEnCours, exclusif
from zettel.whisper import whisper, whisper_actif

CODE_DEJA_EN_COURS = 75          # EX_TEMPFAIL : réessayer plus tard


def arguments() -> argparse.Namespace:
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
    ap.add_argument("--sortie", type=Path, metavar="FICHIER.org",
                    help="avec une demande directe : écrit le résultat seul (sans les lignes "
                         "de progression) dans ce fichier Org")
    args = ap.parse_args()
    if args.sortie and not args.demande:
        ap.error("--sortie n'a de sens qu'avec une demande directe")
    return args


def journal_complet() -> tuple[list[str], set]:
    """Entrées de tous les journaux (JOURNAUX), fusionnées par ordre chronologique."""
    chemins = chemins_journaux()
    entrees, absents = lire_journaux(chemins)
    if len(absents) == len(chemins):
        sys.exit("Aucun journal trouvé : " + ", ".join(map(str, chemins)))
    for chemin in absents:
        print(f"Journal introuvable, ignoré : {chemin}", file=sys.stderr)
    for h in horodatages_en_double(entrees):
        print(f"Horodatage en double [{h}] : ces entrées seront confondues "
              "(modifie l'une d'elles d'une seconde)", file=sys.stderr)
    return entrees, charger_etat()


def entrees_a_traiter(args) -> tuple[list[str], set]:
    entrees, etat = journal_complet()
    if args.entree:
        try:
            return selectionner(entrees, args.entree), etat
        except ValueError as e:
            sys.exit(str(e))
    return [e for e in entrees if args.force or not est_traitee(e, etat)], etat


def ecrire_sortie(path: Path, demande: str, tache: str, resultat: str) -> None:
    """Résultat d'une demande directe, seul, dans un fichier Org (lu par zettel-ai-vocal)."""
    titre = " ".join(demande.split())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"#+title: zettel-ai : {titre}\n\nTâche : {tache}\n\n{resultat.strip()}\n",
                    encoding="utf-8")


def signaler_modifications(tache: str, dry_run: bool) -> None:
    """Une demande directe qui a modifié la base : notification cliquable vers zettel-valider
    (en mode journal, c'est le rapport qui s'en charge)."""
    t = TACHES.get(tache)
    if dry_run or t is None or not t.ecrit:
        return
    notifier("zettel_ai : modification à valider",
             f"Demande traitée ({tache}) : clique pour relire et valider.",
             commande_validation())


def demande_directe(args, ctx: Contexte) -> None:
    ctx.source = f"Demande directe du {datetime.now():%Y-%m-%d %H:%M}"
    demande = corriger_transcription(args.demande)
    tache, resultat = executer_consigne(demande, ctx)
    print(f"\n{resultat}")
    if args.sortie:
        ecrire_sortie(args.sortie, demande, tache, resultat)
    signaler_modifications(tache, args.dry_run)


def traiter(args) -> None:
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
            demande_directe(args, ctx)
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


def main():
    args = arguments()
    charger()                       # ~/.config/zettel-ai/config.toml
    if args.lister:                 # lecture seule : pas de verrou
        print(lister(*journal_complet()) or "Journal vide")
        return
    if not cfg.ROAM_DIR.is_dir():
        sys.exit(f"Introuvable : {cfg.ROAM_DIR}")
    try:
        with exclusif():
            traiter(args)
    except DejaEnCours as e:
        print(f"zettel-ai : {e}, réessaie plus tard.", file=sys.stderr)
        sys.exit(CODE_DEJA_EN_COURS)


if __name__ == "__main__":
    main()
