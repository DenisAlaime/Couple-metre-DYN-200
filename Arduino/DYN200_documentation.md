# Documentation complète — Projet DYN-200 Arduino

> **Objectif de ce document** : expliquer chaque partie du code du projet, y compris les syntaxes C++ spécifiques à Arduino/PlatformIO. Aucune connaissance préalable du C++ embarqué n'est requise.

---

## Table des matières

1. [Structure du projet PlatformIO](#1-structure-du-projet-platformio)
2. [Le fichier `platformio.ini`](#2-le-fichier-platformioini)
3. [Les types de données C++ utilisés](#3-les-types-de-données-c-utilisés)
4. [Le fichier `DYN200.h` — En-tête de la classe](#4-le-fichier-dyn200h--en-tête-de-la-classe)
5. [Le fichier `DYN200.cpp` — Implémentation](#5-le-fichier-dyn200cpp--implémentation)
6. [Le fichier `main.cpp` — Programme principal](#6-le-fichier-maincpp--programme-principal)
7. [Le bus RS485 et le MAX485](#7-le-bus-rs485-et-le-max485)
8. [Le protocole MODBUS RTU](#8-le-protocole-modbus-rtu)
9. [La librairie ModbusMaster](#9-la-librairie-modbusmaster)
10. [Récapitulatif du flux de données](#10-récapitulatif-du-flux-de-données)

---

## 1. Structure du projet PlatformIO

```
dyn200_arduino/
├── platformio.ini      ← Configuration du projet (carte, librairies)
├── include/
│   └── DYN200.h        ← Déclaration de la classe (le "contrat")
└── src/
    ├── DYN200.cpp      ← Corps de la classe (le "travail")
    └── main.cpp        ← Point d'entrée du programme
```

### Pourquoi séparer `.h` et `.cpp` ?

En C++, on sépare systématiquement la **déclaration** (`.h`) de l'**implémentation** (`.cpp`) :

| Fichier | Rôle | Analogie |
|---------|------|---------|
| `.h` (header) | Dit *ce que fait* la classe : liste des fonctions et variables | Plan d'architecte |
| `.cpp` | Dit *comment elle le fait* : le code réel | La construction |

Cette séparation permet à d'autres fichiers d'utiliser la classe **sans avoir besoin de voir le code interne** — ils incluent juste le `.h`.

---

## 2. Le fichier `platformio.ini`

```ini
[env:megaatmega2560]
platform  = atmelavr
board     = megaatmega2560
framework = arduino

lib_deps =
    4-20ma/ModbusMaster @ ^2.0.1

monitor_speed = 115200
upload_speed  = 115200
```

### Explication ligne par ligne

| Clé | Valeur | Signification |
|-----|--------|--------------|
| `platform` | `atmelavr` | Famille de processeurs (AVR = processeur de l'Arduino Mega) |
| `board` | `megaatmega2560` | Identifiant exact de la carte (Mega 2560) |
| `framework` | `arduino` | On utilise les fonctions Arduino (`pinMode`, `Serial`, etc.) |
| `lib_deps` | `4-20ma/ModbusMaster @ ^2.0.1` | Librairie à télécharger automatiquement |
| `monitor_speed` | `115200` | Vitesse du moniteur série (doit correspondre à `Serial.begin(115200)`) |

### La notation `^2.0.1` (versioning sémantique)

```
^2.0.1  →  accepte toute version ≥ 2.0.1 et < 3.0.0
 2.0.1  →  version exacte uniquement
~2.0.1  →  accepte ≥ 2.0.1 et < 2.1.0
```

Le `^` permet d'accepter les **correctifs et nouvelles fonctionnalités** tout en évitant les changements majeurs qui pourraient casser le code.

---

## 3. Les types de données C++ utilisés

Avant d'entrer dans le code, voici les types rencontrés dans le projet :

### Types entiers

| Type | Taille | Plage de valeurs | Utilisation dans le projet |
|------|--------|-----------------|--------------------------|
| `uint8_t` | 8 bits | 0 à 255 | Numéro de broche, adresse MODBUS |
| `uint16_t` | 16 bits | 0 à 65 535 | Adresses de registres |
| `uint32_t` | 32 bits | 0 à 4 294 967 295 | Baudrate, `millis()` |
| `int32_t` | 32 bits signé | −2 147 483 648 à +2 147 483 647 | Valeurs brutes DYN-200 |
| `bool` | 1 bit | `true` / `false` | Drapeaux d'état |

> **Pourquoi `uint8_t` plutôt que `int` ?**
> Sur Arduino, `int` fait 16 bits. Utiliser `uint8_t` pour une broche (0-53) est **plus précis**, évite les erreurs de signe, et économise de la mémoire RAM (très précieuse sur AVR).

### Types à virgule flottante

| Type | Précision | Utilisation |
|------|-----------|-------------|
| `float` | ~7 chiffres significatifs | Couple, vitesse, puissance après conversion |

### Le mot-clé `constexpr`

```cpp
constexpr uint8_t  PIN_DE_RE   = 2;
constexpr uint32_t BAUD_MODBUS = 19200;
```

`constexpr` signifie **"constante évaluée à la compilation"**. C'est plus robuste que `#define` car :
- Le compilateur **connaît le type** → détecte les erreurs de type
- La valeur **n'existe pas en RAM** → économise de la mémoire
- Comparable : `#define PIN_DE_RE 2` fonctionne aussi mais sans contrôle de type

### Le mot-clé `const`

```cpp
void afficherMesures(const DYN200_Mesures &m)
```

`const` avant un paramètre = **promesse de ne pas modifier** la valeur reçue. Le compilateur lèvera une erreur si le code tente de modifier `m`.

---

## 4. Le fichier `DYN200.h` — En-tête de la classe

### 4.1 La garde d'inclusion (`#pragma once`)

```cpp
#pragma once
```

**Problème résolu** : si deux fichiers incluent `DYN200.h`, le compilateur verrait la classe définie deux fois → erreur. `#pragma once` dit au compilateur : *"n'inclus ce fichier qu'une seule fois, peu importe combien de fois il est demandé"*.

L'alternative classique (équivalente) :
```cpp
#ifndef DYN200_H
#define DYN200_H
// ... contenu ...
#endif
```

`#pragma once` est plus lisible et universellement supporté aujourd'hui.

### 4.2 Les includes

```cpp
#include <Arduino.h>
#include <ModbusMaster.h>
```

- `<Arduino.h>` : fonctions de base Arduino (`pinMode`, `digitalWrite`, `Serial`…)
- `<ModbusMaster.h>` : classe de la librairie MODBUS installée via PlatformIO

> **`< >` vs `" "`** :
> - `<fichier.h>` → cherche dans les dossiers système et les librairies
> - `"fichier.h"` → cherche d'abord dans le dossier courant du projet

### 4.3 Le namespace `DYN200_REG`

```cpp
namespace DYN200_REG {
    constexpr uint16_t COUPLE    = 0x00;
    constexpr uint16_t VITESSE   = 0x02;
    constexpr uint16_t PUISSANCE = 0x04;
    // ...
}
```

**Qu'est-ce qu'un namespace ?**
Un espace de noms évite les **conflits de noms**. Sans namespace, si une autre librairie définit aussi une constante `VITESSE`, le compilateur ne saurait pas laquelle utiliser.

Avec namespace, on accède aux constantes ainsi :
```cpp
uint16_t addr = DYN200_REG::VITESSE;  // l'opérateur :: = "appartient à"
```

**Pourquoi `0x02` et pas `2` ?**
La notation hexadécimale (`0x`) est standard dans les datasheets de capteurs. `0x02` = 2, `0x0A` = 10, `0x1E` = 30. C'est plus lisible quand on compare avec la documentation du DYN-200.

### 4.4 Les structures (`struct`)

```cpp
struct DYN200_Mesures {
    float   couple_Nm;
    float   vitesse_RPM;
    float   puissance_kW;
    bool    valide;
};
```

Une `struct` est un **regroupement de variables** qui forment un tout logique. Avantages :
- On passe **un seul objet** à une fonction au lieu de 4 paramètres séparés
- Le champ `valide` voyage toujours avec les données → on ne peut pas oublier de tester l'erreur
- Le code est **auto-documenté** : `mesures.couple_Nm` est plus clair que `val1`

**Comparaison Python** : équivaut à un `dataclass` ou `namedtuple` en Python.

### 4.5 La déclaration de la classe

```cpp
class DYN200 {
public:
    DYN200(HardwareSerial &serial,
           uint8_t         pinDE_RE,
           uint8_t         slaveId  = 1,
           uint32_t        baudrate = 19200);

    void              begin();
    DYN200_Mesures    lireMesures();
    DYN200_Parametres lireParametres();
    bool              remiseAZero();
    bool              resetUsine();
    ModbusMaster&     getNode() { return _node; }

private:
    HardwareSerial &_serial;
    uint8_t         _pinDE_RE;
    // ...
    static DYN200  *_instance;
    static void     _preTransmission();
    static void     _postTransmission();
    static int32_t  _regsToInt32(uint16_t hi, uint16_t lo);
};
```

#### `public` vs `private`

| Visibilité | Signification | Dans ce projet |
|-----------|--------------|----------------|
| `public` | Accessible de partout | Fonctions utilisées dans `main.cpp` |
| `private` | Accessible seulement depuis la classe | Variables internes, fonctions de bas niveau |

La convention `_nomVariable` (underscore en préfixe) signale visuellement qu'une variable est **privée**. Ce n'est pas obligatoire en C++, mais c'est une bonne pratique très répandue.

#### Les paramètres par défaut

```cpp
DYN200(HardwareSerial &serial,
       uint8_t         pinDE_RE,
       uint8_t         slaveId  = 1,      // ← valeur par défaut
       uint32_t        baudrate = 19200); // ← valeur par défaut
```

Si l'utilisateur ne fournit pas `slaveId` et `baudrate`, le compilateur utilise `1` et `19200`. On peut donc créer l'objet de plusieurs façons :

```cpp
DYN200 dyn200(Serial1, 2);              // slaveId=1, baudrate=19200 (défauts)
DYN200 dyn200(Serial1, 2, 3);          // slaveId=3, baudrate=19200 (défaut)
DYN200 dyn200(Serial1, 2, 1, 9600);    // tout explicite
```

#### Le passage par référence (`&`)

```cpp
DYN200(HardwareSerial &serial, ...)
```

Le `&` signifie **"passage par référence"** : on ne copie pas l'objet, on travaille directement sur l'original. C'est indispensable ici car `HardwareSerial` représente un vrai port matériel — le copier n'aurait aucun sens.

**Sans `&`** : le compilateur essaierait de copier l'objet → erreur car `HardwareSerial` n'est pas copiable.

#### Les membres `static`

```cpp
static DYN200  *_instance;
static void     _preTransmission();
static void     _postTransmission();
```

Un membre `static` appartient à **la classe entière**, pas à une instance particulière. Il n'existe **qu'en un seul exemplaire** en mémoire, peu importe combien d'objets `DYN200` sont créés.

**Pourquoi ici ?** La librairie ModbusMaster attend des fonctions callback de la forme `void maFonction()` sans paramètre. Elle ne peut pas recevoir un pointeur vers une méthode d'objet (`void DYN200::maFonction()`) car ces méthodes ont un paramètre caché (`this`). Une méthode `static` n'a pas de `this` → elle est compatible avec les callbacks.

Le pointeur `_instance` permet au callback statique de retrouver l'objet courant pour accéder à `_pinDE_RE`.

---

## 5. Le fichier `DYN200.cpp` — Implémentation

### 5.1 Initialisation du membre statique

```cpp
DYN200 *DYN200::_instance = nullptr;
```

Les membres `static` doivent être **définis une seule fois** dans un `.cpp` (pas dans le `.h`). `nullptr` est le pointeur nul en C++ moderne (équivalent de `NULL` mais avec contrôle de type).

### 5.2 Le constructeur

```cpp
DYN200::DYN200(HardwareSerial &serial,
               uint8_t         pinDE_RE,
               uint8_t         slaveId,
               uint32_t        baudrate)
    : _serial(serial),        // ← liste d'initialisation
      _pinDE_RE(pinDE_RE),
      _slaveId(slaveId),
      _baudrate(baudrate)
{
    _instance = this;
}
```

#### L'opérateur de portée `::`

`DYN200::DYN200(...)` signifie : *"ceci est le constructeur (`DYN200`) qui appartient à la classe `DYN200`"*. Le `::` est l'opérateur de résolution de portée.

#### La liste d'initialisation (`: _serial(serial), ...`)

C'est la façon correcte d'initialiser les membres d'une classe en C++. Elle s'exécute **avant** le corps `{ }` du constructeur.

Pourquoi ne pas écrire `_serial = serial;` dans le corps ?
- Pour les **références** (`HardwareSerial &_serial`), l'initialisation dans le corps est **impossible** : une référence doit être liée à sa cible dès sa création.
- Pour les autres membres, la liste d'initialisation est plus **efficace** (une seule opération au lieu de deux).

#### `this`

```cpp
_instance = this;
```

`this` est un **pointeur vers l'objet courant**. Quand on écrit `DYN200 dyn200(...)`, à l'intérieur du constructeur, `this` pointe vers `dyn200`. On sauvegarde ce pointeur dans `_instance` pour que les callbacks statiques puissent retrouver l'objet.

### 5.3 La méthode `begin()`

```cpp
void DYN200::begin()
{
    pinMode(_pinDE_RE, OUTPUT);
    digitalWrite(_pinDE_RE, LOW);

    _serial.begin(_baudrate, SERIAL_8N2);

    _node.begin(_slaveId, _serial);
    _node.preTransmission(DYN200::_preTransmission);
    _node.postTransmission(DYN200::_postTransmission);
}
```

**Pourquoi une méthode `begin()` séparée du constructeur ?**
Sur Arduino, les périphériques série ne sont pas encore disponibles pendant l'exécution des constructeurs globaux. La convention Arduino est d'initialiser les périphériques dans `setup()`, via une méthode `begin()`.

**`SERIAL_8N2`** : constante Arduino pour le format de trame série :
- `8` = 8 bits de données
- `N` = No parity (pas de parité)
- `2` = 2 bits de stop

C'est la configuration par défaut du DYN-200.

### 5.4 La méthode `lireMesures()`

```cpp
DYN200_Mesures DYN200::lireMesures()
{
    DYN200_Mesures m = {0.0f, 0.0f, 0.0f, false};

    uint8_t status = _node.readHoldingRegisters(DYN200_REG::COUPLE, 6);

    if (status == ModbusMaster::ku8MBSuccess) {
        int32_t rawCouple = _regsToInt32(_node.getResponseBuffer(0),
                                         _node.getResponseBuffer(1));
        // ...
        m.couple_Nm = rawCouple / 1000.0f;
        m.valide    = true;
    }

    return m;
}
```

#### L'initialisation d'une struct avec `{ }`

```cpp
DYN200_Mesures m = {0.0f, 0.0f, 0.0f, false};
```

Initialise les champs dans l'ordre de déclaration : `couple_Nm=0.0`, `vitesse_RPM=0.0`, `puissance_kW=0.0`, `valide=false`. Si la lecture échoue, on retourne cette structure "vide" avec `valide=false`.

#### Le suffixe `f` sur les flottants

```cpp
m.couple_Nm = rawCouple / 1000.0f;
```

Sans le `f`, `1000.0` est un `double` (64 bits). Diviser un `int32_t` par un `double` force le calcul en double précision, inutile sur AVR. Le `f` force le calcul en `float` (32 bits) → plus rapide sur Arduino.

#### `ModbusMaster::ku8MBSuccess`

`ku8MBSuccess` est une constante `static` de la classe `ModbusMaster` (valeur = 0, signifiant "succès"). On y accède avec `::` car c'est un membre de classe, pas d'instance.

### 5.5 Le lambda dans `lireParametres()`

```cpp
auto lireReg = [&](uint16_t addr, int32_t &dest) -> bool {
    uint8_t s = _node.readHoldingRegisters(addr, 2);
    if (s == ModbusMaster::ku8MBSuccess) {
        dest = _regsToInt32(_node.getResponseBuffer(0),
                            _node.getResponseBuffer(1));
        return true;
    }
    return false;
};
```

Un **lambda** est une fonction anonyme définie localement. Décomposons la syntaxe :

| Partie | Signification |
|--------|--------------|
| `auto lireReg =` | Crée une variable `lireReg` qui contient la fonction |
| `[&]` | **Capture par référence** : le lambda peut accéder à toutes les variables locales (dont `_node`) |
| `(uint16_t addr, int32_t &dest)` | Paramètres de la fonction |
| `-> bool` | Type de retour explicite |
| `{ ... }` | Corps de la fonction |

Utilisation ensuite comme une fonction normale :
```cpp
ok &= lireReg(DYN200_REG::FILTRAGE, p.filtrage);
```

**Pourquoi un lambda ici ?** Pour éviter de répéter 5 lignes identiques 9 fois. C'est l'équivalent d'une fonction locale, mais sans la déclarer en dehors de la méthode.

#### L'opérateur `&=`

```cpp
bool ok = true;
ok &= lireReg(DYN200_REG::FILTRAGE, p.filtrage);
ok &= lireReg(DYN200_REG::VITESSE,  p.vitesse);
```

`ok &= condition` est équivalent à `ok = ok & condition`. C'est un **ET binaire** : si *une seule* lecture échoue (retourne `false`), `ok` devient `false` et le reste. Résultat : `ok` est `true` seulement si **toutes** les lectures ont réussi.

### 5.6 Les callbacks `_preTransmission` et `_postTransmission`

```cpp
void DYN200::_preTransmission()
{
    if (_instance) digitalWrite(_instance->_pinDE_RE, HIGH);
}

void DYN200::_postTransmission()
{
    if (_instance) digitalWrite(_instance->_pinDE_RE, LOW);
}
```

#### L'opérateur `->`

`_instance->_pinDE_RE` accède au membre `_pinDE_RE` **via un pointeur**. Si `obj` est un objet normal, on écrit `obj._pinDE_RE`. Si `ptr` est un pointeur vers un objet, on écrit `ptr->_pinDE_RE`. Les deux sont équivalents à `(*ptr)._pinDE_RE`.

#### Pourquoi tester `if (_instance)` ?

Un pointeur nul (`nullptr`) ne doit jamais être déréférencé → crash garanti. Ce test protège contre le cas où le callback serait appelé avant que l'objet soit créé.

### 5.7 La conversion `_regsToInt32`

```cpp
int32_t DYN200::_regsToInt32(uint16_t hi, uint16_t lo)
{
    uint32_t raw = ((uint32_t)hi << 16) | (uint32_t)lo;
    return (int32_t)raw;
}
```

Le DYN-200 stocke chaque valeur sur **deux registres de 16 bits**. Il faut les recombiner en un entier 32 bits :

```
Registre haut (hi) : 0xFFFF
Registre bas  (lo) : 0xFC18

hi << 16  →  0xFFFF0000
     lo   →  0x0000FC18
OR        →  0xFFFFC18  (uint32)
cast      →  -15336     (int32, complément à 2)
```

| Opération | Description |
|-----------|-------------|
| `(uint32_t)hi` | Cast : force `hi` en 32 bits pour éviter une perte lors du décalage |
| `<< 16` | Décalage à gauche de 16 bits (= multiplier par 65536) |
| `\|` | OU binaire : colle les deux moitiés |
| `(int32_t)raw` | Réinterprète les bits comme un entier signé |

---

## 6. Le fichier `main.cpp` — Programme principal

### 6.1 Structure Arduino : `setup()` et `loop()`

```cpp
void setup()  { /* exécuté une seule fois au démarrage */ }
void loop()   { /* exécuté en boucle infinie */           }
```

C'est le modèle de base Arduino. PlatformIO génère automatiquement le `main()` C++ qui appelle `setup()` puis `loop()` en boucle.

### 6.2 Le polling non-bloquant avec `millis()`

```cpp
uint32_t dernierPoll = 0;

void loop()
{
    uint32_t maintenant = millis();

    if (maintenant - dernierPoll >= POLL_MS) {
        dernierPoll = maintenant;
        mesures = dyn200.lireMesures();
        afficherMesures(mesures);
    }
    // ... le reste du loop continue sans être bloqué
}
```

**Pourquoi ne pas utiliser `delay(500)` ?**

`delay(500)` **bloque entièrement** le processeur pendant 500 ms. Pendant ce temps, aucune autre action n't est possible (pas de lecture du port série, pas de réaction à un bouton…).

La technique `millis()` est **non-bloquante** : on mémorise le moment de la dernière exécution, et on ne fait l'action que si assez de temps s'est écoulé. Entre deux lectures, le processeur est libre de faire autre chose (ici : lire les commandes série).

**Attention au débordement de `millis()`** : après ~49 jours, `millis()` repasse à 0. La soustraction `maintenant - dernierPoll` fonctionne **correctement même en cas de débordement** grâce à l'arithmétique non-signée (comportement défini en C++).

### 6.3 Le switch/case pour les commandes

```cpp
if (Serial.available()) {
    char cmd = Serial.read();

    switch (cmd) {
        case 'z':
            dyn200.remiseAZero();
            break;
        case 'r':
            dyn200.resetUsine();
            break;
        default:
            break;
    }
}
```

`switch/case` est plus lisible qu'une chaîne de `if/else if` quand on teste une variable contre plusieurs valeurs constantes. Le `break` est **obligatoire** : sans lui, l'exécution "tombe" dans le case suivant (*fall-through*).

### 6.4 `F()` — Macro pour économiser la RAM

```cpp
Serial.println(F("DYN-200 — MODBUS RTU via MAX485"));
```

Sur AVR (Arduino Mega), les chaînes de caractères sont stockées par défaut en **RAM** (2 Ko seulement sur le Mega). La macro `F()` force le stockage en **Flash** (256 Ko) et la lecture directement depuis la Flash.

Sans `F()`, chaque `Serial.println("texte")` consomme de la RAM précieuse. Avec `F()`, la RAM n'est pas utilisée pour les chaînes constantes.

### 6.5 Affichage des mesures

```cpp
void afficherMesures(const DYN200_Mesures &m)
{
    if (!m.valide) {
        Serial.println(F("[ERREUR] Lecture mesures echouee"));
        return;     // ← sortie anticipée
    }

    Serial.print(F("Couple: "));
    Serial.print(m.couple_Nm, 3);   // 3 décimales
    Serial.println(F(" N.m"));
}
```

Le **passage par `const &`** (`const DYN200_Mesures &m`) est la convention C++ pour passer un objet en lecture seule sans le copier :
- Sans `&` : la struct serait copiée (inutile, coûteux)
- Sans `const` : la fonction pourrait modifier la struct (non souhaité)
- Avec `const &` : efficace et sûr

---

## 7. Le bus RS485 et le MAX485

### Principe du RS485

RS485 est un standard de communication différentielle : au lieu d'une tension par rapport à la masse, il transmet la **différence de tension** entre deux fils (A et B). Cela lui confère une excellente immunité aux interférences.

```
Fil A (+) ────────────────────────────────► DYN-200
Fil B (-) ────────────────────────────────► DYN-200

Si A-B > +0.2V  →  bit "1"
Si A-B < -0.2V  →  bit "0"
```

### Le MAX485 : demi-duplex

Le MAX485 ne peut pas **émettre et recevoir en même temps** (half-duplex). Les broches DE et RE contrôlent la direction :

| DE | RE | Mode |
|----|-----|------|
| 1  | 1  | Émission (TX actif) |
| 0  | 0  | Réception (RX actif) |

Dans le projet, DE et RE sont reliés **à la même broche Arduino (D2)**. Le code bascule cette broche avant et après chaque trame MODBUS via les callbacks.

### Chronogramme d'une transaction

```
Arduino                    MAX485                DYN-200
   │                          │                     │
   │─── D2=HIGH (DE/RE=1) ───►│                     │
   │─── Envoi trame TX ──────►│──── RS485 A/B ─────►│
   │─── D2=LOW  (DE/RE=0) ───►│                     │
   │                          │◄─── RS485 A/B ──────│
   │◄─── Réponse RX ──────────│                     │
```

---

## 8. Le protocole MODBUS RTU

### Trame de requête (lecture de registres, fonction 03H)

```
┌──────────┬──────────┬──────────────────┬─────────────────┬───────┐
│ Adresse  │ Fonction │ Adresse registre │ Nombre registres│  CRC  │
│ esclave  │  (03H)   │   (2 octets)     │   (2 octets)    │(2 oct)│
│  1 octet │  1 octet │                  │                 │       │
└──────────┴──────────┴──────────────────┴─────────────────┴───────┘
  0x01        0x03        0x00  0x00         0x00  0x06      ??  ??
```

**Exemple** : lire 6 registres à partir de 0x0000, esclave 1 :
`01 03 00 00 00 06 C5 C8`

### Trame de réponse

```
┌──────────┬──────────┬──────────┬─────────────────────┬───────┐
│ Adresse  │ Fonction │ Nb octets│     Données          │  CRC  │
│  1 octet │  1 octet │  1 octet │   (nb octets)        │(2 oct)│
└──────────┴──────────┴──────────┴─────────────────────┴───────┘
  0x01       0x03       0x0C      6 × 2 = 12 octets      ??  ??
```

### Conversion des données DYN-200

| Registres | Valeur brute | Facteur | Valeur réelle |
|-----------|-------------|---------|---------------|
| 0x00-0x01 | `int32` | ÷ 1000 | Couple (N·m) |
| 0x02-0x03 | `int32` | ÷ 10   | Vitesse (RPM) |
| 0x04-0x05 | `int32` | ÷ 100  | Puissance (kW) |

---

## 9. La librairie ModbusMaster

### Pourquoi cette librairie ?

`ModbusMaster` (by 4-20ma) est choisie car elle est :
- **Légère** : conçue pour les microcontrôleurs AVR avec peu de RAM
- **Callbacks intégrés** : `preTransmission` / `postTransmission` → parfait pour piloter DE/RE du MAX485
- **API simple** : `readHoldingRegisters(addr, count)` retourne un code d'erreur standard

### Fonctions utilisées dans le projet

| Méthode | Description |
|---------|-------------|
| `begin(slaveId, serial)` | Initialise avec l'adresse esclave et le port série |
| `preTransmission(fn)` | Enregistre le callback appelé avant émission |
| `postTransmission(fn)` | Enregistre le callback appelé après émission |
| `readHoldingRegisters(addr, count)` | Lit `count` registres à partir de `addr` (fonction 03H) |
| `getResponseBuffer(index)` | Récupère le registre numéro `index` dans la réponse |
| `writeSingleCoil(addr, value)` | Écrit un coil (fonction 05H) |
| `setTransmitBuffer(index, value)` | Prépare un registre pour écriture multiple |
| `writeMultipleRegisters(addr, count)` | Écrit plusieurs registres (fonction 10H) |

### Codes de retour

| Constante | Valeur | Signification |
|-----------|--------|--------------|
| `ku8MBSuccess` | 0x00 | Succès |
| `ku8MBResponseTimedOut` | 0xE2 | Timeout (capteur ne répond pas) |
| `ku8MBInvalidCRC` | 0xE3 | CRC invalide (bruit sur le câble) |
| `ku8MBInvalidSlaveID` | 0xE0 | Mauvaise adresse esclave |

---

## 10. Récapitulatif du flux de données

```
┌─────────────────────────────────────────────────────────────┐
│                        main.cpp                             │
│                                                             │
│  setup()                          loop()                    │
│  ├─ dyn200.begin()                ├─ [toutes les 500ms]    │
│  └─ dyn200.lireParametres()       │   mesures = dyn200.    │
│                                   │   lireMesures()         │
│                                   │   afficherMesures()     │
│                                   └─ [si touche série]      │
│                                       traiter commande      │
└────────────────────┬────────────────────────────────────────┘
                     │ appels de méthodes
┌────────────────────▼────────────────────────────────────────┐
│                     DYN200.cpp                              │
│                                                             │
│  lireMesures()                                              │
│  ├─ _node.readHoldingRegisters(0x00, 6)                     │
│  │   ├─ [callback] _preTransmission() → D2=HIGH (émission) │
│  │   ├─ Envoie trame MODBUS RTU sur Serial1                 │
│  │   ├─ [callback] _postTransmission() → D2=LOW (réception)│
│  │   └─ Reçoit réponse DYN-200                             │
│  ├─ _regsToInt32(reg0, reg1) → int32 brut                  │
│  └─ int32 / 1000.0f → float N·m                            │
└────────────────────┬────────────────────────────────────────┘
                     │ Serial1 (UART)
┌────────────────────▼────────────────────────────────────────┐
│                MAX485 (half-duplex)                          │
│  D2=HIGH → émission │ D2=LOW → réception                    │
└────────────────────┬────────────────────────────────────────┘
                     │ RS485 différentiel (fils A et B)
┌────────────────────▼────────────────────────────────────────┐
│               DYN-200 (couple-mètre)                        │
│  Registres MODBUS : couple, vitesse, puissance, config...   │
└─────────────────────────────────────────────────────────────┘
```

---

## Annexe : Syntaxes C++ récapitulées

| Syntaxe | Nom | Exemple dans le projet |
|---------|-----|----------------------|
| `uint8_t`, `int32_t` | Types entiers à taille fixe | `uint8_t _pinDE_RE` |
| `constexpr` | Constante compilation | `constexpr uint8_t PIN_DE_RE = 2` |
| `namespace { }` | Espace de noms | `namespace DYN200_REG { }` |
| `::` | Résolution de portée | `DYN200_REG::COUPLE` |
| `struct { }` | Structure de données | `struct DYN200_Mesures { }` |
| `class { public: private: }` | Classe | `class DYN200 { ... }` |
| `&` (paramètre) | Passage par référence | `void f(const DYN200_Mesures &m)` |
| `*` (pointeur) | Pointeur | `DYN200 *_instance` |
| `->` | Accès via pointeur | `_instance->_pinDE_RE` |
| `this` | Pointeur vers objet courant | `_instance = this` |
| `static` (membre) | Appartient à la classe | `static DYN200 *_instance` |
| `: mem(val)` | Liste d'initialisation | `DYN200::DYN200(...) : _serial(s)` |
| `nullptr` | Pointeur nul | `_instance = nullptr` |
| `auto` | Déduction de type | `auto lireReg = [&](...)` |
| `[&](params) {}` | Lambda / closure | Fonction locale anonyme |
| `&=` | ET binaire assignant | `ok &= lireReg(...)` |
| `<< n` | Décalage gauche | `(uint32_t)hi << 16` |
| `\|` | OU binaire | `hi \| lo` |
| `(type)val` | Cast C-style | `(int32_t)raw` |
| `F("texte")` | Macro Flash (Arduino) | `Serial.println(F("..."))` |
| `#pragma once` | Garde d'inclusion | En-tête de tout `.h` |
| `0x` | Notation hexadécimale | `0x00`, `0x1E` |
| `0.0f` | Littéral float 32 bits | `rawCouple / 1000.0f` |
