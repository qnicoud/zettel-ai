"""Tests sans Ollama ni git : faux LLM, fichiers temporaires."""

import pytest

from conftest import ecrire_note
from zettel import config as cfg
from zettel import journal
from zettel.contenu import valider
from zettel.pipeline import traiter_journal
from zettel.rapport import Rapport, abaisser_titres
from zettel.taches import executer_consigne
from zettel.taches.extraire import valider_plages
from zettel.taches.todos import mots_ouverts, todos_fichier

NOTE_HYPR = (":PROPERTIES:\n:ID:       SRC\n:END:\n#+title: Notes\n\nIntro.\n\n"
             "* Hyprbinds\nProgramme.\nRaccourcis.\n\n* Autre\nX\n")


# --- journal ---------------------------------------------------------------
def test_decoupe_par_horodatage_et_titres():
    texte = "# T\nligne\n- [2026-01-01 10:00:00] a\nsuite\n- [2026-01-01 11:00] b"
    e = journal.entrees_journal(texte)
    assert e == ["# T\nligne", "- [2026-01-01 10:00:00] a\nsuite", "- [2026-01-01 11:00] b"]
    assert journal.source_entree(e[1]) == "2026-01-01 10:00:00"
    assert journal.texte_entree(e[1]) == "a\nsuite"


@pytest.mark.parametrize("texte, attendu", [
    ("Instruction : sors hyprbinds", "sors hyprbinds"),
    ("instruction, liste mes todos", "liste mes todos"),
    ("Une instruction ici", None),
    ("Instructif", None),
])
def test_declencheur_instruction(texte, attendu):
    assert journal.consigne_instruction(texte) == attendu


# --- contenu ordinaire -----------------------------------------------------
def test_valider_titre_existant_devient_complement_et_liens_nettoyes(chemins, ctx):
    c = ctx(ecrire_note(chemins, "a.org", "A", "Rust", "x"),
            ecrire_note(chemins, "b.org", "B", "Compiled language", "y"))
    d = valider({"action": "creer", "cible_id": "", "titre": "rust", "tags": [],
                 "contenu": "Un [[id:B][langage compilé]], [[id:Z][faux]], [[id:A][soi]]",
                 "liens": [{"id": "B", "raison": "r"}, {"id": "Z", "raison": "r"}]}, c.ids)
    assert d["action"] == "completer" and d["cible_id"] == "A"
    assert d["contenu"] == "Un [[id:B][langage compilé]], faux, soi"
    assert d["liens"] == []          # B déjà lié dans le texte, Z inventé


# --- routeur ---------------------------------------------------------------
def test_routeur_tache_inconnue(faux_llm, ctx):
    faux_llm.reponses = [{"tache": "inconnue", "sujet": ""}]
    nom, msg = executer_consigne("fais le café", ctx())
    assert nom == "inconnue" and "non prise en charge" in msg


def test_routeur_tache_qui_ecrit_isole_ses_commits(faux_llm, chemins, ctx):
    c = ctx(ecrire_note(chemins, "n.org", "SRC", "Notes", ""))
    faux_llm.reponses = [{"tache": "extraire", "sujet": ""},
                         {"source_id": "FAUX", "nouveau_titre": "H", "sujet": "h"}]
    nom, msg = executer_consigne("sors H", c)
    assert nom == "extraire" and msg.startswith("Refusé")
    assert c.lot_notes.commits == 1 and c.lot_remaniement.commits == 1


# --- extraire --------------------------------------------------------------
@pytest.mark.parametrize("plages, erreur", [
    ([{"debut": 2, "fin": 9}], "en-tête"),
    ([{"debut": 8, "fin": 10}, {"debut": 10, "fin": 11}], "chevauchent"),
    ([{"debut": 8, "fin": 99}], "hors"),
    ([], "aucune"),
])
def test_plages_refusees(plages, erreur):
    with pytest.raises(ValueError, match=erreur):
        valider_plages(plages, NOTE_HYPR.splitlines())


def test_extraire_deplace_mot_pour_mot(faux_llm, chemins, ctx):
    src = chemins / "n.org"
    src.write_text(NOTE_HYPR, encoding="utf-8")
    c = ctx(src)
    faux_llm.reponses = [
        {"tache": "extraire", "sujet": "hyprbinds"},
        {"source_id": "SRC", "nouveau_titre": "Hyprbinds", "sujet": "hyprbinds"},
        {"plages": [{"debut": 8, "fin": 10}], "intro": "Outil, issu de [[id:SRC][Notes]].",
         "tags": ["outil"]},
    ]
    _, msg = executer_consigne("sors hyprbinds de Notes", c)
    assert msg.startswith("Fait")
    nouvelle = next(p for p in chemins.glob("*hyprbinds*.org")).read_text()
    assert "Programme.\nRaccourcis." in nouvelle
    assert "* Hyprbinds" not in nouvelle            # titre en doublon retiré
    assert "* Liens" not in nouvelle                # lien vers la source déjà dans l'intro
    reste = src.read_text()
    assert "Programme." not in reste and "Voir [[id:" in reste and "* Autre" in reste
    assert len(c.lot_remaniement.fichiers) == 2


