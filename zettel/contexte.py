"""État partagé d'un traitement : index des notes, mode simulation, lots de commits."""

from dataclasses import dataclass, field
from datetime import datetime

from .index import Note
from .relecture import LotCommit


@dataclass
class Contexte:
    notes: list[Note]
    ids: dict[str, Note]
    dry_run: bool
    lot_notes: LotCommit
    lot_remaniement: LotCommit
    source: str = ""            # horodatage de l'entrée du journal, ou « demande directe »
    quand: datetime = field(default_factory=datetime.now)   # date de la dictée (« demain »…)

    def ajouter_note(self, n: Note):
        """Les entrées / tâches suivantes du même traitement peuvent la lier ou la compléter."""
        self.notes.append(n)
        self.ids[n.id] = n

    def retirer_note(self, n: Note):
        self.notes = [x for x in self.notes if x.id != n.id]
        self.ids.pop(n.id, None)

    def reelles(self) -> list[Note]:
        """Notes présentes sur disque (exclut celles simulées en dry-run)."""
        return [n for n in self.notes if n.path is not None]
