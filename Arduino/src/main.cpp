// ============================================================
//  main.cpp  —  Programme principal DYN-200 sur Arduino Mega
//
//  Câblage MAX485 → Arduino Mega :
//  ┌──────────────┬──────────────────────────────────────┐
//  │  MAX485 pin  │  Arduino Mega                        │
//  ├──────────────┼──────────────────────────────────────┤
//  │  RO  (RX)    │  D19  (RX1 de Serial1)               │
//  │  DI  (TX)    │  D18  (TX1 de Serial1)               │
//  │  DE + RE     │  D2   (broche de direction, définie  │
//  │              │        par PIN_DE_RE ci-dessous)      │
//  │  A           │  RS485 A du DYN-200 (fil jaune)      │
//  │  B           │  RS485 B du DYN-200 (fil bleu)       │
//  │  VCC         │  5V                                  │
//  │  GND         │  GND                                 │
//  └──────────────┴──────────────────────────────────────┘
//
//  Port de debug : Serial0 (USB) @ 115200 bauds
// ============================================================

#include <Arduino.h>
#include "DYN200.h"

// ── Paramètres matériels ─────────────────────────────────────
constexpr uint8_t  PIN_DE_RE    = 2;        // broche DE/RE du MAX485
constexpr uint8_t  SLAVE_ID     = 1;        // adresse MODBUS du DYN-200
constexpr uint32_t BAUD_MODBUS  = 19200;    // vitesse MODBUS (19200 par défaut)
constexpr uint32_t POLL_MS      = 500;      // intervalle de lecture (ms)

// ── Instanciation du couple-mètre ────────────────────────────
// Serial1 = port UART1 du Mega (broches 18/19)
DYN200 dyn200(Serial1, PIN_DE_RE, SLAVE_ID, BAUD_MODBUS);

// ── Variables globales ───────────────────────────────────────
DYN200_Mesures    mesures;
DYN200_Parametres parametres;
uint32_t          dernierPoll = 0;
bool              parametresLus = false;    // lus une seule fois au démarrage

// ── Prototypes ───────────────────────────────────────────────
void afficherMesures(const DYN200_Mesures &m);
void afficherParametres(const DYN200_Parametres &p);
void afficherErreur(const char *contexte);

// ─────────────────────────────────────────────────────────────
//  SETUP
// ─────────────────────────────────────────────────────────────
void setup()
{
    // Port debug (moniteur série USB)
    Serial.begin(115200);
    while (!Serial) { ; }

    Serial.println(F("============================================"));
    Serial.println(F("  DYN-200 — MODBUS RTU via MAX485"));
    Serial.println(F("  Arduino Mega 2560 — PlatformIO"));
    Serial.println(F("============================================"));
    Serial.print(F("  Slave ID  : ")); Serial.println(SLAVE_ID);
    Serial.print(F("  Baudrate  : ")); Serial.println(BAUD_MODBUS);
    Serial.print(F("  Poll (ms) : ")); Serial.println(POLL_MS);
    Serial.println(F("--------------------------------------------"));

    // Initialisation du couple-mètre
    dyn200.begin();

    // Lecture initiale des paramètres de configuration
    Serial.println(F("\n[INIT] Lecture des parametres..."));
    parametres = dyn200.lireParametres();
    afficherParametres(parametres);
    parametresLus = true;

    Serial.println(F("\n[INIT] Demarrage du polling...\n"));
}

// ─────────────────────────────────────────────────────────────
//  LOOP
// ─────────────────────────────────────────────────────────────
void loop()
{
    uint32_t maintenant = millis();

    // ── Polling périodique ────────────────────────────────────
    if (maintenant - dernierPoll >= POLL_MS) {
        dernierPoll = maintenant;

        mesures = dyn200.lireMesures();
        afficherMesures(mesures);
    }

    // ── Commandes via moniteur série ──────────────────────────
    if (Serial.available()) {
        char cmd = Serial.read();

        switch (cmd) {
            case 'z':   // Remise à zéro
                Serial.println(F("\n[CMD] Remise a zero..."));
                if (dyn200.remiseAZero())
                    Serial.println(F("      OK"));
                else
                    afficherErreur("remise a zero");
                break;

            case 'r':   // Reset usine
                Serial.println(F("\n[CMD] Reset usine..."));
                if (dyn200.resetUsine())
                    Serial.println(F("      OK"));
                else
                    afficherErreur("reset usine");
                break;

            case 'p':   // Relire les paramètres
                Serial.println(F("\n[CMD] Relecture des parametres..."));
                parametres = dyn200.lireParametres();
                afficherParametres(parametres);
                break;

            case 'h':   // Aide
                Serial.println(F("\n--- Commandes disponibles ---"));
                Serial.println(F("  z : Remise a zero du couple"));
                Serial.println(F("  r : Reset usine"));
                Serial.println(F("  p : Relire les parametres"));
                Serial.println(F("  h : Cette aide"));
                Serial.println(F("-----------------------------\n"));
                break;

            default:
                break;
        }
    }
}

// ─────────────────────────────────────────────────────────────
//  Affichage des mesures sur le moniteur série
// ─────────────────────────────────────────────────────────────
void afficherMesures(const DYN200_Mesures &m)
{
    if (!m.valide) {
        Serial.println(F("[ERREUR] Lecture mesures echouee (timeout MODBUS ?)"));
        return;
    }

    // Horodatage (ms depuis démarrage)
    Serial.print(F("["));
    Serial.print(millis());
    Serial.print(F(" ms]  "));

    // Couple
    Serial.print(F("Couple: "));
    Serial.print(m.couple_Nm, 3);
    Serial.print(F(" N.m  |  "));

    // Vitesse
    Serial.print(F("Vitesse: "));
    Serial.print(m.vitesse_RPM, 1);
    Serial.print(F(" RPM  |  "));

    // Puissance
    Serial.print(F("Puissance: "));
    Serial.print(m.puissance_kW, 3);
    Serial.println(F(" kW"));
}

// ─────────────────────────────────────────────────────────────
//  Affichage des paramètres de configuration
// ─────────────────────────────────────────────────────────────
void afficherParametres(const DYN200_Parametres &p)
{
    Serial.println(F("\n--- Parametres DYN-200 ---"));
    if (!p.valide) {
        Serial.println(F("  [ERREUR] Lecture parametres echouee"));
        return;
    }
    Serial.print(F("  Filtrage num.     : ")); Serial.println(p.filtrage);
    Serial.print(F("  Point decimal     : ")); Serial.println(p.point_decimal);
    Serial.print(F("  Zero demarrage    : ")); Serial.println(p.zero_demarrage);
    Serial.print(F("  Zero transmission : ")); Serial.println(p.zero_transmis);
    Serial.print(F("  Pleine echelle    : ")); Serial.println(p.pleine_echelle);
    Serial.print(F("  Plage transmis.   : ")); Serial.println(p.plage_transmis);
    Serial.print(F("  Direction couple  : ")); Serial.println(p.dir_couple);
    Serial.print(F("  Filtre vitesse    : ")); Serial.println(p.filtre_vitesse);
    Serial.print(F("  Dec. vitesse      : ")); Serial.println(p.dec_vitesse);
    Serial.println(F("--------------------------\n"));
}

// ─────────────────────────────────────────────────────────────
//  Affichage d'un message d'erreur
// ─────────────────────────────────────────────────────────────
void afficherErreur(const char *contexte)
{
    Serial.print(F("[ERREUR] Commande echouee : "));
    Serial.println(contexte);
}
