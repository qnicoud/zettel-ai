"""Tâche « renommer » : change le #+title d'une note. L'ancien titre devient un alias
org-roam (la note reste trouvable), et les liens dont le libellé était l'ancien titre
sont mis à jour dans les autres notes. L'ID et le nom de fichier ne changent pas."""

from ..contexte import Contexte
from ..index import fichiers_org, meme_titre
from ..ollama import embed, llm
from ..structure import ajouter_alias, definir_titre, renommer_libelles
from .base import Tache, candidats, liste_notes, note_reelle, refus

PROMPT = """On te donne une demande de renommage d'une note org-roam et une liste de notes
(id, titre, extrait). note_id = id de la note à renommer (UNIQUEMENT un id de la liste),
nouveau_titre = le nouveau titre demandé, tel quel."""

SCHEMA = {
    "type": "object",
    "properties": {"note_id": {"type": "string"}, "nouveau_titre": {"type": "string"}},
    "required": ["note_id", "nouveau_titre"],
}


def executer(consigne: str, sujet: str, ctx: Contexte) -> str:
    vec = embed([consigne])[0]
    d = llm(PROMPT, f"Demande : {consigne}\n\nNotes :\n{liste_notes(candidats(consigne, vec, ctx))}",
            SCHEMA)
    note, titre = note_reelle(ctx, d["note_id"]), d["nouveau_titre"].strip()
    if note is None:
        return refus(f"note inconnue « {d['note_id']} »")
    if not titre or titre == note.titre:
        return refus(f"nouveau titre « {titre} » vide ou identique")
    if (autre := meme_titre(titre, ctx.ids)) and autre.id != note.id:
        return refus(f"le titre « {titre} » est déjà pris par une autre note")
    ancien = note.titre
    print(f"  ✎ RENOMMER « {ancien} » → « {titre} »")
    if ctx.dry_run:
        return f"Simulation : « {ancien} » renommée « {titre} »."
    txt = note.path.read_text(encoding="utf-8")
    note.path.write_text(ajouter_alias(definir_titre(txt, titre), [ancien]), encoding="utf-8")
    ctx.lot_remaniement.ajouter(note.path, f"✎ {ancien} → {titre}")
    for p in fichiers_org():
        if p == note.path:
            continue
        avant = p.read_text(encoding="utf-8")
        if (apres := renommer_libelles(avant, note.id, ancien, titre)) != avant:
            p.write_text(apres, encoding="utf-8")
            ctx.lot_remaniement.ajouter(p, f"~ libellé du lien vers « {titre} »")
    note.titre, note.alias = titre, [*note.alias, ancien]
    return f"Fait : « {ancien} » renommée « {titre} » (ancien titre gardé en alias)."


TACHE = Tache(
    nom="renommer",
    description="changer le titre d'une note existante",
    executer=executer,
    ecrit=True,
)
