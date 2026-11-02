"""Tâches, suivi de projet, notes journalières."""

from datetime import date, datetime

import pytest

from conftest import ecrire_note
from zettel import config as cfg
from zettel.contenu import traiter_entree
from zettel.index import est_journaliere
from zettel.journal import date_entree
from zettel.contenu import PROMPT_EXTRACTION, SCHEMA_SUJETS
from zettel.suivi import date_valide, inserer_dans_section, lignes_todo, todo_existe
from zettel.taches.marquer_fait import clore
from zettel.taches.todos import todos_fichier

QUAND = datetime(2026, 11, 1, 17, 9)       # un dimanche


def test_date_entree():
    assert date_entree("- [2026-11-01 17:09:18] x") == datetime(2026, 11, 1, 17, 9, 18)
    assert date_entree("- [2026-11-01 17:09] x") == datetime(2026, 11, 1, 17, 9)
    assert date_entree("# Titre") is None


@pytest.mark.parametrize("texte, attendu", [
    ("2026-11-02", date(2026, 11, 2)),
    (" 2026-11-30 ", date(2026, 11, 30)),
    ("2026-02-30", None),          # date impossible
    ("demain", None),
    ("2031-01-01", None),          # trop loin : probablement une erreur
    ("", None),
])
def test_date_valide(texte, attendu):
    assert date_valide(texte, QUAND.date()) == attendu


CREATED = [":PROPERTIES:", ":CREATED:  [2026-11-01 Sun 17:09]", ":END:"]


def test_lignes_todo():
    assert lignes_todo({"texte": "Appeler", "date": "2026-11-02", "date_limite": False}, QUAND) \
        == ["** TODO Appeler", "SCHEDULED: <2026-11-02 Mon>", *CREATED]
    assert lignes_todo({"texte": "Rendre", "date": "2026-11-06", "date_limite": True}, QUAND)[1] \
        == "DEADLINE: <2026-11-06 Fri>"
    assert lignes_todo({"texte": "Lire", "date": "bientôt"}, QUAND) == ["** TODO Lire", *CREATED]


def test_todo_cree_puis_clos(chemins):
    """CLOSED se place sous le titre, avant le tiroir :CREATED:, comme dans org-mode."""
    p = chemins / "t.org"
    p.write_text("* Tâches\n" + "\n".join(lignes_todo({"texte": "Lire", "date": ""}, QUAND)) + "\n")
    t = todos_fichier(p)[0]
    assert clore(p.read_text().splitlines(), t, "DONE", datetime(2026, 11, 2, 9, 0)) == [
        "* Tâches", "** DONE Lire", "CLOSED: [2026-11-02 Mon 09:00]", *CREATED]


def test_inserer_dans_section():
    txt = "#+title: P\n\nIntro.\n\n* Tâches\n** TODO A\n\n* Suivi\n- x\n"
    assert inserer_dans_section(txt, "Tâches", ["** TODO B"]) == (
        "#+title: P\n\nIntro.\n\n* Tâches\n** TODO A\n** TODO B\n\n* Suivi\n- x\n")
    assert inserer_dans_section(txt, "Suivi", ["- y"]).endswith("* Suivi\n- x\n- y\n")
    assert inserer_dans_section("#+title: P\n\nIntro.\n\n", "Suivi", ["- y"]) == (
        "#+title: P\n\nIntro.\n\n* Suivi\n- y\n")
    # « ** Tâches » (niveau 2) n'est pas la section de niveau 1
    assert "* Tâches\n- z" in inserer_dans_section("* X\n** Tâches\n", "Tâches", ["- z"])


def test_todo_existe():
    txt = "* Tâches\n** TODO Appeler le garage :perso:\n** DONE Finir\n"
    assert todo_existe(txt, "appeler le garage")
    assert todo_existe(txt, "Finir")              # même fait : pas de doublon
    assert not todo_existe(txt, "Appeler")


def test_index_exclut_les_notes_journalieres(chemins):
    assert est_journaliere(chemins / cfg.DAILY_DIR / "2026-11-01.org")
    assert not est_journaliere(chemins / "daily-life.org")


def reponse(**kw):
    return {"sujets": [], "taches": [], "suivi": [], "perso": [], **kw}


def test_entree_projet_taches_suivi_perso(faux_llm, chemins, ctx):
    c = ctx(ecrire_note(chemins, "dm.org", "DM", "DM Gym", "Appli d'impro."))
    c.quand = QUAND
    faux_llm.reponses = [reponse(
        taches=[{"texte": "Ajouter un agent", "projet": "dm gym", "date": "", "date_limite": False},
                {"texte": "Appeler le garage", "projet": "", "date": "2026-11-02",
                 "date_limite": False},
                {"texte": "Écrire la doc", "projet": "Nouveau Projet", "date": "",
                 "date_limite": False}],
        suivi=[{"projet": "DM Gym", "texte": "Installée sur le téléphone"}],
        perso=["Rendez-vous chez le dentiste reporté"])]
    actions = traiter_entree("…", c)
    assert len(actions) == 5
    assert "Date de la dictée : 2026-11-01 (dimanche)" in faux_llm.appels[0][1]

    dm = (chemins / "dm.org").read_text()
    assert dm.startswith(":PROPERTIES:\n:ID:       DM\n:END:\n#+title: DM Gym\n\nAppli d'impro.")
    assert "* Tâches\n** TODO Ajouter un agent\n" in dm
    assert "* Suivi\n- [2026-11-01] Installée sur le téléphone\n" in dm

    jour = (chemins / cfg.DAILY_DIR / "2026-11-01.org").read_text()
    assert "#+title: 2026-11-01" in jour and ":ID:" in jour
    assert "* Tâches\n** TODO Appeler le garage\nSCHEDULED: <2026-11-02 Mon>" in jour
    assert "* Journal\n- 17:09 Rendez-vous chez le dentiste reporté" in jour

    nouveau = next(chemins.glob("*-nouveau_projet.org")).read_text()
    assert "#+filetags: :projet:" in nouveau and "** TODO Écrire la doc" in nouveau

    # les todos écrits sont retrouvés par lister_todos
    assert [t.texte for t in todos_fichier(chemins / cfg.DAILY_DIR / "2026-11-01.org")] == [
        "Appeler le garage"]

    # 2e passage identique : pas de TODO en double
    faux_llm.reponses = [reponse(taches=[{"texte": "Ajouter un agent", "projet": "DM Gym",
                                          "date": "", "date_limite": False}])]
    assert traiter_entree("…", c) == []
    assert (chemins / "dm.org").read_text().count("Ajouter un agent") == 1


