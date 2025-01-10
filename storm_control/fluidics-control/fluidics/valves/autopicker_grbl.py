import ctypes
import serial 
import time
from valves.cnc_talk import MockCNC
#import cnc_talk

# class XYZ(cnc_talk.MockCNC):
class GRBL(MockCNC):  # see cnc_talk.MockCNC
    def __init__(self,
                 com_port = "COM4",
                 config=r"./valves/XYZ_layout.json",
                 parameters = False):

        # Define attributes
        self.status = ("Initializing", False)
        self.com_port = com_port # COM port (see Device Manager)
        self.restore_config(config) #  plate configuration
        
        # Create serial port
        self.serial = serial.Serial(port = self.com_port, baudrate = 115200) # GRBL operates at 115200 baud

        # Define initial valve status
        self.xpos = 'X0'
        self.ypos = 'Y0'
        self.zpos = 'Z0'
        self.position = (self.xpos,self.ypos,self.zpos)
        self.feedspeed = 'F2000'
        # wake up grbl, homing and set the home position zero
        self.wakeUp()

    # Wake up grbl
    def wakeUp(self):
        self.sendCommand('\r\n\r\n')
        time.sleep(2)   # Wait for grbl to initialize
        self.serial.flushInput()  # Flush startup text in serial input
        print('MESSAGE -- GRBL woke up.')
        self.sendCommand('$H') # homing
        self.sendCommand('G92 X0 Y0 Z0') # set current position 0
        print('MESSAGE -- Homing is done. Ready to send commands.')
        self.xpos = 'X0'
        self.ypos = 'Y0'
        self.zpos = 'Z0'
        self.position = (0,0,0)
        # may not need this
        # self.current_position = (0,0,0)      

    def moveXY(self,newx,newy):
        command = 'G01 '+newx+' '+newy+' '+self.feedspeed
        self.sendCommand(command)
        self.xpos = newx
        self.ypos = newy
            # self.current_position = (self.current_position[0]+newx,slef.current_position[1]+newy,0)  # it looks like this has absolute position

    def needleUp(self):
        # command = 'G01 '+self.xpos+' '+self.ypos+' '+'Z0'+' '+self.feedspeed
        self.sendCommand('G01 Z0')
        self.zpos = 'Z0'

    def needleDown(self):
        self.sendCommand('G01 Z-37')
        self.zpos = 'Z-37'

    def wait(self,waitingtime=1):
        command = 'G04 P'+str(waitingtime)
        self.sendCommand(command)
        return True

    # Stream g-code to grbl
    def sendCommand(self,command):
        line = command+'\n'
        print('Sending: ' + command)
        self.serial.write(line.encode()) # Send g-code block to grbl
        res = self.getResponse()
        return res

    def getResponse(self):
        grbl_out = self.serial.readline() # Wait for grbl response with carriage return
        return grbl_out.strip().decode()

    def set(self, position = (0, 0, 0)):
        if position[0] is not None:
            print('setting position')
            print(position)
            newX = 'X'+str(position[0])
            newY = 'Y'+str(position[1])
            if self.xpos == newX and self.ypos == newY:  # we only stop down anyway
                pass
                # print('aready here')
            else:
                self.needleUp()  # if we remove this, it doesn't bounce
                self.moveXY(newX,newY)
                self.needleDown()
                # self.position = position
        
        # return position #  self.coords()  # it looks like this keeps track of absolute position  