"""Validation des modifications en attente sur REVIEW_BRANCH (logique git, sans interface).

- accepter : cherry-pick du commit sur BASE_BRANCH, dans ton dépôt (qui doit être sur main)
- refuser / plus tard : décidé à la fin par `reconstruire` : REVIEW_BRANCH repart de main
  et ne garde que les commits « plus tard ». Une sauvegarde de la branche est faite avant.
"""

import subprocess
from dataclasses import dataclass
from datetime import datetime

from . import config as cfg
from .relecture import git

SEP_CHAMP, SEP_COMMIT = "\x1f", "\x1e"
REF_SAUVEGARDES = "refs/zettel-ai-sauvegardes"


class ErreurValidation(Exception):
    pass


@dataclass(frozen=True)
class Commit:
    sha: str
    titre: str
    corps: str

    @property
    def court(self) -> str:
        return self.sha[:8]


def en_attente() -> list[Commit]:
    """Commits de REVIEW_BRANCH absents de main (ni fusionnés ni déjà cherry-pickés),
    du plus ancien au plus récent. Les merges de main dans la branche sont ignorés."""
    r = git("log", "--reverse", "--no-merges", "--cherry-pick", "--right-only",
            f"--format=%H{SEP_CHAMP}%s{SEP_CHAMP}%b{SEP_COMMIT}",
            f"{cfg.BASE_BRANCH}...{cfg.REVIEW_BRANCH}", check=False)
    if r.returncode:
        return []
    commits = []
    for bloc in r.stdout.split(SEP_COMMIT):
        if bloc.strip():
            sha, titre, corps = bloc.strip("\n").split(SEP_CHAMP)
            commits.append(Commit(sha, titre, corps.strip()))
    return commits


def resume_fichiers(c: Commit) -> str:
    return git("show", "--stat", "--format=", "--color=always", c.sha).stdout.rstrip()


def afficher_diff(c: Commit):
    """Diff complet dans le pager (q pour revenir)."""
    subprocess.run(["git", "-C", str(cfg.ROAM_DIR), "-c", "core.pager=less -R",
                    "show", "--color=always", c.sha], check=False)


def verifier_depot():
    branche = git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    if branche != cfg.BASE_BRANCH:
        raise ErreurValidation(f"ton dépôt est sur « {branche} » : passe sur "
                               f"« {cfg.BASE_BRANCH} » pour valider")
    if git("status", "--porcelain", cwd=cfg.WORKTREE).stdout.strip():
        raise ErreurValidation(f"le worktree {cfg.WORKTREE} contient des modifications "
                               "non commitées")


def accepter(c: Commit):
    """Cherry-pick sur main. En cas de conflit (ex. le commit complète une note créée par
    un commit pas encore accepté), annule proprement et lève ErreurValidation."""
    r = git("cherry-pick", "-x", c.sha, check=False)
    if r.returncode:
        git("cherry-pick", "--abort", check=False)
        raise ErreurValidation("conflit en l'appliquant sur main (il dépend peut-être d'un "
                               "commit pas encore accepté) : laissé en attente\n"
                               + (r.stderr or r.stdout).strip())


def reconstruire(gardes: list[Commit]) -> str:
    """REVIEW_BRANCH = main + les commits gardés. Renvoie le nom de la sauvegarde."""
    sauvegarde = f"{REF_SAUVEGARDES}/{datetime.now():%Y%m%d-%H%M%S}"
    git("update-ref", sauvegarde, cfg.REVIEW_BRANCH)
    wt = cfg.WORKTREE
    git("reset", "--hard", "--quiet", cfg.BASE_BRANCH, cwd=wt)
    for c in gardes:
        r = git("cherry-pick", c.sha, cwd=wt, check=False)
        if r.returncode:
            git("cherry-pick", "--abort", cwd=wt, check=False)
            git("reset", "--hard", "--quiet", sauvegarde, cwd=wt)
            raise ErreurValidation(f"impossible de garder {c.court} « {c.titre} » : branche "
                                   f"restaurée telle qu'avant ({sauvegarde})")
    return sauvegarde


def synchroniser_org_roam() -> bool:
    """org-roam-db-sync via emacsclient si un serveur Emacs tourne."""
    try:
        r = subprocess.run(["emacsclient", "-e", "(org-roam-db-sync)"], check=False,
                           capture_output=True, text=True, timeout=60)
        return r.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False
