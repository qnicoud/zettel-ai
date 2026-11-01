"""hyprwhspr : on le coupe pendant le traitement pour libérer la VRAM, puis on le relance."""

import json
import subprocess
import sys
import time

from . import config as cfg


def whisper_classe() -> str | None:
    """Lit uniquement la 1re ligne du script (il peut émettre en continu)."""
    try:
        p = subprocess.Popen([cfg.WHISPER_CTL], stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL, text=True)
        try:
            ligne = p.stdout.readline()
        finally:
            p.kill()
            p.wait()
        return str(json.loads(ligne).get("class", "")).strip().lower()
    except (OSError, ValueError) as e:
        print(f"Statut hyprwhspr illisible ({e}) : on n'y touche pas", file=sys.stderr)
        return None


def whisper_actif() -> bool:
    """True si hyprwhspr tourne (après avoir attendu la fin d'une dictée en cours)."""
    classe = whisper_classe()
    print(f"hyprwhspr : statut « {classe} »")
    attente = 0
    while classe == "recording" and attente < cfg.RECORDING_WAIT_MAX:
        if attente == 0:
            print("Dictée en cours, attente de la fin…")
        time.sleep(5)
        attente += 5
        classe = whisper_classe()
    return classe in cfg.WHISPER_ACTIVE_CLASSES


def whisper(action: str):
    print(f"hyprwhspr : {action}")
    subprocess.run([cfg.WHISPER_CTL, action], check=False,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
