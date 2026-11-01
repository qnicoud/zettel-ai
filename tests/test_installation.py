"""Points d'entrée installés (pyproject.toml) et lancement du validateur depuis la notification."""

import sys

from zettel import config as cfg
from zettel import rapport


def test_points_d_entree_importables():
    from zettel import cli, cli_valider
    assert callable(cli.main) and callable(cli_valider.main)


def test_validation_lance_la_commande_installee(monkeypatch):
    chemins = {cfg.TERMINAL: "/usr/bin/kitty", cfg.VALIDEUR: "/usr/bin/zettel-valider"}
    monkeypatch.setattr(rapport.shutil, "which", chemins.get)
    assert rapport.commande_validation() == [
        "/usr/bin/kitty", "--title", "zettel_ai : validation", "-e", "/usr/bin/zettel-valider"]


def test_validation_sans_commande_installee_passe_par_le_module(monkeypatch):
    monkeypatch.setattr(rapport.shutil, "which", lambda nom: None)
    commande = rapport.commande_validation()
    assert commande[-3:] == [sys.executable, "-m", "zettel.cli_valider"]


def test_valideur_installe_affiche_l_erreur_et_garde_la_fenetre(monkeypatch, capsys):
    """La commande installée appelle main() : erreur et pause doivent y être, pas sous __main__."""
    from zettel import cli_valider

    def echec():
        raise cli_valider.ErreurValidation("dépôt pas sur main")

    pauses = []
    monkeypatch.setattr(cli_valider, "valider", echec)
    monkeypatch.setattr("builtins.input", lambda invite: pauses.append(invite))
    assert cli_valider.main() == 1
    assert "dépôt pas sur main" in capsys.readouterr().out
    assert len(pauses) == 1
