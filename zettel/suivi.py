"""Tâches (TODO), suivi de projet et notes journalières (org-roam-dailies).

- tâche liée à un projet  -> « ** TODO » dans la section « * Tâches » de la note du projet
- tâche sans projet        -> « ** TODO » dans « * Tâches » de la note du jour
- avancement d'un projet   -> « - [AAAA-MM-JJ] … » dans « * Suivi » de la note du projet
- logistique / infos perso -> « - HH:MM … » dans « * Journal » de la note du jour
Toujours en ajout : le contenu existant n'est jamais modifié. Une note de projet absente
est créée (relue comme le reste avant fusion)."""

import re
import uuid
from datetime import date, datetime
from pathlib import Path

from . import config as cfg
from .contexte import Contexte
from .ecriture import creer_note, inserer_dans_section
from .index import Note, meme_titre
from .ollama import embed

JOURS_ORG = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def date_valide(texte: str, ref: date) -> date | None:
    """AAAA-MM-JJ plausible (d'un mois avant à deux ans après la dictée), sinon None."""
    try:
        d = datetime.strptime(texte.strip(), "%Y-%m-%d").date()
    except ValueError:
        return None
    return d if -31 <= (d - ref).days <= 730 else None


def horodatage_org(d: date) -> str:
    return f"<{d:%Y-%m-%d} {JOURS_ORG[d.weekday()]}>"


def lignes_todo(t: dict, ref: date) -> list[str]:
    lignes = [f"** TODO {t['texte'].strip().rstrip('.').strip()}"]
    if (d := date_valide(t.get("date", ""), ref)):
        mot = "DEADLINE" if t.get("date_limite") else "SCHEDULED"
        lignes.append(f"{mot}: {horodatage_org(d)}")
    return lignes


def todo_existe(txt: str, texte: str) -> bool:
    motif = rf"(?mi)^\*+\s+\S+\s+{re.escape(texte.strip())}\s*(?::[\w@#%:]+:)?\s*$"
    return re.search(motif, txt) is not None


def chemin_journalier(d: date) -> Path:
    return cfg.NOTES_DIR / cfg.DAILY_DIR / f"{d:%Y-%m-%d}.org"


def note_journaliere(d: date) -> Path:
    """Crée la note du jour au format d'org-roam-dailies si elle n'existe pas."""
    p = chemin_journalier(d)
    if not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(f":PROPERTIES:\n:ID:       {str(uuid.uuid4()).upper()}\n:END:\n"
                     f"#+title: {d:%Y-%m-%d}\n", encoding="utf-8")
    return p


def resoudre_projet(titre: str, ctx: Contexte) -> Note | None:
    """Note du projet (existante, créée plus tôt dans ce traitement, ou créée ici)."""
    if not titre.strip():
        return None
    if (n := meme_titre(titre, ctx.ids)):
        return n
    titre = titre.strip()
    print(f"  + CRÉER le projet « {titre} »")
    if ctx.dry_run:
        n = Note(f"simulation-{uuid.uuid4()}", titre, None, [], ["projet"], "Projet personnel.")
    else:
        n = creer_note(titre, "Projet personnel.", ["projet"], [], ctx.ids, ctx.source)
        ctx.lot_notes.ajouter(n.path, f"+ {titre} (projet)")
    n.vec = embed([titre])[0]
    ctx.ajouter_note(n)
    return n


def ajouter(path: Path | None, section: str, lignes: list[str], ctx: Contexte, resume: str):
    """Écrit (hors dry-run et hors note simulée) et inscrit le fichier au lot de commit."""
    if ctx.dry_run or path is None:
        return
    txt = path.read_text(encoding="utf-8")
    path.write_text(inserer_dans_section(txt, section, lignes), encoding="utf-8")
    ctx.lot_notes.ajouter(path, resume)


def appliquer_taches(taches: list[dict], ctx: Contexte) -> list[str]:
    ref, actions = ctx.quand.date(), []
    for t in taches:
        texte = t.get("texte", "").strip().rstrip(".").strip()
        if not texte:
            continue
        projet = resoudre_projet(t.get("projet", ""), ctx)
        if projet:
            path, ou = projet.path, projet.titre
        else:
            path = chemin_journalier(ref) if ctx.dry_run else note_journaliere(ref)
            ou = f"journée du {ref:%Y-%m-%d}"
        if path is not None and path.exists() and todo_existe(path.read_text(encoding="utf-8"), texte):
            print(f"  = TODO déjà présent : « {texte} » ({ou})")
            continue
        lignes = lignes_todo(t, ref)
        print(f"  ☐ TODO « {texte} » → {ou}" + (f"  {lignes[1]}" if len(lignes) > 1 else ""))
        ajouter(path, "Tâches", lignes, ctx, f"☐ {texte} ({ou})")
        actions.append(f"☐ TODO {texte} ({ou})" + (f", {lignes[1]}" if len(lignes) > 1 else ""))
    return actions


def appliquer_suivi_projets(suivi: list[dict], ctx: Contexte) -> list[str]:
    actions = []
    for s in suivi:
        texte = s.get("texte", "").strip()
        projet = resoudre_projet(s.get("projet", ""), ctx)
        if not texte or projet is None:
            continue
        print(f"  ↳ SUIVI {projet.titre} : {texte}")
        ajouter(projet.path, "Suivi", [f"- [{ctx.quand:%Y-%m-%d}] {texte}"], ctx,
                f"↳ {projet.titre} : suivi")
        actions.append(f"↳ suivi {projet.titre} : {texte}")
    return actions


def appliquer_perso(perso: list[str], ctx: Contexte) -> list[str]:
    infos = [p.strip() for p in perso if p.strip()]
    if not infos:
        return []
    ref = ctx.quand.date()
    for p in infos:
        print(f"  • PERSO {ref:%Y-%m-%d} : {p}")
    path = None if ctx.dry_run else note_journaliere(ref)
    ajouter(path, "Journal", [f"- {ctx.quand:%H:%M} {p}" for p in infos], ctx,
            f"• journée du {ref:%Y-%m-%d}")
    return [f"• journée du {ref:%Y-%m-%d} : {p}" for p in infos]


def appliquer_suivi(r: dict, ctx: Contexte) -> list[str]:
    """Tâches, suivi de projet et infos perso extraits d'une entrée."""
    return (appliquer_taches(r.get("taches", []), ctx)
            + appliquer_suivi_projets(r.get("suivi", []), ctx)
            + appliquer_perso(r.get("perso", []), ctx))
