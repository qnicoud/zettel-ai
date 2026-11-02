"""Entrée de journal ordinaire -> sujets (concepts) -> créer / compléter / ignorer,
puis tâches, suivi de projet et infos perso (voir suivi.py)."""

import re
import uuid

from . import config as cfg
from .contexte import Contexte
from .ecriture import (
    completer_note,
    creer_note,
    lier_mentions,
    nettoyer_contenu,
    nettoyer_liens_texte,
)
from .index import Note, meme_titre, plus_proches, titres_existants
from .ollama import embed, llm
from .suivi import appliquer_suivi
from .tri_sujets import NATURES, est_projet, nature, separer_actions

PROMPT_EXTRACTION = """Tu analyses une entrée de mon journal intime, dictée puis transcrite
automatiquement (fautes, hésitations et répétitions possibles), pour alimenter ma base org-roam.
Range ce qu'elle contient dans cinq listes.

1. sujets : ce qui mérite une note permanente. La base est organisée par CONCEPTS : une note
   par sujet (« Rust », « Compiled language »), qui regroupe tout ce qu'on sait du sujet.
   Sont des sujets : concepts, technologies, outils, méthodes ; idées, réflexions,
   apprentissages ; PROJETS PERSONNELS (ce que je crée : application, programme, script,
   œuvre). « Ce week-end j'ai développé X » : X est un sujet.
   - Regroupe TOUTES les informations sur un même sujet dans un seul élément (Rust, son
     ownership et sa gestion mémoire = UN sujet « Rust »). Ne sépare une notion que si
     l'entrée apporte une vraie information sur elle.
   - Une technologie ou un outil seulement cité (« écrit en Kotlin », « avec Claude Code »)
     n'est PAS un sujet : nomme-le dans le contenu du sujet principal (le lien vers sa
     note éventuelle sera ajouté ensuite).
   - titre = NOM du concept ou du projet, 1 à 4 mots (« Rust », « Hyprbinds »), jamais une
     phrase ni un verbe. S'il existe déjà une note sur ce sujet (liste fournie), reprends
     EXACTEMENT son titre.
   - Une ACTION (migrer, installer, configurer, remplacer… : « Migrer X vers Y ») n'est JAMAIS
     un sujet : c'est une tâche du projet ou du sujet concerné (liste 2).
   - contenu = les informations sur le sujet, reformulées clairement, autonomes, en
     français. Pour un projet : but, technologies, état actuel (les choses à faire vont dans
     taches, pas ici).
   - nature = "projet" pour un projet personnel (ou mon installation : serveur, cluster…),
     "concept" pour tout le reste, "action" si c'est en fait une chose à faire (elle sera
     alors traitée comme une tâche : mets-la plutôt directement dans taches).
2. taches : ce que j'ai à faire (« je dois », « il faut que », « il faudrait ajouter »…) OU
   que je suis en train de faire (« je suis en train de », « je commence à », « je vais »),
   en action courte à l'infinitif, 10 mots au plus (« Ajouter la connexion à un agent »).
   - en_cours = true si j'ai déjà commencé (« je suis en train de migrer… »), false sinon.
   - projet = titre du projet concerné (un sujet ci-dessus ou une note existante), vide sinon.
   - date = AAAA-MM-JJ UNIQUEMENT si l'entrée mentionne un moment (« demain », « vendredi »,
     « avant la fin du mois » : calcule-le à partir de la date de la dictée). Si aucun moment
     n'est mentionné, date = "" : ne mets JAMAIS la date de la dictée par défaut.
   - date_limite = true pour une échéance (« avant », « au plus tard »), false pour le jour prévu.
3. suivi : une étape TERMINÉE d'un projet (« Première version installée sur le téléphone »),
   une phrase courte, avec projet = titre du projet. Ce qui est en cours ou à faire va dans
   taches, jamais ici.
4. perso : MA vie hors projets et hors sujets : démarches, santé, famille, événements,
   nouvelles. Une phrase courte chacune, qui dit précisément quoi : n'écris JAMAIS d'élément
   vague (« événement non spécifié ») ; s'il n'y a rien de précis, liste vide.
5. rendez_vous : un rendez-vous ou un événement à un jour précis (« demain à 13h30, coiffeur »).
   - texte = quoi et où, court (« Coiffeur, sur le site du travail »).
   - date = AAAA-MM-JJ, calculée à partir de la date de la dictée ; heure = HH:MM, ou "" si
     aucune heure n'est dite.
   - Il va UNIQUEMENT ici, jamais aussi dans perso. Sans jour précis, ce n'est pas un
     rendez-vous : mets-le dans perso.

Chaque information va dans UNE seule liste : ce qui concerne un sujet ou un projet n'est
jamais répété dans perso.
La transcription déforme souvent les noms propres : écris-les avec l'orthographe de la liste
« Noms propres » fournie dès que tu les reconnais (« Hyper CTL » -> « hyprctl »).
Ignore tout ce qui parle de la dictée, du micro, du journal ou de ce traitement lui-même
(« ceci est un test », « cette entrée va être traitée ») : ce n'est ni perso ni un sujet.
N'invente rien. Pour le reste, dans le doute, GARDE l'information : tout est relu.

Exemple, dictée le 2026-03-10 : « Hier soir j'ai écrit un script Bash, photo-backup, qui
copie mes photos sur le NAS chaque nuit ; ça marche, il faudra ajouter le chiffrement avant
la fin du mois. Et je dois appeler le garage demain, la voiture fait un bruit bizarre.
Dentiste jeudi à 9 h. Sur mon serveur maison, je suis en train de remplacer Docker par
Podman. »
-> sujets : « photo-backup » (projet : but, Bash, fonctionne) ;
   taches : « Ajouter le chiffrement » (projet photo-backup, 2026-03-31, date_limite),
            « Appeler le garage » (sans projet, 2026-03-11),
            « Remplacer Docker par Podman » (projet Serveur maison, en_cours) ;
   suivi : photo-backup « Script écrit, il fonctionne » ;
   perso : « La voiture fait un bruit bizarre » ;
   rendez_vous : « Dentiste » (2026-03-12, 09:00).
« Test du micro, ceci est un essai de dictée » -> toutes les listes vides."""

