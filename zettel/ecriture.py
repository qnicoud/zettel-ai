"""Écriture des fichiers .org : création, complément, sections, liens validés.

Structure d'une note : texte principal SANS titre, puis uniquement les sections
« * Liens » (liste), « * Tâches », « * Suivi » et « * Source » (liste, toujours en dernier).
"""

import re
import unicodedata
import uuid
from datetime import datetime

from . import config as cfg
from .index import Note

RE_LIEN_ID = re.compile(r"\[\[id:([^\]]+)\]\[([^\]]*)\]\]")
RE_TITRE_N1 = re.compile(r"^\*\s")
RE_TITRE = re.compile(r"^(\*+|#+)\s+")                     # titre Org ou Markdown
RE_LIGNE_TAGS = re.compile(r"^[*/_\s]*tags?[*/_\s]*:", re.I)
RE_LIGNE_LIEN = re.compile(r"^(?:liens?|lien avec|voir aussi)\b[^\[]*\[\[id:([^\]]+)\]\[[^\]]*\]\]"
                           r"\s*[:–-]?\s*(.*)$", re.I)
SECTION_FINALE = "Source"


def slug(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")[:60] or "note"


def lignes_liens(liens: list[dict], ids: dict) -> list[str]:
    return [f"- [[id:{l['id']}][{ids[l['id']].titre}]] : {l['raison'].strip()}" for l in liens]


def nettoyer_contenu(contenu: str) -> tuple[str, list[dict]]:
    """Le contenu généré ne doit contenir aucun titre : « * x » devient un paragraphe,
    « Lien avec [[id:…][…]] : raison » part dans la section Liens, les lignes de tags
    sont retirées. Renvoie (texte, liens extraits)."""
    lignes, liens = [], []
    for l in contenu.strip().splitlines():
        texte = RE_TITRE.sub("", l.strip()) if RE_TITRE.match(l.strip()) else l.rstrip()
        if (m := RE_LIGNE_LIEN.match(texte.strip())):
            liens.append({"id": m.group(1).strip(), "raison": m.group(2).strip() or "lié"})
        elif not RE_LIGNE_TAGS.match(texte.strip()):
            lignes.append(texte)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lignes)).strip(), liens


def nettoyer_liens_texte(contenu: str, ids: dict, cible: str) -> tuple[str, set]:
    """Garde les [[id:…][…]] du texte qui pointent vers une note connue (hors auto-lien),
    remplace les autres par leur libellé. Renvoie le texte et les id liés."""
    lies = set()

    def remplacer(m):
        lid = m.group(1).strip()
        if lid in ids and lid != cible:
            lies.add(lid)
            return f"[[id:{lid}][{m.group(2)}]]"
        print(f"    (lien dans le texte vers « {lid} » retiré)")
        return m.group(2)

    return RE_LIEN_ID.sub(remplacer, contenu), lies


def lier_mentions(contenu: str, ids: dict, cible: str) -> tuple[str, set]:
    """Lie (1re occurrence, mot entier, casse ignorée) les titres et alias de notes existantes
    cités dans le texte. Les liens sont posés par le script, pas par le LLM : il ne peut donc
    pas remplacer un mot par le titre d'une autre note."""
    lies = {m.group(1).strip() for m in RE_LIEN_ID.finditer(contenu)}
    noms = sorted(((nom, n.id) for n in ids.values() if n.id != cible and n.id not in lies
                   for nom in [n.titre, *n.alias] if len(nom.strip()) >= 3),
                  key=lambda p: -len(p[0]))          # « Programming Languages » avant « Languages »
    for nom, nid in noms:
        if nid in lies:
            continue
        occupe = [m.span() for m in RE_LIEN_ID.finditer(contenu)]
        for m in re.finditer(rf"(?<![\w\[\]/-]){re.escape(nom.strip())}(?![\w\]/-])", contenu, re.I):
            if not any(a <= m.start() < b for a, b in occupe):
                contenu = f"{contenu[:m.start()]}[[id:{nid}][{m.group(0)}]]{contenu[m.end():]}"
                lies.add(nid)
                break
    return contenu, lies


