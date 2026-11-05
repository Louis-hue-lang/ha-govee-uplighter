"""Constantes de l'intégration Govee Uplighter (local)."""
from __future__ import annotations

DOMAIN = "govee_uplighter"
DEFAULT_NAME = "Lampadaire Govee"
LAMP_PORT = 4003
MIN_GAP = 0.15  # s : un message arrivé pendant que la lampe traite le précédent peut être perdu
MAX_FRAMES = 12  # la lampe a ignoré en bloc des messages de 24 trames
BATCH_WINDOW = 0.15  # s : les commandes aussi rapprochées (une scène HA) forment un seul changement
SIGNAL_UPDATE = f"{DOMAIN}_update_{{}}"
