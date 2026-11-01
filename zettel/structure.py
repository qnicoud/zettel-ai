"""Opérations déterministes sur la structure d'une note org-roam (texte -> texte) :
découpage en sections, titre, alias, tags, redirection des liens id."""

import re
from dataclasses import dataclass, field

RE_N1 = re.compile(r"^\*\s+(.*?)\s*$")


@dataclass
class Decoupe:
    entete: list[str] = field(default_factory=list)     # drawer :PROPERTIES: + lignes #+
    corps: list[str] = field(default_factory=list)      # texte principal (avant 1re section)
    sections: list[tuple[str, list[str]]] = field(default_factory=list)


def decouper(txt: str) -> Decoupe:
    l, i = txt.splitlines(), 0
    if l and l[0].strip().upper() == ":PROPERTIES:":
        while i < len(l) and l[i].strip().upper() != ":END:":
            i += 1
        i += 1
    while i < len(l) and l[i].startswith("#+"):
        i += 1
    d = Decoupe(entete=l[:i])
    courant = d.corps
    for x in l[i:]:
        if (m := RE_N1.match(x)):
            d.sections.append((m.group(1), []))
            courant = d.sections[-1][1]
        else:
            courant.append(x)
    return d


def texte_lignes(lignes: list[str]) -> str:
    return "\n".join(lignes).strip("\n")


def definir_titre(txt: str, titre: str) -> str:
    return re.sub(r"(?mi)^#\+title:.*$", lambda _: f"#+title: {titre}", txt, count=1)


def lire_alias(txt: str) -> list[str]:
    m = re.search(r"(?mi)^\s*:ROAM_ALIASES:\s*(.+)$", txt)
    return [a or b for a, b in re.findall(r'"([^"]+)"|(\S+)', m.group(1))] if m else []


def ajouter_alias(txt: str, alias: list[str]) -> str:
    """Ajoute des alias org-roam dans le drawer de tête (sans doublon)."""
    existants = lire_alias(txt)
    nouveaux = [a for a in alias if a.strip() and a not in existants]
    if not nouveaux:
        return txt
    valeur = " ".join(f'"{a}"' for a in [*existants, *nouveaux])
    if re.search(r"(?mi)^\s*:ROAM_ALIASES:", txt):
        return re.sub(r"(?mi)^(\s*:ROAM_ALIASES:).*$", lambda m: f"{m.group(1)} {valeur}", txt,
                      count=1)
    return re.sub(r"(?mi)^:END:\s*$", lambda _: f":ROAM_ALIASES: {valeur}\n:END:", txt, count=1)


def lire_tags(txt: str) -> list[str]:
    m = re.search(r"(?mi)^#\+filetags:\s*(.+)$", txt)
    return [t for t in m.group(1).strip().split(":") if t.strip()] if m else []


def ajouter_tags(txt: str, tags: list[str]) -> str:
    tous = list(dict.fromkeys([*lire_tags(txt), *tags]))
    if not tous:
        return txt
    ligne = f"#+filetags: :{':'.join(tous)}:"
    if re.search(r"(?mi)^#\+filetags:", txt):
        return re.sub(r"(?mi)^#\+filetags:.*$", lambda _: ligne, txt, count=1)
    return re.sub(r"(?mi)^(#\+title:.*)$", lambda m: f"{m.group(1)}\n{ligne}", txt, count=1)


def rediriger_liens(txt: str, ancien: str, nouveau: str) -> str:
    return re.sub(rf"\[\[id:{re.escape(ancien)}\]", f"[[id:{nouveau}]", txt, flags=re.I)


def delier(txt: str, nid: str) -> str:
    """Remplace les liens vers `nid` par leur libellé (pour éviter un lien vers soi-même)."""
    return re.sub(rf"\[\[id:{re.escape(nid)}\]\[([^\]]*)\]\]", r"\1", txt, flags=re.I)


def renommer_libelles(txt: str, nid: str, ancien: str, nouveau: str) -> str:
    """[[id:nid][Ancien titre]] -> [[id:nid][Nouveau titre]] (libellé identique seulement)."""
    return re.sub(rf"\[\[id:{re.escape(nid)}\]\[{re.escape(ancien)}\]\]",
                  lambda _: f"[[id:{nid}][{nouveau}]]", txt, flags=re.I)
