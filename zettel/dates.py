"""Dates dites en français dans une consigne (« demain », « jeudi dernier », « le 3 novembre »)
et horodatages Org. Tout part d'une date de référence : celle de la dictée.

`sens` tranche les expressions ambiguës : un jour de semaine ou une date sans année désigne
la prochaine occurrence (sens > 0, préparer une journée) ou la dernière (sens < 0, bilan)."""

import re
import unicodedata
from datetime import date, datetime, timedelta

JOURS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")
JOURS_ORG = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
MOIS = ("janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
        "septembre", "octobre", "novembre", "décembre")
NOMBRES = {"un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "six": 6,
           "sept": 7, "huit": 8, "neuf": 9, "dix": 10}
# Du plus long au plus court : « avant-hier » avant « hier », « après-demain » avant « demain ».
RELATIFS = ((r"avant[- ]hier", -2), (r"apres[- ]demain", 2), (r"aujourd'?hui", 0),
            (r"hier", -1), (r"demain", 1))


def sans_accents(texte: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texte)
                   if unicodedata.category(c) != "Mn")


def normaliser(texte: str) -> str:
    return sans_accents(texte.lower().replace("’", "'"))


_MOIS = tuple(sans_accents(m) for m in MOIS)
_NOMBRE = r"(\d{1,3}|" + "|".join(NOMBRES) + ")"
RE_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
RE_NUMERIQUE = re.compile(r"(?<![\d/])(\d{1,2})/(\d{1,2})(?:/(\d{4}|\d{2}))?(?![\d/])")
RE_JOUR_MOIS = re.compile(rf"\b(\d{{1,2}})(?:er)?\s+({'|'.join(_MOIS)})(?:\s+(\d{{4}}))?\b")
RE_DANS = re.compile(rf"\bdans\s+{_NOMBRE}\s+jours?\b")
RE_IL_Y_A = re.compile(rf"\bil y a\s+{_NOMBRE}\s+jours?\b")
RE_JOUR_SEMAINE = re.compile(rf"\b({'|'.join(JOURS)})\b(?:\s+(dernier|passe|prochain))?")


def _date(annee: int, mois: int, jour: int) -> date | None:
    try:
        return date(annee, mois, jour)
    except ValueError:
        return None


def _sans_annee(mois: int, jour: int, ref: date, sens: int) -> date | None:
    d = _date(ref.year, mois, jour)
    if d is None:
        return None
    if sens >= 0 and d < ref:
        return _date(ref.year + 1, mois, jour)
    if sens < 0 and d > ref:
        return _date(ref.year - 1, mois, jour)
    return d


def _nombre(texte: str) -> int:
    return int(texte) if texte.isdigit() else NOMBRES[texte]


def _iso(t: str, ref: date, sens: int) -> date | None:
    m = RE_ISO.search(t)
    return _date(int(m[1]), int(m[2]), int(m[3])) if m else None


def _numerique(t: str, ref: date, sens: int) -> date | None:
    m = RE_NUMERIQUE.search(t)
    if not m:
        return None
    jour, mois = int(m[1]), int(m[2])
    if not m[3]:
        return _sans_annee(mois, jour, ref, sens)
    annee = int(m[3])
    return _date(annee + 2000 if annee < 100 else annee, mois, jour)


def _jour_mois(t: str, ref: date, sens: int) -> date | None:
    m = RE_JOUR_MOIS.search(t)
    if not m:
        return None
    jour, mois = int(m[1]), _MOIS.index(m[2]) + 1
    return _date(int(m[3]), mois, jour) if m[3] else _sans_annee(mois, jour, ref, sens)


def _decalage(t: str, ref: date, sens: int) -> date | None:
    if (m := RE_DANS.search(t)):
        return ref + timedelta(days=_nombre(m[1]))
    if (m := RE_IL_Y_A.search(t)):
        return ref - timedelta(days=_nombre(m[1]))
    return None


def _relatif(t: str, ref: date, sens: int) -> date | None:
    for motif, ecart in RELATIFS:
        if re.search(rf"(?<![\w-]){motif}(?![\w-])", t):
            return ref + timedelta(days=ecart)
    return None


def _jour_semaine(t: str, ref: date, sens: int) -> date | None:
    m = RE_JOUR_SEMAINE.search(t)
    if not m:
        return None
    cible = JOURS.index(m[1])
    vers_l_avant = {"dernier": False, "passe": False, "prochain": True}.get(m[2] or "", sens >= 0)
    if vers_l_avant:      # strictement après : « lundi », dit un lundi, = la semaine suivante
        return ref + timedelta(days=(cible - ref.weekday()) % 7 or 7)
    return ref - timedelta(days=(ref.weekday() - cible) % 7 or 7)


LECTEURS = (_iso, _numerique, _jour_mois, _decalage, _relatif, _jour_semaine)


def date_dans(texte: str, ref: date, sens: int = 1) -> date | None:
    """Première date reconnue dans le texte, sinon None (le texte ne désigne aucune journée,
    ou une date impossible comme « le 31 février »)."""
    t = normaliser(texte)
    for lire in LECTEURS:
        if (d := lire(t, ref, sens)) is not None:
            return d
    return None


def heure_valide(texte: str) -> str:
    """« 13h30 », « 9 h », « 13:30 », « 14 » -> « HH:MM » ; « » si ce n'est pas une heure."""
    m = re.fullmatch(r"\s*(\d{1,2})\s*(?:[:h]\s*(\d{2})?)?\s*", texte.lower())
    if not m:
        return ""
    heure, minute = int(m[1]), int(m[2] or 0)
    return f"{heure:02d}:{minute:02d}" if heure < 24 and minute < 60 else ""


def horodatage_actif(d: date, heure: str = "") -> str:
    """Horodatage Org actif (vu par org-agenda) : « <2026-11-03 Tue 13:30> »."""
    return f"<{d:%Y-%m-%d} {JOURS_ORG[d.weekday()]}{' ' + heure if heure else ''}>"


def horodatage_inactif(t: datetime) -> str:
    """Horodatage Org inactif : « [2026-11-01 Sun 19:09] »."""
    return f"[{t:%Y-%m-%d} {JOURS_ORG[t.weekday()]} {t:%H:%M}]"


def nom_jour(d: date) -> str:
    """« lundi 2 novembre 2026 », « dimanche 1er novembre 2026 »."""
    jour = "1er" if d.day == 1 else str(d.day)
    return f"{JOURS[d.weekday()]} {jour} {MOIS[d.month - 1]} {d.year}"
