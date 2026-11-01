"""Index des notes org-roam (ID, titre, alias, tags, extrait) + embeddings en cache."""

import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import config as cfg
from .ollama import embed


@dataclass
class Note:
    id: str
    titre: str
    path: Path | None          # None = note simulée (dry-run)
    alias: list = field(default_factory=list)
    tags: list = field(default_factory=list)
    extrait: str = ""
    vec: list = None

    def texte_embedding(self) -> str:
        return f"{self.titre}. {' '.join(self.alias)}. {self.extrait}"


def cosinus(a, b) -> float:
    num = sum(x * y for x, y in zip(a, b))
    den = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return num / den if den else 0.0


def lire_note(path: Path) -> Note | None:
    txt = path.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"^\*+\s", txt, re.M)
    entete = txt[:m.start()] if m else txt          # niveau fichier uniquement
    m_id = re.search(r"^\s*:ID:\s*(\S+)", entete, re.M | re.I)
    if not m_id:
        return None
    m_t = re.search(r"^#\+title:\s*(.+)$", entete, re.M | re.I)
    m_tags = re.search(r"^#\+filetags:\s*(.+)$", entete, re.M | re.I)
    m_al = re.search(r"^\s*:ROAM_ALIASES:\s*(.+)$", entete, re.M | re.I)
    alias = [a or b for a, b in re.findall(r'"([^"]+)"|(\S+)', m_al.group(1))] if m_al else []
    tags = [t for t in m_tags.group(1).strip().split(":") if t.strip()] if m_tags else []
    return Note(m_id.group(1), m_t.group(1).strip() if m_t else path.stem,
                path, alias, tags, extrait_corps(txt))


def extrait_corps(txt: str, n: int = 400) -> str:
    corps = re.sub(r":PROPERTIES:.*?:END:", "", txt, flags=re.S | re.I)
    corps = re.sub(r"(?m)^#\+.*$", "", corps)
    return re.sub(r"\s+", " ", corps).strip()[:n]


def fichiers_org() -> list[Path]:
    return [p for p in sorted(cfg.NOTES_DIR.rglob("*.org")) if ".git" not in p.parts]


def est_journaliere(path: Path) -> bool:
    try:
        return path.relative_to(cfg.NOTES_DIR).parts[0] == cfg.DAILY_DIR
    except (ValueError, IndexError):
        return False


def indexer() -> list[Note]:
    """Notes « concept » uniquement : les notes journalières ne sont ni liées ni complétées."""
    notes = [n for p in fichiers_org() if not est_journaliere(p) and (n := lire_note(p))]
    cache_f = cfg.STATE_DIR / "embeddings.json"
    cache = json.loads(cache_f.read_text()) if cache_f.exists() else {}
    manquantes = []
    for n in notes:
        cle = f"{n.path}:{n.path.stat().st_mtime_ns}"
        if cle in cache:
            n.vec = cache[cle]
        else:
            manquantes.append(n)
    if manquantes:
        print(f"Embeddings : {len(manquantes)} note(s) à calculer…")
        for n, v in zip(manquantes, embed([n.texte_embedding() for n in manquantes])):
            n.vec = v
    nouveau_cache = {f"{n.path}:{n.path.stat().st_mtime_ns}": n.vec for n in notes}
    cfg.STATE_DIR.mkdir(parents=True, exist_ok=True)
    cache_f.write_text(json.dumps(nouveau_cache))
    print(f"Index : {len(notes)} note(s) org-roam")
    return notes


def plus_proches(vec, notes: list[Note], k: int) -> list[Note]:
    return sorted(notes, key=lambda n: cosinus(vec, n.vec), reverse=True)[:k]


def meme_titre(titre: str, ids: dict) -> Note | None:
    """Note dont le titre ou un alias est identique (casse ignorée)."""
    t = titre.strip().lower()
    return next((n for n in ids.values()
                 if t == n.titre.lower() or t in (a.lower() for a in n.alias)), None)


def titres_existants(notes: list[Note]) -> str:
    return "\n".join(f"- {n.titre}" for n in notes) or "(aucune)"
