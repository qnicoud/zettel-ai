"""Tâche « lier » : ajoute un lien d'une note vers une autre, dans la section « * Liens »
de la note source (org-roam affiche le rétrolien de l'autre côté)."""

from ..contexte import Contexte
from ..ecriture import inserer_dans_section
from ..ollama import embed, llm
from .base import Tache, candidats, liste_notes, note_reelle, refus

PROMPT = """On te donne une demande de lien entre deux notes org-roam et une liste de notes
(id, titre, extrait). source_id = la note qui doit contenir le lien, cible_id = la note
vers laquelle il pointe (UNIQUEMENT des id de la liste), raison = en quelques mots, pourquoi
elles sont liées (reprends la demande si elle le dit)."""

SCHEMA = {
    "type": "object",
    "properties": {"source_id": {"type": "string"}, "cible_id": {"type": "string"},
                   "raison": {"type": "string"}},
    "required": ["source_id", "cible_id", "raison"],
}


def executer(consigne: str, sujet: str, ctx: Contexte) -> str:
    vec = embed([consigne])[0]
    d = llm(PROMPT, f"Demande : {consigne}\n\nNotes :\n{liste_notes(candidats(consigne, vec, ctx))}",
            SCHEMA)
    src, cible = note_reelle(ctx, d["source_id"]), note_reelle(ctx, d["cible_id"])
    if src is None or cible is None:
        return refus(f"note inconnue (« {d['source_id']} » ou « {d['cible_id']} »)")
    if src.id == cible.id:
        return refus("une note ne peut pas se lier à elle-même")
    txt = src.path.read_text(encoding="utf-8")
    if f"[[id:{cible.id}]" in txt:
        return f"« {src.titre} » contient déjà un lien vers « {cible.titre} » : rien à faire."
    raison = d["raison"].strip() or "lié"
    print(f"  🔗 LIER « {src.titre} » → « {cible.titre} » : {raison}")
    if ctx.dry_run:
        return f"Simulation : lien « {src.titre} » → « {cible.titre} »."
    ligne = f"- [[id:{cible.id}][{cible.titre}]] : {raison}"
    src.path.write_text(inserer_dans_section(txt, "Liens", [ligne]), encoding="utf-8")
    ctx.lot_remaniement.ajouter(src.path, f"🔗 {src.titre} → {cible.titre}")
    return f"Fait : lien « {src.titre} » → « {cible.titre} » ({raison})."


TACHE = Tache(
    nom="lier",
    description="ajouter un lien entre deux notes existantes",
    executer=executer,
    ecrit=True,
)
