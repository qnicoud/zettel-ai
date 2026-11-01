"""Appels à l'API Ollama : chat à sortie JSON structurée, embeddings, déchargement."""

import json
import subprocess

import requests

from . import config as cfg


def llm(system: str, user: str, schema: dict) -> dict:
    payload = {
        "model": cfg.MODEL,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        "format": schema,
        "think": cfg.THINK,
        "stream": False,
        "keep_alive": "5m",
        "options": {"num_ctx": cfg.NUM_CTX, "temperature": cfg.TEMPERATURE},
    }
    r = requests.post(f"{cfg.OLLAMA_BASE}/api/chat", json=payload, timeout=900)
    if not r.ok:
        raise RuntimeError(f"Ollama /api/chat {r.status_code} : {r.text.strip()}")
    return json.loads(r.json()["message"]["content"])


def embed(textes: list[str]) -> list[list[float]]:
    vecs = []
    for i in range(0, len(textes), 32):
        r = requests.post(f"{cfg.OLLAMA_BASE}/api/embed", timeout=300,
                          json={"model": cfg.EMBED_MODEL, "input": textes[i:i + 32],
                                "keep_alive": "5m"})
        if not r.ok:
            raise RuntimeError(f"Ollama /api/embed {r.status_code} : {r.text.strip()}")
        vecs.extend(r.json()["embeddings"])
    return vecs


def decharger_modeles():
    for m in (cfg.MODEL, cfg.EMBED_MODEL):
        subprocess.run(["ollama", "stop", m], check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print("Modèles déchargés de la VRAM")