JOURS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")

PROMPT_DECISION = """Tu gères une base org-roam organisée par CONCEPTS : une note par sujet,
au titre court, qui regroupe tout ce qu'on sait du sujet et renvoie vers les concepts voisins.
On te donne un sujet issu du journal et les notes existantes les plus proches (avec leur id).
Décide :
- "completer" si une note existante porte sur LE MÊME sujet (même nom, synonyme ou
  traduction : « Langage compilé » = « Compiled language ») : cible_id = son id, contenu =
  UNIQUEMENT ce qui est nouveau par rapport à son extrait ;
- "creer" si aucune note ne porte sur ce sujet : titre = nom court du concept,
  contenu = la note complète ;
- "ignorer" si tout est déjà dans la note existante.
Une note plus générale ou voisine (« Programming Languages », « Compiled language » pour
« Rust ») n'est PAS le même sujet : crée la note et fais un lien vers elle.

Forme du contenu (syntaxe Org) :
- AUCUN TITRE : en Org, une ligne qui commence par « * » est un titre. N'en écris jamais.
  Uniquement des paragraphes et des listes dont chaque élément commence par « - ».
- *gras* et /italique/ seulement à l'intérieur d'une phrase, jamais en début de ligne.
- Pas de ligne de liens ni de ligne de tags dans le contenu : les liens vont dans le champ
  liens, les tags dans le champ tags.
- Écris directement la version finale : jamais d'hésitation ni d'auto-correction
  (« non, c'est… », « -> »).
Exemple de contenu correct :
  Rust est un langage compilé centré sur la sûreté mémoire.
  - Le système d'/ownership/ évite les fuites mémoire.
  - Une variable sans propriétaire est libérée automatiquement.

Liens :
- N'écris AUCUN lien dans le contenu : du texte simple, qui nomme les choses telles qu'elles
  sont dans l'entrée (« écrit en Kotlin » reste « écrit en Kotlin »). Les liens vers les notes
  dont le nom apparaît dans le texte sont ajoutés automatiquement ensuite.
- Dans le champ liens : les notes de la liste réellement liées au sujet (au plus 5), avec une
  raison courte. Utilise UNIQUEMENT des id de la liste. Si aucune n'est liée, liste vide.
Les tags sont 1 à 3 mots simples, en minuscules."""

