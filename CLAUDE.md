# Projet : journaux vocaux → notes Zettelkasten org-roam (LLM local)

Contexte repris d'une discussion précédente. Langue de travail : **français**.

## Objectif

Traiter automatiquement mes journaux vocaux (dictés avec hyprwhspr, déjà transcrits en texte)
avec un LLM **local**, pour générer des notes Zettelkasten dans ma base **org-roam**.
Je valide moi-même tout ce que le script produit avant que ça arrive sur `main`.

## Machine

- Arch Linux + Hyprland
- 32 Go RAM, Intel i5 14e gen
- NVIDIA RTX 3060 **12 Go VRAM**
- hyprwhspr (Whisper) occupe ~5 Go de VRAM quand il est chargé

## Chemins

| Quoi | Où |
|---|---|
| Journaux dictés (entrée) | `~/Documents/journal-dictee.md` (une ligne `- [AAAA-MM-JJ HH:MM:SS] …` par dictée) ; réglage `JOURNAUX` / `chemins.journaux` = liste, fusion chronologique, absent → ignoré avec avertissement. **Jamais dans la base** (données brutes perso, poussée sur GitHub) |
| Base org-roam (dépôt git) | `~/bin/git-repos-personal/org-roam-database/` |
| État du script + cache embeddings | `~/.local/state/zettel_ai/` |
| Rapports des runs du journal | `~/.local/state/zettel_ai/rapports/*.org` |
| Worktree de relecture | `~/.local/state/zettel_ai/worktree` (branche `zettel-ai`) |
| Contrôle hyprwhspr | `/usr/lib/hyprwhspr/config/hyprland/hyprwhspr-tray.sh` |

## Stack

- **Ollama** (`ollama-cuda`, service systemd), API sur `http://localhost:11434`
- LLM : `hf.co/bartowski/Qwen_Qwen3.5-9B-GGUF:Q5_K_M` (≈7,1 Go), `think: false` par défaut,
  contexte 16k, température 0.3, sorties JSON structurées via le paramètre `format` d'Ollama