def test_sujet_projet_recoit_le_tag_et_ses_taches_en_dry_run(faux_llm, chemins, ctx):
    c = ctx(dry_run=True)
    c.quand = QUAND
    faux_llm.reponses = [
        reponse(sujets=[{"titre": "DM Gym", "contenu": "Appli", "est_projet": True}],
                taches=[{"texte": "Ajouter un agent", "projet": "DM Gym", "date": "",
                         "date_limite": False}],
                perso=["Info"]),
        {"action": "creer", "cible_id": "", "titre": "DM Gym", "tags": ["android"],
         "contenu": "Appli", "liens": []},
    ]
    actions = traiter_entree("…", c)
    assert actions[0] == "+ créée : DM Gym"
    assert any("Ajouter un agent (DM Gym)" in a for a in actions)   # projet simulé retrouvé
    assert c.notes[-1].tags == ["projet", "android"]
    assert list(chemins.rglob("*.org")) == []                       # rien écrit


def test_fusion_des_sujets_de_meme_titre():
    from zettel.contenu import fusionner_sujets
    s = fusionner_sujets([{"titre": "DM Gym", "contenu": "But.", "est_projet": True},
                          {"titre": "Rust", "contenu": "R", "est_projet": False},
                          {"titre": "dm gym ", "contenu": "Idée.", "est_projet": False}])
    assert [x["titre"] for x in s] == ["DM Gym", "Rust"]
    assert s[0]["contenu"] == "But.\n\nIdée." and s[0]["est_projet"] is True


def test_perso_en_doublon_d_un_sujet_retire():
    from zettel.contenu import filtrer_perso
    r = {"sujets": [{"titre": "DM Gym"}], "taches": [{"projet": "photo-backup"}], "suivi": [],
         "perso": ["J'ai développé DM GYM ce week-end", "Le script photo-backup tourne",
                   "Rendez-vous chez le dentiste"]}
    assert filtrer_perso(r) == ["Rendez-vous chez le dentiste"]


# --- rendez-vous datés ---------------------------------------------------------------------

RDV = [{"texte": "Coiffeur, site du travail", "date": "2026-11-03", "heure": "13h30"},
       {"texte": "Dîner chez Paul", "date": "", "heure": ""}]


def test_schema_d_extraction_avec_rendez_vous():
    assert "rendez_vous" in SCHEMA_SUJETS["required"]
    assert "rendez_vous" in PROMPT_EXTRACTION


def test_rendez_vous_date_dans_l_agenda_du_jour(faux_llm, chemins, ctx):
    c = ctx()
    c.quand = datetime(2026, 11, 2, 15, 27)
    faux_llm.reponses = [reponse(rendez_vous=RDV)]
    actions = traiter_entree("…", c)
    assert any("Coiffeur" in a and "2026-11-03 à 13:30" in a for a in actions)

    demain = (chemins / cfg.DAILY_DIR / "2026-11-03.org").read_text()
    assert "#+title: 2026-11-03" in demain
    assert "* Agenda\n- <2026-11-03 Tue 13:30> Coiffeur, site du travail\n" in demain
    jour = (chemins / cfg.DAILY_DIR / "2026-11-02.org").read_text()
    assert "- 15:27 Rendez-vous le 2026-11-03 à 13:30 : Coiffeur, site du travail" in jour
    assert "- 15:27 Dîner chez Paul" in jour          # sans date : simple info perso

    # même dictée retraitée : ni l'agenda ni le journal ne reçoivent de doublon
    faux_llm.reponses = [reponse(rendez_vous=RDV[:1])]
    traiter_entree("…", c)
    assert (chemins / cfg.DAILY_DIR / "2026-11-03.org").read_text().count("Coiffeur") == 1
    assert (chemins / cfg.DAILY_DIR / "2026-11-02.org").read_text().count("Coiffeur") == 1


def test_rendez_vous_en_dry_run(faux_llm, chemins, ctx):
    c = ctx(dry_run=True)
    c.quand = datetime(2026, 11, 2, 15, 27)
    faux_llm.reponses = [reponse(rendez_vous=RDV)]
    assert any("Coiffeur" in a for a in traiter_entree("…", c))
    assert not (chemins / cfg.DAILY_DIR).exists()