def inserer_dans_section(txt: str, section: str, lignes: list[str]) -> str:
    """Ajoute les lignes à la fin de la section de niveau 1 `section`. Si elle n'existe pas,
    elle est créée juste avant « * Source » (ou en fin de fichier). Rien n'est modifié."""
    l = txt.splitlines()
    titres = {re.sub(r"^\*\s+", "", x).strip(): i for i, x in enumerate(l) if RE_TITRE_N1.match(x)}
    if section not in titres:
        bloc = [f"* {section}", *lignes]
        if section != SECTION_FINALE and SECTION_FINALE in titres:
            i = titres[SECTION_FINALE]
            return "\n".join(l[:i] + bloc + [""] + l[i:]) + "\n"
        return f"{txt.rstrip()}\n\n" + "\n".join(bloc) + "\n"
    debut = titres[section]
    fin = next((i for i in range(debut + 1, len(l)) if RE_TITRE_N1.match(l[i])), len(l))
    while fin > debut + 1 and not l[fin - 1].strip():
        fin -= 1                                   # avant les lignes vides de fin de section
    return "\n".join(l[:fin] + lignes + l[fin:]) + "\n"


def inserer_corps(txt: str, texte: str) -> str:
    """Ajoute un paragraphe à la fin du texte principal (avant la première section)."""
    l = txt.splitlines()
    section = next((i for i, x in enumerate(l) if RE_TITRE_N1.match(x)), len(l))
    fin = section
    while fin > 0 and not l[fin - 1].strip():
        fin -= 1                                   # fin réelle du texte principal
    suite = [""] + l[section:] if section < len(l) else []
    return "\n".join(l[:fin] + ["", texte.strip()] + suite).rstrip() + "\n"


def creer_note(titre, contenu, tags, liens, ids, source, nid=None) -> Note:
    """Nouvelle note YYYYMMDDHHMMSS-slug.org (format par défaut d'org-roam)."""
    nid = nid or str(uuid.uuid4()).upper()
    t = datetime.now()
    path = cfg.NOTES_DIR / f"{t:%Y%m%d%H%M%S}-{slug(titre)}.org"
    i = 1
    while path.exists():
        path = cfg.NOTES_DIR / f"{t:%Y%m%d%H%M%S}-{slug(titre)}-{i}.org"
        i += 1
    tags = list(dict.fromkeys(slug(x) for x in tags if slug(x)))[:4]
    txt = f":PROPERTIES:\n:ID:       {nid}\n:END:\n#+title: {titre}\n"
    if tags:
        txt += f"#+filetags: :{':'.join(tags)}:\n"
    txt += f"\n{contenu.strip()}\n"
    if liens:
        txt += "\n* Liens\n" + "\n".join(lignes_liens(liens, ids)) + "\n"
    txt += f"\n* {SECTION_FINALE}\n- {source} (note créée le {t:%Y-%m-%d})\n"
    path.write_text(txt, encoding="utf-8")
    return Note(nid, titre, path, [], tags, re.sub(r"\s+", " ", contenu)[:400])


def completer_note(note: Note, contenu, liens, ids, source):
    """Ajout uniquement : le texte en fin de contenu principal, les liens dans « * Liens »,
    la source dans « * Source ». Le contenu existant n'est jamais réécrit."""
    t = datetime.now()
    avant = note.path.read_text(encoding="utf-8")
    liens = [l for l in liens if f"[[id:{l['id']}]" not in avant]     # déjà liée : pas de doublon
    txt = inserer_corps(avant, contenu)
    if liens:
        txt = inserer_dans_section(txt, "Liens", lignes_liens(liens, ids))
    txt = inserer_dans_section(txt, SECTION_FINALE, [f"- {source} (complément du {t:%Y-%m-%d})"])
    note.path.write_text(txt, encoding="utf-8")