def test_extraire_dry_run_n_ecrit_rien(faux_llm, chemins, ctx):
    src = chemins / "n.org"
    src.write_text(NOTE_HYPR, encoding="utf-8")
    faux_llm.reponses = [
        {"tache": "extraire", "sujet": ""},
        {"source_id": "SRC", "nouveau_titre": "Hyprbinds", "sujet": "h"},
        {"plages": [{"debut": 8, "fin": 10}], "intro": "x", "tags": []},
    ]
    _, msg = executer_consigne("sors hyprbinds", ctx(src, dry_run=True))
    assert msg.startswith("Simulation")
    assert src.read_text() == NOTE_HYPR and len(list(chemins.glob("*.org"))) == 1


# --- todos -----------------------------------------------------------------
def test_mots_ouverts():
    assert "TODO" in mots_ouverts("rien")
    assert mots_ouverts("#+TODO: TODO(t) EN-COURS | FINI\n") == {"TODO", "EN-COURS"}
    assert mots_ouverts("#+TODO: A B C\n") == {"A", "B"}   # sans « | » : C = état final


def test_todos_fichier(chemins):
    p = ecrire_note(chemins, "t.org", "T", "Projet Rust",
                    "* TODO Lire le livre :rust:\nDEADLINE: <2026-11-10 mar.>\n"
                    "* DONE Installer\n* Pas un todo\n** NEXT Écrire un test\n")
    t = todos_fichier(p)
    assert [(x.etat, x.texte, x.echeance) for x in t] == [
        ("TODO", "Lire le livre", "DEADLINE <2026-11-10 mar.>"),
        ("NEXT", "Écrire un test", ""),
    ]
    assert t[0].note == "Projet Rust" and t[0].ligne == 6


def test_lister_todos_filtre_par_sujet(faux_llm, chemins, ctx):
    ecrire_note(chemins, "t.org", "T", "Projet", "* TODO Rust\n* TODO Python\n")
    faux_llm.reponses = [{"tache": "lister_todos", "sujet": "Rust"}, {"numeros": [1, 1, 7]}]
    _, msg = executer_consigne("mes todos Rust", ctx())
    assert msg.startswith("1 todo(s) ouvert(s) sur « Rust »")
    assert "TODO Rust" in msg and "Python" not in msg


# --- résumé ----------------------------------------------------------------
def test_resume_ne_cite_que_des_notes_fournies(faux_llm, chemins, ctx):
    c = ctx(ecrire_note(chemins, "r.org", "R", "Rust", "Langage compilé."))
    faux_llm.reponses = [{"tache": "resumer", "sujet": "Rust"},
                         {"resume": "Rust est compilé.", "notes_utilisees": ["rust", "Inventée"]}]
    _, msg = executer_consigne("résume Rust", c)
    assert "Rust est compilé." in msg and "[[id:R][Rust]]" in msg and "Inventée" not in msg
    assert "Langage compilé." in faux_llm.appels[-1][1]     # le texte de la note est envoyé


# --- rapport + pipeline ----------------------------------------------------
def test_rapport(chemins):
    assert Rapport().publier() is None
    r = Rapport()
    r.ajouter("Vide", "  ")
    r.ajouter("Résumé", "* Titre\ntexte")
    p = r.publier()
    assert p.parent == cfg.RAPPORTS_DIR
    assert "* Résumé\n** Titre\ntexte" in p.read_text() and "Vide" not in p.read_text()
    assert abaisser_titres("** a\n*gras*") == "*** a\n*gras*"


def test_pipeline_journal(faux_llm, chemins, ctx):
    ecrire_note(chemins, "t.org", "T", "Projet", "* TODO Rust\n")
    c = ctx()
    entrees = ["- [2026-11-01 10:00:00] Instruction : liste mes todos",
               "- [2026-11-01 11:00:00] Rien de notable aujourd'hui."]
    faux_llm.reponses = [{"tache": "lister_todos", "sujet": ""}, {"sujets": []}]
    rapport, etat = Rapport(), set()
    traiter_journal(entrees, etat, c, rapport)
    assert len(etat) == 2 and journal.charger_etat() == etat
    assert len(rapport.sections) == 1           # l'entrée sans sujet ne produit rien
    titre, texte = rapport.sections[0]
    assert "lister_todos" in titre and "TODO Rust" in texte


