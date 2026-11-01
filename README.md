# zettel-ai

Transforme un journal vocal dicté en notes **Zettelkasten** dans une base **org-roam**, avec un
LLM qui tourne **en local** (Ollama). Aucune donnée ne quitte la machine.

Le script ne touche jamais directement à la base : tout ce qu'il produit arrive sur une branche
git de relecture (`zettel-ai`), et rien n'atteint `main` sans validation explicite.

## But

Dicter des idées au fil de la journée (avec [hyprwhspr](https://github.com/goodroot/hyprwhspr)),
puis laisser un traitement du soir :

- extraire les **sujets et concepts** de chaque dictée, à raison d'une note par concept ;
- **créer** une note ou **compléter** une note existante, sans jamais réécrire le contenu déjà présent ;
- poser des **liens** `[[id:…]]` vers les notes proches ;
- ranger les **tâches** (`TODO`), l'**avancement des projets** et la **logistique du jour** au bon endroit ;
- exécuter des **consignes** dictées (« Instruction : fusionne les notes X et Y ») ou passées en
  ligne de commande (`zettel-ai "liste mes todos Rust"`).

### Pourquoi un pipeline guidé plutôt qu'un agent

Un modèle de 9 milliards de paramètres est peu fiable en boucle d'outils libre : il invente des
ID et réécrit les notes. Ici, le script fait tout le travail déterministe (lecture, recherche,
écriture, git). Le LLM ne prend que des décisions encadrées : sorties JSON contraintes par un
schéma, puis validées avant toute écriture (ID inconnus rejetés, pas d'auto-lien, dates vérifiées…).

## Fonctionnement

```
dictée (hyprwhspr-journal)
   │  - [AAAA-MM-JJ HH:MM:SS] texte…
   ▼
~/Documents/journal-dictee.md
   │
   ▼  zettel-ai (à la main, ou timer systemd à 23:30)
┌───────────────────────────────────────────────────────────┐
│ 1. découpe en entrées, saute celles déjà traitées         │
│ 2. worktree de la branche zettel-ai ← fusion de main      │
│ 3. index des notes .org + embeddings bge-m3 (en cache)    │
│ 4. Qwen : sujets, tâches, suivi, infos perso              │
│ 5. pour chaque sujet : 10 notes proches → Qwen décide     │
│    créer / compléter / ignorer + liens                    │
│ 6. validation par le script, puis écriture                │
│ 7. un commit par entrée sur zettel-ai                     │
└───────────────────────────────────────────────────────────┘
   │
   ▼  notification → clic → zettel-valider
relecture commit par commit → cherry-pick sur main → org-roam-db-sync
```

### Ce qui est écrit

**Nouvelle note** : `AAAAMMJJHHMMSS-slug.org`, au format org-roam par défaut. Elle contient le
drawer `:ID:`, `#+title`, `#+filetags`, un texte sans titre (paragraphes et listes), puis
uniquement ces sections :

```org
* Liens
- [[id:…][Titre]] : raison du lien
* Tâches
* Suivi
* Source
- [2026-11-01 21:14:02] journal dicté
```

**Complément d'une note existante** : un paragraphe ajouté à la fin du texte, les nouveaux
liens ajoutés à `* Liens` (sans doublon) et la source ajoutée à `* Source`. Le contenu
existant n'est jamais réécrit.

Les liens dans le texte sont posés par le script, et seulement quand le titre ou un alias d'une
note existante est cité mot pour mot. Qwen n'écrit que du texte simple.

**Tâches et journal** :

| Élément extrait | Destination |
|---|---|
| tâche liée à un projet | `** TODO …` dans `* Tâches` de la note du projet |
| tâche sans projet | `** TODO …` dans `* Tâches` de `daily/AAAA-MM-JJ.org` |
| avancement d'un projet | `- [AAAA-MM-JJ] …` dans `* Suivi` de la note du projet |
| logistique, infos perso | `- HH:MM …` dans `* Journal` de `daily/AAAA-MM-JJ.org` |

Les dates d'échéance deviennent `SCHEDULED:` ou `DEADLINE:` si elles sont plausibles (d'un mois
avant à deux ans après la dictée). Un TODO déjà présent n'est pas répété.

### Consignes

Une dictée qui commence par **« Instruction »**, ou un argument passé à `zettel-ai`, est envoyée
à un routeur qui choisit l'une des tâches ci-dessous. Si la demande n'est pas reconnue, rien
n'est fait.

| Tâche | Effet | Écrit ? |
|---|---|---|
| `extraire` | déplace des lignes d'une note vers une note neuve, laisse `Voir [[id:…]]` | oui |
| `fusionner` | absorbe une note dans une autre, redirige les liens, garde l'ancien titre en alias | oui |
| `renommer` | change `#+title`, garde l'ancien en alias, met à jour les libellés des liens | oui |
| `lier` | ajoute un lien dans `* Liens` | oui |
| `marquer_fait` | passe des TODO à `DONE` (ou `KILL`) avec `CLOSED: […]` | oui |
| `lister_todos` | liste les tâches ouvertes, filtrées par sujet | non |
| `resumer` | résume un sujet à partir des 6 notes les plus proches, en les citant | non |

Le mot « Instruction » sert de déclencheur obligatoire dans les dictées : une simple réflexion
n'est jamais exécutée par erreur.

## Prérequis

- Arch Linux (le paquet est construit avec `makepkg`)
- Python ≥ 3.11 et `python-requests`
- [Ollama](https://ollama.com) qui répond sur `http://localhost:11434` (`ollama-cuda` conseillé)
- Une base org-roam qui est un **dépôt git** avec une branche `main`
- Facultatif : hyprwhspr (dictée), `libnotify` + `kitty` (notification cliquable), Emacs
  (`org-roam-db-sync` après validation)

Modèles à télécharger :

```bash
ollama pull hf.co/bartowski/Qwen_Qwen3.5-9B-GGUF:Q5_K_M   # ≈ 7,1 Go
ollama pull bge-m3                                        # ≈ 1,2 Go
```

Ils tiennent ensemble dans 12 Go de VRAM tant que hyprwhspr est coupé. C'est pour ça que
zettel-ai coupe hyprwhspr pendant le traitement puis le relance.

## Installation

```bash
cd packaging
makepkg -si
```

`makepkg` copie les sources du dépôt (y compris les modifications non commitées), construit
la wheel, lance les tests (un échec arrête le build) puis installe :

| Fichier | Rôle |
|---|---|
| `/usr/bin/zettel-ai` | traitement du journal et consignes |
| `/usr/bin/zettel-valider` | relecture des commits proposés |
| `/usr/bin/hyprwhspr-journal` | dictée vers le journal (bascule démarrer / arrêter) |
| `/usr/lib/systemd/user/zettel-ai.{service,timer}` | traitement automatique, **inactif** par défaut |
| `/usr/share/doc/zettel-ai/config.exemple.toml` | modèle de configuration commenté |

**Mise à jour après une modification du code** : incrémente `pkgrel` (ou `pkgver`) dans
[packaging/PKGBUILD](packaging/PKGBUILD), puis relance `makepkg -si`. Sans changement de
version, `makepkg -sif` force la reconstruction.

### Configuration

```bash
mkdir -p ~/.config/zettel-ai
cp /usr/share/doc/zettel-ai/config.exemple.toml ~/.config/zettel-ai/config.toml
```

Le fichier est cherché dans `$ZETTEL_AI_CONFIG`, puis dans
`$XDG_CONFIG_HOME/zettel-ai/config.toml`, puis dans `~/.config/zettel-ai/config.toml`. Toutes
les clés sont facultatives. Une clé inconnue ou mal typée arrête le programme avec un message.

| Section | Contenu |
|---|---|
| `[chemins]` | journal dicté, base org-roam, dossier des notes journalières |
| `[ollama]` | URL, modèles, contexte, température, `think` |
| `[notes]` | nombre de notes proches montrées au LLM, nombre max de liens |
| `[transcription]` | `noms_propres` et `[transcription.corrections]` (erreurs de Whisper), **ajoutés** aux valeurs intégrées |
| `[todo]` | mots-clés TODO ouverts, fait, abandon (par défaut ceux de Doom Emacs) |
| `[git]` | noms des branches principale et de relecture |
| `[hyprwhspr]` | couper ou non hyprwhspr pendant le traitement, chemin du script de contrôle |
| `[notification]` | activer la notification, terminal ouvert au clic |

### Dictée

Associe `hyprwhspr-journal` à un raccourci Hyprland, par exemple :

```ini
bind = SUPER, J, exec, hyprwhspr-journal
```

Un premier appui démarre l'enregistrement, un second l'arrête. La transcription est ajoutée au
journal sous la forme `- [AAAA-MM-JJ HH:MM:SS] texte`, et le presse-papier n'est pas touché.
Les variables `HYPRWHSPR_JOURNAL` (fichier) et `HYPRWHSPR_JOURNAL_LANG` (langue forcée, ex. `fr`)
sont facultatives.

### Traitement automatique

```bash
systemctl --user enable --now zettel-ai.timer    # chaque soir à 23:30
systemctl --user list-timers zettel-ai.timer     # prochaine exécution
systemctl --user start zettel-ai.service         # lancer maintenant
journalctl --user -u zettel-ai.service -e        # sortie du dernier traitement
```

Si le PC était éteint à 23:30, le traitement se fait au démarrage suivant (`Persistent=true`).
Le service vérifie qu'Ollama répond sur `localhost:11434` avant de commencer.

## Utilisation

### Traiter le journal

```bash
zettel-ai                       # traite les nouvelles entrées
zettel-ai --dry-run             # montre décisions et contenu proposé, n'écrit rien
zettel-ai --lister              # numéro, horodatage, statut (traitée / nouvelle), contenu
zettel-ai --entree 12           # (re)traite l'entrée n° 12 de --lister
zettel-ai --entree 2026-11-01   # (re)traite toutes les entrées de la journée
zettel-ai --force               # retraite tout le journal
```

`--entree` est répétable. Retraiter une entrée déjà traitée peut produire des compléments en
double : relis-les attentivement.

Une entrée est reconnue par son horodatage : corriger le texte d'une dictée ne la fait donc pas
retraiter.

À la fin d'un run qui a produit quelque chose, un rapport est écrit dans
`~/.local/state/zettel_ai/rapports/AAAA-MM-JJ_HHMMSS.org` et une notification s'affiche.

### Consignes directes

```bash
zettel-ai "liste mes todos Rust"
zettel-ai "résume ce que je sais sur Hyprland"
zettel-ai "renomme la note Emacs en Doom Emacs"
zettel-ai "marque comme fait la tâche de mise à jour du PKGBUILD"
```

Le résultat est affiché dans la console. Les consignes qui modifient la base passent par la
même relecture que le reste.

### Relire et valider

Clique sur la notification de fin de traitement, ou lance :

```bash
zettel-valider
```

Le dépôt de la base doit être sur `main`. Pour chaque commit proposé (un par entrée ou par
remaniement) :

| Touche | Action |
|---|---|
| `a` | accepter : cherry-pick sur `main` |
| `r` | refuser |
| `p` | plus tard : le commit reste en attente |
| `v` | voir le diff |
| `q` | quitter |

À la fin, la branche `zettel-ai` est reconstruite à partir de `main` et des commits mis en
attente. L'ancienne branche est d'abord sauvegardée dans
`refs/zettel-ai-sauvegardes/AAAAMMJJ-HHMMSS`, et la commande pour revenir en arrière est
affichée. Un commit qui entre en conflit (par exemple, le complément d'une note dont la
création a été refusée) est annulé et laissé en attente. Si un serveur Emacs tourne,
`org-roam-db-sync` est lancé automatiquement.

Validation manuelle, si besoin :

```bash
cd ~/bin/git-repos-personal/org-roam-database
git log main..zettel-ai          # commits proposés
git diff main...zettel-ai        # tout le diff
git merge zettel-ai              # tout accepter
git cherry-pick <commit>         # accepter un commit
git -C ~/.local/state/zettel_ai/worktree reset --hard main   # tout refuser
```

## Fichiers et état

| Quoi | Où |
|---|---|
| Journal dicté | `~/Documents/journal-dictee.md` |
| Configuration | `~/.config/zettel-ai/config.toml` |
| Entrées traitées, cache des embeddings | `~/.local/state/zettel_ai/` |
| Rapports des runs | `~/.local/state/zettel_ai/rapports/` |
| Worktree de relecture (branche `zettel-ai`) | `~/.local/state/zettel_ai/worktree` |

Sécurités :

- zettel-ai n'écrit jamais sur `main`, ni dans le dossier de travail de la base.
- hyprwhspr est relancé dans tous les cas, y compris après une erreur ou un SIGTERM.
- Les modèles sont déchargés d'Ollama à la fin du run.
- Ce qui a déjà été écrit est commité même si le run s'interrompt.

## Développement

```bash
python -m pytest         # à la racine ; faux LLM, fichiers et dépôts git temporaires
```

Les tests n'appellent jamais Ollama. Organisation du paquet `zettel/` :

| Module | Rôle |
|---|---|
| `cli.py`, `cli_valider.py` | points d'entrée |
| `config.py`, `config_utilisateur.py` | réglages intégrés et lecture du TOML (`SCHEMA`) |
| `ollama.py`, `whisper.py` | client Ollama, contrôle de hyprwhspr |
| `journal.py`, `index.py` | découpage du journal, index et embeddings des notes |
| `pipeline.py`, `contenu.py`, `contexte.py` | traitement des entrées ordinaires |
| `ecriture.py`, `suivi.py` | écriture des notes, tâches et notes journalières |
| `relecture.py` | worktree, commits par lot |
| `rapport.py` | rapport org et notification |
| `taches/` | consignes (une tâche par module) |

**Ajouter une consigne** : créer un module dans `zettel/taches/` qui expose
`TACHE = Tache(nom, description, executer, ecrit)`, puis l'inscrire dans `TACHES`
(`zettel/taches/__init__.py`).

**Ajouter un réglage utilisateur** : ajouter une entrée dans `SCHEMA`
(`zettel/config_utilisateur.py`) et la documenter dans `config.exemple.toml`. Un test vérifie
que l'exemple documente chaque clé.

## Limites connues

- Les TODO de la base n'apparaissent dans l'agenda Emacs que si la base et son dossier `daily/`
  sont ajoutés à `org-agenda-files`.
- `zettel-ai.service` vérifie Ollama sur `localhost:11434` en dur, quelle que soit l'URL configurée.
- Le modèle peut mal découper ou mal nommer un sujet : c'est la raison d'être de la relecture.
  Si les décisions sont faibles, essaie `think = true` (plus lent).
