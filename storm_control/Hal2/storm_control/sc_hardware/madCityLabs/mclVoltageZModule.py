#!/usr/bin/env python
"""
Mad City Labs (voltage controlled) Z stage functionality.

Hazen 05/17

updates 05/19, Alistair:  copied from ludl VoltageZModule

"""

from PyQt5 import QtCore # added based on ludlVoltageZ. Doesn't look like it is used though. 

import storm_control.sc_hardware.baseClasses.voltageZModule as voltageZModule


class MCLVoltageZ(voltageZModule.VoltageZ):
    """
    This is a Mad City Labs stage in analog control mode.
    """
    def __init__(self, module_params = None, qt_settings = None, **kwds):
        super().__init__(module_params, qt_settings, **kwds)

    # added from ludulVoltageZModule, (which still claims to be an MCL)
    def handleResponse(self, message, response):
        if message.isType("get functionality"):
            self.z_stage_functionality = voltageZModule.VoltageZFunctionality(
                  ao_fn = response.getData()["functionality"],
                  parameters = self.configuration.get("parameters"),
                  microns_to_volts = self.configuration.get("microns_to_volts"),
                  invert_signal = True)

