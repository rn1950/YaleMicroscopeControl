import ctypes
from valves.cnc_talk import MockCNC
#import cnc_talk

# class XYZ(cnc_talk.MockCNC):
class XYZ(MockCNC):
    def __init__(self, device=b"/dev/ttyACM0", config=r"./valves/XYZ_layout.json"):   # changed device="/dev/ttyACM0",  to device=b"/dev/serial" for python3
    # def __init__(self, device="/dev/ttyACM0", config=r"./valves/VWR_Plate_Lid.json"):
        self.status = ("Initializing", False)
        self.mm = ctypes.CDLL("./libminimover.so")
        self.device = device
        self.restore_config(config) #  plate configuration
        print('sending home')
        self.home()  # doesn't actually home 

    def home(self):
        self.mm._Z4homePc(ctypes.c_char_p(self.device))
        self.current_position = (0,0,0)
        print(self.current_position)
        print(self.device)

    def jog(self, x=0, y=0, z=0):
        self.mm._Z3jogPciii(ctypes.c_char_p(self.device), ctypes.c_int(x), ctypes.c_int(y), ctypes.c_int(z))

        self.current_position = (self.current_position[0] + x, self.current_position[1] + y, self.current_position[2] + z)

    def coords(self, add_offset=True):
        return self.current_position

    def set(self, position = (0, 0, 0)):

        if position[0] is None:
            position = (self.current_position[0],position[1], position[2])
        if position[1] is None:
            position = (position[0],self.current_position[1], position[2])
        if position[2] is None:
            position = (position[0],position[1], self.current_position[2])

        # Unfortunately this easy interface to the XYZ only supports integer mm :(
        offset = (int(position[0] - self.current_position[0]),
                  int(position[1] - self.current_position[1]),
                  int(position[2] - self.current_position[2]))

        self.jog(*offset)

        return self.coords()

    def wait(self):
        self.mm._Z4waitPc(ctypes.c_char_p(self.device))
