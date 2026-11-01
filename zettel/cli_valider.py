"""Relire et valider les modifications proposées par zettel-ai (branche « zettel-ai »).

Pour chaque commit en attente (une entrée du journal, ou un remaniement) :
  [a]ccepter   -> appliqué sur main (cherry-pick)
  [r]efuser    -> retiré de la branche de relecture
  [p]lus tard  -> reste en attente
  [v]oir       -> diff complet (q pour revenir)
  [q]uitter    -> les commits restants restent en attente
La branche de relecture est sauvegardée avant d'être réécrite.
Lancé par un clic sur la notification de fin de traitement, ou à la main.
"""

import sys

from zettel import config as cfg
from zettel.config_utilisateur import charger
from zettel.validation import (ErreurValidation, accepter, afficher_diff, en_attente,
                               reconstruire, resume_fichiers, synchroniser_org_roam,
                               verifier_depot)

GRAS, GRIS, VERT, ROUGE, JAUNE, FIN = "\033[1m", "\033[2m", "\033[32m", "\033[31m", "\033[33m", "\033[0m"
INVITE = f"{GRAS}[a]{FIN}ccepter  {GRAS}[r]{FIN}efuser  {GRAS}[v]{FIN}oir le diff  " \
         f"{GRAS}[p]{FIN}lus tard  {GRAS}[q]{FIN}uitter > "


def demander() -> str:
    try:
        return input(INVITE).strip().lower()[:1]
    except (EOFError, KeyboardInterrupt):
        print()
        return "q"


def relire(commits) -> tuple[list, list, list]:
    acceptes, refuses, gardes = [], [], []
    for i, c in enumerate(commits, 1):
        print(f"\n{GRAS}[{i}/{len(commits)}] {c.titre}{FIN}  {GRIS}{c.court}{FIN}")
        if c.corps:
            print(c.corps)
        print(resume_fichiers(c))
        while True:
            choix = demander()
            if choix == "v":
                afficher_diff(c)
            elif choix == "a":
                try:
                    accepter(c)
                    acceptes.append(c)
                    print(f"{VERT}✔ accepté{FIN}")
                except ErreurValidation as e:
                    gardes.append(c)
                    print(f"{JAUNE}⚠ {e}{FIN}")
                break
            elif choix == "r":
                refuses.append(c)
                print(f"{ROUGE}✘ refusé{FIN}")
                break
            elif choix == "p":
                gardes.append(c)
                break
            elif choix == "q":
                return acceptes, refuses, gardes + commits[i - 1:]
    return acceptes, refuses, gardes


def bilan(acceptes, refuses, gardes):
    if acceptes or refuses:
        sauvegarde = reconstruire(gardes)
        print(f"\n{GRIS}Branche {cfg.REVIEW_BRANCH} réécrite. Pour revenir en arrière :\n"
              f"  git -C {cfg.WORKTREE} reset --hard {sauvegarde}{FIN}")
    print(f"\n{VERT}{len(acceptes)} accepté(s){FIN}, {ROUGE}{len(refuses)} refusé(s){FIN}, "
          f"{len(gardes)} en attente.")
    if acceptes:
        if synchroniser_org_roam():
            print("Base org-roam synchronisée (org-roam-db-sync).")
        else:
            print("Pense à lancer M-x org-roam-db-sync dans Emacs.")


def valider() -> int:
    commits = en_attente()
    if not commits:
        print("Rien à valider.")
        return 0
    verifier_depot()
    print(f"{GRAS}{len(commits)} modification(s) en attente sur « {cfg.REVIEW_BRANCH} »{FIN}")
    bilan(*relire(commits))
    return 0


def main() -> int:
    """Commande `zettel-valider` : l'erreur et la pause finale sont ici (et non sous __main__)
    car la commande installée appelle main() directement."""
    charger()
    try:
        code = valider()
    except ErreurValidation as e:
        print(f"{ROUGE}Impossible de valider : {e}{FIN}")
        code = 1
    try:
        input(f"\n{GRIS}Entrée pour fermer…{FIN}")   # la fenêtre du terminal reste ouverte
    except (EOFError, KeyboardInterrupt):
        pass
    return code


if __name__ == "__main__":
    sys.exit(main())