SCHEMA_SUJETS = {
    "type": "object",
    "properties": {
        "sujets": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"titre": {"type": "string"}, "contenu": {"type": "string"},
                               "nature": {"type": "string", "enum": list(NATURES)}},
                "required": ["titre", "contenu", "nature"],
            },
        },
        "taches": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"texte": {"type": "string"}, "projet": {"type": "string"},
                               "date": {"type": "string"}, "date_limite": {"type": "boolean"},
                               "en_cours": {"type": "boolean"}},
                "required": ["texte", "projet", "date", "date_limite", "en_cours"],
            },
        },
        "suivi": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"projet": {"type": "string"}, "texte": {"type": "string"}},
                "required": ["projet", "texte"],
            },
        },
        "perso": {"type": "array", "items": {"type": "string"}},
        "rendez_vous": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"texte": {"type": "string"}, "date": {"type": "string"},
                               "heure": {"type": "string"}},
                "required": ["texte", "date", "heure"],
            },
        },
    },
    "required": ["sujets", "taches", "suivi", "perso", "rendez_vous"],
}

SCHEMA_DECISION = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["creer", "completer", "ignorer"]},
        "cible_id": {"type": "string"},
        "titre": {"type": "string"},
        "contenu": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}},
        "liens": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"id": {"type": "string"}, "raison": {"type": "string"}},
                "required": ["id", "raison"],
            },
        },
    },
    "required": ["action", "cible_id", "titre", "contenu", "tags", "liens"],
}


def decider(sujet: dict, candidats: list[Note]) -> dict:
    liste = "\n".join(
        f"- id: {n.id} | titre: {n.titre} | tags: {', '.join(n.tags) or '-'} | extrait: {n.extrait[:250]}"
        for n in candidats) or "(aucune note existante)"
    user = (f"Sujet à classer\nTitre proposé : {sujet['titre']}\nContenu : {sujet['contenu']}\n\n"
            f"Notes existantes les plus proches :\n{liste}")
    return llm(PROMPT_DECISION, user, SCHEMA_DECISION)


def valider(d: dict, ids: dict) -> dict:
    """ID inconnus rejetés, cible inconnue -> création, titre existant -> complément."""
    action = d["action"]
    cible = d.get("cible_id", "").strip()
    if action == "completer" and cible not in ids:
        print(f"    (cible inconnue « {cible} » → création)")
        action = "creer"
    if action == "creer" and (meme := meme_titre(d["titre"], ids)):   # pas de doublon de titre
        action, cible = "completer", meme.id
    contenu, liens_lignes = nettoyer_contenu(d["contenu"])    # aucun titre dans le contenu
    contenu, lies_texte = nettoyer_liens_texte(contenu, ids, cible)   # s'il en a écrit malgré tout
    contenu, lies_texte = lier_mentions(contenu, ids, cible)
    vus, liens = set(lies_texte), []   # section Liens : seulement ce qui n'est pas déjà dans le texte
    for l in liens_lignes + d["liens"]:
        lid = l["id"].strip()
        if lid in ids and lid != cible and lid not in vus:
            vus.add(lid)
            liens.append({"id": lid, "raison": l["raison"]})
        elif lid not in ids:
            print(f"    (lien vers id inventé « {lid} » ignoré)")
    return {**d, "action": action, "cible_id": cible, "contenu": contenu,
            "liens": liens[:cfg.MAX_LIENS], "lies_texte": lies_texte}


def fusionner_sujets(sujets: list[dict]) -> list[dict]:
    """Deux sujets au même titre (casse ignorée) n'en font qu'un : une note par concept."""
    par_titre: dict[str, dict] = {}
    for s in sujets:
        cle = s["titre"].strip().lower()
        if cle in par_titre:
            p = par_titre[cle]
            natures = {nature(p), nature(s)}
            n = next(x for x in ("projet", "concept", "action") if x in natures)
            par_titre[cle] = {**p, "contenu": f"{p['contenu'].strip()}\n\n{s['contenu'].strip()}",
                              "nature": n}
        else:
            par_titre[cle] = s
    return list(par_titre.values())


