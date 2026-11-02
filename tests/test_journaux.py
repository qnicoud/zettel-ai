"""Plusieurs journaux sources (PC, téléphone…) : chemins, fusion, fichiers absents."""

import sys
from pathlib import Path

import pytest

from zettel import cli
from zettel import config as cfg
from zettel import config_utilisateur as cu
from zettel.journal import chemins_journaux, horodatages_en_double, lire_journaux


def ecrire(path: Path, texte: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(texte, encoding="utf-8")
    return path


# --- chemins -------------------------------------------------------------------------------

def test_chemin_relatif_resolu_depuis_la_base(chemins, monkeypatch):
    monkeypatch.setattr(cfg, "JOURNAUX", (Path("journal/pc.md"), Path("/abs/tel.md")))
    assert chemins_journaux() == (cfg.ROAM_DIR / "journal/pc.md", Path("/abs/tel.md"))


def test_par_defaut_un_journal_hors_de_la_base():
    """Le journal brut ne doit pas finir versionné (et poussé) avec la base."""
    assert cfg.JOURNAUX == (Path.home() / "Documents" / "journal-dictee.md",)
    assert not any(p.is_relative_to(cfg.ROAM_DIR) for p in cfg.JOURNAUX)


# --- lecture et fusion ---------------------------------------------------------------------

def test_fusion_chronologique(tmp_path):
    pc = ecrire(tmp_path / "pc.md", "- [2026-11-01 08:00:00] matin PC\n"
                                    "- [2026-11-01 20:00:00] soir PC\n")
    tel = ecrire(tmp_path / "tel.md", "- [2026-11-01 12:00:00] midi téléphone\n")
    entrees, absents = lire_journaux((pc, tel))
    assert [e.split("] ")[1] for e in entrees] == ["matin PC", "midi téléphone", "soir PC"]
    assert absents == []


def test_entree_sans_horodatage_gardee_en_fin(tmp_path):
    pc = ecrire(tmp_path / "pc.md", "# Titre libre\ntexte\n- [2026-11-01 08:00:00] daté\n")
    entrees, _ = lire_journaux((pc,))
    assert entrees[0].startswith("- [2026-11-01 08:00:00]")
    assert entrees[1].startswith("# Titre libre")


def test_fichier_absent_signale_sans_bloquer(tmp_path):
    pc = ecrire(tmp_path / "pc.md", "- [2026-11-01 08:00:00] bonjour\n")
    entrees, absents = lire_journaux((pc, tmp_path / "absent.md"))
    assert len(entrees) == 1
    assert absents == [tmp_path / "absent.md"]


def test_horodatages_en_double():
    entrees = ["- [2026-11-01 08:00:00] a", "- [2026-11-01 08:00:00] b",
               "- [2026-11-01 09:00:00] c", "# sans horodatage"]
    assert horodatages_en_double(entrees) == ["2026-11-01 08:00:00"]


# --- CLI -----------------------------------------------------------------------------------

def test_lister_lit_tous_les_journaux(chemins, tmp_path, monkeypatch, capsys):
    pc = ecrire(tmp_path / "pc.md", "- [2026-11-01 08:00:00] depuis le PC\n")
    tel = ecrire(tmp_path / "tel.md", "- [2026-11-01 09:00:00] depuis le téléphone\n")
    monkeypatch.setattr(cfg, "JOURNAUX", (pc, tel))
    monkeypatch.setattr(sys, "argv", ["zettel-ai", "--lister"])
    cli.main()
    sortie = capsys.readouterr()
    assert "depuis le PC" in sortie.out and "depuis le téléphone" in sortie.out
    assert sortie.err == ""


def test_journal_absent_avertit(chemins, tmp_path, monkeypatch, capsys):
    pc = ecrire(tmp_path / "pc.md", "- [2026-11-01 08:00:00] bonjour\n")
    monkeypatch.setattr(cfg, "JOURNAUX", (pc, tmp_path / "absent.md"))
    monkeypatch.setattr(sys, "argv", ["zettel-ai", "--lister"])
    cli.main()
    sortie = capsys.readouterr()
    assert "bonjour" in sortie.out
    assert "absent.md" in sortie.err


def test_tous_les_journaux_absents_arrete(chemins, tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "JOURNAUX", (tmp_path / "a.md", tmp_path / "b.md"))
    monkeypatch.setattr(sys, "argv", ["zettel-ai", "--lister"])
    with pytest.raises(SystemExit) as e:
        cli.main()
    assert "Aucun journal" in str(e.value.code)


def test_horodatage_en_double_avertit(chemins, tmp_path, monkeypatch, capsys):
    pc = ecrire(tmp_path / "pc.md", "- [2026-11-01 08:00:00] PC\n")
    tel = ecrire(tmp_path / "tel.md", "- [2026-11-01 08:00:00] téléphone\n")
    monkeypatch.setattr(cfg, "JOURNAUX", (pc, tel))
    monkeypatch.setattr(sys, "argv", ["zettel-ai", "--lister"])
    cli.main()
    assert "2026-11-01 08:00:00" in capsys.readouterr().err


# --- config utilisateur --------------------------------------------------------------------

def test_config_journaux(tmp_path):
    f = ecrire(tmp_path / "config.toml",
               '[chemins]\njournaux = ["~/pc.md", "journal/tel.md"]\n')
    assert cu.lire(f) == {"JOURNAUX": (Path.home() / "pc.md", Path("journal/tel.md"))}


@pytest.mark.parametrize("valeur", ['"~/pc.md"', "[]", '[""]', "[1]"])
def test_config_journaux_invalide(tmp_path, valeur):
    f = ecrire(tmp_path / "config.toml", f"[chemins]\njournaux = {valeur}\n")
    with pytest.raises(cu.ErreurConfig):
        cu.lire(f)


def test_ancienne_cle_journal_refusee(tmp_path):
    f = ecrire(tmp_path / "config.toml", '[chemins]\njournal = "~/pc.md"\n')
    with pytest.raises(cu.ErreurConfig, match="journaux"):
        cu.lire(f)
