"""Lecture déterministe de la base pour les journées : tâches datées, rendez-vous, sections."""

from datetime import date

from conftest import ecrire_journees, ecrire_note

from zettel.taches import agenda as ag

J01, J02, J03 = date(2026, 11, 1), date(2026, 11, 2), date(2026, 11, 3)


def base(chemins):
    ecrire_journees(chemins)
    return ag.lire_base()


def test_taches_datees(chemins):
    t = {x.texte: x for x in ag.taches_org(base(chemins))}
    doc = t["Écrire la doc"]
    assert (doc.ouverte, doc.prevue, doc.limite, doc.creee) == (True, J03, None, J02)
    assert t["Rendre le rapport"].limite == J01
    installer = t["Installer"]
    assert (installer.ouverte, installer.faite, installer.prevue) == (False, J02, J01)
    sans = t["Sans date"]
    assert (sans.prevue, sans.limite, sans.faite, sans.creee) == (None, None, None, None)
    assert t["Appeler le garage"].fichier.titre == "2026-11-02"


def test_mots_cles_du_fichier(chemins):
    p = ecrire_note(chemins, "k.org", "K", "K", "#+TODO: A_FAIRE | FINI\n* A_FAIRE Un\n"
                                               "* FINI Deux\nCLOSED: [2026-11-02 Mon 08:00]\n"
                                               "* TODO Pas un mot du fichier\n")
    t = {x.texte: x for x in ag.taches_org(ag.lire_base()) if x.fichier.path == p}
    assert t["Un"].ouverte and not t["Deux"].ouverte and t["Deux"].faite == J02
    assert "Pas un mot du fichier" not in t


def test_creees_le(chemins):
    creees = ag.creees_le(ag.taches_org(base(chemins)), J02)
    # :CREATED: du jour, ou tâche de la note journalière du jour (sans :CREATED:)
    assert {t.texte for t in creees} == {"Écrire la doc", "Appeler le garage"}


def test_rendez_vous(chemins):
    rdv = ag.rendez_vous(base(chemins), J03)
    assert [(r.heure, r.texte) for r in rdv] == [("13:30", "Coiffeur, site du travail"),
                                                  ("", "Anniversaire de Léa")]
    assert "[[file:" in rdv[0].org() and "/2026-11-03/" in rdv[0].org()
    # SCHEDULED et DEADLINE ne sont pas des rendez-vous
    assert ag.rendez_vous(ag.lire_base(), J01) == []


def test_rendez_vous_dans_un_titre(chemins):
    ecrire_note(chemins, "r.org", "R", "R", "* Dentiste <2026-11-05 Thu 9:00>\n")
    rdv = ag.rendez_vous(ag.lire_base(), date(2026, 11, 5))
    assert [(r.heure, r.texte) for r in rdv] == [("09:00", "Dentiste")]


def test_note_du_jour_et_section(chemins):
    b = base(chemins)
    assert ag.section(ag.note_du_jour(b, J02), "Journal") == [
        "- 15:27 Rendez-vous le 2026-11-03 à 13:30 : Coiffeur"]
    assert ag.note_du_jour(b, date(2026, 11, 9)) is None
    assert ag.section(None, "Journal") == []


def test_notes_du_jour(chemins):
    b = base(chemins)
    assert [(f.titre, k) for f, k in ag.notes_du_jour(b, J02)] == [
        ("Autre", ["complétée"]), ("Projet X", ["créée"])]
    assert [(f.titre, k) for f, k in ag.notes_du_jour(b, J01)] == [("Autre", ["créée"])]
    assert ag.notes_du_jour(b, J02)[1][0].lien() == "[[id:ID-P][Projet X]]"


def test_suivi_du_jour(chemins):
    assert [(f.titre, s) for f, s in ag.suivi_du_jour(base(chemins), J02)] == [
        ("Projet X", "Première version installée")]
