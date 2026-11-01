"""Tâche « extraire » : sortir une partie d'une note existante vers une nouvelle note.
Le LLM ne fait que désigner des numéros de lignes : le script déplace ces lignes telles
quelles, il ne peut donc ni inventer ni reformuler le contenu existant."""

import re
import uuid

from .. import config as cfg
from ..contexte import Contexte
from ..ecriture import creer_note, nettoyer_contenu, nettoyer_liens_texte
from ..index import lire_note, meme_titre
from ..ollama import embed, llm
from .base import Tache, candidats, liste_notes, note_reelle, refus

PROMPT_SOURCE = """On te donne une demande de réorganisation d'une base org-roam : sortir une
partie du contenu d'une note existante (la source) pour en faire une nouvelle note à part.
On te donne aussi une liste de notes existantes (id, titre, extrait).
source_id = id de la note qui contient aujourd'hui l'information (UNIQUEMENT un id de la
liste, n'en invente jamais), nouveau_titre = nom court du concept de la nouvelle note
(1 à 4 mots), sujet = en une phrase, ce qu'il faut déplacer."""

SCHEMA_SOURCE = {
    "type": "object",
    "properties": {
        "source_id": {"type": "string"},
        "nouveau_titre": {"type": "string"},
        "sujet": {"type": "string"},
    },
    "required": ["source_id", "nouveau_titre", "sujet"],
}

PROMPT_PLAGES = """On te donne une note org-roam aux lignes numérotées, et un sujet à déplacer
dans une nouvelle note.
Donne les plages de lignes (debut et fin incluses) qui traitent de ce sujet et doivent être
déplacées. Sélectionne des lignes entières, seulement celles qui concernent le sujet, et
jamais les lignes :PROPERTIES:, :ID:, :END: ni celles qui commencent par #+.
Ne réécris rien : ces lignes seront recopiées telles quelles.
Écris aussi intro : une phrase courte en français qui présente le sujet en tête de la nouvelle
note (syntaxe Org, jamais de Markdown), et 1 à 3 tags simples en minuscules."""

SCHEMA_PLAGES = {
    "type": "object",
    "properties": {
        "plages": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"debut": {"type": "integer"}, "fin": {"type": "integer"}},
                "required": ["debut", "fin"],
            },
        },
        "intro": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["plages", "intro", "tags"],
}


def lignes_protegees(lignes: list[str]) -> set[int]:
    """Numéros (à partir de 1) des lignes de drawer :PROPERTIES: et des mots-clés #+."""
    prot, dans_drawer = set(), False
    for i, l in enumerate(lignes, 1):
        s = l.strip().upper()
        if s == ":PROPERTIES:":
            dans_drawer = True
        if dans_drawer or l.lstrip().startswith("#+"):
            prot.add(i)
        if s == ":END:":
            dans_drawer = False
    return prot


def valider_plages(plages: list[dict], lignes: list[str]) -> list[tuple[int, int]]:
    prot, res = lignes_protegees(lignes), []
    for p in sorted(plages, key=lambda p: p["debut"]):
        a, b = p["debut"], p["fin"]
        if not 1 <= a <= b <= len(lignes):
            raise ValueError(f"plage {a}-{b} hors de la note ({len(lignes)} lignes)")
        if prot & set(range(a, b + 1)):
            raise ValueError(f"plage {a}-{b} touche l'en-tête de la note")
        if res and a <= res[-1][1]:
            raise ValueError(f"plages {res[-1][0]}-{res[-1][1]} et {a}-{b} se chevauchent")
        res.append((a, b))
    if not res:
        raise ValueError("aucune ligne à déplacer")
    return res


def deplacer(lignes: list[str], plages: list[tuple[int, int]], lien: str) -> tuple[str, str]:
    """Renvoie (texte déplacé, nouveau texte de la source). Le lien remplace la 1re plage."""
    deplace = "\n\n".join("\n".join(lignes[a - 1:b]).strip("\n") for a, b in plages)
    retirees = {i for a, b in plages for i in range(a, b + 1)}
    reste = []
    for i, l in enumerate(lignes, 1):
        if i == plages[0][0]:
            reste.append(lien)
        if i not in retirees:
            reste.append(l)
    return deplace, "\n".join(reste) + "\n"


def sans_titre_doublon(deplace: str, titre: str) -> str:
    """« * Hyprbinds » en tête du passage ferait doublon avec le #+title de la nouvelle note."""
    premiere, _, suite = deplace.partition("\n")
    if re.fullmatch(r"\*+\s+" + re.escape(titre) + r"\s*", premiere, re.I):
        return suite.strip("\n")
    return deplace


def executer(consigne: str, sujet: str, ctx: Contexte) -> str:
    vec = embed([consigne])[0]
    liste = liste_notes(candidats(consigne, vec, ctx))
    d = llm(PROMPT_SOURCE, f"Demande : {consigne}\n\nNotes :\n{liste}", SCHEMA_SOURCE)
    src, titre = note_reelle(ctx, d["source_id"]), d["nouveau_titre"].strip()
    if src is None:
        return refus(f"note source inconnue « {d['source_id']} »")
    if not titre or meme_titre(titre, ctx.ids):
        return refus(f"titre « {titre} » vide ou déjà pris par une note")
    lignes = src.path.read_text(encoding="utf-8").splitlines()
    numerote = "\n".join(f"{i:>4}| {l}" for i, l in enumerate(lignes, 1))
    e = llm(PROMPT_PLAGES, f"Sujet à déplacer : {d['sujet']}\nNouvelle note : {titre}\n\n"
                           f"Note « {src.titre} » :\n{numerote}", SCHEMA_PLAGES)
    try:
        plages = valider_plages(e["plages"], lignes)
    except ValueError as err:
        return refus(str(err))
    nid = str(uuid.uuid4()).upper()
    deplace, reste = deplacer(lignes, plages, f"Voir [[id:{nid}][{titre}]].")
    deplace = sans_titre_doublon(deplace, titre)
    resume = (f"« {titre} » extraite de « {src.titre} » (lignes "
              + ", ".join(f"{a}-{b}" for a, b in plages) + ")")
    print(f"  ✂ EXTRAIRE : {resume}")
    if ctx.dry_run:
        print("    " + deplace.replace("\n", "\n    "))
        return f"Simulation : {resume}."
    intro, _ = nettoyer_contenu(e["intro"])
    intro, lies = nettoyer_liens_texte(intro, ctx.ids, "")
    liens = [] if src.id in lies else [{"id": src.id, "raison": "note d'origine de ce contenu"}]
    n = creer_note(titre, f"{intro.strip()}\n\n{deplace}", e["tags"], liens, ctx.ids,
                   ctx.source, nid=nid)
    src.path.write_text(reste, encoding="utf-8")
    src.extrait = (lire_note(src.path) or src).extrait
    n.vec = vec
    ctx.ajouter_note(n)
    ctx.lot_remaniement.ajouter(n.path, f"+ {titre} (extrait de « {src.titre} »)")
    ctx.lot_remaniement.ajouter(src.path, f"~ {src.titre} : contenu déplacé vers « {titre} »")
    return f"Fait : {resume}. À relire sur la branche {cfg.REVIEW_BRANCH}."


TACHE = Tache(
    nom="extraire",
    description="sortir une partie du contenu d'une note existante pour en faire une "
                "nouvelle note à part (restructurer, séparer, déplacer des informations)",
    executer=executer,
    ecrit=True,
)
