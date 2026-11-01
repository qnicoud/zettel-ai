"""Mise en forme des notes : aucun titre dans le contenu, sections Liens / Source en liste."""

import re

from conftest import ecrire_note
from zettel.ecriture import (completer_note, inserer_corps, inserer_dans_section,
                             nettoyer_contenu)
from zettel.index import lire_note

# Extraits réels produits par Qwen (notes Rust et DM Gym du 2026-11-01)
GENERE = """* Rust est un [[id:C][Compiled language]] conçu pour la sûreté mémoire.

- Il évite les fuites grâce à l'*ownership*.

* Lien avec [[id:H][HyperBinds]] : application personnelle développée en Rust.
* Lien avec [[id:P][Programming Languages]] : catégorie générale.

*tags: rust, ownership, memory-safety*
*Tags*: dm_gym, android
## Objectif : improviser"""


def test_nettoyer_contenu():
    texte, liens = nettoyer_contenu(GENERE)
    assert texte == ("Rust est un [[id:C][Compiled language]] conçu pour la sûreté mémoire.\n\n"
                     "- Il évite les fuites grâce à l'*ownership*.\n\nObjectif : improviser")
    assert liens == [{"id": "H", "raison": "application personnelle développée en Rust."},
                     {"id": "P", "raison": "catégorie générale."}]
    assert not any(l.startswith("*") for l in texte.splitlines())


def test_nettoyer_contenu_garde_le_gras_en_cours_de_phrase():
    assert nettoyer_contenu("Un mot *gras* ici.\n- item")[0] == "Un mot *gras* ici.\n- item"


def test_section_creee_avant_source():
    txt = "#+title: P\n\nTexte.\n\n* Source\n- s\n"
    assert inserer_dans_section(txt, "Tâches", ["** TODO A"]) == (
        "#+title: P\n\nTexte.\n\n* Tâches\n** TODO A\n\n* Source\n- s\n")
    assert inserer_dans_section(txt, "Source", ["- t"]).endswith("* Source\n- s\n- t\n")


def test_inserer_corps():
    assert inserer_corps("#+title: P\n\nTexte.\n\n* Liens\n- l\n", "Ajout.") == (
        "#+title: P\n\nTexte.\n\nAjout.\n\n* Liens\n- l\n")
    assert inserer_corps("#+title: P\n\nTexte.\n", "Ajout.") == "#+title: P\n\nTexte.\n\nAjout.\n"


def test_complement_liens_dans_la_section_sans_doublon(chemins, ctx):
    p = ecrire_note(chemins, "n.org", "N", "Note", "Texte.\n\n* Liens\n- [[id:A][A]] : déjà\n\n"
                    "* Source\n- origine\n")
    c = ctx(p, ecrire_note(chemins, "a.org", "A", "A", ""), ecrire_note(chemins, "b.org", "B", "B", ""))
    completer_note(lire_note(p), "Ajout.", [{"id": "A", "raison": "x"}, {"id": "B", "raison": "y"}],
                   c.ids, "Journal dicté, t")
    txt = p.read_text()
    assert "Texte.\n\nAjout.\n\n* Liens\n- [[id:A][A]] : déjà\n- [[id:B][B]] : y\n\n* Source\n" in txt
    assert txt.count("[[id:A]") == 1
    assert "* Complément" not in txt
    assert re.search(r"\* Source\n- origine\n- Journal dicté, t \(complément du \d{4}-\d\d-\d\d\)\n$", txt)


def test_lier_mentions(chemins, ctx):
    from zettel.ecriture import lier_mentions
    c = ctx(ecrire_note(chemins, "p.org", "P", "Programming Languages", ""),
            ecrire_note(chemins, "k.org", "K", "Kotlin", ""),
            ecrire_note(chemins, "r.org", "R", "R", ""),                # titre trop court : jamais lié
            ecrire_note(chemins, "s.org", "S", "Soi", ""))
    c.ids["P"].alias = ["langages de programmation"]
    texte, lies = lier_mentions(
        "Écrite en kotlin. Kotlin encore. Un des langages de programmation. R aussi. Soi.", c.ids, "S")
    assert texte == ("Écrite en [[id:K][kotlin]]. Kotlin encore. Un des "
                     "[[id:P][langages de programmation]]. R aussi. Soi.")
    assert lies == {"K", "P"}
    # pas de lien imbriqué, ni dans un mot plus long
    assert lier_mentions("[[id:K][Kotlin]] et Kotlinx", c.ids, "")[0] == "[[id:K][Kotlin]] et Kotlinx"
