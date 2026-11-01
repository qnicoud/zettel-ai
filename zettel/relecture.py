"""Branche de relecture : le script travaille dans un worktree séparé, sur REVIEW_BRANCH,
que tu fusionnes toi-même. Il n'écrit jamais sur BASE_BRANCH ni dans ton dossier de travail."""

import shutil
import subprocess
import sys
from pathlib import Path

from . import config as cfg

MSG_NOTES = "zettel_ai : notes depuis le journal dicté"
MSG_REMANIEMENT = "zettel_ai : remaniement demandé"


def git(*args, cwd=None, check=True):
    return subprocess.run(["git", "-C", str(cwd or cfg.ROAM_DIR), *args], check=check,
                          capture_output=True, text=True)


def preparer_branche():
    """Crée/rafraîchit le worktree de REVIEW_BRANCH et y intègre BASE_BRANCH,
    pour que le script voie tes notes à jour + les siennes pas encore validées."""
    if not (cfg.ROAM_DIR / ".git").exists():
        sys.exit(f"{cfg.ROAM_DIR} n'est pas un dépôt git")
    base, revue, wt = cfg.BASE_BRANCH, cfg.REVIEW_BRANCH, cfg.WORKTREE
    if git("rev-parse", "--verify", "--quiet", f"refs/heads/{base}", check=False).returncode:
        sys.exit(f"Branche « {base} » introuvable : ajuste BASE_BRANCH")
    git("worktree", "prune")
    if not (wt / ".git").exists():
        if wt.exists():
            shutil.rmtree(wt)            # reste d'un worktree supprimé
        wt.parent.mkdir(parents=True, exist_ok=True)
        existe = git("rev-parse", "--verify", "--quiet", f"refs/heads/{revue}",
                     check=False).returncode == 0
        if existe:
            git("worktree", "add", str(wt), revue)
        else:
            git("worktree", "add", "-b", revue, str(wt), base)
            print(f"Branche « {revue} » créée depuis « {base} »")
    r = git("merge", "--no-edit", base, cwd=wt, check=False)
    if r.returncode:
        git("merge", "--abort", cwd=wt, check=False)
        sys.exit(f"Conflit en intégrant « {base} » dans « {revue} ».\n"
                 f"Valide ou abandonne d'abord les notes en attente, puis relance.")


def git_commit(fichiers: list[Path], message: str):
    if not fichiers:
        return
    chemins = [str(f.relative_to(cfg.NOTES_DIR)) for f in fichiers]
    git("add", "--", *chemins, cwd=cfg.NOTES_DIR)
    git("commit", "-q", "-m", message, "--", *chemins, cwd=cfg.NOTES_DIR)
    print(f"Commit sur « {cfg.REVIEW_BRANCH} ». Pour relire :\n"
          f"  git diff {cfg.BASE_BRANCH}...{cfg.REVIEW_BRANCH}")


class LotCommit:
    """Fichiers écrits pas encore commités. Créé par main() pour que son finally
    commite ce qui a été écrit, même si le traitement plante en route."""

    def __init__(self, message: str):
        self.message, self.fichiers, self.resume = message, [], []

    def ajouter(self, path: Path, ligne: str):
        self.fichiers.append(path)
        self.resume.append(ligne)

    def commiter(self, precision: str = ""):
        """Un commit = une unité de validation (une entrée du journal, un remaniement)."""
        if self.fichiers:
            titre = f"{self.message} ({precision})" if precision else self.message
            git_commit(list(dict.fromkeys(self.fichiers)),
                       f"{titre}\n\n" + "\n".join(self.resume))
        self.fichiers, self.resume = [], []
