"""Tâche « marquer_fait » : « j'ai fini… » -> le TODO correspondant passe à DONE (ou KILL).
Qwen ne fait que désigner des numéros dans la liste des todos ouverts ; le script change
le mot-clé sur la ligne et ajoute « CLOSED: [...] » comme org-log-done 'time."""

import re
from datetime import datetime

from .. import config as cfg
from ..contexte import Contexte
from ..ollama import llm
from .base import Tache, refus
from .todos import RE_MOTS_TODO, Todo, todos_ouverts

JOURS_ORG = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
RE_PLANNING = re.compile(r"^(\s*)((?:SCHEDULED|DEADLINE):)")

PROMPT = """On te donne une liste numérotée de tâches encore ouvertes (todo), chacune précédée
du titre de sa note entre crochets, et une phrase où j'annonce avoir terminé ou abandonné
quelque chose.
numeros = les numéros des tâches que la phrase désigne CLAIREMENT (au plus 5). En cas de
doute, ou si aucune ne correspond, liste vide : mieux vaut ne rien cocher que cocher la
mauvaise tâche.
etat = "fait" si c'est terminé, "abandonne" si j'y renonce."""

SCHEMA = {
    "type": "object",
    "properties": {
        "numeros": {"type": "array", "items": {"type": "integer"}},
        "etat": {"type": "string", "enum": ["fait", "abandonne"]},
    },
    "required": ["numeros", "etat"],
}


def mot_final(txt: str, abandon: bool) -> str:
    """1er (ou 2e pour un abandon) mot-clé après « | » d'une ligne #+TODO:, sinon config."""
    for ligne in RE_MOTS_TODO.findall(txt):
        avant, sep, apres = ligne.partition("|")
        finis = [re.sub(r"\(.*\)$", "", m) for m in (apres.split() if sep else avant.split()[-1:])]
        if finis:
            return finis[1] if abandon and len(finis) > 1 else finis[0]
    return cfg.MOT_ABANDON if abandon else cfg.MOT_FAIT


def horodatage_inactif(t: datetime) -> str:
    return f"[{t:%Y-%m-%d} {JOURS_ORG[t.weekday()]} {t:%H:%M}]"


def clore(lignes: list[str], todo: Todo, mot: str, quand: datetime) -> list[str]:
    """Nouveau contenu du fichier. Vérifie que la ligne est toujours ce todo ouvert."""
    i = todo.ligne - 1
    if i >= len(lignes) or not re.match(rf"^\*+\s+{re.escape(todo.etat)}\s", lignes[i]):
        raise ValueError(f"la ligne {todo.ligne} a changé")
    nouv = list(lignes)
    nouv[i] = re.sub(rf"^(\*+\s+){re.escape(todo.etat)}\b", rf"\g<1>{mot}", lignes[i], count=1)
    closed = f"CLOSED: {horodatage_inactif(quand)}"
    if i + 1 < len(nouv) and (m := RE_PLANNING.match(nouv[i + 1])):
        nouv[i + 1] = f"{m.group(1)}{closed} {nouv[i + 1][len(m.group(1)):]}"
    else:
        nouv.insert(i + 1, closed)
    return nouv


def executer(consigne: str, sujet: str, ctx: Contexte) -> str:
    todos = todos_ouverts()
    if not todos:
        return "Aucun todo ouvert dans la base."
    liste = "\n".join(f"{i}. [{t.note}] {t.etat} {t.texte}" for i, t in enumerate(todos, 1))
    d = llm(PROMPT, f"Phrase : {consigne}\n\nTâches ouvertes :\n{liste}", SCHEMA)
    choisis = [todos[n - 1] for n in sorted(set(d["numeros"]))[:5] if 1 <= n <= len(todos)]
    if not choisis:
        return refus("aucune tâche ouverte ne correspond clairement")
    abandon = d["etat"] == "abandonne"
    faits = []
    # par fichier, en partant du bas : les numéros de ligne des autres todos restent valides
    for t in sorted(choisis, key=lambda t: (str(t.path), -t.ligne)):
        mot = mot_final(t.path.read_text(encoding="utf-8"), abandon)
        print(f"  ✔ {t.etat} → {mot} : {t.texte} ({t.note})")
        faits.append(f"{mot} {t.texte} ({t.note})")
        if ctx.dry_run:
            continue
        lignes = t.path.read_text(encoding="utf-8").splitlines()
        try:
            t.path.write_text("\n".join(clore(lignes, t, mot, datetime.now())) + "\n",
                              encoding="utf-8")
        except ValueError as e:
            return refus(f"{t.texte} : {e}")
        ctx.lot_remaniement.ajouter(t.path, f"✔ {mot} {t.texte} ({t.note})")
    prefixe = "Simulation : " if ctx.dry_run else ""
    return prefixe + "Tâche(s) clôturée(s) :\n" + "\n".join(f"- {f}" for f in reversed(faits))


TACHE = Tache(
    nom="marquer_fait",
    description="marquer comme terminée ou abandonnée une tâche TODO existante "
                "(« j'ai fini… », « c'est fait », « j'abandonne… »)",
    executer=executer,
    ecrit=True,
)
