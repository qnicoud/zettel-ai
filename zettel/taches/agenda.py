"""Lecture déterministe de la base pour le bilan et la préparation d'une journée : tâches
datées (prévue, à rendre, faite, créée), rendez-vous (horodatages actifs), sections des notes
journalières, notes touchées par les dictées d'un jour, suivi des projets. Aucun LLM ici."""

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .. import config as cfg
from ..ecriture import SECTION_FINALE
from ..index import est_journaliere, fichiers_org
from .todos import RE_MOTS_TODO, RE_TAGS_FIN, RE_TITRE, chemin_lien, mots_ouverts

RE_ID = re.compile(r"(?mi)^:ID:\s*(\S+)")
RE_TITRE_FICHIER = re.compile(r"(?mi)^#\+title:\s*(.+)$")
RE_SECTION = re.compile(r"^\*\s+(.*?)\s*$")                 # titre de niveau 1
RE_PLANNING = re.compile(r"^\s*(?:SCHEDULED|DEADLINE|CLOSED):")
RE_PREVUE = re.compile(r"SCHEDULED:\s*<(\d{4}-\d{2}-\d{2})")
RE_LIMITE = re.compile(r"DEADLINE:\s*<(\d{4}-\d{2}-\d{2})")
RE_FAITE = re.compile(r"CLOSED:\s*\[(\d{4}-\d{2}-\d{2})")
RE_CREEE = re.compile(r"^\s*:CREATED:\s*[\[<](\d{4}-\d{2}-\d{2})", re.IGNORECASE)
# <2026-11-03 Tue 13:30>, <2026-11-03 mar.>, <2026-11-03 Tue 09:00-10:00 +1w>…
RE_ACTIF = re.compile(r"<(\d{4}-\d{2}-\d{2})(?:\s+[^\s>\d][^\s>]*)?(?:\s+(\d{1,2}):(\d{2}))?[^>]*>")
RE_SOURCE = re.compile(r"^- (?:Journal dicté, |Demande directe du )(\d{4}-\d{2}-\d{2})\b(.*)$")
RE_SUIVI = re.compile(r"^- \[(\d{4}-\d{2}-\d{2})\]\s*(.*)$")
NATURES = (("note créée", "créée"), ("complément", "complétée"), ("tâche ajoutée", "tâche ajoutée"))


@dataclass(frozen=True)
class Fichier:
    path: Path
    titre: str
    id: str
    lignes: tuple[str, ...]

    def lien(self) -> str:
        if self.id:
            return f"[[id:{self.id}][{self.titre}]]"
        return f"[[file:{chemin_lien(self.path)}][{self.titre}]]"

    def journalier(self) -> bool:
        return est_journaliere(self.path)


def lien_ligne(f: Fichier, ligne: int) -> str:
    return f"/{f.titre}/ [[file:{chemin_lien(f.path)}::{ligne}][ouvrir]]"


@dataclass(frozen=True)
class TacheOrg:
    mot: str
    texte: str
    ouverte: bool
    fichier: Fichier
    ligne: int                      # numéro de ligne du titre (1 = première)
    prevue: date | None = None      # SCHEDULED
    limite: date | None = None      # DEADLINE
    faite: date | None = None       # CLOSED
    creee: date | None = None       # :CREATED: (todos écrits par zettel-ai)

    def org(self) -> str:
        dates = [f"{nom} le {d:%Y-%m-%d}" for nom, d in
                 (("prévue", self.prevue), ("à rendre", self.limite)) if d]
        precision = f" ({', '.join(dates)})" if dates else ""
        return f"- {self.mot} {self.texte}{precision} — {lien_ligne(self.fichier, self.ligne)}"


@dataclass(frozen=True)
class RendezVous:
    heure: str                      # « HH:MM », ou « » pour toute la journée
    texte: str
    fichier: Fichier
    ligne: int

    def org(self) -> str:
        heure = f"{self.heure} " if self.heure else ""
        return f"- {heure}{self.texte} — {lien_ligne(self.fichier, self.ligne)}"


def lire_base() -> list[Fichier]:
    base = []
    for p in fichiers_org():
        txt = p.read_text(encoding="utf-8", errors="replace")
        m_t, m_i = RE_TITRE_FICHIER.search(txt), RE_ID.search(txt)
        base.append(Fichier(p, m_t.group(1).strip() if m_t else p.stem,
                            m_i.group(1) if m_i else "", tuple(txt.splitlines())))
    return base


def _jour(m: re.Match | None) -> date | None:
    if m is None:
        return None
    try:
        return date.fromisoformat(m.group(1))
    except ValueError:
        return None


