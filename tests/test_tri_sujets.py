"""Une action (« Migrer l'ingress controller… ») devient une tâche, pas une note."""

from datetime import datetime

import pytest
from conftest import ecrire_note

from zettel.contenu import (
    PROMPT_EXTRACTION,
    SCHEMA_SUJETS,
    fusionner_sujets,
    traiter_entree,
)
from zettel.index import lire_note
from zettel.suivi import lignes_todo
from zettel.tri_sujets import commence_par_un_verbe, est_action, nature, separer_actions

QUAND = datetime(2026, 11, 2, 17, 50)
KUBE = {"titre": "Kubernetes", "contenu": "Cluster sur Raspberry Pi.", "nature": "projet"}
MIGRER = {"titre": "Migrer l'ingress controller vers la gateway", "contenu": "Nginx déprécié.",
          "nature": "concept"}


@pytest.mark.parametrize("titre, attendu", [
    ("Migrer l'ingress controller vers la gateway", True),
    ("Déployer Forgejo", True),
    ("deployer Forgejo", True),               # accents et casse ignorés
    ("Mettre en place restic", True),
    ("Docker", False),                         # finit par -er, mais pas un verbe de la liste
    ("Migration vers Gateway API", False),     # un nom : reste un sujet possible
    ("Rust", False),
    ("", False),
])
def test_commence_par_un_verbe(titre, attendu):
    assert commence_par_un_verbe(titre) is attendu


def test_nature_et_ancien_format():
    assert nature({"nature": "action"}) == "action"
    assert nature({"est_projet": True}) == "projet"
    assert nature({"est_projet": False}) == "concept"
    assert nature({"nature": "n'importe quoi"}) == "concept"


def test_une_note_existante_au_titre_d_action_est_respectee(chemins):
    n = lire_note(ecrire_note(chemins, "m.org", "ID-M", "Migrer vers Wayland", "Ma note."))
    assert not est_action({"titre": "Migrer vers Wayland", "nature": "action"}, {n.id: n})
    assert est_action({"titre": "Fondue", "nature": "action"}, {n.id: n})


def test_separer_actions_rattache_au_projet_de_l_entree():
    sujets, taches, converties = separer_actions([KUBE, MIGRER], [], {})
    assert sujets == [KUBE]
    assert converties == [MIGRER["titre"]]
    assert taches == [{"texte": MIGRER["titre"], "projet": "Kubernetes", "date": "",
                       "date_limite": False, "en_cours": False}]


def test_separer_actions_sans_doublon_ni_projet():
    deja = {"texte": "Migrer l'ingress controller vers la gateway.", "projet": "Kubernetes",
            "date": "", "date_limite": False, "en_cours": True}
    _, taches, _ = separer_actions([KUBE, MIGRER], [deja], {})
    assert taches == [deja]                               # la tâche de Qwen est gardée telle quelle
    sujets, taches, _ = separer_actions([{**MIGRER, "nature": "action"}], [], {})
    assert sujets == [] and taches[0]["projet"] == ""     # → note du jour


def test_fusion_garde_la_nature_la_plus_forte():
    s = fusionner_sujets([{"titre": "K", "contenu": "a", "nature": "action"},
                          {"titre": "k", "contenu": "b", "nature": "projet"}])
    assert s[0]["nature"] == "projet"


def test_tache_en_cours():
    assert lignes_todo({"texte": "Migrer", "date": "", "en_cours": True}, QUAND)[0] \
        == "** STRT Migrer"


def test_schema_et_prompt():
    sujet = SCHEMA_SUJETS["properties"]["sujets"]["items"]
    assert sujet["properties"]["nature"]["enum"] == ["concept", "projet", "action"]
    assert "en_cours" in SCHEMA_SUJETS["properties"]["taches"]["items"]["required"]
    assert "en_cours" in PROMPT_EXTRACTION and "ACTION" in PROMPT_EXTRACTION


def test_dictee_kubernetes(faux_llm, chemins, ctx):
    """Cas réel du 2026-11-02 17:50 : la migration devient un STRT dans la note Kubernetes,
    aucune note « Migrer… » n'est créée."""
    c = ctx()
    c.quand = QUAND
    faux_llm.reponses = [
        {"sujets": [KUBE, MIGRER], "perso": [], "suivi": [], "rendez_vous": [],
         "taches": [{"texte": "Migrer l'ingress controller vers la gateway", "projet": "Kubernetes",
                     "date": "", "date_limite": False, "en_cours": True}]},
        {"action": "creer", "cible_id": "", "titre": "Kubernetes", "tags": ["infrastructure"],
         "contenu": "Cluster sur Raspberry Pi.", "liens": []},
    ]
    actions = traiter_entree("…", c)
    assert len(faux_llm.appels) == 2                       # pas de décision pour l'action
    assert actions[0] == "+ créée : Kubernetes"
    assert any(a.startswith("☐ STRT Migrer l'ingress") for a in actions)
    notes = list(chemins.glob("*.org"))
    assert len(notes) == 1
    txt = notes[0].read_text(encoding="utf-8")
    assert "** STRT Migrer l'ingress controller vers la gateway" in txt
    assert ":projet:" in txt
