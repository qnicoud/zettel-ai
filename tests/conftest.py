"""Fixtures : chemins temporaires, faux LLM (réponses en file), faux embeddings, notes."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from zettel import config as cfg  # noqa: E402
from zettel import contenu, index, suivi, taches  # noqa: E402
from zettel.contexte import Contexte  # noqa: E402
from zettel.index import lire_note  # noqa: E402
from zettel.taches import (bilan, extraire, fusionner, jour, lier,  # noqa: E402
                           marquer_fait, renommer, resume, todos)

# Chaque module importe llm / embed par nom : il faut les remplacer partout.
MODULES_LLM = (contenu, taches, extraire, todos, resume, fusionner, lier, renommer, marquer_fait,
               bilan, jour)
MODULES_EMBED = (index, contenu, suivi, extraire, todos, resume, fusionner, lier, renommer)


@pytest.fixture(autouse=True)
def chemins(tmp_path, monkeypatch):
    notes = tmp_path / "notes"
    notes.mkdir()
    monkeypatch.setattr(cfg, "NOTES_DIR", notes)
    monkeypatch.setattr(cfg, "ROAM_DIR", tmp_path / "roam")
    monkeypatch.setattr(cfg, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(cfg, "RAPPORTS_DIR", tmp_path / "state" / "rapports")
    monkeypatch.setattr(cfg, "NOTIFIER", False)
    # jamais le vrai ~/.config/zettel-ai/config.toml dans les tests
    monkeypatch.setenv("ZETTEL_AI_CONFIG", str(tmp_path / "config-absente.toml"))
    return notes


class FauxLLM:
    def __init__(self):
        self.reponses, self.appels = [], []

    def __call__(self, system, user, schema):
        self.appels.append((system, user, schema))
        assert self.reponses, "appel LLM inattendu"
        return self.reponses.pop(0)


@pytest.fixture
def faux_llm(monkeypatch):
    f = FauxLLM()
    for m in MODULES_LLM:
        monkeypatch.setattr(m, "llm", f)
    for m in MODULES_EMBED:
        monkeypatch.setattr(m, "embed", lambda xs: [[1.0, 0.0] for _ in xs])
    return f


class FauxLot:
    def __init__(self):
        self.fichiers, self.resume, self.commits = [], [], 0

    def ajouter(self, path, ligne):
        self.fichiers.append(path)
        self.resume.append(ligne)

    def commiter(self, precision=""):
        self.commits += 1


def ecrire_note(dossier: Path, nom: str, nid: str, titre: str, corps: str) -> Path:
    p = dossier / nom
    p.write_text(f":PROPERTIES:\n:ID:       {nid}\n:END:\n#+title: {titre}\n\n{corps}",
                 encoding="utf-8")
    return p


PROJET_X = """Texte du projet.

* Tâches
** TODO Écrire la doc
SCHEDULED: <2026-11-03 Tue>
:PROPERTIES:
:CREATED:  [2026-11-02 Mon 15:27]
:END:
** TODO Rendre le rapport
DEADLINE: <2026-11-01 Sun>
** DONE Installer
CLOSED: [2026-11-02 Mon 10:00] SCHEDULED: <2026-11-01 Sun>
** TODO Sans date

* Suivi
- [2026-11-02] Première version installée

* Source
- Journal dicté, 2026-11-02 15:27:49 (note créée le 2026-11-02)
"""

AUTRE = """Autre texte.

* Source
- Journal dicté, 2026-11-01 10:00:00 (note créée le 2026-11-01)
- Journal dicté, 2026-11-02 09:00:00 (complément du 2026-11-02)
"""


def ecrire_journees(notes: Path) -> None:
    """Petite base datée autour du lundi 2026-11-02 (bilan et préparation de journée)."""
    ecrire_note(notes, "20261102-projet_x.org", "ID-P", "Projet X", PROJET_X)
    ecrire_note(notes, "20261101-autre.org", "ID-A", "Autre", AUTRE)
    daily = notes / cfg.DAILY_DIR
    daily.mkdir(exist_ok=True)
    ecrire_note(daily, "2026-11-02.org", "J02", "2026-11-02",
                "* Journal\n- 15:27 Rendez-vous le 2026-11-03 à 13:30 : Coiffeur\n\n"
                "* Tâches\n** TODO Appeler le garage\n")
    ecrire_note(daily, "2026-11-03.org", "J03", "2026-11-03",
                "* Agenda\n- <2026-11-03 Tue 13:30> Coiffeur, site du travail\n"
                "- <2026-11-03 Tue> Anniversaire de Léa\n")


@pytest.fixture
def ctx(chemins):
    def fabrique(*paths, dry_run=False):
        notes = [lire_note(p) for p in paths]
        for n in notes:
            n.vec = [1.0, 0.0]
        return Contexte(notes, {n.id: n for n in notes}, dry_run, FauxLot(), FauxLot(),
                        source="Journal dicté, 2026-11-01 16:00:00")
    return fabrique
