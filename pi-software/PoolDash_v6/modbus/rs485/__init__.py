# modbus/rs485/__init__.py
# RS485 Modbus RTU subsystem for PoolAIssistant
#
# This package provides support for RS485 serial devices using Modbus RTU protocol.
# Currently supports:
#   - Water testing devices (TDS, conductivity, etc.)
#
# Structure:
#   rtu_client.py         - Modbus RTU serial client wrapper
#   water_tester_points.py - Register definitions for water tester devices

from .rtu_client import RS485Client, RS485ConnectionError
from .water_tester_points import POINTS as WATER_TESTER_POINTS

__all__ = [
    "RS485Client",
    "RS485ConnectionError",
    "WATER_TESTER_POINTS",
]
