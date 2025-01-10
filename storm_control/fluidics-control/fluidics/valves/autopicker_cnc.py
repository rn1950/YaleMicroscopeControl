import usb
import crccheck
from valves.autopicker import MockAutopicker
import valves.cnc_commands as cnc_commands
# import autopicker

# class CNC(autopicker.MockAutopicker):
class CNC(MockAutopicker):
    def __init__(self, idVendor=0x2121, idProduct=0x2130, configuration=(0,0)):
        self.status = ("Initializing", False)
        # self.dev = usb.core.find(idVendor=idVendor, idProduct=idProduct)
        import usb.backend.libusb0
        backend = usb.backend.libusb0.get_backend(find_library=lambda x: r'./windows_dll/libusb0.dll')
        self.dev = usb.core.find(idVendor=idVendor, idProduct=idProduct, backend=backend)
        if self.dev:
            self.dev.set_configuration()
            self.cfg = self.dev.get_active_configuration()
            self.inf = self.cfg[configuration]
            self.endpoint_out = usb.util.find_descriptor(self.inf, custom_match = lambda e: usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_OUT)
            self.endpoint_in = usb.util.find_descriptor(self.inf, custom_match = lambda e: usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_IN)
            self.send(cnc_commands.cmd_init_1())
            self.send(cnc_commands.cmd_init_2())
            self.send(cnc_commands.cmd_init_3())
            self.send(cnc_commands.cmd_init_4())
            self.send(cnc_commands.cmd_init_5())
            self.send(cnc_commands.cmd_init_6())
            self.send(cnc_commands.cmd_init_7())
            self.send(cnc_commands.cmd_init_8())
            self.send(cnc_commands.cmd_init_9())
            self.send(cnc_commands.cmd_init_10())
            self.restore_config(r"./valves/VWR_Plate_Lid.json")

        else:
            raise Exception("Can't find device with vendor %0d and product %0d!" % (idVendor, idProduct))

    def send(self, msg):
        assert len(msg) == 64
        #output = crccheck.crc.Crc8DvbS2.calc(map(ord, msg[:-1])) == ord(msg[-1])  # python2 version 
        output = crccheck.crc.Crc8DvbS2.calc(list(msg[:-1])) == msg[-1]
        assert output
        self.endpoint_out.write(msg)
        return self.receive()

    def receive(self):
        return cnc_commands.parse_reply(self.endpoint_in.read(64))

    def coords(self, add_offset=True):
        received = self.receive()
        return (received["x"], received["y"], received["z"])

    def set(self, position = (0, 0, 0)):  # required
        current_position = self.coords()
        
        if position[0] is None:
            position = (current_position[0],current_position[1],-180) # changed -60 to -180
        print(position)
        self.send(cnc_commands.cmd_set_offset(current_position[0]-position[0], current_position[1]-position[1], current_position[2]-position[2]))
        self.wait()

        self.send(cnc_commands.cmd_zero())
        self.wait()

        self.send(cnc_commands.cmd_set_offset(position[0], position[1], position[2]))
        self.wait()

        return self.coords()

    def wait(self):
        while self.receive()["busy"]:
            pass
