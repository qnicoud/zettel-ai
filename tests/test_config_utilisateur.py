"""Fichier de configuration utilisateur (~/.config/zettel-ai/config.toml)."""

from pathlib import Path

import pytest

from zettel import config as cfg
from zettel import config_utilisateur as cu

EXEMPLE = Path(__file__).resolve().parent.parent / "config.exemple.toml"


def ecrire(tmp_path: Path, texte: str) -> Path:
    chemin = tmp_path / "config.toml"
    chemin.write_text(texte, encoding="utf-8")
    return chemin


def test_fichier_absent_ne_change_rien(tmp_path):
    assert cu.lire(tmp_path / "absent.toml") == {}


def test_valeurs_simples(tmp_path):
    valeurs = cu.lire(ecrire(tmp_path, """
[ollama]
url = "http://serveur:11434/"
think = true
temperature = 0.5
contexte = 8192
[chemins]
journaux = ["~/journal.md"]
"""))
    assert valeurs == {"OLLAMA_BASE": "http://serveur:11434", "THINK": True,
                       "TEMPERATURE": 0.5, "NUM_CTX": 8192,
                       "JOURNAUX": (Path.home() / "journal.md",)}


def test_lire_ne_modifie_pas_la_config(tmp_path):
    avant = cfg.THINK
    cu.lire(ecrire(tmp_path, "[ollama]\nthink = true\n"))
    assert cfg.THINK == avant


def test_noms_propres_et_corrections_s_ajoutent(tmp_path):
    valeurs = cu.lire(ecrire(tmp_path, """
[transcription]
noms_propres = ["Zettelkasten", "Rust"]
[transcription.corrections]
"zettel casten" = "Zettelkasten"
"""))
    assert valeurs["NOMS_PROPRES"][:len(cfg.NOMS_PROPRES)] == tuple(cfg.NOMS_PROPRES)
    assert valeurs["NOMS_PROPRES"].count("Rust") == 1          # pas de doublon
    assert valeurs["NOMS_PROPRES"][-1] == "Zettelkasten"
    assert valeurs["CORRECTIONS_TRANSCRIPTION"]["zettel casten"] == "Zettelkasten"
    assert valeurs["CORRECTIONS_TRANSCRIPTION"]["Cloud Code"] == "Claude Code"


def test_mots_todo_remplacent(tmp_path):
    valeurs = cu.lire(ecrire(tmp_path, '[todo]\nmots_ouverts = ["TODO", "NEXT"]\n'))
    assert valeurs["TODO_OUVERTS"] == ("TODO", "NEXT")


@pytest.mark.parametrize("texte, message", [
    ("[ollama]\nmodel = 'x'\n", "ollama.model"),                   # clé inconnue
    ("[olama]\nurl = 'http://x'\n", "olama"),                      # section inconnue
    ("think = true\n", "think"),                                    # hors section
    ("[ollama]\nthink = 'oui'\n", "booléen"),
    ("[ollama]\ncontexte = true\n", "entier"),
    ("[ollama]\ncontexte = 0\n", "positif"),
    ("[ollama]\ntemperature = 3\n", "entre 0 et 2"),
    ("[ollama]\nurl = 'localhost:11434'\n", "http"),
    ("[ollama]\nmodele = ''\n", "vide"),
    ("[transcription]\nnoms_propres = 'Rust'\n", "liste"),
    ("[transcription.corrections]\na = 1\n", "texte"),
    ("[ollama\n", "TOML"),
])
def test_erreurs_claires(tmp_path, texte, message):
    with pytest.raises(cu.ErreurConfig, match=message):
        cu.lire(ecrire(tmp_path, texte))


def test_appliquer(monkeypatch):
    monkeypatch.setattr(cfg, "THINK", False)
    cu.appliquer({"THINK": True})
    assert cfg.THINK is True


def test_chemin_config(monkeypatch, tmp_path):
    monkeypatch.delenv("ZETTEL_AI_CONFIG", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert cu.chemin_config() == tmp_path / "zettel-ai" / "config.toml"
    monkeypatch.setenv("ZETTEL_AI_CONFIG", str(tmp_path / "autre.toml"))
    assert cu.chemin_config() == tmp_path / "autre.toml"


def test_charger_signale_le_fichier_en_erreur(monkeypatch, tmp_path):
    chemin = ecrire(tmp_path, "[ollama]\nthink = 'oui'\n")
    monkeypatch.setenv("ZETTEL_AI_CONFIG", str(chemin))
    with pytest.raises(SystemExit, match=str(chemin)):
        cu.charger()


def test_exemple_valide_et_complet():
    texte = EXEMPLE.read_text(encoding="utf-8")
    cu.lire(EXEMPLE)                                   # aucune erreur
    for section, cle in cu.SCHEMA:                     # chaque réglage y est documenté
        assert f"{cle} =" in texte or f"[{section}.{cle}]" in texte, f"{section}.{cle}"
