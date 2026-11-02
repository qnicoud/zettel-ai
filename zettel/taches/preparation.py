"""Tâche « preparer_journee » (lecture seule) : programme d'une journée à venir (ou du jour).
Tout est lu de façon déterministe dans les notes ; le LLM ne sert, au besoin, qu'à comprendre
la date demandée."""

from datetime import date

from ..contexte import Contexte
from ..dates import nom_jour
from .agenda import TacheOrg, lire_base, note_du_jour, rendez_vous, section, taches_org
from .base import Tache, refus
from .jour import assembler, bloc, journee_demandee


def en_retard(t: TacheOrg, j: date) -> bool:
    return any(d is not None and d < j for d in (t.limite, t.prevue))


def executer(consigne: str, sujet: str, ctx: Contexte) -> str:
    j = journee_demandee(consigne, ctx, sens=1)
    if j is None:
        return refus("journée non reconnue ou trop lointaine")
    base = lire_base()
    ouvertes = [t for t in taches_org(base) if t.ouverte]
    a_faire = [t for t in ouvertes if t.prevue == j]
    a_rendre = [t for t in ouvertes if t.limite == j]
    focus = a_faire + a_rendre
    retard = sorted((t for t in ouvertes if t not in focus and en_retard(t, j)),
                    key=lambda t: min(d for d in (t.limite, t.prevue) if d is not None))
    autres = sorted((t for t in ouvertes if t not in focus and t not in retard),
                    key=lambda t: t.fichier.titre.lower())
    rdv = rendez_vous(base, j)
    print(f"    {nom_jour(j)} : {len(rdv)} rendez-vous, {len(a_faire)} prévue(s), "
          f"{len(a_rendre)} échéance(s), {len(retard)} en retard")
    return assembler(
        f"Programme du {nom_jour(j)}",
        bloc("Rendez-vous", [r.org() for r in rdv]),
        bloc("À faire ce jour-là", [t.org() for t in a_faire]),
        bloc("À rendre ce jour-là", [t.org() for t in a_rendre]),
        bloc("En retard", [t.org() for t in retard]),
        bloc("Notes du jour", section(note_du_jour(base, j), "Journal")),
        bloc(f"Autres tâches ouvertes ({len(autres)})", [t.org() for t in autres]),
        vide="Rien de prévu, aucune tâche ouverte.",
    )


TACHE = Tache(
    nom="preparer_journee",
    description="préparer une journée à venir ou celle d'aujourd'hui (« prépare demain », "
                "« qu'est-ce que j'ai jeudi ») : rendez-vous, tâches prévues, échéances, "
                "tâches en retard, puis les autres tâches ouvertes",
    executer=executer,
    ecrit=False,
)