def mots_finis(txt: str) -> set[str]:
    """Mots-clés après « | » des lignes #+TODO: (sans « | », le dernier), sinon config."""
    lignes = RE_MOTS_TODO.findall(txt)
    if not lignes:
        return {cfg.MOT_FAIT, cfg.MOT_ABANDON}
    finis = set()
    for ligne in lignes:
        avant, sep, apres = ligne.partition("|")
        finis |= {re.sub(r"\(.*\)$", "", m) for m in (apres.split() if sep else avant.split()[-1:])}
    return finis


def _planning_et_creation(lignes: tuple[str, ...], i: int) -> tuple[str, date | None]:
    """Ligne de planification (juste sous le titre, règle Org) et :CREATED: du tiroir suivant."""
    j, planning = i + 1, ""
    if j < len(lignes) and RE_PLANNING.match(lignes[j]):
        planning, j = lignes[j], j + 1
    if j < len(lignes) and lignes[j].strip().upper() == ":PROPERTIES:":
        for ligne in lignes[j + 1:]:
            if ligne.strip().upper() == ":END:":
                break
            if (m := RE_CREEE.match(ligne)):
                return planning, _jour(m)
    return planning, None


def taches_fichier(f: Fichier) -> list[TacheOrg]:
    txt = "\n".join(f.lignes)
    ouverts, finis = mots_ouverts(txt), mots_finis(txt)
    res = []
    for i, ligne in enumerate(f.lignes):
        m = RE_TITRE.match(ligne)
        if not m or m.group(2) not in ouverts | finis:
            continue
        planning, creee = _planning_et_creation(f.lignes, i)
        res.append(TacheOrg(m.group(2), RE_TAGS_FIN.sub("", m.group(3)), m.group(2) in ouverts,
                            f, i + 1, _jour(RE_PREVUE.search(planning)),
                            _jour(RE_LIMITE.search(planning)), _jour(RE_FAITE.search(planning)),
                            creee))
    return res


def taches_org(base: list[Fichier]) -> list[TacheOrg]:
    return [t for f in base for t in taches_fichier(f)]


def creees_le(taches: list[TacheOrg], j: date) -> list[TacheOrg]:
    """:CREATED: du jour, ou (sans :CREATED:, todos anciens) rangée dans la note du jour."""
    return [t for t in taches if t.creee == j or (
        t.creee is None and t.fichier.journalier() and t.fichier.path.stem == j.isoformat())]


def rendez_vous(base: list[Fichier], j: date) -> list[RendezVous]:
    """Lignes portant un horodatage actif du jour (hors SCHEDULED/DEADLINE), heure d'abord."""
    res = []
    for f in base:
        for i, ligne in enumerate(f.lignes):
            if RE_PLANNING.match(ligne):
                continue
            m = next((m for m in RE_ACTIF.finditer(ligne) if m.group(1) == j.isoformat()), None)
            if m is None:
                continue
            heure = f"{int(m.group(2)):02d}:{m.group(3)}" if m.group(2) else ""
            texte = re.sub(r"^\s*(?:\*+|-)\s+", "", RE_ACTIF.sub("", ligne)).strip()
            res.append(RendezVous(heure, re.sub(r"\s{2,}", " ", texte), f, i + 1))
    return sorted(res, key=lambda r: (r.heure == "", r.heure))


def note_du_jour(base: list[Fichier], j: date) -> Fichier | None:
    return next((f for f in base if f.journalier() and f.path.stem == j.isoformat()), None)


def section(f: Fichier | None, nom: str) -> list[str]:
    """Lignes non vides de la section de niveau 1 « * nom » (sous-titres compris)."""
    if f is None:
        return []
    dedans, res = False, []
    for ligne in f.lignes:
        if (m := RE_SECTION.match(ligne)):
            dedans = m.group(1).lower() == nom.lower()
        elif dedans and ligne.strip():
            res.append(ligne.rstrip())
    return res


def notes_du_jour(base: list[Fichier], j: date) -> list[tuple[Fichier, list[str]]]:
    """Notes dont « * Source » cite une dictée (ou une demande) du jour, et ce qui leur est
    arrivé (créée, complétée…), par titre."""
    res = []
    for f in base:
        if f.journalier():
            continue
        natures: list[str] = []
        for ligne in section(f, SECTION_FINALE):
            m = RE_SOURCE.match(ligne)
            if not m or m.group(1) != j.isoformat():
                continue
            nature = next((nom for cle, nom in NATURES if cle in m.group(2)), "modifiée")
            if nature not in natures:
                natures.append(nature)
        if natures:
            res.append((f, natures))
    return sorted(res, key=lambda p: p[0].titre.lower())


def suivi_du_jour(base: list[Fichier], j: date) -> list[tuple[Fichier, str]]:
    """Lignes « - [AAAA-MM-JJ] … » du jour dans les sections « * Suivi » des projets."""
    return [(f, m.group(2).strip()) for f in base for ligne in section(f, "Suivi")
            if (m := RE_SUIVI.match(ligne)) and m.group(1) == j.isoformat()]
