// ============================================================
//  DYN200.cpp  —  Implémentation de la classe DYN200
// ============================================================

#include "DYN200.h"

// ── Membre statique (nécessaire pour les callbacks) ──────────
DYN200 *DYN200::_instance = nullptr;

// ── Constructeur ─────────────────────────────────────────────
DYN200::DYN200(HardwareSerial &serial,
               uint8_t         pinDE_RE,
               uint8_t         slaveId,
               uint32_t        baudrate)
    : _serial(serial),
      _pinDE_RE(pinDE_RE),
      _slaveId(slaveId),
      _baudrate(baudrate)
{
    _instance = this;   // enregistre l'instance pour les callbacks statiques
}

// ── Initialisation ───────────────────────────────────────────
void DYN200::begin()
{
    // Configuration de la broche DE/RE du MAX485
    pinMode(_pinDE_RE, OUTPUT);
    digitalWrite(_pinDE_RE, LOW);   // mode réception par défaut

    // Ouverture du port série : 8N2 (8 bits, pas de parité, 2 stop bits)
    // conforme à la configuration par défaut du DYN-200
    _serial.begin(_baudrate, SERIAL_8N2);

    // Configuration ModbusMaster
    _node.begin(_slaveId, _serial);

    // Liaison des callbacks DE/RE pour le half-duplex MAX485
    _node.preTransmission(DYN200::_preTransmission);
    _node.postTransmission(DYN200::_postTransmission);
}

// ── Lecture des mesures en temps réel ────────────────────────
DYN200_Mesures DYN200::lireMesures()
{
    DYN200_Mesures m = {0.0f, 0.0f, 0.0f, false};

    // Lecture de 6 registres à partir de 0x00
    // (couple 0x00-01 + vitesse 0x02-03 + puissance 0x04-05)
    uint8_t status = _node.readHoldingRegisters(DYN200_REG::COUPLE, 6);

    if (status == ModbusMaster::ku8MBSuccess) {
        int32_t rawCouple    = _regsToInt32(_node.getResponseBuffer(0),
                                            _node.getResponseBuffer(1));
        int32_t rawVitesse   = _regsToInt32(_node.getResponseBuffer(2),
                                            _node.getResponseBuffer(3));
        int32_t rawPuissance = _regsToInt32(_node.getResponseBuffer(4),
                                            _node.getResponseBuffer(5));

        m.couple_Nm    = rawCouple    / 1000.0f;  // facteur ×1000 dans le capteur
        m.vitesse_RPM  = rawVitesse   / 10.0f;    // facteur ×10
        m.puissance_kW = rawPuissance / 100.0f;   // facteur ×100
        m.valide       = true;
    }

    return m;
}

// ── Lecture des paramètres de configuration ──────────────────
DYN200_Parametres DYN200::lireParametres()
{
    DYN200_Parametres p;
    p.valide = false;

    // Helper lambda local pour lire un registre int32 (2 × 16 bits)
    auto lireReg = [&](uint16_t addr, int32_t &dest) -> bool {
        uint8_t s = _node.readHoldingRegisters(addr, 2);
        if (s == ModbusMaster::ku8MBSuccess) {
            dest = _regsToInt32(_node.getResponseBuffer(0),
                                _node.getResponseBuffer(1));
            return true;
        }
        return false;
    };

    bool ok = true;
    ok &= lireReg(DYN200_REG::FILTRAGE,       p.filtrage);
    ok &= lireReg(DYN200_REG::POINT_DECIMAL,  p.point_decimal);
    ok &= lireReg(DYN200_REG::ZERO_DEMARRAGE, p.zero_demarrage);
    ok &= lireReg(DYN200_REG::ZERO_TRANSMIS,  p.zero_transmis);
    ok &= lireReg(DYN200_REG::PLEINE_ECHELLE, p.pleine_echelle);
    ok &= lireReg(DYN200_REG::PLAGE_TRANSMIS, p.plage_transmis);
    ok &= lireReg(DYN200_REG::DIR_COUPLE,     p.dir_couple);
    ok &= lireReg(DYN200_REG::FILTRE_VITESSE, p.filtre_vitesse);
    ok &= lireReg(DYN200_REG::DEC_VITESSE,    p.dec_vitesse);

    p.valide = ok;
    return p;
}

// ── Remise à zéro du couple (fonction MODBUS 05H) ────────────
bool DYN200::remiseAZero()
{
    uint8_t status = _node.writeSingleCoil(0x0000, true);
    return (status == ModbusMaster::ku8MBSuccess);
}

// ── Reset usine (fonction MODBUS 10H) ────────────────────────
bool DYN200::resetUsine()
{
    // Écriture de 0x00000001 dans les registres 0x06 (2 registres)
    _node.setTransmitBuffer(0, 0x0000);
    _node.setTransmitBuffer(1, 0x0001);
    uint8_t status = _node.writeMultipleRegisters(DYN200_REG::FILTRAGE, 2);
    return (status == ModbusMaster::ku8MBSuccess);
}

// ── Callbacks MAX485 half-duplex ─────────────────────────────
void DYN200::_preTransmission()
{
    // Passe en mode émission : DE=HIGH, RE=HIGH
    if (_instance) digitalWrite(_instance->_pinDE_RE, HIGH);
}

void DYN200::_postTransmission()
{
    // Repasse en mode réception : DE=LOW, RE=LOW
    if (_instance) digitalWrite(_instance->_pinDE_RE, LOW);
}

// ── Helper : int32 signé depuis deux registres 16 bits ────────
int32_t DYN200::_regsToInt32(uint16_t hi, uint16_t lo)
{
    uint32_t raw = ((uint32_t)hi << 16) | (uint32_t)lo;
    return (int32_t)raw;    // reinterprétation signée (complément à 2)
}
