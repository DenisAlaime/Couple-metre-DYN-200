#pragma once

// ============================================================
//  DYN200.h  —  Classe pour le couple-mètre DYN-200
//  Protocole : MODBUS RTU via RS485 (MAX485 half-duplex)
//  Cible      : Arduino Mega 2560 + PlatformIO
// ============================================================

#include <Arduino.h>
#include <ModbusMaster.h>

// ──────────────────────────────────────────────────────────────
//  Adresses des registres MODBUS DYN-200 (lecture : fonction 03H)
//  Chaque mesure occupe 2 registres de 16 bits → int32 signé
// ──────────────────────────────────────────────────────────────
namespace DYN200_REG {
    constexpr uint16_t COUPLE          = 0x00;  // Torque  (N·m  × 1000)
    constexpr uint16_t VITESSE         = 0x02;  // Speed   (RPM  × 10)
    constexpr uint16_t PUISSANCE       = 0x04;  // Power   (kW   × 100)
    constexpr uint16_t FILTRAGE        = 0x06;  // Filtre numérique
    constexpr uint16_t POINT_DECIMAL   = 0x08;  // Point décimal
    constexpr uint16_t ZERO_DEMARRAGE  = 0x0A;  // Zéro au démarrage
    constexpr uint16_t ZERO_TRANSMIS   = 0x0C;  // Zéro transmission
    constexpr uint16_t PLEINE_ECHELLE  = 0x0E;  // Pleine échelle
    constexpr uint16_t PLAGE_TRANSMIS  = 0x10;  // Plage de transmission
    constexpr uint16_t DIR_COUPLE      = 0x12;  // Direction du couple
    constexpr uint16_t FILTRE_VITESSE  = 0x1E;  // Filtre vitesse
    constexpr uint16_t DEC_VITESSE     = 0x20;  // Décimales vitesse
}

// ──────────────────────────────────────────────────────────────
//  Structure principale des mesures en temps réel
// ──────────────────────────────────────────────────────────────
struct DYN200_Mesures {
    float   couple_Nm;      // Couple en N·m
    float   vitesse_RPM;    // Vitesse en RPM
    float   puissance_kW;   // Puissance en kW
    bool    valide;         // true si la dernière lecture a réussi
};

// ──────────────────────────────────────────────────────────────
//  Structure des paramètres de configuration (registres étendus)
// ──────────────────────────────────────────────────────────────
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

// ──────────────────────────────────────────────────────────────
//  Classe DYN200
// ──────────────────────────────────────────────────────────────
class DYN200 {
public:
    // ── Construction ──────────────────────────────────────────
    // serial      : port série HardwareSerial utilisé (ex: Serial1)
    // pinDE_RE    : broche DE/RE du MAX485 (direction TX/RX)
    // slaveId     : adresse MODBUS de l'esclave (défaut = 1)
    // baudrate    : vitesse de communication (défaut = 19200)
    DYN200(HardwareSerial &serial,
           uint8_t         pinDE_RE,
           uint8_t         slaveId  = 1,
           uint32_t        baudrate = 19200);

    // ── Initialisation (à appeler dans setup()) ───────────────
    void begin();

    // ── Lecture des mesures en temps réel ─────────────────────
    // Lit couple + vitesse + puissance en une seule trame MODBUS
    // Retourne la structure remplie (champ .valide = false si erreur)
    DYN200_Mesures lireMesures();

    // ── Lecture des paramètres de configuration ───────────────
    DYN200_Parametres lireParametres();

    // ── Commandes d'écriture ──────────────────────────────────
    bool remiseAZero();     // Zéro couple (coil 0x0000, fonction 05H)
    bool resetUsine();      // Reset usine (registres 0x06, fonction 10H)

    // ── Accès bas niveau ──────────────────────────────────────
    ModbusMaster& getNode() { return _node; }

private:
    HardwareSerial &_serial;
    uint8_t         _pinDE_RE;
    uint8_t         _slaveId;
    uint32_t        _baudrate;
    ModbusMaster    _node;

    // Callbacks MAX485 pour piloter DE/RE (demi-duplex)
    static DYN200  *_instance;          // pointeur pour les callbacks statiques
    static void     _preTransmission(); // DE/RE HIGH → mode émission
    static void     _postTransmission();// DE/RE LOW  → mode réception

    // Helper : combine deux registres 16 bits en int32 signé
    static int32_t  _regsToInt32(uint16_t hi, uint16_t lo);
};
