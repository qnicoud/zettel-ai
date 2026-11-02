"""Configuration. Les autres modules lisent ces valeurs via `cfg.NOM` (et non par
`from config import NOM`) pour qu'on puisse les modifier à l'exécution ou dans les tests."""

from pathlib import Path

# --- Chemins ---------------------------------------------------------------
# Journaux dictés lus par zettel-ai (fusionnés par ordre chronologique). Hors de la base :
# le journal brut (infos perso) ne doit pas être versionné ni poussé. Un chemin relatif
# partirait de ROAM_DIR.
JOURNAUX = (Path.home() / "Documents" / "journal-dictee.md",)   # hyprwhspr-journal
ROAM_DIR = Path.home() / "bin" / "git-repos-personal" / "org-roam-database"
STATE_DIR = Path.home() / ".local" / "state" / "zettel_ai"   # état, cache, rapports
WORKTREE = STATE_DIR / "worktree"
NOTES_DIR = WORKTREE          # dossier où le script lit et écrit les notes
RAPPORTS_DIR = STATE_DIR / "rapports"
# Notes journalières (logistique, infos perso, todos sans projet) : réglage par défaut
# d'org-roam-dailies (org-roam-dailies-directory = "daily/", fichiers AAAA-MM-JJ.org).
DAILY_DIR = "daily"

# --- Ollama ----------------------------------------------------------------
OLLAMA_BASE = "http://localhost:11434"
MODEL = "hf.co/bartowski/Qwen_Qwen3.5-9B-GGUF:Q5_K_M"
EMBED_MODEL = "bge-m3"       # embeddings multilingues (~1,2 Go), bon en français
NUM_CTX = 16384
TEMPERATURE = 0.3
THINK = False                # True = Qwen « réfléchit » avant de décider : meilleur, plus lent

# --- Notes depuis le journal -----------------------------------------------
TOP_K = 10                   # nb de notes proches montrées à Qwen pour chaque sujet
MAX_LIENS = 5

# --- Tâches (« Instruction : … » ou prompt direct) -------------------------
TOP_K_INSTRUCTION = 15       # notes candidates pour trouver la note source d'un remaniement
TOP_K_RESUME = 6             # notes lues pour résumer un sujet
MAX_CARACTERES_NOTE = 3000   # texte de chaque note envoyé pour un résumé
MAX_TODOS_FILTRE = 150       # au-delà, pré-filtrage des todos par embeddings avant Qwen
ECART_MAX_JOURNEE = 730      # bilan / préparation : journée à 2 ans au plus de la dictée
MAX_CARACTERES_BILAN = 8000  # dictées + journal du jour envoyés pour le résumé d'un bilan
# Mots-clés si un fichier n'a pas de ligne #+TODO: : ceux de Doom Emacs
# (TODO PROJ LOOP STRT WAIT HOLD IDEA | DONE KILL), + quelques variantes courantes.
TODO_OUVERTS = ("TODO", "PROJ", "LOOP", "STRT", "WAIT", "HOLD", "IDEA",
                "NEXT", "WAITING", "STARTED")
MOT_FAIT = "DONE"            # état posé par « marquer_fait »
MOT_ABANDON = "KILL"         # état posé pour une tâche abandonnée (Doom : KILL)

# --- Transcription (Whisper) ------------------------------------------------
# Orthographe correcte des noms propres, transmise à Qwen.
NOMS_PROPRES = (
    # Écosystème Hyprland (paquets installés + outils courants)
    "Hyprland", "hyprctl", "hyprpm", "hyprpaper", "hyprlock", "hypridle", "hyprpicker",
    "hyprsunset", "hyprshot", "hyprcursor", "hyprpolkitagent", "hyprlang", "hyprutils",
    "hyprgraphics", "hyprtoolkit", "hyprwire", "hyprwayland-scanner", "hyprland-qt-support",
    "hyprland-guiutils", "xdg-desktop-portal-hyprland", "aquamarine", "Astal", "HyprPanel",
    "uwsm", "Wayland",
    # Dictée
    "hyprwhspr", "Whisper",
    # Emacs / Org
    "Emacs", "Doom Emacs", "Emacs Lisp", "org-mode", "Org mode", "org-roam", "org-roam-ui",
    "org-roam-dailies", "org-agenda", "org-capture", "org-babel", "Magit",
    # Projets et outils
    "HyperBinds", "DM Gym", "Claude Code", "Ollama", "Qwen", "Kotlin", "Rust", "GTK4",
    "Raspberry Pi",
)
# Erreurs de transcription fréquentes, corrigées dans le texte AVANT Qwen
# (mot entier, casse ignorée). Ajoute ici celles que tu repères.
CORRECTIONS_TRANSCRIPTION = {
    # Hyprland
    "hyperland": "Hyprland", "hyper land": "Hyprland", "hyperlampes": "Hyprland",
    "HyperCTL": "hyprctl", "hyper CTL": "hyprctl", "hyper control": "hyprctl",
    "hyper PM": "hyprpm", "hyperpaper": "hyprpaper", "hyper paper": "hyprpaper",
    "hyperlock": "hyprlock", "hyper lock": "hyprlock",
    "hyperidle": "hypridle", "hyper idle": "hypridle",
    "hyperpicker": "hyprpicker", "hyper picker": "hyprpicker",
    "hypersunset": "hyprsunset", "hyper sunset": "hyprsunset",
    "hypershot": "hyprshot", "hyper shot": "hyprshot",
    "hypercursor": "hyprcursor", "hyper cursor": "hyprcursor",
    "hyper panel": "HyprPanel", "hyperpanel": "HyprPanel",
    # Dictée
    "hyper whisper": "hyprwhspr", "hyperwhisper": "hyprwhspr", "hyprwhisper": "hyprwhspr",
    # Org
    "org mode": "org-mode", "orgmode": "org-mode", "ORG mode": "org-mode",
    "org roam": "org-roam", "orgroam": "org-roam", "org rome": "org-roam", "org-rom": "org-roam",
    "org roam UI": "org-roam-ui", "org roam dailies": "org-roam-dailies",
    "org agenda": "org-agenda", "org capture": "org-capture", "org babel": "org-babel",
    # Divers
    "Cloud Code": "Claude Code",
}

# --- Git : branche de relecture ---------------------------------------------
# Le script n'écrit JAMAIS sur BASE_BRANCH ni dans ton dossier de travail.
BASE_BRANCH = "main"
REVIEW_BRANCH = "zettel-ai"

# --- hyprwhspr -------------------------------------------------------------
TOGGLE_WHISPER = True
WHISPER_CTL = "/usr/lib/hyprwhspr/config/hyprland/hyprwhspr-tray.sh"
WHISPER_ACTIVE_CLASSES = {"ready", "recording"}   # stopped / error / unloaded : on n'y touche pas
RECORDING_WAIT_MAX = 300
VRAM_RELEASE_DELAY = 3

# --- Notification ----------------------------------------------------------
NOTIFIER = True              # notify-send en fin de traitement du journal
# Clic sur la notification -> utilitaire de validation dans un terminal
TERMINAL = "kitty"           # doit accepter --title et -e (kitty, alacritty…)
VALIDEUR = "zettel-valider"   # commande installée (pyproject.toml), cherchée dans le PATH
ATTENTE_CLIC = 12 * 3600     # durée max (s) pendant laquelle le clic reste actif
