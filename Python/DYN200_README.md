# DYN-200 — Interface Python MODBUS RTU
## Installation rapide

```bash
pip install pymodbus pyserial matplotlib
```

## Lancement

```bash
# Avec le capteur branché (RS232→RS485)
python dyn200_interface.py

# Sans matériel — mode démo avec données simulées
python dyn200_interface.py --demo
```

## Configuration

| Paramètre | Valeur par défaut | Notes |
|-----------|-------------------|-------|
| Baud rate | 19200 | Recommandé pour MODBUS RTU |
| Stop bits | 2 | Par défaut DYN-200 |
| Parity    | None (N) | |
| Data bits | 8 | |
| Adresse esclave | 1 | Modifiable dans l'UI |

## Fonctionnalités

- **Lecture en temps réel** : Couple (N·m), Vitesse (RPM), Puissance (kW)
- **Paramètres MODBUS** : Tous les registres du capteur en lecture
- **Graphiques** : 3 courbes animées en temps réel (matplotlib)
- **Connexion/Déconnexion** : Bouton unique, détection automatique des ports COM
- **Remise à zéro** : Commande MODBUS 05H
- **Reset usine** : Commande MODBUS 10H
- **Journal** : Log horodaté exportable en .txt
- **Mode démo** : Test sans matériel avec données sinusoïdales simulées

## Registres MODBUS lus (03H)

| Registre | Adresse | Description |
|----------|---------|-------------|
| 0x00-01  | Couple  | Torque en N·m (int32 signé) |
| 0x02-03  | Vitesse | Vitesse en RPM |
| 0x04-05  | Puissance | Puissance × 0.1 kW |
| 0x06     | Filtrage | Coefficient filtre numérique |
| 0x12     | Direction | Direction du couple |
| ...      | ...     | Voir code source |

## Câblage RS232→RS485

```
Câble DYN-200  →  Adaptateur RS485
Pin 5 (jaune RS485 A)  →  A+
Pin 6 (bleu  RS485 B)  →  B-
Pin 1 (rouge +24V)     →  Alimentation DC 24V
Pin 2 (noir  0V)       →  GND
```
