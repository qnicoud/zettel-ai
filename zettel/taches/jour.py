"""Outils communs au bilan et à la préparation d'une journée : journée demandée, mise en forme."""

from datetime import date

from .. import config as cfg
from ..contexte import Contexte
from ..dates import JOURS, date_dans
from ..ollama import llm

PROMPT_DATE = """On te donne une demande adressée à l'assistant d'une base de notes, et la date
du jour. date = la journée dont parle la demande, au format AAAA-MM-JJ, calculée à partir de
la date du jour. Si la demande ne désigne aucune journée précise, date = "" (chaîne vide)."""

SCHEMA_DATE = {
    "type": "object",
    "properties": {"date": {"type": "string"}},
    "required": ["date"],
}


def journee_demandee(consigne: str, ctx: Contexte, sens: int) -> date | None:
    """Journée visée, par rapport à la date de la dictée : reconnue par le code (« demain »,
    « jeudi dernier »…), sinon proposée par Qwen puis vérifiée ; aucune journée désignée =
    le jour même. None = date impossible ou trop lointaine (la tâche refuse)."""
    ref = ctx.quand.date()
    d = date_dans(consigne, ref, sens)
    if d is None:
        rep = llm(PROMPT_DATE, f"Date du jour : {ref:%Y-%m-%d} ({JOURS[ref.weekday()]})\n\n"
                               f"Demande : {consigne}", SCHEMA_DATE)["date"].strip()
        if not rep:
            return ref
        try:
            d = date.fromisoformat(rep)
        except ValueError:
            return None
    return d if abs((d - ref).days) <= cfg.ECART_MAX_JOURNEE else None


def bloc(titre: str, lignes: list[str]) -> str:
    """« Titre :\\n- …\\n- … », ou « » s'il n'y a rien (le bloc est alors omis)."""
    return f"{titre} :\n" + "\n".join(lignes) if lignes else ""


def assembler(entete: str, *blocs: str, vide: str) -> str:
    """En-tête puis blocs non vides, séparés par une ligne vide ; `vide` s'il n'y a rien."""
    pleins = [b for b in blocs if b]
    return "\n\n".join([entete, *(pleins or [vide])])
