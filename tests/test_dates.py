"""Dates dites en français dans une consigne, horodatages Org."""

from datetime import date, datetime

import pytest

from zettel.dates import (
    date_dans,
    heure_valide,
    horodatage_actif,
    horodatage_inactif,
    nom_jour,
)

REF = date(2026, 11, 2)      # un lundi


@pytest.mark.parametrize("texte, sens, attendu", [
    ("bilan d'aujourd'hui", 1, date(2026, 11, 2)),
    ("ma journée d’aujourd’hui", -1, date(2026, 11, 2)),
    ("prépare demain", 1, date(2026, 11, 3)),
    ("bilan d'hier", -1, date(2026, 11, 1)),
    ("avant-hier", -1, date(2026, 10, 31)),
    ("avant hier", -1, date(2026, 10, 31)),
    ("après-demain", 1, date(2026, 11, 4)),
    ("apres demain", 1, date(2026, 11, 4)),
    ("prépare jeudi", 1, date(2026, 11, 5)),
    ("bilan de jeudi", -1, date(2026, 10, 29)),
    ("lundi", 1, date(2026, 11, 9)),               # le même jour de semaine : la semaine suivante
    ("lundi dernier", 1, date(2026, 10, 26)),
    ("vendredi prochain", -1, date(2026, 11, 6)),
    ("le 3 novembre", 1, date(2026, 11, 3)),
    ("le 3 novembre", -1, date(2025, 11, 3)),
    ("le 1er novembre", -1, date(2026, 11, 1)),
    ("le 5 décembre 2027", -1, date(2027, 12, 5)),
    ("2026-11-05", 1, date(2026, 11, 5)),
    ("le 5/11", 1, date(2026, 11, 5)),
    ("le 5/11/2025", 1, date(2025, 11, 5)),
    ("dans 3 jours", 1, date(2026, 11, 5)),
    ("dans deux jours", 1, date(2026, 11, 4)),
    ("il y a trois jours", -1, date(2026, 10, 30)),
])
def test_date_dans(texte, sens, attendu):
    assert date_dans(texte, REF, sens) == attendu


@pytest.mark.parametrize("texte", ["prépare ma journée", "le fichier du projet", "le lendemain",
                                   "le 31 février", "le 31/02"])
def test_pas_de_date(texte):
    assert date_dans(texte, REF, 1) is None


@pytest.mark.parametrize("texte, attendu", [
    ("13:30", "13:30"), ("13h30", "13:30"), ("9h", "09:00"), ("9 h 05", "09:05"), ("14", "14:00"),
    ("", ""), ("25:00", ""), ("12:75", ""), ("midi", ""),
])
def test_heure_valide(texte, attendu):
    assert heure_valide(texte) == attendu


def test_horodatages():
    assert horodatage_actif(date(2026, 11, 3)) == "<2026-11-03 Tue>"
    assert horodatage_actif(date(2026, 11, 3), "13:30") == "<2026-11-03 Tue 13:30>"
    assert horodatage_inactif(datetime(2026, 11, 1, 19, 9)) == "[2026-11-01 Sun 19:09]"


def test_nom_jour():
    assert nom_jour(date(2026, 11, 2)) == "lundi 2 novembre 2026"
    assert nom_jour(date(2026, 11, 1)) == "dimanche 1er novembre 2026"
