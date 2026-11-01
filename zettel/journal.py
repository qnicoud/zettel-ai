"""Lecture du journal dicté : découpage en entrées, empreintes des entrées déjà traitées."""

import hashlib
import json
import re
from datetime import datetime

from . import config as cfg

# Une entrée commence par un titre # / ## ou par une ligne hyprwhspr « - [AAAA-MM-JJ HH:MM:SS] ».
# Les lignes suivantes sans ce préfixe sont rattachées à l'entrée en cours.
RE_DEBUT_ENTREE = re.compile(r"(?m)^(?=#{1,2}\s|- \[\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(?::\d{2})?\])")
RE_HORODATAGE = re.compile(r"^- \[([^\]]+)\]\s*")
# Une dictée qui commence par « Instruction » est une consigne, pas du contenu.
RE_INSTRUCTION = re.compile(r"^\s*instructions?\b\s*[:,.;–-]?\s*", re.I)


def entrees_journal(texte: str) -> list[str]:
    return [b.strip() for b in RE_DEBUT_ENTREE.split(texte) if b.strip()]


def source_entree(entree: str) -> str:
    """Référence courte de l'entrée : son horodatage hyprwhspr, ou son titre."""
    m = RE_HORODATAGE.match(entree)
    return m.group(1) if m else entree.splitlines()[0].lstrip("# ").strip()[:80]


def date_entree(entree: str) -> datetime | None:
    """Date et heure de la dictée, d'après son horodatage hyprwhspr."""
    m = RE_HORODATAGE.match(entree)
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M"):
        try:
            return datetime.strptime(m.group(1).strip(), fmt) if m else None
        except ValueError:
            continue
    return None


def texte_entree(entree: str) -> str:
    return RE_HORODATAGE.sub("", entree, count=1)


def corriger_transcription(texte: str) -> str:
    """Remplace les erreurs de transcription connues (CORRECTIONS_TRANSCRIPTION)."""
    for faux, juste in sorted(cfg.CORRECTIONS_TRANSCRIPTION.items(), key=lambda p: -len(p[0])):
        texte = re.sub(rf"(?<![\w-]){re.escape(faux)}(?![\w-])", juste, texte, flags=re.I)
    return texte


def consigne_instruction(texte: str) -> str | None:
    m = RE_INSTRUCTION.match(texte)
    return texte[m.end():].strip() if m else None


def selectionner(entrees: list[str], choix: list[str]) -> list[str]:
    """Entrées désignées par leur numéro (celui de --lister) ou par le début de leur
    horodatage (« 2026-11-01 14:59 », « 2026-11-01 » pour toute la journée)."""
    retenues = []
    for c in choix:
        c = c.strip()
        if c.isdigit() and 1 <= int(c) <= len(entrees):
            trouvees = [entrees[int(c) - 1]]
        else:
            trouvees = [e for e in entrees if source_entree(e).startswith(c)]
        if not trouvees:
            raise ValueError(f"aucune entrée ne correspond à « {c} » (voir --lister)")
        retenues += [e for e in trouvees if e not in retenues]
    return [e for e in entrees if e in retenues]          # ordre du journal


def lister(entrees: list[str], etat: set) -> str:
    lignes = []
    for i, e in enumerate(entrees, 1):
        statut = "✔ traitée " if est_traitee(e, etat) else "• nouvelle"
        texte = texte_entree(e)
        genre = "instruction" if consigne_instruction(texte) is not None else "contenu"
        resume = re.sub(r"\s+", " ", texte)[:70]
        lignes.append(f"{i:>3}  {source_entree(e):<19}  {statut}  {genre:<11}  {resume}")
    return "\n".join(lignes)


def empreinte(entree: str) -> str:
    return hashlib.sha256(re.sub(r"\s+", " ", entree).strip().encode()).hexdigest()


def cle_entree(entree: str) -> str:
    """Identifiant stable d'une entrée : son horodatage hyprwhspr (corriger une faute dans
    la dictée ne la fait donc pas retraiter), sinon l'empreinte de son texte."""
    m = RE_HORODATAGE.match(entree)
    return f"horodatage:{m.group(1).strip()}" if m else empreinte(entree)


def est_traitee(entree: str, etat: set) -> bool:
    """Reconnaît aussi les anciennes empreintes (état enregistré avant le suivi par horodatage)."""
    return cle_entree(entree) in etat or empreinte(entree) in etat


def charger_etat() -> set:
    f = cfg.STATE_DIR / "entrees_traitees.json"
    return set(json.loads(f.read_text())) if f.exists() else set()


def sauver_etat(etat: set):
    cfg.STATE_DIR.mkdir(parents=True, exist_ok=True)
    (cfg.STATE_DIR / "entrees_traitees.json").write_text(json.dumps(sorted(etat)))
