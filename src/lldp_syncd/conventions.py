"""
LLDP 802.1AB - Textual Conventions (Enumerated Types)

See:
http://www.ieee802.org/1/files/public/MIBs/LLDP-MIB-200505060000Z.txt
"""

from enum import unique, Enum


@unique
class LldpChassisIdSubtype(int, Enum):
    """
    LldpChassisIdSubtype ::= TEXTUAL-CONVENTION
        SYNTAX  INTEGER {
            chassisComponent(1),
            interfaceAlias(2),
            portComponent(3),
            macAddress(4),
            networkAddress(5),
            interfaceName(6),
            local(7)
        }
    """
    chassisComponent = 1
    interfaceAlias = 2
    portComponent = 3
    macAddress = 4
    networkAddress = 5
    interfaceName = 6
    local = 7


@unique
class LldpPortIdSubtype(int, Enum):
    """
    LldpPortIdSubtype ::= TEXTUAL-CONVENTION
        SYNTAX  INTEGER {
                interfaceAlias(1),
                portComponent(2),
                macAddress(3),
                networkAddress(4),
                interfaceName(5),
                agentCircuitId(6),
                local(7)
        }
    """
    interfaceAlias = 1
    portComponent = 2
    macAddress = 3
    networkAddress = 4
    interfaceName = 5
    agentCircuitId = 6
    local = 7


@unique
class LldpManAddrIfSubtype(int, Enum):
    """
    LldpManAddrIfSubtype ::= TEXTUAL-CONVENTION
        SYNTAX  INTEGER {
                unknown(1),
                ifIndex(2),
                systemPortNumber(3)
        }
    """
    unknown = 1
    ifIndex = 2
    systemPortNumber = 3


@unique
class LldpSystemCapabilitiesMap(int, Enum):
    """
    LldpSystemCapabilitiesMap::= TEXTUAL - CONVENTION
    SYNTAX  BITS {
            other(0),
            repeater(1),
            bridge(2),
            wlanAccessPoint(3),
            router(4),
            telephone(5),
            docsisCableDevice(6),
            stationOnly(7)
    }
    """
    other = 0
    repeater = 1
    bridge = 2
    wlanAccessPoint = 3
    router = 4
    telephone = 5
    docsisCableDevice = 6
    stationOnly = 7
