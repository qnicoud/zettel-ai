"""Un seul traitement zettel-ai à la fois (timer, verrouillage de session, consigne vocale) :
deux processus écriraient dans le même worktree et la même branche de relecture."""

import fcntl
from collections.abc import Iterator
from contextlib import contextmanager

from . import config as cfg

NOM = "zettel-ai.lock"


class DejaEnCours(RuntimeError):
    """Un autre traitement zettel-ai détient le verrou."""


@contextmanager
def exclusif() -> Iterator[None]:
    """Verrou flock non bloquant dans STATE_DIR ; rendu par le noyau même si le processus
    est tué. Lève DejaEnCours si un autre traitement le détient."""
    cfg.STATE_DIR.mkdir(parents=True, exist_ok=True)
    with open(cfg.STATE_DIR / NOM, "w", encoding="utf-8") as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as e:
            raise DejaEnCours("un traitement zettel-ai est déjà en cours") from e
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)
