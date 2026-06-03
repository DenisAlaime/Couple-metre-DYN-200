# DYN-200 — Arduino Mega + PlatformIO

Interface MODBUS RTU pour le couple-mètre DYN-200 via convertisseur RS485 MAX485.

## Structure du projet

```
dyn200_arduino/
├── platformio.ini        ← Configuration PlatformIO
├── include/
│   └── DYN200.h          ← Classe + structures de données
└── src/
    ├── DYN200.cpp         ← Implémentation de la classe
    └── main.cpp           ← Programme principal
```

## Câblage

```
MAX485        Arduino Mega          DYN-200
──────        ────────────          ───────
RO   ───────► D19 (RX1)
DI   ◄─────── D18 (TX1)
DE + RE ◄──── D2  (contrôle direction)
A    ◄───────────────────────────► Fil jaune (RS485 A)
B    ◄───────────────────────────► Fil bleu  (RS485 B)
VCC  ◄─────── 5V
GND  ◄─────── GND                  GND commun
                                   Rouge → +24V (alim. DYN-200)
```

> **Important** : DE et RE du MAX485 sont reliés ensemble sur la même broche Arduino (D2).

## Configuration MODBUS (DYN-200 par défaut)

| Paramètre  | Valeur  |
|------------|---------|
| Baud rate  | 19200   |
| Data bits  | 8       |
| Parity     | None    |
| Stop bits  | **2**   |
| Slave ID   | 1       |

## Compilation et upload

```bash
# Ouvrir le dossier dans VS Code avec l'extension PlatformIO
# Puis dans le terminal PlatformIO :

pio run                    # Compiler
pio run --target upload    # Compiler + uploader
pio device monitor         # Ouvrir le moniteur série (115200 bauds)
```

## Commandes disponibles (moniteur série)

| Touche | Action                        |
|--------|-------------------------------|
| `z`    | Remise à zéro du couple       |
| `r`    | Reset usine                   |
| `p`    | Relire les paramètres         |
| `h`    | Afficher l'aide               |

## Structures de données

```cpp
// Mesures en temps réel
struct DYN200_Mesures {
    float couple_Nm;      // Couple en N·m
    float vitesse_RPM;    // Vitesse en RPM
    float puissance_kW;   // Puissance en kW
    bool  valide;         // false si erreur MODBUS
};

// Paramètres de configuration
struct DYN200_Parametres {
    int32_t filtrage;
    int32_t point_decimal;
    int32_t zero_demarrage;
    int32_t zero_transmis;
    int32_t pleine_echelle;
    int32_t plage_transmis;
    int32_t dir_couple;
    int32_t filtre_vitesse;
    int32_t dec_vitesse;
    bool    valide;
};
```

## Librairie utilisée

**ModbusMaster** (`4-20ma/ModbusMaster`) :
- Légère et fiable sur AVR
- Gère nativement RTU + callbacks pre/post transmission
- Parfaite pour le contrôle DE/RE du MAX485 en half-duplex
