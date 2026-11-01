"""marquer_fait, renommer, lier, fusionner, glossaire, --lister / --entree."""

import re
from datetime import datetime
from pathlib import Path

import pytest

from conftest import ecrire_note
from zettel import config as cfg
from zettel import journal
from zettel.structure import ajouter_alias, decouper, lire_alias
from zettel.taches import executer_consigne
from zettel.taches.marquer_fait import clore, mot_final
from zettel.taches.todos import Todo, todos_fichier


# --- glossaire -------------------------------------------------------------
def test_corrections_de_transcription():
    assert journal.corriger_transcription(
        "J'utilise HyperCTL sous hyperland avec cloud code, pas Hyperlandia.") == \
        "J'utilise hyprctl sous Hyprland avec Claude Code, pas Hyperlandia."


# --- --lister / --entree ---------------------------------------------------
ENTREES = ["- [2026-11-01 10:00:00] Rust est compilé",
           "- [2026-11-01 14:59:28] Instruction : liste mes todos",
           "- [2026-11-02 09:00:00] Autre jour"]


def test_selectionner():
    assert journal.selectionner(ENTREES, ["2"]) == [ENTREES[1]]
    assert journal.selectionner(ENTREES, ["2026-11-01"]) == ENTREES[:2]
    assert journal.selectionner(ENTREES, ["3", "2026-11-01 10"]) == [ENTREES[0], ENTREES[2]]
    with pytest.raises(ValueError, match="2025"):
        journal.selectionner(ENTREES, ["2025"])


def test_lister():
    sortie = journal.lister(ENTREES, {journal.empreinte(ENTREES[0])}).splitlines()
    assert sortie[0].startswith("  1  2026-11-01 10:00:00  ✔ traitée   contenu")
    assert "• nouvelle  instruction" in sortie[1]


# --- marquer_fait ----------------------------------------------------------
def test_clore_ajoute_closed_et_garde_le_planning():
    lignes = ["* Tâches", "** TODO Appeler", "SCHEDULED: <2026-11-02 Mon>", "** TODO Lire"]
    p, quand = Path("x.org"), datetime(2026, 11, 2, 18, 30)
    a = clore(lignes, Todo("TODO", "Appeler", "N", p, 2), "DONE", quand)
    assert a[1:3] == ["** DONE Appeler", "CLOSED: [2026-11-02 Mon 18:30] SCHEDULED: <2026-11-02 Mon>"]
    b = clore(lignes, Todo("TODO", "Lire", "N", p, 4), "KILL", quand)
    assert b[3:] == ["** KILL Lire", "CLOSED: [2026-11-02 Mon 18:30]"]
    with pytest.raises(ValueError, match="a changé"):
        clore(lignes, Todo("TODO", "Lire", "N", p, 3), "DONE", quand)


def test_mot_final():
    assert mot_final("rien", False) == cfg.MOT_FAIT and mot_final("rien", True) == cfg.MOT_ABANDON
    assert mot_final("#+TODO: A B | FINI ANNULE\n", True) == "ANNULE"


def test_marquer_fait(faux_llm, chemins, ctx):
    p = ecrire_note(chemins, "dm.org", "DM", "DM Gym",
                    "* Tâches\n** TODO Ajouter un agent\n** TODO Écrire la doc\n")
    faux_llm.reponses = [{"tache": "marquer_fait", "sujet": ""},
                         {"numeros": [1, 99], "etat": "fait"}]
    _, msg = executer_consigne("j'ai fini l'agent de DM Gym", ctx(p))
    assert "DONE Ajouter un agent" in msg
    assert [t.texte for t in todos_fichier(p)] == ["Écrire la doc"]
    assert re.search(r"\*\* DONE Ajouter un agent\nCLOSED: \[\d{4}-\d\d-\d\d \w{3} \d\d:\d\d\]",
                     p.read_text())


def test_marquer_fait_sans_correspondance(faux_llm, chemins, ctx):
    ecrire_note(chemins, "dm.org", "DM", "DM Gym", "* Tâches\n** TODO Ajouter un agent\n")
    faux_llm.reponses = [{"tache": "marquer_fait", "sujet": ""}, {"numeros": [], "etat": "fait"}]
    assert executer_consigne("j'ai fini le ménage", ctx())[1].startswith("Refusé")


# --- renommer --------------------------------------------------------------
def test_renommer(faux_llm, chemins, ctx):
    a = ecrire_note(chemins, "a.org", "A", "Programming Languages", "Texte.")
    b = ecrire_note(chemins, "b.org", "B", "Python", "Un [[id:A][Programming Languages]], "
                    "un [[id:A][langage]].")
    faux_llm.reponses = [{"tache": "renommer", "sujet": ""},
                         {"note_id": "A", "nouveau_titre": "Langages de programmation"}]
    c = ctx(a, b)
    assert executer_consigne("renomme Programming Languages", c)[1].startswith("Fait")
    txt = a.read_text()
    assert "#+title: Langages de programmation" in txt
    assert lire_alias(txt) == ["Programming Languages"]
    assert b.read_text().endswith("Un [[id:A][Langages de programmation]], un [[id:A][langage]].")
    assert len(c.lot_remaniement.fichiers) == 2


