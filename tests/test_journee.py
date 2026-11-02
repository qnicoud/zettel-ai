"""Tâches « bilan_journee » et « preparer_journee » (lecture seule)."""

from datetime import datetime

import pytest
from conftest import ecrire_journees

from zettel import config as cfg
from zettel.taches import TACHES

QUAND = datetime(2026, 11, 2, 18, 0)       # un lundi


def bloc_de(resultat: str, titre: str) -> str:
    """Contenu du bloc « titre… : » du résultat (blocs séparés par une ligne vide)."""
    for b in resultat.split("\n\n"):
        if b.startswith(titre):
            return b
    return ""


@pytest.fixture
def c(ctx, chemins):
    ecrire_journees(chemins)
    x = ctx()
    x.quand = QUAND
    return x


def test_taches_inscrites_en_lecture_seule():
    for nom in ("bilan_journee", "preparer_journee"):
        assert nom in TACHES and not TACHES[nom].ecrit


# --- préparation ---------------------------------------------------------------------------

def test_preparer_demain_sans_llm(faux_llm, c):
    r = TACHES["preparer_journee"].executer("prépare ma journée de demain", "", c)
    assert faux_llm.appels == []                       # date reconnue par le code
    assert r.startswith("Programme du mardi 3 novembre 2026")
    rdv = bloc_de(r, "Rendez-vous")
    assert "- 13:30 Coiffeur, site du travail" in rdv and "Anniversaire de Léa" in rdv
    assert "Écrire la doc" in bloc_de(r, "À faire ce jour-là")
    assert "Rendre le rapport" in bloc_de(r, "En retard")
    autres = bloc_de(r, "Autres tâches ouvertes")
    assert autres.startswith("Autres tâches ouvertes (2)")
    assert "Sans date" in autres and "Appeler le garage" in autres
    assert "Écrire la doc" not in autres               # déjà dans le focus
    assert "Installer" not in r                        # terminée


def test_preparer_sans_date_demande_au_llm(faux_llm, c):
    faux_llm.reponses = [{"date": ""}]                 # aucune journée désignée : aujourd'hui
    r = TACHES["preparer_journee"].executer("prépare ma journée", "", c)
    assert "Date du jour : 2026-11-02" in faux_llm.appels[0][1]
    assert r.startswith("Programme du lundi 2 novembre 2026")
    assert "Coiffeur" in bloc_de(r, "Notes du jour")
    assert "Rendre le rapport" in bloc_de(r, "En retard")


def test_date_du_llm_hors_limites_refusee(faux_llm, c):
    faux_llm.reponses = [{"date": "2031-01-01"}]
    assert TACHES["preparer_journee"].executer("prépare la fête", "", c).startswith("Refusé")


# --- bilan ---------------------------------------------------------------------------------

def test_bilan(faux_llm, c, tmp_path, monkeypatch):
    journal = tmp_path / "journal.md"
    journal.write_text("- [2026-11-01 20:00:00] la veille\n"
                       "- [2026-11-02 15:27:49] Demain coiffeur à 13h30.\n"
                       "- [2026-11-02 16:00:00] Instruction : liste mes todos\n", encoding="utf-8")
    monkeypatch.setattr(cfg, "JOURNAUX", (journal,))
    faux_llm.reponses = [{"resume": "Tu as pris rendez-vous chez le coiffeur."}]
    r = TACHES["bilan_journee"].executer("fais le bilan d'aujourd'hui", "", c)

    prompt = faux_llm.appels[0][1]
    assert "15:27 Demain coiffeur à 13h30." in prompt
    assert "- 15:27 Rendez-vous le 2026-11-03 à 13:30 : Coiffeur" in prompt
    assert "la veille" not in prompt and "liste mes todos" not in prompt

    assert r.startswith("Bilan du lundi 2 novembre 2026\n\nTu as pris rendez-vous chez le coiffeur.")
    creees = bloc_de(r, "Tâches créées")
    assert "Écrire la doc" in creees and "Appeler le garage" in creees
    assert "Installer" in bloc_de(r, "Tâches terminées")
    notes = bloc_de(r, "Notes créées ou complétées")
    assert "- [[id:ID-P][Projet X]] : créée" in notes and "- [[id:ID-A][Autre]] : complétée" in notes
    assert "- Projet X : Première version installée" in bloc_de(r, "Suivi des projets")
    assert bloc_de(r, "Tâches prévues ou à rendre") == ""     # rien d'échu ce jour-là


def test_bilan_d_une_journee_vide_sans_llm(faux_llm, c, tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "JOURNAUX", (tmp_path / "absent.md",))
    r = TACHES["bilan_journee"].executer("bilan du 15 octobre", "", c)
    assert faux_llm.appels == []
    assert r == "Bilan du jeudi 15 octobre 2026\n\nRien de noté pour cette journée."
