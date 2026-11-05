# Govee Uplighter (local)

Intégration Home Assistant pour le lampadaire Govee Uplighter **H60B0**, entièrement en réseau local : pas de cloud Govee, pas de clé API, pas de compte.

L'API officielle de Govee ne règle la lampe que d'un bloc : un seul blanc pour le plafond et le bas, une couleur qui recolore aussi l'anneau, pas de débit. Cette intégration envoie les commandes que l'app Govee Home utilise elle-même, zone par zone.

| Entité | Réglages |
|---|---|
| `light.<nom>` | marche / arrêt, luminosité générale |
| `light.<nom>_ondulante` | plafond : marche / arrêt, luminosité, couleur, blanc 2700–6500 K |
| `light.<nom>_laterale` | anneau : marche / arrêt, luminosité, couleur, blanc ; attribut `segments` |
| `light.<nom>_inferieure` | lampe du bas : marche / arrêt, luminosité, blanc |
| `number.<nom>_debit` | vitesse des ondulations, 0 (figées) à 100 |

Action `govee_uplighter.set_segments` sur la lumière Latérale : couleur, blanc ou luminosité de certains des 8 segments (numérotés 1 à 8).

## Règles de la lampe

- Deux zones au plus : en allumer une troisième éteint celle allumée depuis le plus longtemps.
- La lampe du bas n'a que du blanc (une couleur l'éteindrait) ; les blancs sont bornés à 2700–6500 K.
- Les commandes rapprochées (une scène) partent en un seul envoi, espacées d'au moins 150 ms.
- La lampe ne dit pas quelles zones sont allumées : l'état affiché est le dernier réglage envoyé depuis Home Assistant. Après un changement dans l'app Govee, refaire le réglage voulu depuis Home Assistant.

## Installation

1. App Govee Home → lampe → ⚙️ → activer **Contrôle LAN**.
2. Réserver l'adresse IP de la lampe sur la box (sinon : Paramètres → Appareils et services → Govee Uplighter → Reconfigurer).
3. Marketplace / HACS → dépôts personnalisés → ce dépôt, catégorie « Integration », télécharger, redémarrer.
4. Paramètres → Appareils et services → Ajouter → « Govee Uplighter (local) » → adresse IP.

## Crédits

Le protocole du H60B0 (trames `33 30`, `33 05 2c`, règles des zones, délais) vient de [SamWiIIiams/govee-lan-bridge](https://github.com/SamWiIIiams/govee-lan-bridge) (MIT), qui l'a relevé dans le trafic Bluetooth de l'app Govee. Non affilié à Govee ; une mise à jour du micrologiciel pourrait changer ces commandes.
