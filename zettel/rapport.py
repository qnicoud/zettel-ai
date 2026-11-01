"""Rapport d'un traitement du journal : fichier .org dans STATE_DIR/rapports + notification.
Sert surtout aux tâches en lecture seule (todos, résumés) lancées depuis le journal, dont
personne ne voit la sortie console quand le script tourne via systemd."""

import os
import re
import shlex
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from . import config as cfg


def abaisser_titres(texte: str) -> str:
    """Les titres Org d'un résultat deviennent des sous-titres de sa section."""
    return re.sub(r"(?m)^(\*+)(\s)", r"*\1\2", texte)


class Rapport:
    def __init__(self):
        self.sections: list[tuple[str, str]] = []

    def ajouter(self, titre: str, texte: str):
        if texte.strip():
            self.sections.append((titre, texte.strip()))

    def texte(self, quand: datetime) -> str:
        corps = "\n\n".join(f"* {titre}\n{abaisser_titres(texte)}" for titre, texte in self.sections)
        return f"#+title: Rapport zettel_ai du {quand:%Y-%m-%d %H:%M}\n\n{corps}\n"

    def publier(self, a_valider: int = 0) -> Path | None:
        """Écrit le fichier et envoie une notification (cliquable s'il y a des modifications
        à valider). Rien si le rapport est vide."""
        if not self.sections:
            return None
        quand = datetime.now()
        cfg.RAPPORTS_DIR.mkdir(parents=True, exist_ok=True)
        path = cfg.RAPPORTS_DIR / f"{quand:%Y-%m-%d_%H%M%S}.org"
        path.write_text(self.texte(quand), encoding="utf-8")
        print(f"Rapport : {path}")
        titres = ", ".join(t for t, _ in self.sections[:3])
        if len(self.sections) > 3:
            titres += "…"
        corps = f"{titres}\n{path}"
        if a_valider:
            corps = f"{a_valider} modification(s) à valider : clique pour relire.\n{corps}"
        notifier(f"zettel_ai : {len(self.sections)} élément(s)", corps,
                 commande_validation() if a_valider else None)
        return path


ENV_GRAPHIQUE = ("WAYLAND_DISPLAY", "DISPLAY", "XDG_RUNTIME_DIR", "DBUS_SESSION_BUS_ADDRESS",
                 "HYPRLAND_INSTANCE_SIGNATURE", "PATH", "HOME", "LANG")


def commande_validation() -> list[str]:
    terminal = shutil.which(cfg.TERMINAL) or cfg.TERMINAL
    valideur = shutil.which(cfg.VALIDEUR)
    # Pas installé (lancement depuis les sources) : même code, via le module
    lancement = [valideur] if valideur else [sys.executable, "-m", "zettel.cli_valider"]
    return [terminal, "--title", "zettel_ai : validation", "-e", *lancement]


def notifier(titre: str, corps: str, commande: list[str] | None = None):
    """notify-send ; depuis systemd il faut DBUS_SESSION_BUS_ADDRESS (import-environment).
    Avec `commande`, un clic sur la notification la lance (action « default » de swaync)."""
    if not cfg.NOTIFIER:
        return
    notify = shutil.which("notify-send") or "notify-send"
    if commande is None:
        executer([notify, "-a", "zettel_ai", titre, corps])
        return
    # notify-send -A attend le clic : on le lance hors de ce processus (et hors du service
    # systemd, qui sinon le tuerait à la fin du traitement).
    script = (f"a=$(timeout {cfg.ATTENTE_CLIC} {shlex.quote(notify)} -a zettel_ai "
              f"-A default={shlex.quote('Relire et valider')} "
              f"{shlex.quote(titre)} {shlex.quote(corps)}); "
              f'[ "$a" = default ] && exec {shlex.join(commande)}')
    lancer_detache(["sh", "-c", script])


def executer(cmd: list[str]) -> bool:
    try:
        r = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired) as e:
        print(f"Notification impossible : {e}")
        return False
    if r.returncode:
        print(f"Notification impossible : {(r.stderr or r.stdout).strip()}")
    return r.returncode == 0


def lancer_detache(cmd: list[str]):
    """Via systemd-run (unité transitoire indépendante), sinon nouvelle session."""
    env = [f"--setenv={k}={os.environ[k]}" for k in ENV_GRAPHIQUE if k in os.environ]
    if shutil.which("systemd-run") and executer(
            ["systemd-run", "--user", "--collect", "--quiet", *env, "--", *cmd]):
        return
    try:
        subprocess.Popen(cmd, start_new_session=True, stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError as e:
        print(f"Notification impossible : {e}")