def test_renommer_titre_pris(faux_llm, chemins, ctx):
    c = ctx(ecrire_note(chemins, "a.org", "A", "A1", ""), ecrire_note(chemins, "b.org", "B", "B1", ""))
    faux_llm.reponses = [{"tache": "renommer", "sujet": ""}, {"note_id": "A", "nouveau_titre": "b1"}]
    assert "déjà pris" in executer_consigne("renomme A1 en B1", c)[1]


# --- lier ------------------------------------------------------------------
def test_lier(faux_llm, chemins, ctx):
    a = ecrire_note(chemins, "a.org", "A", "Rust", "Texte.\n\n* Source\n- s\n")
    c = ctx(a, ecrire_note(chemins, "b.org", "B", "Kotlin", ""))
    faux_llm.reponses = [{"tache": "lier", "sujet": ""},
                         {"source_id": "A", "cible_id": "B", "raison": "deux langages compilés"}]
    assert executer_consigne("lie Rust à Kotlin", c)[1].startswith("Fait")
    assert "* Liens\n- [[id:B][Kotlin]] : deux langages compilés\n\n* Source" in a.read_text()
    faux_llm.reponses = [{"tache": "lier", "sujet": ""},
                         {"source_id": "A", "cible_id": "B", "raison": "x"}]
    assert "déjà" in executer_consigne("lie Rust à Kotlin", c)[1]


# --- fusionner -------------------------------------------------------------
def test_fusionner(faux_llm, chemins, ctx):
    a = ecrire_note(chemins, "a.org", "A", "Rust", "Rust est compilé.\n\n* Liens\n"
                    "- [[id:P][Programming Languages]] : catégorie\n\n* Source\n- sa\n")
    b = ecrire_note(chemins, "b.org", "B", "Rust lang", "Voir [[id:A][Rust]]. Ownership.\n\n"
                    "* Liens\n- [[id:P][Programming Languages]] : doublon\n- [[id:K][Kotlin]] : voisin\n"
                    "- [[id:A][Rust]] : soi\n\n* Tâches\n** TODO Lire le livre\n\n* Source\n- sb\n")
    p = ecrire_note(chemins, "p.org", "P", "Programming Languages", "Voir [[id:B][Rust lang]].")
    k = ecrire_note(chemins, "k.org", "K", "Kotlin", "")
    c = ctx(a, b, p, k)
    faux_llm.reponses = [{"tache": "fusionner", "sujet": ""}, {"garder_id": "A", "absorber_id": "B"}]
    assert executer_consigne("fusionne Rust lang dans Rust", c)[1].startswith("Fait")
    txt = a.read_text()
    assert not b.exists() and "B" not in c.ids
    assert lire_alias(txt) == ["Rust lang"]
    d = decouper(txt)
    assert "\n".join(d.corps).strip() == "Rust est compilé.\n\nVoir Rust. Ownership."
    sections = dict(d.sections)
    assert [l for l in sections["Liens"] if l] == [
        "- [[id:P][Programming Languages]] : catégorie", "- [[id:K][Kotlin]] : voisin"]
    assert "** TODO Lire le livre" in sections["Tâches"]
    assert [l for l in sections["Source"] if l] == ["- sa", "- sb"]
    assert [s for s, _ in d.sections][-1] == "Source"
    assert p.read_text().endswith("Voir [[id:A][Rust lang]].")       # lien redirigé
    assert b in c.lot_remaniement.fichiers


def test_ajouter_alias_existant():
    txt = ':PROPERTIES:\n:ID:       X\n:ROAM_ALIASES: "Un"\n:END:\n#+title: T\n'
    assert lire_alias(ajouter_alias(txt, ["Deux", "Un"])) == ["Un", "Deux"]


# --- suivi des entrées par horodatage --------------------------------------
def test_suivi_par_horodatage():
    e = "- [2026-11-01 14:59:28] Rust est compilé"
    corrigee = "- [2026-11-01 14:59:28] Rust est un langage compilé"     # faute corrigée
    assert journal.cle_entree(e) == "horodatage:2026-11-01 14:59:28"
    etat = {journal.cle_entree(e)}
    assert journal.est_traitee(corrigee, etat)                          # pas retraitée
    assert not journal.est_traitee("- [2026-11-01 15:00:00] Rust est compilé", etat)
    assert journal.est_traitee(e, {journal.empreinte(e)})               # ancien état reconnu
    assert journal.cle_entree("# Titre\ntexte") == journal.empreinte("# Titre\ntexte")