def traiter_entree(texte: str, ctx: Contexte) -> list[str]:
    """Traite une entrée ordinaire. Renvoie le résumé des actions (pour le rapport)."""
    q = ctx.quand
    user = (f"Date de la dictée : {q:%Y-%m-%d} ({JOURS[q.weekday()]})\n\n"
            f"Noms propres (orthographe exacte) : {', '.join(cfg.NOMS_PROPRES)}\n\n"
            f"Titres des notes existantes :\n{titres_existants(ctx.notes)}\n\n"
            f"Entrée du journal :\n\n{texte}")
    r = llm(PROMPT_EXTRACTION, user, SCHEMA_SUJETS)
    sujets, taches, converties = separer_actions(fusionner_sujets(r["sujets"]),
                                                 r.get("taches", []), ctx.ids)
    for titre in converties:
        print(f"  (« {titre} » est une action : tâche au lieu d'une note)")
    r = {**r, "taches": taches}
    print(f"  {len(sujets)} sujet(s) : {', '.join(s['titre'] for s in sujets) or '-'}"
          f" | {len(r.get('taches', []))} tâche(s), {len(r.get('suivi', []))} suivi(s),"
          f" {len(r.get('perso', []))} info(s) perso, {len(r.get('rendez_vous', []))} rendez-vous")
    actions = []
    for sujet in sujets:     # d'abord les sujets : les tâches peuvent viser un projet créé ici
        vec = embed([f"{sujet['titre']}. {sujet['contenu']}"])[0]
        d = valider(decider(sujet, plus_proches(vec, ctx.notes, cfg.TOP_K)), ctx.ids)
        if est_projet(sujet) and "projet" not in d["tags"]:
            d = {**d, "tags": ["projet", *d["tags"]]}
        if (ligne := appliquer(d, vec, ctx)):
            actions.append(ligne)
    return actions + appliquer_suivi({**r, "perso": filtrer_perso(r), "sujets": sujets}, ctx)


def filtrer_perso(r: dict) -> list[str]:
    """Retire des infos perso celles qui citent un sujet ou un projet de la même entrée :
    elles sont déjà dans la note du sujet ou dans le suivi du projet."""
    noms = {s["titre"] for s in r.get("sujets", [])}
    noms |= {x.get("projet", "") for x in r.get("taches", []) + r.get("suivi", [])}
    noms = {n.strip().lower() for n in noms if len(n.strip()) >= 3}
    garde = []
    for p in r.get("perso", []):
        if any(n in p.lower() for n in noms):
            print(f"  (info perso en doublon d'un sujet retirée : « {p[:60]} »)")
        else:
            garde.append(p)
    return garde


def appliquer(d: dict, vec, ctx: Contexte) -> str | None:
    tous_liens = list(d["lies_texte"]) + [l["id"] for l in d["liens"]]
    liens_txt = ", ".join(ctx.ids[i].titre for i in tous_liens) or "aucun"
    if d["action"] == "ignorer":
        print(f"  - ignoré : {d['titre']}")
        return None
    if d["action"] == "creer":
        print(f"  + CRÉER « {d['titre']} »  liens : {liens_txt}")
        if ctx.dry_run:   # note simulée : les sujets suivants peuvent la compléter ou la lier
            n = Note(f"simulation-{uuid.uuid4()}", d["titre"], None, [], d["tags"],
                     re.sub(r"\s+", " ", d["contenu"])[:400])
        else:
            n = creer_note(d["titre"], d["contenu"], d["tags"], d["liens"], ctx.ids, ctx.source)
            ctx.lot_notes.ajouter(n.path, f"+ {d['titre']}")
        n.vec = vec
        ctx.ajouter_note(n)
        ligne = f"+ créée : {d['titre']}"
    else:
        cible = ctx.ids[d["cible_id"]]
        print(f"  ~ COMPLÉTER « {cible.titre} »  liens : {liens_txt}")
        if not ctx.dry_run:
            completer_note(cible, d["contenu"], d["liens"], ctx.ids, ctx.source)
            ctx.lot_notes.ajouter(cible.path, f"~ {cible.titre}")
        ligne = f"~ complétée : {cible.titre}"
    if ctx.dry_run:
        print("    " + d["contenu"].strip().replace("\n", "\n    "))
    return ligne
