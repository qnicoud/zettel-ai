"""Demande directe sans terminal : --sortie (résultat seul dans un fichier), verrou contre
deux traitements simultanés, notification quand la demande a modifié la base."""

import subprocess
import sys
from pathlib import Path

import pytest

from zettel import cli, verrou
from zettel import config as cfg

RACINE = Path(__file__).resolve().parent.parent


# --- verrou -------------------------------------------------------------------------------

def test_verrou_refuse_un_second_traitement(chemins):
    with verrou.exclusif(), pytest.raises(verrou.DejaEnCours), verrou.exclusif():
        pass


def test_verrou_libere_apres_usage_meme_sur_erreur(chemins):
    with pytest.raises(RuntimeError), verrou.exclusif():
        raise RuntimeError("panne")
    with verrou.exclusif():          # ne lève pas : le verrou a bien été rendu
        pass


def test_verrou_dans_le_dossier_d_etat(chemins):
    with verrou.exclusif():
        assert (cfg.STATE_DIR / verrou.NOM).exists()


def test_main_s_arrete_si_un_traitement_tourne_deja(chemins, monkeypatch, capsys):
    cfg.ROAM_DIR.mkdir()
    monkeypatch.setattr(sys, "argv", ["zettel-ai", "liste mes todos"])
    monkeypatch.setattr(cli, "preparer_branche",
                        lambda: pytest.fail("ne doit rien préparer pendant un autre traitement"))
    with verrou.exclusif(), pytest.raises(SystemExit) as e:
        cli.main()
    assert e.value.code == cli.CODE_DEJA_EN_COURS
    assert "déjà en cours" in capsys.readouterr().err


def test_lister_ne_prend_pas_le_verrou(chemins, tmp_path, monkeypatch, capsys):
    """--lister ne fait que lire : utilisable pendant un traitement."""
    journal = tmp_path / "journal.md"
    journal.write_text("- [2026-11-01 10:00:00] bonjour\n", encoding="utf-8")
    monkeypatch.setattr(cfg, "JOURNAUX", (journal,))
    monkeypatch.setattr(sys, "argv", ["zettel-ai", "--lister"])
    with verrou.exclusif():
        cli.main()
    assert "bonjour" in capsys.readouterr().out


# --- --sortie -----------------------------------------------------------------------------

def test_sortie_exige_une_demande(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["zettel-ai", "--sortie", "x.org"])
    with pytest.raises(SystemExit) as e:
        cli.arguments()
    assert e.value.code == 2
    assert "--sortie" in capsys.readouterr().err


def test_ecrire_sortie_ne_contient_que_le_resultat(tmp_path):
    sortie = tmp_path / "sous" / "dossier" / "res.org"
    cli.ecrire_sortie(sortie, "liste mes todos Rust", "lister_todos",
                      "1 todo(s) ouvert(s) :\n- TODO Finir le livre")
    texte = sortie.read_text(encoding="utf-8")
    assert texte.startswith("#+title: zettel-ai : liste mes todos Rust\n")
    assert "Tâche : lister_todos" in texte
    assert "- TODO Finir le livre" in texte
    assert "⚙" not in texte and "→ tâche" not in texte     # pas de lignes de progression


def test_ecrire_sortie_titre_sur_une_ligne(tmp_path):
    sortie = tmp_path / "res.org"
    cli.ecrire_sortie(sortie, "résume\nHyprland", "resumer", "Résumé")
    premiere = sortie.read_text(encoding="utf-8").splitlines()[0]
    assert premiere == "#+title: zettel-ai : résume Hyprland"


# --- notification après une demande qui écrit -----------------------------------------------

@pytest.fixture
def notifications(monkeypatch):
    envoyees = []
    monkeypatch.setattr(cli, "notifier",
                        lambda titre, corps, commande=None: envoyees.append((titre, corps, commande)))
    monkeypatch.setattr(cli, "commande_validation", lambda: ["kitty", "-e", "zettel-valider"])
    return envoyees


def test_demande_qui_ecrit_notifie_la_validation(notifications):
    cli.signaler_modifications("renommer", dry_run=False)
    assert len(notifications) == 1
    _, corps, commande = notifications[0]
    assert "valider" in corps
    assert commande == ["kitty", "-e", "zettel-valider"]


@pytest.mark.parametrize("nom, dry_run", [
    ("lister_todos", False),     # lecture seule
    ("resumer", False),
    ("inconnue", False),         # rien n'a été fait
    ("renommer", True),          # simulation : rien d'écrit
])
def test_pas_de_notification_sans_modification(notifications, nom, dry_run):
    cli.signaler_modifications(nom, dry_run=dry_run)
    assert notifications == []


# --- script zettel-ai-vocal ------------------------------------------------------------------

def test_script_vocal_syntaxe_bash():
    script = RACINE / "zettel-ai-vocal"
    assert script.stat().st_mode & 0o111, "le script doit être exécutable"
    subprocess.run(["bash", "-n", str(script)], check=True)


def test_script_vocal_installe_par_le_paquet():
    chemin = RACINE / "packaging" / "PKGBUILD"
    if not chemin.exists():              # check() de makepkg : copie sans packaging/
        pytest.skip("PKGBUILD absent de cette copie des sources")
    pkgbuild = chemin.read_text(encoding="utf-8")
    sources = next(l for l in pkgbuild.splitlines() if l.startswith("_sources="))
    assert "zettel-ai-vocal" in sources
    assert any("zettel-ai-vocal" in l and "/usr/bin" in l for l in pkgbuild.splitlines()
               if l.strip().startswith("install"))


def test_script_vocal_utilise_le_code_d_arret_du_verrou():
    """Le script reconnaît le code « déjà en cours » pour afficher un message clair."""
    texte = (RACINE / "zettel-ai-vocal").read_text(encoding="utf-8")
    assert f"CODE_DEJA_EN_COURS={cli.CODE_DEJA_EN_COURS} " in texte
    assert '-eq "$CODE_DEJA_EN_COURS"' in texte