# --- contenu ordinaire de bout en bout -------------------------------------
def test_entree_cree_puis_complete_la_note_simulee_en_dry_run(faux_llm, chemins, ctx):
    from zettel.contenu import traiter_entree
    c = ctx(ecrire_note(chemins, "c.org", "C", "Compiled language", "y"), dry_run=True)
    creer = {"action": "creer", "cible_id": "", "titre": "Rust", "tags": ["rust"],
             "contenu": "Un [[id:C][langage compilé]].", "liens": []}
    faux_llm.reponses = [{"sujets": [{"titre": "Rust", "contenu": "a"}]}, creer,
                         {"sujets": [{"titre": "Rust", "contenu": "b"}]}, {**creer, "contenu": "Ownership."}]
    assert traiter_entree("Rust est compilé", c) == ["+ créée : Rust"]
    # 2e entrée : même titre -> complément de la note simulée, pas de doublon
    assert traiter_entree("Rust a l'ownership", c) == ["~ complétée : Rust"]
    assert len(list(chemins.glob("*.org"))) == 1          # rien écrit sur disque


def test_entree_ecrit_et_complete(faux_llm, chemins, ctx):
    from zettel.contenu import traiter_entree
    c = ctx(ecrire_note(chemins, "c.org", "C", "Compiled language", "y"))
    faux_llm.reponses = [
        {"sujets": [{"titre": "Rust", "contenu": "a"}, {"titre": "Compiled", "contenu": "b"},
                    {"titre": "Bof", "contenu": "c"}]},
        {"action": "creer", "cible_id": "", "titre": "Rust", "tags": ["Rust lang"],
         "contenu": "Un [[id:C][langage compilé]].", "liens": [{"id": "C", "raison": "r"}]},
        {"action": "completer", "cible_id": "C", "titre": "", "tags": [],
         "contenu": "Exemple : Rust.", "liens": []},
        {"action": "ignorer", "cible_id": "", "titre": "Bof", "tags": [], "contenu": "", "liens": []},
    ]
    assert traiter_entree("…", c) == ["+ créée : Rust", "~ complétée : Compiled language"]
    rust = next(chemins.glob("*-rust.org")).read_text()
    assert "#+filetags: :rust_lang:" in rust and "* Liens" not in rust
    jour = rust.split("note créée le ")[1][:10]
    assert rust.endswith(f"* Source\n- Journal dicté, 2026-11-01 16:00:00 (note créée le {jour})\n")
    # complément : dans le texte principal, sans titre ; source ajoutée à la liste
    assert (chemins / "c.org").read_text() == (
        ":PROPERTIES:\n:ID:       C\n:END:\n#+title: Compiled language\n\ny\n\n"
        f"Exemple : [[id:{c.ids[next(i for i in c.ids if i not in ('C',))].id}][Rust]].\n\n"
        f"* Source\n- Journal dicté, 2026-11-01 16:00:00 (complément du {jour})\n")
    assert len(c.lot_notes.fichiers) == 2


# --- git : branche de relecture --------------------------------------------
def test_branche_de_relecture(tmp_path, monkeypatch):
    import subprocess
    from zettel import relecture
    roam, wt = tmp_path / "roam", tmp_path / "state" / "worktree"
    roam.mkdir()
    g = lambda *a, cwd=roam: subprocess.run(["git", "-C", str(cwd), *a], check=True,
                                            capture_output=True, text=True).stdout
    g("init", "-q", "-b", "main")
    g("config", "user.email", "t@t"), g("config", "user.name", "t")
    (roam / "a.org").write_text("a\n")
    g("add", "."), g("commit", "-qm", "init")
    monkeypatch.setattr(cfg, "WORKTREE", wt)
    monkeypatch.setattr(cfg, "NOTES_DIR", wt)
    relecture.preparer_branche()
    assert (wt / "a.org").exists()
    lot = relecture.LotCommit("zettel_ai : test")
    (wt / "b.org").write_text("b\n")
    lot.ajouter(wt / "b.org", "+ b")
    lot.commiter()
    assert "zettel_ai : test" in g("log", "main..zettel-ai", "--format=%B")
    assert not (roam / "b.org").exists()                 # main et dossier de travail intacts
    relecture.preparer_branche()                          # 2e passage : worktree déjà là
    assert lot.fichiers == []
