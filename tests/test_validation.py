"""Validation (vrai dépôt git temporaire) et notification cliquable."""

import subprocess

import pytest

from zettel import config as cfg
from zettel import rapport, relecture, validation
from zettel.relecture import LotCommit


def g(*args, cwd):
    return subprocess.run(["git", "-C", str(cwd), *args], check=True,
                          capture_output=True, text=True).stdout


@pytest.fixture
def depot(tmp_path, monkeypatch):
    roam, wt = tmp_path / "roam", tmp_path / "state" / "worktree"
    roam.mkdir()
    g("init", "-q", "-b", "main", cwd=roam)
    g("config", "user.email", "t@t", cwd=roam)
    g("config", "user.name", "t", cwd=roam)
    (roam / "a.org").write_text("a\n")
    g("add", ".", cwd=roam)
    g("commit", "-qm", "init", cwd=roam)
    monkeypatch.setattr(cfg, "ROAM_DIR", roam)
    monkeypatch.setattr(cfg, "WORKTREE", wt)
    monkeypatch.setattr(cfg, "NOTES_DIR", wt)
    relecture.preparer_branche()
    return roam, wt


def proposer(wt, nom, texte, precision):
    lot = LotCommit("zettel_ai : notes")
    (wt / nom).write_text(texte)
    lot.ajouter(wt / nom, f"+ {nom}")
    lot.commiter(precision)


def test_accepter_refuser_garder(depot):
    roam, wt = depot
    proposer(wt, "b.org", "b\n", "entrée 1")
    proposer(wt, "c.org", "c\n", "entrée 2")
    proposer(wt, "d.org", "d\n", "entrée 3")
    c1, c2, c3 = validation.en_attente()
    assert c1.titre == "zettel_ai : notes (entrée 1)" and c1.corps == "+ b.org"

    validation.verifier_depot()
    validation.accepter(c1)
    assert (roam / "b.org").read_text() == "b\n"
    sauvegarde = validation.reconstruire([c3])          # c2 refusé, c3 plus tard
    assert [c.titre for c in validation.en_attente()] == ["zettel_ai : notes (entrée 3)"]
    assert not (wt / "c.org").exists() and (wt / "d.org").exists()
    assert not (roam / "c.org").exists()
    assert g("rev-parse", sauvegarde, cwd=roam).strip()   # retour arrière possible

    # au prochain traitement, main est réintégré sans faire réapparaître c1
    relecture.preparer_branche()
    assert [c.titre for c in validation.en_attente()] == ["zettel_ai : notes (entrée 3)"]


def test_conflit_laisse_main_propre(depot):
    roam, wt = depot
    proposer(wt, "b.org", "b\n", "création")
    lot = LotCommit("zettel_ai : notes")
    (wt / "b.org").write_text("b\ncomplément\n")
    lot.ajouter(wt / "b.org", "~ b")
    lot.commiter("complément")
    _, complement = validation.en_attente()
    with pytest.raises(validation.ErreurValidation, match="pas encore accepté"):
        validation.accepter(complement)               # dépend de la création, non acceptée
    assert g("status", "--porcelain", cwd=roam) == ""
    assert not (roam / "b.org").exists()


def test_verifier_depot_hors_main(depot):
    roam, _ = depot
    g("checkout", "-qb", "autre", cwd=roam)
    with pytest.raises(validation.ErreurValidation, match="autre"):
        validation.verifier_depot()


def test_notification_cliquable_lancee_hors_du_processus(monkeypatch):
    lances = []
    monkeypatch.setattr(cfg, "NOTIFIER", True)
    monkeypatch.setattr(rapport, "executer", lambda cmd: lances.append(cmd) or True)
    rapport.notifier("titre", "corps l'été", ["kitty", "-e", "valider"])
    (cmd,) = lances
    assert cmd[:4] == ["systemd-run", "--user", "--collect", "--quiet"]
    script = cmd[-1]
    assert "-A default='Relire et valider'" in script
    assert "'corps l'\"'\"'été'" in script                  # apostrophe correctement échappée
    assert script.endswith('[ "$a" = default ] && exec kitty -e valider')


def test_publier_sans_modification_n_est_pas_cliquable(chemins, monkeypatch):
    appels = []
    monkeypatch.setattr(rapport, "notifier", lambda t, c, cmd=None: appels.append((c, cmd)))
    r = rapport.Rapport()
    r.ajouter("Résumé", "texte")
    r.publier(a_valider=0)
    r.publier(a_valider=2)
    assert appels[0][1] is None
    assert appels[1][0].startswith("2 modification(s) à valider") and appels[1][1]