- Embeddings : `bge-m3` (multilingue, ≈1,2 Go) via `/api/embed`
- Python + `requests` (pas d'autre dépendance ; `pytest` pour les tests)
- Ollama installé via le paquet pacman `ollama-cuda` (l'ancienne install manuelle 0.6.2 dans
  `/usr/local` a été retirée : elle ne savait pas charger Qwen3.5)

## hyprwhspr

- `hyprwhspr-tray.sh` sans argument → JSON avec un champ `class`
- États possibles : `recording`, `ready`, `unloaded`, `stopped`, `error`
- `hyprwhspr-tray.sh stop` / `start` pour couper / relancer
- Règle actuelle dans les scripts :
  - `ready` → stop avant traitement, start après
  - `recording` → attendre la fin de la dictée (max 300 s), puis comme `ready`
  - `unloaded`, `stopped`, `error` → ne pas y toucher
- Toujours relancer dans un `finally` (+ handler SIGTERM pour systemd)
- Lire uniquement la première ligne de sortie du script (il peut émettre en continu)

## Scripts

### `zettel-ai` (commande principale, `zettel/cli.py`)

Choix d'architecture : **pipeline guidé plutôt qu'agent autonome**. Un 9B est peu fiable en
boucle d'outils libre (ID inventés, réécritures). Le script fait le déterministe, le LLM ne
prend que des décisions encadrées, validées avant écriture.

1. Découpe le journal en entrées (une ligne hyprwhspr `- [AAAA-MM-JJ HH:MM:SS] …` ou un titre `#`/`##`) ; ignore celles déjà traitées (`entrees_traitees.json` : clé
   `horodatage:AAAA-MM-JJ HH:MM:SS`, donc corriger une dictée ne la fait pas retraiter ; empreinte
   SHA-256 pour une entrée à titre `#`, et anciennes empreintes toujours reconnues).
2. Prépare le worktree `zettel-ai` et y fusionne `main` (arrêt propre en cas de conflit).
3. Indexe les notes `.org` du worktree : `:ID:` au niveau fichier, `#+title`, `#+filetags`,
   `:ROAM_ALIASES:`, extrait de 400 caractères. Embeddings en cache (clé = chemin + mtime).
4. Qwen extrait des **sujets/concepts** de chaque entrée (une note par concept, titre court type « Rust »,
   toutes les infos du sujet regroupées ; la liste des titres existants lui est fournie pour les réutiliser).
5. Pour chaque sujet : top-10 notes proches par cosinus → Qwen décide `creer` / `completer` /
   `ignorer` + jusqu'à 5 liens, et peut mettre des liens `[[id:…][…]]` directement dans le texte.
6. Validation : ID inconnus rejetés (y compris les liens dans le texte, remplacés par leur libellé), cible inconnue → création, titre déjà existant → complément,
   pas d'auto-lien.
7. Écriture :
   - nouvelle note : `YYYYMMDDHHMMSS-slug.org` (format par défaut org-roam), drawer `:ID:` (UUID),
     `#+title`, `#+filetags`, contenu **sans aucun titre** (paragraphes et listes `-`), puis
     uniquement les sections `* Liens` (liste `- [[id:…][Titre]] : raison`), `* Tâches`,
     `* Suivi` et `* Source` (liste, toujours en dernier)
   - garde-fous de forme (`ecriture.nettoyer_contenu`) : une ligne `* …` générée devient un
     paragraphe, « Lien avec [[id:…]] : … » part dans `* Liens`, lignes de tags retirées
   - liens dans le texte posés **par le script** (`ecriture.lier_mentions` : titre ou alias
     d'une note existante cité mot pour mot) ; Qwen n'écrit que du texte simple (sinon il
     remplaçait des mots par des titres de notes et écrivait son raisonnement dans la note)
   - complément : paragraphe ajouté à la fin du texte principal, liens ajoutés à `* Liens`
     (sans doublon), source ajoutée à `* Source` ; **jamais de réécriture** du contenu existant
   - les nouvelles notes sont ajoutées à l'index en cours de run (liables par les idées suivantes)
   - pas de backlinks écrits (org-roam les affiche lui-même)
   - exception : les entrées « Instruction : … » (voir ci-dessous) peuvent déplacer du contenu
8. Commit sur `zettel-ai` uniquement. **Ne jamais écrire sur `main`** ni dans le dossier de travail.
9. `finally` : `ollama stop` des deux modèles, relance hyprwhspr si besoin, commit de ce qui a été écrit.

#### Tâches, suivi de projet, logistique (`zettel/suivi.py`)

L'extraction (un seul appel Qwen, avec la date de la dictée) renvoie cinq listes :
`sujets` (`nature` : `concept` / `projet` / `action`), `taches` (`en_cours`), `suivi` (étapes terminées seulement), `perso`, `rendez_vous`
(texte, date, heure). Écriture, toujours
en ajout dans une section de niveau 1 (créée si absente) :

| Élément | Destination |
|---|---|
| tâche liée à un projet | `** TODO …` dans `* Tâches` de la note du projet (créée si absente, tag `projet`) |
| tâche sans projet | `** TODO …` dans `* Tâches` de `daily/AAAA-MM-JJ.org` |
| avancement d'un projet | `- [AAAA-MM-JJ] …` dans `* Suivi` de la note du projet |
| logistique / infos perso | `- HH:MM …` dans `* Journal` de `daily/AAAA-MM-JJ.org` |
| rendez-vous daté | `- <AAAA-MM-JJ Ddd HH:MM> …` dans `* Agenda` de la note du **jour du rendez-vous** + mention `Rendez-vous le …` dans `* Journal` du jour de la dictée (même ligne déjà présente → rien) ; sans date valable → simple info perso |

Actions (`zettel/tri_sujets.py`) : un sujet classé `action`, ou dont le titre commence par un
verbe de `VERBES_ACTION` (« Migrer… », accents ignorés), devient une tâche rattachée au premier
projet (sinon concept) de l'entrée, pas une note ; jamais si une note porte déjà ce titre.
Tâche `en_cours` (« je suis en train de… ») → mot-clé `MOT_EN_COURS` (`STRT`) au lieu de `TODO`.
Garde-fous dans le code : date `AAAA-MM-JJ` vérifiée (d'un mois avant à deux ans après la
dictée, sinon tâche gardée sans date) → `SCHEDULED:` ou `DEADLINE:` ; chaque nouveau TODO
reçoit `:PROPERTIES:` / `:CREATED:  [AAAA-MM-JJ Ddd HH:MM]` / `:END:` (après la planification) ; TODO déjà présent
(même texte, quel que soit l'état) non répété ; sujets de même titre fusionnés ; infos perso
qui citent un sujet/projet de l'entrée retirées. Les notes journalières (format
org-roam-dailies par défaut) sont exclues de l'index des concepts.
⚠ `org-agenda-files` (config Doom) ne contient que `org-notes/` : les TODO de la base
org-roam n'apparaissent dans l'agenda Emacs que si on y ajoute la base et son `daily/`.

#### Consignes et routeur de tâches

Une consigne vient soit d'une dictée qui commence par « Instruction » (déclencheur conservé
pour qu'une simple réflexion ne soit jamais exécutée), soit d'un prompt direct :
`zettel-ai "liste mes todos Rust"`. Un **routeur** (Qwen, `enum` fermé dans le
schéma JSON, + `sujet` extrait) choisit une tâche ou `inconnue` (→ rien n'est fait).
bge-m3 sert à retrouver les notes, pas à router (il n'extrait pas les paramètres).

| Tâche | Exécution | Écrit ? |
|---|---|---|
| `extraire` | Qwen choisit la note source (ID validé) puis des **numéros de lignes** ; le script les déplace mot pour mot (jamais d'en-tête, pas de chevauchement, titre neuf) et laisse `Voir [[id:…][Titre]].` | oui, commit séparé « remaniement demandé » |
| `fusionner` | Qwen choisit la note gardée et l'absorbée (ID validés) ; le script recopie le texte tel quel, fusionne les sections (sans lien en double ni vers soi), garde l'ancien titre en alias, redirige tous les liens, supprime le fichier | oui |
| `renommer` | `#+title` changé, ancien titre en alias, libellés `[[id:X][Ancien]]` mis à jour ailleurs ; ID et fichier inchangés | oui |
| `lier` | ajoute `- [[id:…][Titre]] : raison` dans `* Liens` de la note source (rien si déjà lié) | oui |
| `marquer_fait` | Qwen désigne des numéros dans la liste des todos ouverts ; le script passe le mot-clé à `DONE` (ou `KILL` si abandon, ou les mots-clés `#+TODO:` du fichier) et ajoute `CLOSED: [...]` (comme `org-log-done 'time`) | oui |
| `lister_todos` | lecture déterministe des titres org (`#+TODO:` respecté, sinon `TODO_OUVERTS`), échéance `DEADLINE`/`SCHEDULED` ; Qwen ne fait que filtrer par sujet (numéros validés) | non |
| `resumer` | bge-m3 → 6 notes les plus proches, Qwen résume **uniquement** à partir d'elles ; seules les notes réellement fournies sont citées | non |
| `bilan_journee` | journée J passée : lecture déterministe (`taches/agenda.py`) des rendez-vous (horodatages actifs `<J …>` hors planification), `* Journal` de `daily/J.org`, todos créés (`:CREATED:` = J, ou dans `daily/J.org`), prévus/à rendre J, `CLOSED` J, notes dont `* Source` cite une dictée de J (créée/complétée), `* Suivi` `[J]` ; Qwen ne rédige que le résumé, à partir des dictées brutes de J (hors consignes) et du journal du jour | non |
| `preparer_journee` | journée J à venir : rendez-vous, todos ouverts prévus J, à rendre J, en retard (échéance < J), `* Journal` de `daily/J.org`, autres todos ouverts ; aucun LLM | non |

Journée demandée (`taches/jour.py`) : `zettel/dates.py` reconnaît « aujourd'hui », « hier »,
« demain », jours de semaine (± « dernier »/« prochain » ; sinon prochain pour la préparation,
dernier pour le bilan), « 3 novembre », « 5/11 », ISO, « dans / il y a N jours », par rapport
à `ctx.quand` ; sinon Qwen propose AAAA-MM-JJ ("" = le jour même), refus au-delà de
`ECART_MAX_JOURNEE` (730 j).

Ajouter une tâche : un module dans `zettel/taches/` qui expose `TACHE = Tache(nom,
description, executer, ecrit)`, puis l'inscrire dans `TACHES` (`zettel/taches/__init__.py`).

**Sorties** : en mode journal, toutes les actions et résultats sont réunis dans
`~/.local/state/zettel_ai/rapports/AAAA-MM-JJ_HHMMSS.org` + notification `notify-send`
(rien si le run n'a rien produit, ni en `--dry-run`). En prompt direct : affichage console,
`--sortie FICHIER.org` écrit en plus le résultat seul (titre, `Tâche : nom`, résultat), et une
tâche qui écrit envoie une notification cliquable vers `zettel-valider`.

**Consigne vocale** : `zettel-ai-vocal` (bash, bascule comme `hyprwhspr-journal`, installé dans
`/usr/bin`) → `hyprwhspr record capture` → `zettel-ai --sortie
rapports/AAAA-MM-JJ_HHMMSS-demande.org -- "$texte"` → affichage `emacsclient -c` (si serveur),
sinon `zenity --text-info`, sinon notification. Log : `$XDG_RUNTIME_DIR/zettel-ai-vocal.log`.
Raccourci Hyprland géré par l'utilisateur.

**Verrou** (`zettel/verrou.py`) : `flock` non bloquant sur `STATE_DIR/zettel-ai.lock` autour de
tout traitement (timer, verrouillage de session, consigne vocale) ; déjà pris → message sur
stderr et code 75 (`CODE_DEJA_EN_COURS`, reconnu par `zettel-ai-vocal`). `--lister` n'en prend pas.

Options : `--dry-run` (affiche les décisions et le contenu proposé sans écrire ; les créations sont simulées
en mémoire pour que les entrées suivantes puissent les compléter), `--force` (retraite toutes les entrées),
`--lister` (numéro, horodatage, statut traitée/nouvelle, contenu/instruction), `--entree N|HORODATAGE`
(répétable : numéro de `--lister` ou début d'horodatage, ex. `2026-11-01` pour la journée ;
retraite même une entrée déjà traitée → risque de compléments en double).

**Transcription** : `CORRECTIONS_TRANSCRIPTION` (config) corrige les erreurs connues de
Whisper dans le texte avant Qwen (« HyperCTL » → hyprctl, « Cloud Code » → Claude Code…) ;
`NOMS_PROPRES` est transmis à Qwen pour l'orthographe. À enrichir au fil des erreurs vues.
Mots-clés TODO par défaut = ceux de Doom (`TODO PROJ LOOP STRT WAIT HOLD IDEA | DONE KILL`),
la config Doom ne redéfinissant pas `org-todo-keywords`.

#### Organisation du code

`zettel/cli.py` = point d'entrée de `zettel-ai` (CLI, hyprwhspr, `finally`),
`zettel/cli_valider.py` = celui de `zettel-valider`. Paquet `zettel/` :
`config.py` (tous les réglages, lus via `cfg.NOM`), `ollama.py`, `whisper.py`, `index.py`,
`journal.py`, `dates.py` (dates en français, horodatages Org), `ecriture.py`, `relecture.py` (worktree + `LotCommit`), `contexte.py`,
`contenu.py` (entrées ordinaires), `tri_sujets.py` (actions → tâches), `pipeline.py`, `rapport.py`, `verrou.py`, `taches/`
(une tâche par module, + `base.py`, `agenda.py` = lecture datée de la base, `jour.py` =
journée demandée et mise en forme).
Tests : `python -m pytest` à la racine du dépôt (faux LLM, fichiers et dépôt git
temporaires ; aucun appel à Ollama).

### `journal_ai.py` (version précédente, conservée)

Un `.txt` de `~/Journaux/transcriptions` → une fiche Markdown dans `~/Journaux/fiches`
(titre, résumé, humeur, tags, tâches, idées, personnes). Même gestion de hyprwhspr.

## Relecture (workflow git)

**Utilitaire** : `zettel-valider` (cherché dans le PATH ; sinon `python -m zettel.cli_valider`), lancé par un **clic sur la notification**
de fin de traitement (swaync, action `default` de `notify-send -A`, attente détachée via
`systemd-run --user` pour survivre à la fin du service ; terminal `TERMINAL = "kitty"`), ou à
la main. Un commit = une entrée du journal (ou un remaniement). Pour chacun : `[a]ccepter`
(cherry-pick `-x` sur `main`, dépôt obligatoirement sur `main`), `[r]efuser`, `[p]lus tard`,
`[v]oir` le diff, `[q]uitter`. À la fin, `zettel-ai` est reconstruite = `main` + commits
« plus tard » (sauvegarde préalable dans `refs/zettel-ai-sauvegardes/AAAAMMJJ-HHMMSS`, la
commande de retour arrière est affichée). Conflit (ex. complément d'une note dont la création
n'est pas acceptée) → annulé, laissé en attente. Puis `org-roam-db-sync` via `emacsclient`
si un serveur Emacs tourne. Commits en attente = `git log --cherry-pick --right-only
--no-merges main...zettel-ai`.

À la main, si besoin :

```bash
cd ~/bin/git-repos-personal/org-roam-database
git log main..zettel-ai
git diff main...zettel-ai
git merge zettel-ai                       # tout valider
git cherry-pick <commit>                  # valider un commit
git -C ~/.local/state/zettel_ai/worktree reset --hard main   # tout refuser
```
Puis `M-x org-roam-db-sync` dans Emacs.

## Installation (paquet Arch)

`pyproject.toml` (setuptools) déclare les commandes `zettel-ai` et `zettel-valider` ;
`packaging/PKGBUILD` construit le paquet depuis le dépôt (sources non commitées comprises),
lance les tests dans `check()` et installe aussi `/usr/bin/hyprwhspr-journal`,
`/usr/bin/zettel-ai-vocal` et les unités
systemd utilisateur :

```bash
cd packaging && makepkg -si      # après chaque modification du code (incrémenter pkgrel/version)
```

### Configuration utilisateur

`~/.config/zettel-ai/config.toml` (ou `$XDG_CONFIG_HOME/…`, ou `$ZETTEL_AI_CONFIG`), lu au
début de `zettel-ai` et `zettel-valider` par `zettel/config_utilisateur.py` (`tomllib`).
Modèle complet et commenté : `config.exemple.toml` (installé dans
`/usr/share/doc/zettel-ai/`). Sections : `chemins`, `ollama` (url, modèles, contexte,
température, `think`), `notes`, `transcription` (`noms_propres` et
`[transcription.corrections]` **s'ajoutent** aux valeurs intégrées), `todo`, `git`,
`hyprwhspr`, `notification`. Les autres clés remplacent la valeur de `zettel/config.py`.
Clé inconnue ou mal typée → arrêt avec message (le schéma est `SCHEMA` ; un test vérifie que
l'exemple documente chaque clé). Ajouter un réglage : une entrée dans `SCHEMA` + l'exemple.
Les réglages internes (worktree, rapports, délais) restent dans `zettel/config.py`.
⚠ `zettel-ai.service` vérifie Ollama sur `localhost:11434` en dur (`ExecStartPre`).

## Automatisation (unités systemd utilisateur)

`systemd/zettel-ai.service` (oneshot, lance `/usr/bin/zettel-ai`, vérifie qu'Ollama répond
via `curl` avant) + `zettel-ai.timer` (chaque soir à 23:30, `Persistent=true`). Installées par
le paquet dans `/usr/lib/systemd/user/`, **inactives** : `systemctl --user enable --now
zettel-ai.timer` pour planifier. Sans planification, lancer `zettel-ai` à la main.
Pas de `.path` (`PathChanged=`) : il relancerait le traitement, et couperait hyprwhspr, après
chaque dictée. L'environnement graphique (`WAYLAND_DISPLAY`, `HYPRLAND_INSTANCE_SIGNATURE`,
`DBUS_SESSION_BUS_ADDRESS`) est déjà connu du gestionnaire systemd utilisateur : pas besoin
de ligne `import-environment` dans Hyprland.

## État / à faire

- En service avec le vrai Qwen (Ollama `ollama-cuda` 0.40) ; tests : `python -m pytest` à la
  racine (faux LLM, fichiers et dépôts git temporaires). Paquet en 0.4.1 (actions → tâches, `STRT` ; 0.4.0 : bilan / préparation de
  journée, rendez-vous datés, `:CREATED:` ; 0.3.0 : `zettel-ai-vocal`, verrou, `--sortie`), `zettel-ai-vocal` pas encore essayé avec le vrai hyprwhspr.
- Langue des notes : **français** (notes anglaises traduites le 2026-11-01, anciens titres
  gardés en alias).
- Idées en attente : filtre des dictées de test (mots-clés) ; filtre des sujets vides
  (technologie seulement citée) ;
  `THINK = True` si les décisions sont faibles ; raccourci de routage par bge-m3 si beaucoup
  de tâches ; `* Suivi` à garder en section ou passer en liste (à trancher).
- Alternatives de modèle si Qwen3.5-9B déçoit en français : Gemma 4 12B, ou Mistral Small 3.2 24B
  (ne tient pas entièrement en VRAM, débord en RAM, plus lent).
