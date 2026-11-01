"""Tâche « fusionner » : deux notes sur le même sujet n'en font plus qu'une.
Qwen choisit seulement quelle note est gardée et laquelle est absorbée ; tout le reste est
déterministe : le texte de la note absorbée est recopié tel quel, ses sections fusionnées
(sans lien en double ni lien vers soi), son titre devient un alias, tous les liens vers
elle sont redirigés, puis son fichier est supprimé."""

import re

from ..contexte import Contexte
from ..ecriture import inserer_corps, inserer_dans_section
from ..index import fichiers_org, lire_note
from ..ollama import embed, llm
from ..structure import (ajouter_alias, ajouter_tags, decouper, delier, lire_alias, lire_tags,
                         rediriger_liens, texte_lignes)
from .base import Tache, candidats, liste_notes, note_reelle, refus

PROMPT = """On te donne une demande de fusion de deux notes org-roam et une liste de notes
(id, titre, extrait). garder_id = la note qui reste (par défaut, la plus complète ou celle
dont le titre est le plus juste), absorber_id = celle qui disparaît dans la première.
UNIQUEMENT des id de la liste."""

SCHEMA = {
    "type": "object",
    "properties": {"garder_id": {"type": "string"}, "absorber_id": {"type": "string"}},
    "required": ["garder_id", "absorber_id"],
}
RE_ID = re.compile(r"\[\[id:([^\]]+)\]")


def fusionner_textes(txt_a: str, id_a: str, txt_b: str) -> str:
    """Texte de A après absorption de B (les liens de B vers A deviennent du texte)."""
    b = decouper(delier(txt_b, id_a))
    txt = txt_a
    if (corps := texte_lignes(b.corps).strip()):
        txt = inserer_corps(txt, corps)
    for titre, lignes in b.sections:
        lignes = [l for l in lignes if l.strip()]
        if titre == "Liens":       # pas de lien déjà présent dans A, ni de ligne devenue vide
            lignes = [l for l in lignes
                      if (ids := RE_ID.findall(l)) and not any(f"[[id:{i}]" in txt for i in ids)]
        if lignes:
            txt = inserer_dans_section(txt, titre, lignes)
    return txt


def executer(consigne: str, sujet: str, ctx: Contexte) -> str:
    vec = embed([consigne])[0]
    d = llm(PROMPT, f"Demande : {consigne}\n\nNotes :\n{liste_notes(candidats(consigne, vec, ctx))}",
            SCHEMA)
    a, b = note_reelle(ctx, d["garder_id"]), note_reelle(ctx, d["absorber_id"])
    if a is None or b is None:
        return refus(f"note inconnue (« {d['garder_id']} » ou « {d['absorber_id']} »)")
    if a.id == b.id:
        return refus("il faut deux notes différentes")
    print(f"  ⧉ FUSIONNER « {b.titre} » dans « {a.titre} »")
    if ctx.dry_run:
        return f"Simulation : « {b.titre} » fusionnée dans « {a.titre} »."
    txt_b = b.path.read_text(encoding="utf-8")
    txt = fusionner_textes(a.path.read_text(encoding="utf-8"), a.id, txt_b)
    txt = ajouter_tags(ajouter_alias(txt, [b.titre, *lire_alias(txt_b)]), lire_tags(txt_b))
    a.path.write_text(txt, encoding="utf-8")
    ctx.lot_remaniement.ajouter(a.path, f"⧉ {a.titre} ← {b.titre}")
    for p in fichiers_org():
        if p in (a.path, b.path):
            continue
        avant = p.read_text(encoding="utf-8")
        if (apres := rediriger_liens(avant, b.id, a.id)) != avant:
            p.write_text(apres, encoding="utf-8")
            ctx.lot_remaniement.ajouter(p, f"~ liens « {b.titre} » → « {a.titre} »")
    b.path.unlink()
    ctx.lot_remaniement.ajouter(b.path, f"- {b.titre} (fusionnée)")
    ctx.retirer_note(b)
    a.alias, a.extrait = [*a.alias, b.titre], (lire_note(a.path) or a).extrait
    return f"Fait : « {b.titre} » fusionnée dans « {a.titre} » (ancien titre gardé en alias)."


TACHE = Tache(
    nom="fusionner",
    description="fusionner deux notes existantes qui parlent du même sujet en une seule",
    executer=executer,
    ecrit=True,
)
