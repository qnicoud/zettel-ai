"""Tâche « lister_todos » (lecture seule) : todos ouverts des fichiers .org.
La lecture est déterministe ; le LLM n'intervient que pour filtrer par sujet."""

import re
from dataclasses import dataclass
from pathlib import Path

from .. import config as cfg
from ..contexte import Contexte
from ..index import cosinus, fichiers_org
from ..ollama import embed, llm
from .base import Tache

RE_MOTS_TODO = re.compile(r"^#\+(?:SEQ_|TYP_)?TODO:[ \t]*(.*)$", re.M | re.I)
RE_TITRE = re.compile(r"^(\*+)\s+(\S+)\s+(.*?)\s*$")
RE_TAGS_FIN = re.compile(r"\s+:[\w@#%:]+:\s*$")
RE_ECHEANCE = re.compile(r"(DEADLINE|SCHEDULED):\s*(<[^>]+>)")
RE_TITRE_FICHIER = re.compile(r"^#\+title:\s*(.+)$", re.M | re.I)

PROMPT_FILTRE = """On te donne une liste numérotée de tâches (todo) issues d'une base de notes,
chacune précédée du titre de sa note entre crochets, et un sujet.
Renvoie les numéros des tâches qui concernent ce sujet (directement ou par leur note).
Si aucune ne correspond, renvoie une liste vide."""

SCHEMA_NUMEROS = {
    "type": "object",
    "properties": {"numeros": {"type": "array", "items": {"type": "integer"}}},
    "required": ["numeros"],
}


@dataclass(frozen=True)
class Todo:
    etat: str
    texte: str
    note: str
    path: Path
    ligne: int
    echeance: str = ""

    def org(self) -> str:
        ech = f" ({self.echeance})" if self.echeance else ""
        return (f"- {self.etat} {self.texte}{ech} — /{self.note}/ "
                f"[[file:{chemin_lien(self.path)}::{self.ligne}][ouvrir]]")


def chemin_lien(path: Path) -> Path:
    """Lien vers ta copie de travail si le fichier y existe, sinon vers le worktree."""
    try:
        principal = cfg.ROAM_DIR / path.relative_to(cfg.NOTES_DIR)
    except ValueError:
        return path
    return principal if principal.exists() else path


def mots_ouverts(txt: str) -> set[str]:
    """Mots-clés avant « | » des lignes #+TODO: (sans « | », le dernier est l'état final)."""
    lignes = RE_MOTS_TODO.findall(txt)
    if not lignes:
        return set(cfg.TODO_OUVERTS)
    ouverts = set()
    for l in lignes:
        avant, sep, _ = l.partition("|")
        mots = avant.split() if sep else avant.split()[:-1]
        ouverts |= {re.sub(r"\(.*\)$", "", m) for m in mots}
    return ouverts


def todos_fichier(path: Path) -> list[Todo]:
    txt = path.read_text(encoding="utf-8", errors="replace")
    ouverts = mots_ouverts(txt)
    m_t = RE_TITRE_FICHIER.search(txt)
    note = m_t.group(1).strip() if m_t else path.stem
    lignes = txt.splitlines()
    res = []
    for i, l in enumerate(lignes):
        m = RE_TITRE.match(l)
        if not m or m.group(2) not in ouverts:
            continue
        suivante = lignes[i + 1] if i + 1 < len(lignes) else ""
        m_e = RE_ECHEANCE.search(suivante)
        echeance = f"{m_e.group(1)} {m_e.group(2)}" if m_e else ""
        res.append(Todo(m.group(2), RE_TAGS_FIN.sub("", m.group(3)), note, path, i + 1, echeance))
    return res


def todos_ouverts() -> list[Todo]:
    return [t for p in fichiers_org() for t in todos_fichier(p)]


def filtrer(todos: list[Todo], sujet: str) -> list[Todo]:
    if len(todos) > cfg.MAX_TODOS_FILTRE:      # pré-filtrage pour tenir dans le contexte
        vec = embed([sujet])[0]
        vecs = embed([f"{t.note} : {t.texte}" for t in todos])
        classes = sorted(zip(vecs, todos), key=lambda p: cosinus(vec, p[0]), reverse=True)
        todos = [t for _, t in classes[:cfg.MAX_TODOS_FILTRE]]
    liste = "\n".join(f"{i}. [{t.note}] {t.texte}" for i, t in enumerate(todos, 1))
    d = llm(PROMPT_FILTRE, f"Sujet : {sujet}\n\nTâches :\n{liste}", SCHEMA_NUMEROS)
    return [todos[n - 1] for n in sorted(set(d["numeros"])) if 1 <= n <= len(todos)]


def executer(consigne: str, sujet: str, ctx: Contexte) -> str:
    todos = todos_ouverts()
    if not todos:
        return "Aucun todo ouvert dans la base."
    total = len(todos)
    if sujet:
        todos = filtrer(todos, sujet)
        if not todos:
            return f"Aucun todo ouvert sur « {sujet} » ({total} au total)."
    entete = f"{len(todos)} todo(s) ouvert(s)" + (f" sur « {sujet} »" if sujet else "")
    return entete + " :\n" + "\n".join(t.org() for t in todos)


TACHE = Tache(
    nom="lister_todos",
    description="lister les tâches TODO encore ouvertes dans les notes, éventuellement "
                "sur un sujet donné",
    executer=executer,
    ecrit=False,
)
