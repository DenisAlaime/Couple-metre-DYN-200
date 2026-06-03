# Philosophie de conception — Projet DYN-200 Arduino

> Ce document explique **pourquoi** le code a été écrit de cette façon, et pas seulement **comment** il fonctionne. Chaque choix de conception a une raison précise, souvent liée aux contraintes du monde embarqué.

---

## Table des matières

1. [La contrainte fondamentale : le monde embarqué](#1-la-contrainte-fondamentale--le-monde-embarqué)
2. [Principe 1 — Séparation des responsabilités](#2-principe-1--séparation-des-responsabilités)
3. [Principe 2 — Encapsulation : cacher ce qui ne doit pas être touché](#3-principe-2--encapsulation--cacher-ce-qui-ne-doit-pas-être-touché)
4. [Principe 3 — Les données voyagent avec leur validité](#4-principe-3--les-données-voyagent-avec-leur-validité)
5. [Principe 4 — Ne jamais bloquer le processeur](#5-principe-4--ne-jamais-bloquer-le-processeur)
6. [Principe 5 — La mémoire est une ressource précieuse](#6-principe-5--la-mémoire-est-une-ressource-précieuse)
7. [Principe 6 — Le code doit ressembler au problème réel](#7-principe-6--le-code-doit-ressembler-au-problème-réel)
8. [Principe 7 — Préférer les erreurs à la compilation plutôt qu'à l'exécution](#8-principe-7--préférer-les-erreurs-à-la-compilation-plutôt-quà-lexécution)
9. [Principe 8 — Rendre l'extension facile, la modification rare](#9-principe-8--rendre-lextension-facile-la-modification-rare)
10. [Principe 9 — La convention de nommage comme documentation](#10-principe-9--la-convention-de-nommage-comme-documentation)
11. [Principe 10 — Coller au modèle Arduino](#11-principe-10--coller-au-modèle-arduino)
12. [La hiérarchie des décisions de conception](#12-la-hiérarchie-des-décisions-de-conception)
13. [Ce qui a été volontairement exclu](#13-ce-qui-a-été-volontairement-exclu)

---

## 1. La contrainte fondamentale : le monde embarqué

Tout le reste découle de cette réalité :

```
Arduino Mega 2560 — Ressources disponibles
──────────────────────────────────────────
Flash (code)    :   256 Ko   ← là où vit le programme
RAM (données)   :     8 Ko   ← là où vivent les variables
EEPROM          :     4 Ko   ← mémoire persistante
Fréquence CPU   :    16 MHz  ← pas de cache, pas de pipeline complexe
Système d'exploit.: AUCUN   ← pas de scheduler, pas de threads OS
```

Sur un PC, on ne pense jamais à la mémoire pour un petit programme. Sur un Arduino Mega, **8 Ko de RAM c'est tout**. Un `String` mal utilisé, une librairie trop lourde, quelques variables inutilement grandes — et le programme plante silencieusement par débordement de pile (*stack overflow*).

Ce contexte explique **chaque décision** qui suit.

---

## 2. Principe 1 — Séparation des responsabilités

### L'idée

Chaque fichier, chaque classe, chaque fonction ne doit faire **qu'une seule chose**, et la faire bien. C'est le principe dit *Single Responsibility*.

### Application dans le projet

```
main.cpp        →  Orchestration : quand faire quoi
DYN200.cpp/.h   →  Communication : comment parler au capteur
platformio.ini  →  Configuration : quel matériel, quelles librairies
```

`main.cpp` ne sait **pas** comment fonctionne le MODBUS. `DYN200.cpp` ne sait **pas** à quelle fréquence on veut lire les données. Chacun fait son travail.

### Pourquoi c'est important ici

Imagine que tu veuilles passer à un Arduino Due demain, ou changer la fréquence de polling, ou ajouter un écran LCD. Avec cette séparation :

- Changer le matériel → modifier `platformio.ini` et éventuellement les broches dans `main.cpp`
- Changer la fréquence → modifier `POLL_MS` dans `main.cpp`
- Ajouter un affichage → ajouter du code dans `main.cpp`, sans toucher à `DYN200.cpp`

Sans séparation, tout serait mélangé et chaque modification risquerait de casser autre chose.

---

## 3. Principe 2 — Encapsulation : cacher ce qui ne doit pas être touché

### L'idée

Tout ce qui est un détail d'implémentation doit être **invisible de l'extérieur**. On n'expose que ce qui est nécessaire.

### Application dans le projet

```cpp
class DYN200 {
public:
    // ← Ce que l'utilisateur PEUT et DOIT utiliser
    void              begin();
    DYN200_Mesures    lireMesures();
    bool              remiseAZero();

private:
    // ← Les rouages internes, personne n'a besoin de les voir
    HardwareSerial &_serial;
    ModbusMaster    _node;
    static void     _preTransmission();
    static int32_t  _regsToInt32(uint16_t hi, uint16_t lo);
};
```

L'utilisateur de la classe dans `main.cpp` n'a **jamais besoin de savoir** :
- Que le MAX485 nécessite un contrôle DE/RE
- Que les données sont encodées sur deux registres 16 bits
- Comment fonctionne le CRC MODBUS

Il appelle `lireMesures()` et reçoit un `float` en N·m. C'est tout.

### La métaphore de la voiture

Quand tu conduis une voiture, tu utilises le volant et les pédales (`public`). Tu n'as pas accès à l'injection du carburant ou à la gestion de l'allumage (`private`). Ce n'est pas parce que c'est dangereux — c'est parce que **tu n'en as pas besoin**, et que te donner accès compliquerait inutilement ton travail.

### Conséquence pratique

Si demain la façon de contrôler le MAX485 change (nouveau composant, logique inversée), on modifie **uniquement** l'intérieur de `DYN200.cpp`. Le code dans `main.cpp` ne change pas d'une ligne, parce qu'il n'a jamais vu ces détails.

---

## 4. Principe 3 — Les données voyagent avec leur validité

### Le problème à résoudre

Quand on lit un capteur sur un bus série, la lecture peut **échouer** : timeout, bruit électrique, mauvais CRC. Que fait-on alors ?

Deux mauvaises approches :
1. **Retourner 0.0** en cas d'erreur → impossible de distinguer "capteur à 0 N·m" de "capteur silencieux"
2. **Variable globale d'erreur séparée** → le code qui reçoit les données peut oublier de vérifier l'erreur

### La solution adoptée : le champ `valide`

```cpp
struct DYN200_Mesures {
    float couple_Nm;
    float vitesse_RPM;
    float puissance_kW;
    bool  valide;        // ← toujours présent, impossible à oublier
};
```

La validité **fait partie de la donnée elle-même**. Quand on reçoit une `DYN200_Mesures`, on a forcément le champ `valide` avec. Le compilateur ne laisse pas accéder aux données sans avoir la struct entière.

### Dans la pratique

```cpp
// main.cpp — on est forcé de voir le champ valide
void afficherMesures(const DYN200_Mesures &m)
{
    if (!m.valide) {
        Serial.println(F("[ERREUR] Lecture echouee"));
        return;   // on ne lit pas des données corrompues
    }
    // ici on est sûr que les données sont fiables
    Serial.print(m.couple_Nm, 3);
}
```

Ce pattern vient du concept de **"type qui porte son état"**. C'est une forme simplifiée de ce qu'on appelle `Option<T>` ou `Result<T>` dans les langages modernes (Rust, Swift, Kotlin).

---

## 5. Principe 4 — Ne jamais bloquer le processeur

### Le problème avec `delay()`

```cpp
// ❌ Approche naïve
void loop() {
    mesures = dyn200.lireMesures();
    afficherMesures(mesures);
    delay(500);   // le processeur dort 500ms — rien d'autre ne peut se passer
}
```

Pendant ces 500ms, **impossible** de :
- Lire une commande envoyée depuis le moniteur série
- Détecter un bouton pressé
- Mettre à jour un affichage
- Réagir à une alarme

### La solution : polling non-bloquant

```cpp
// ✅ Approche non-bloquante
uint32_t dernierPoll = 0;

void loop() {
    // Tâche 1 : lecture capteur toutes les 500ms
    if (millis() - dernierPoll >= 500) {
        dernierPoll = millis();
        mesures = dyn200.lireMesures();
        afficherMesures(mesures);
    }

    // Tâche 2 : lecture commandes série (toujours réactive)
    if (Serial.available()) {
        traiterCommande(Serial.read());
    }

    // Tâche 3 : on pourrait en ajouter d'autres ici sans rien casser
}
```

`loop()` tourne des **milliers de fois par seconde**. À chaque tour, chaque tâche vérifie si c'est son moment d'agir. Le processeur n'attend jamais.

### La philosophie derrière

Sur un système sans OS, **tu es le scheduler**. Tu décides quelle tâche s'exécute et quand. La technique `millis()` est la forme la plus simple de gestion de tâches concurrentes sur microcontrôleur. Elle simule ce qu'un OS ferait avec des threads ou des timers.

---

## 6. Principe 5 — La mémoire est une ressource précieuse

### Trois zones de mémoire à gérer

```
┌─────────────────────────────────────────────────┐
│  FLASH (256 Ko) — Programme + constantes        │
│  ├─ Code compilé                                │
│  └─ Chaînes avec F("...") ← on les met ici     │
├─────────────────────────────────────────────────┤
│  RAM (8 Ko) — Données d'exécution               │
│  ├─ Variables globales (bas de la RAM)          │
│  ├─ Tas / Heap (malloc, new)   ↑                │
│  │                             │  collision !   │
│  └─ Pile / Stack (appels fn)   ↓                │
└─────────────────────────────────────────────────┘
```

Si la pile et le tas se rencontrent → **crash silencieux** ou comportement aléatoire.

### Décisions prises pour économiser la RAM

**1. Macro `F()` pour les chaînes**
```cpp
// ❌ Stocke "DYN-200 MODBUS RTU" en RAM (18 octets perdus)
Serial.println("DYN-200 MODBUS RTU");

// ✅ Stocke en Flash, lu directement depuis la Flash
Serial.println(F("DYN-200 MODBUS RTU"));
```

**2. Types à taille exacte**
```cpp
uint8_t  _pinDE_RE;   // 1 octet  — une broche va de 0 à 53
uint32_t _baudrate;   // 4 octets — 19200 ne tient pas sur 16 bits... si, mais 115200 non
```
Utiliser `int` partout (2 octets sur AVR) pour une broche gaspille 1 octet par variable. Multiplié par des dizaines de variables, ça s'accumule.

**3. Pas d'allocation dynamique**
Le projet n'utilise ni `malloc`, ni `new`, ni `String` (la classe Arduino). Toutes les données ont une taille fixe connue à la compilation. Cela évite la fragmentation du heap — un problème critique sur les petits microcontrôleurs.

**4. Constantes en `constexpr`**
```cpp
constexpr uint8_t PIN_DE_RE = 2;
```
Une constante `constexpr` est remplacée par sa valeur directement dans le code machine — elle n'occupe **aucun espace en RAM**.

---

## 7. Principe 6 — Le code doit ressembler au problème réel

### L'idée

Le code devrait être lisible par quelqu'un qui connaît le domaine, même sans connaître le C++. Si tu lis `dyn200.lireMesures()`, tu comprends immédiatement ce qui se passe sans avoir besoin de lire l'implémentation.

### Nommage orienté domaine

```cpp
// ❌ Nommage technique, opaque
uint8_t   addr = 0x00;
uint8_t   r    = node.readHR(addr, 6);
int32_t   v1   = (buf[0] << 16) | buf[1];
float     f1   = v1 / 1000.0f;

// ✅ Nommage orienté métier
uint8_t        status     = _node.readHoldingRegisters(DYN200_REG::COUPLE, 6);
int32_t        rawCouple  = _regsToInt32(...);
float          couple_Nm  = rawCouple / 1000.0f;
DYN200_Mesures mesures;
mesures.couple_Nm = couple_Nm;
```

La deuxième version raconte une histoire : on lit des registres MODBUS, on obtient une valeur brute, on la convertit en Newton-mètres.

### Les structures comme vocabulaire du domaine

```cpp
struct DYN200_Mesures { ... }
struct DYN200_Parametres { ... }
```

Ces structures **ne sont pas juste des groupements de variables** — ce sont des **concepts du domaine** : "une mesure du DYN-200" et "les paramètres de configuration du DYN-200". Elles existeraient dans un cahier des charges, dans une conversation avec un ingénieur. Le code parle le même langage que le problème.

### Les namespaces comme glossaire

```cpp
namespace DYN200_REG {
    constexpr uint16_t COUPLE    = 0x00;
    constexpr uint16_t VITESSE   = 0x02;
}
```

Au lieu d'avoir des adresses hexadécimales nues (`0x00`, `0x02`) disséminées dans le code — chiffres magiques impossibles à comprendre sans la datasheet — on leur donne des noms. `DYN200_REG::COUPLE` est auto-documenté.

---

## 8. Principe 7 — Préférer les erreurs à la compilation plutôt qu'à l'exécution

### La hiérarchie des erreurs

```
Erreur à la compilation   ←  la meilleure : le compilateur te la signale
Erreur à l'édition de    ←  bonne : détectée avant l'exécution
  liens (linker)
Warning compilateur       ←  acceptable : détectée, mais non bloquante
Erreur à l'exécution      ←  mauvaise : détectée seulement quand ça plante
Comportement silencieux   ←  la pire : le programme fait des bêtises sans le dire
  incorrect
```

Sur Arduino, une erreur à l'exécution peut signifier : un capteur qui retourne des valeurs aberrantes, un programme qui freeze aléatoirement, ou une corruption mémoire silencieuse. Très difficile à déboguer.

### Comment le code force les erreurs tôt

**Types stricts au lieu de `int` générique :**
```cpp
// Si on passe accidentellement un baudrate là où on attend une broche,
// le compilateur peut le détecter grâce aux types différents
void DYN200(HardwareSerial &serial, uint8_t pinDE_RE, uint8_t slaveId, uint32_t baudrate)
//                                  ^^^^^^^^ 0-255    ^^^^^^^^ 0-255   ^^^^^^^^^ 0-4G
```

**`const` comme contrat :**
```cpp
void afficherMesures(const DYN200_Mesures &m)
```
Si par erreur quelqu'un essaie de modifier `m` dans cette fonction, le compilateur refuse. Le contrat "cette fonction ne modifie pas ses données" est **garanti par le compilateur**, pas par la discipline du programmeur.

**Pas de valeurs magiques :**
```cpp
// ❌ Que signifie 0x03 ici ? erreur facile à faire
_node.readHoldingRegisters(0x03, 6);

// ✅ Impossible de se tromper de registre
_node.readHoldingRegisters(DYN200_REG::VITESSE, 6);
```
Si `DYN200_REG::VELOCITE` n'existe pas, le compilateur l'indique. `0x03` incorrect ne génère aucune erreur.

---

## 9. Principe 8 — Rendre l'extension facile, la modification rare

### L'idée

Un bon code anticipe les évolutions probables sans les surconcevoir. On appelle ça le principe *Open/Closed* : ouvert à l'extension, fermé à la modification.

### Comment ajouter un registre au DYN-200

Si le DYN-200 a un nouveau registre à lire, il suffit de :

```cpp
// 1. Ajouter dans DYN200.h (namespace)
namespace DYN200_REG {
    // ... existants ...
    constexpr uint16_t NOUVEAU_REG = 0x22;  // ← ajouter ici
}

// 2. Ajouter dans la struct si nécessaire
struct DYN200_Parametres {
    // ... existants ...
    int32_t nouveau_param;  // ← ajouter ici
};

// 3. Lire dans lireParametres()
ok &= lireReg(DYN200_REG::NOUVEAU_REG, p.nouveau_param);
```

Zéro modification dans `main.cpp`. Le reste du code ne bouge pas.

### Comment changer la broche DE/RE

```cpp
// main.cpp — une seule ligne à changer
constexpr uint8_t PIN_DE_RE = 5;   // était 2, devient 5
```

Une seule source de vérité pour chaque paramètre configurable.

### Comment adapter à un autre Arduino

```ini
; platformio.ini — changer la cible
[env:uno]
board = uno
```

Et dans `main.cpp`, vérifier les broches disponibles. `DYN200.cpp` ne change pas car il utilise `HardwareSerial` (abstraction Arduino valide sur toutes les cartes).

---

## 10. Principe 9 — La convention de nommage comme documentation

### Les conventions appliquées

| Convention | Exemple | Signification |
|-----------|---------|--------------|
| `_nomMembre` | `_pinDE_RE`, `_node` | Variable privée de classe |
| `NomClasse` | `DYN200`, `ModbusMaster` | Classe (PascalCase) |
| `NOM_CONSTANTE` | `PIN_DE_RE`, `POLL_MS` | Constante globale |
| `nomFonction` | `lireMesures()`, `begin()` | Méthode (camelCase) |
| `NOM_REG::CONSTANTE` | `DYN200_REG::COUPLE` | Constante de namespace |
| Suffixe d'unité | `couple_Nm`, `vitesse_RPM` | Unité physique incluse dans le nom |

### Pourquoi inclure l'unité dans le nom

```cpp
float couple_Nm;     // Newton-mètres — explicite
float vitesse_RPM;   // Tours par minute — explicite
float puissance_kW;  // kiloWatts — explicite
```

Un bug classique en ingénierie : confondre les unités. La NASA a perdu une sonde Mars (Mars Climate Orbiter, 1999) à cause d'une confusion entre Newton-mètres et livre-force-pieds. Mettre l'unité dans le nom du champ **rend la confusion visible** immédiatement.

### Le préfixe `_` pour les membres privés

```cpp
private:
    HardwareSerial &_serial;    // ← underscore = privé
    uint8_t         _pinDE_RE;
```

Quand on lit le code de `DYN200.cpp`, les variables préfixées par `_` sont immédiatement identifiées comme des **membres de la classe**, pas des variables locales. Cela réduit la charge mentale : pas besoin de chercher où la variable est définie.

---

## 11. Principe 10 — Coller au modèle Arduino

### Respecter les idiomes existants

La librairie Arduino a ses conventions. Les respecter rend le code **immédiatement familier** pour quiconque a déjà utilisé Arduino :

```cpp
// Même interface que Serial, Wire, SPI...
dyn200.begin();             // initialisation dans setup()
mesures = dyn200.lireMesures();  // appel dans loop()
```

Quelqu'un qui connaît `Serial.begin(9600)` comprend `dyn200.begin()` sans documentation.

### Utiliser les abstractions Arduino, pas les registres AVR

```cpp
// ✅ Code Arduino — portable, lisible
pinMode(_pinDE_RE, OUTPUT);
digitalWrite(_pinDE_RE, HIGH);

// ❌ Code AVR direct — non portable, cryptique
DDRD  |= (1 << PD2);
PORTD |= (1 << PD2);
```

La version AVR est plus rapide (~1 cycle vs ~10 cycles), mais cette différence est **totalement négligeable** sur un bus MODBUS à 19200 bauds où chaque octet prend ~520 microsecondes. On sacrifie une performance inutile en échange d'une lisibilité bien supérieure.

### Utiliser `HardwareSerial` comme paramètre, pas un numéro

```cpp
// ✅ On passe le port série lui-même
DYN200 dyn200(Serial1, PIN_DE_RE);

// ❌ On pourrait passer un numéro et faire une sélection interne
DYN200 dyn200(1, PIN_DE_RE);  // 1 = Serial1 ??
```

Passer `Serial1` directement est plus explicite, plus flexible (on pourrait passer `Serial2` ou `Serial3` sans modifier la classe), et cohérent avec la façon dont les autres librairies Arduino fonctionnent (ex: `lcd.begin(Serial2)`).

---

## 12. La hiérarchie des décisions de conception

Voici, dans l'ordre de priorité, les considérations qui ont guidé les choix :

```
┌─────────────────────────────────────────────────────────────┐
│  1. Fiabilité                                               │
│     Le code doit fonctionner correctement dans toutes les   │
│     conditions, y compris les erreurs de communication.     │
│     → Champ valide, vérification des codes retour MODBUS    │
├─────────────────────────────────────────────────────────────┤
│  2. Lisibilité / Maintenabilité                             │
│     Le code sera relu dans 6 mois. Il doit être             │
│     compréhensible sans avoir à relire toute la datasheet.  │
│     → Nommage explicite, namespaces, structures             │
├─────────────────────────────────────────────────────────────┤
│  3. Économie de ressources                                  │
│     RAM et Flash sont limitées. Chaque octet compte.        │
│     → Types exacts, F(), constexpr, pas d'allocation        │
│       dynamique                                             │
├─────────────────────────────────────────────────────────────┤
│  4. Extensibilité                                           │
│     Le projet va probablement évoluer. Il doit être         │
│     facile d'ajouter des fonctionnalités.                   │
│     → Séparation des responsabilités, paramètres            │
│       configurables centralisés                             │
├─────────────────────────────────────────────────────────────┤
│  5. Performance                                             │
│     Optimiser seulement quand c'est nécessaire.             │
│     → float plutôt que double, mais pas d'optimisations     │
│       prématurées                                           │
└─────────────────────────────────────────────────────────────┘
```

La **performance est en dernière position**. C'est intentionnel. À 16 MHz, l'Arduino Mega peut exécuter ~16 millions d'instructions par seconde. Lire un registre MODBUS prend plusieurs millisecondes (temps de transmission série). Le goulot d'étranglement est la communication, pas le code C++.

Optimiser le code CPU sur ce projet serait du temps perdu — et rendrait le code moins lisible pour un gain nul.

---

## 13. Ce qui a été volontairement exclu

Comprendre ce qui n'a **pas** été fait est aussi important que comprendre ce qui l'a été.

### Pas de gestion d'interruptions

On aurait pu utiliser les interruptions série pour recevoir les données MODBUS de façon asynchrone. C'est plus complexe à implémenter, et **inutile ici** : la librairie ModbusMaster gère déjà correctement la réception, et notre timing est largement suffisant avec le polling à 500ms.

### Pas de machine à états (state machine)

Pour un système plus complexe (plusieurs capteurs, logique conditionnelle avancée), une machine à états serait appropriée. Ici, le flux est simple et linéaire — une machine à états ajouterait de la complexité sans bénéfice.

### Pas d'EEPROM pour la configuration

On aurait pu sauvegarder l'adresse esclave et le baudrate en EEPROM pour les rendre persistants entre les resets. C'est une évolution naturelle si le projet grandit, mais elle aurait alourdi le code initial.

### Pas de classe abstraite / héritage

C++ permet de créer des hiérarchies de classes (`class CapteurGenerique { virtual lireMesures() = 0; }`). C'est utile si on a plusieurs types de capteurs. Avec un seul capteur, c'est de la sur-ingénierie (*over-engineering*) — on crée de la complexité pour une flexibilité dont on n'a pas besoin.

### Pas d'allocation dynamique (`new`, `malloc`)

C'est une décision de **robustesse**. Sur microcontrôleur, la fragmentation du heap peut provoquer des pannes après des heures ou des jours de fonctionnement — très difficile à reproduire et déboguer. Toutes les structures ont une taille fixe connue à la compilation : aucun risque de fragmentation.

---

## En résumé : la philosophie en une phrase

> **Écrire le code le plus simple possible qui soit correct, lisible, et adapté aux contraintes du matériel** — ni plus, ni moins.

La tentation en ingénierie est toujours d'ajouter de la sophistication. Un bon code embarqué résiste à cette tentation : chaque ligne de code est une ligne qui peut contenir un bug, consommer de la RAM, et compliquer la maintenance. La simplicité n'est pas un manque d'ambition — c'est une discipline.
