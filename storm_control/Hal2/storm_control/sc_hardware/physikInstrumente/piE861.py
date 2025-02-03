#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
This contains the code required to connect to the piE861 stage and N-565.260 stage. 

Robby Nelson
robby.nelson@yale.edu
"""

from pipython import GCSDevice, pitools
import time
import traceback 
CONTROLLERNAME = 'E-861.1A1'
STAGES = ['N-565.260'] 
REFMODES = ['FRF'] # ['FNL', 'FRF']

class piE861(object):

    ## __init__
    #
    # Connect to the PI E873 stage.
    #
    #
    def __init__(self, serialnum = '120014096'):  
        print(serialnum)
    
        # Connect to the PI E861 stage.
        # with GCSDevice(CONTROLLERNAME) as pidevice:
        pidevice = GCSDevice(CONTROLLERNAME) 
        print(pidevice.EnumerateUSB())    

        pidevice.ConnectUSB(serialnum) #   pidevice.ConnectUSB(serialnum='119006811')
        print('connected: {}'.format(pidevice.qIDN().strip()))

        # Show the version info which is helpful for PI support when there
        # are any issues.

        if pidevice.HasqVER():
            print('version info:\n{}'.format(pidevice.qVER().strip()))

        # In the module pipython.pitools there are some helper
        # functions to make using a PI device more convenient. The "startup"
        # function will initialize your system. There are controllers that
        # cannot discover the connected stages hence we set them with the
        # "stages" argument. The desired referencing method (see controller
        # user manual) is passed as "refmode" argument. All connected axes
        # will be stopped if they are moving and their servo will be enabled.

        # print('initialize connected stages...')
        # pitools.enableaxes(pidevice, 'Axis_1')
        # print('initialize connected stages...')
        # # pitools.startup(pidevice, stages=None, refmodes=REFMODES, False)
        pitools.startup(pidevice, stages=STAGES, refmodes=REFMODES)
        print('initialized stages')




        # # Now we query the allowed motion range and current position of all
        # # connected stages. GCS commands often return an (ordered) dictionary
        # # with axes/channels as "keys" and the according values as "values".

        self.pidevice = pidevice
        
        # self.wait = 1 # move commands wait for motion to stop
        # self.unit_to_um = 100.0 # needs calibration
        # self.um_to_unit = 1.0/self.unit_to_um


        # # Connect to the stage.
        # self.good = 1

        # get min and max range
        self.rangemin = pidevice.qTMN()
        self.rangemax = pidevice.qTMX()
        self.curpos = pidevice.qPOS()
        self.servo_state = pidevice.qSVO()
        self.servo_velocity = pidevice.qVEL()
        # self.last_time = time.time() * 1000

        print(self.rangemin)
        print(self.rangemax)
        print(self.curpos)
        print(self.servo_state)
        print(self.servo_velocity)

        print('done initializing PI stage')
        self.good = 1

        pidevice.VEL(1, 4)
        # print(pidevice.qVEL())

        # pidevice.MOV(1, -2)
        # print('done')

        

    ## getStatus
    #
    # @return True/False if we are actually connected to the stage.
    #
    def getStatus(self):
        return self.good

    ## goAbsolute
    #
    # @param x Stage x position in um.
    # @param y Stage y position in um.
    #
    def runZStackMacro(self, step_size, num_runs):

        if step_size == 0.0250:
            macro_string = 'MAC NSTART ZSTEP250 ' + str(num_runs)
            # print('macro 250==========================================================================================')
        elif step_size == 0.050:
            macro_string = 'MAC NSTART ZSTEP50 ' + str(num_runs)
            # print('macro 50 ==========================================================================================')
        else:
            raise Exception('You entered an unsupported step size!')
        self.pidevice.send(macro_string)

    def startEndZMacro(self):
        macro_string = 'MAC START STARTZ'
        self.pidevice.send(macro_string)

    def goAbsolute(self, x):
        # print('go abs ' + str(x) )
        # print("z motion")
        # traceback.print_stack()
        # breakpoint()
        # print(x)
        # curr_time = time.time() * 1000
        # time_diff = curr_time - self.last_time
        # self.last_time = curr_time 
        if self.good:
            # If the stage is currently moving due to a jog command
            # and then you try to do a positional move everything
            # will freeze, so we stop the stage first.
            # self.jog(0.0,0.0)
            X = x / 1000

            # The native units for the N-565 are mm
            # Although the range is (-13, 13) mm, this is not practical since it would hit 
            # the sample and the focus lock dichroic. Instead we limit it to (-2, 2.5)
            if X > -2 and X < 5:
                # print(X)
                # print(time_diff)
                self.pidevice.MOV(1, X)
                # print(X)
            else:
                print('requested move outside max range!')

    ## goRelative
    #
    # @param dx Amount to displace the stage in x in um.
    # @param dy Amount to displace the stage in y in um.
    #
    def goRelative(self, dx):
        print('go rel command for ' + str(dx))
        if self.good:
            # self.jog(0.0,0.0)
            x0 = self.pidevice.qPOS(1)[1]  
            X = x0 - dx
            self.goAbsolute(X)

            # pitools.waitontarget(self.pidevice, axes=1) # actively hold on target
            # pitools.waitontarget(self.pidevice, axes=2) # actively hold on target
            
            
    ## position
    #
    # @return [stage x (um), stage y (um), stage z (um)]
    #
    def position(self):
        # print('get pos called')
        if self.good:
            x0 = self.pidevice.qPOS(1)[1]
            x0 = x0 * 1000
            return {"z" : x0}

     
    def zMoveTo(self, z):
        """
        Move the z stage to the specified position (in microns).
        """
        self.goAbsolute(z)

    def zPosition(self):
        """
        Query for current z position in microns.
        """
        return self.position()

    def zSetVelocity(self, z_vel):
        pass
        # self.pidevice.VEL(1, z_vel)
        
    def zZero(self):
        print('not implemented')
        # if self.good:
        #     pitools._ref_with_pos(self, self.pidevice.axes([2])) # added axes [0,1], not sure this ever worked anyway

    ## jog
    #
    # @param x_speed Speed to jog the stage in x in um/s.
    # @param y_speed Speed to jog the stage in y in um/s.
    #
    def jog(self, x_speed, y_speed):
        pass
        # figure out how to do something here
        # if self.good:
        #     c_xs = c_double(x_speed * self.um_to_unit)
        #     c_ys = c_double(y_speed * self.um_to_unit)
        #     c_zr = c_double(0.0)
        #     tango.LSX_SetDigJoySpeed(self.LSID, c_xs, c_ys, c_zr, c_zr)

    ## joystickOnOff
    #
    # @param on True/False enable/disable the joystick.
    #
    def joystickOnOff(self, on):
        pass
        # No joystick used

    ## lockout
    #
    # Calls joystickOnOff.
    #
    # @param flag True/False.
    #
    def lockout(self, flag):
        pass
        # self.joystickOnOff(not flag)

            

    ## setVelocity
    #
    # FIXME: figure out how to set velocity..
    #
    def setVelocity(self, x_vel, y_vel):
        pass

    ## shutDown
    #
    # Disconnect from the stage.
    #
    def shutDown(self):
        # Disconnect from the stage
        if self.good:
            self.pidevice.StopAll(noraise=True)
            # pitools.waitonready(self.pidevice)  # there are controllers that need some time to halt all axes

    ## zero
    #
    # Set the current position as the new zero position.
    #
    def zero(self):
        pass
        # if self.good:
        #     pitools._ref_with_pos(self, self.pidevice.axes([0,1])) # added axes [0,1], not sure this ever worked anyway



# stage_n565 = piE861()
# stage_n565.goAbsolute(-1.5)
# time.sleep(1)
# print(stage_n565.position())
# stage_n565.goRelative(3)
# print(stage_n565.position())
