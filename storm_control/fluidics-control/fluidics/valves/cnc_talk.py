import usb
import crccheck
import time
import sys
import numpy
import json
import math

import matplotlib.tri

import valves.cnc_commands



# >>>
# >>> c
# <__main__.CNC object at 0x0000000002C28438>
# >>> c.set((1300, 900, 0))
# (1300.0, 900.0, 0.0)
# >>> c.plates[0]
# <__main__.Plate object at 0x00000000045D98D0>
# >>> c.plates[0].height
# -60.0
# >>> c.plates[0].record_height()
# >>> c.plates[0].height
# 0.0
# >>> p = Plate(c)
# >>> p
# <__main__.Plate object at 0x00000000045D9828>
# >>> p.record_well()
# >>>  c.set((1300, 900, 0))
# File "<stdin>", line 1
 # c.set((1300, 900, 0))

# IndentationError: unexpected indent
# >>> c.coords()
# (1300.0, 900.0, 0.0)
# >>> c.set((1300, 900, -60))
# (1300.0, 900.0, -60.0)
# >>> p.record_height()
# >>> p.move()
# >>> p.home()
# >>> c.register_plate(p)
# >>> c.write(



def calculate_distance(start, end):
    dist = 0
    if start[0] is not None and end[0] is not None:
        dist += (start[0] - end[0])**2
    if start[1] is not None and end[1] is not None:
        dist += (start[1] - end[1])**2
    if start[2] is not None and end[2] is not None:
        dist += (start[2] - end[2])**2
    return math.sqrt(dist)

def max_distance_fix(positions, max_distance=1000):
    out_positions = []
    current_position = list(positions[0])

    for end in positions[1:]:
        d = calculate_distance(current_position, end)

        if d > max_distance:
            parts = int(math.ceil(d/max_distance))
            delta = [x - y if x is not None and y is not None else 0 for x, y in zip(end, current_position)]
            for p in range(parts):
                out_positions.append([c + d * (p+1)/float(parts) for d, c in zip(delta, current_position)])
        else:
            out_positions.append(end)

        if end[0] is not None:
            current_position[0] = end[0]
        if end[1] is not None:
            current_position[1] = end[1]
        if end[2] is not None:
            current_position[2] = end[2]

    return out_positions


class MockCNC(object):
    def __init__(self, plates=2, plate_shape=(12, 8),com_port=0):
        self.position = [0, 0, 0]
        self.plates = range(plates)
        self.plate_shape = plate_shape
        self.status = ("Initializing", True)
        self.wells = []
        self.restore_config(r"./valves/VWR_Plate_Lid.json")


    def step_through(self, positions):
        position = list(self.coords())
        for p in max_distance_fix([position] + positions):
            self.set(p)

    def coords(self, add_offset=True):
        print("MockCNC queried for position = ", self.position)
        return self.position

    def set(self, position):
        print("MockCNC setting position to", position)
        self.position = list(position)

    def move(self, port, direction):
        if isinstance(port, tuple):
            plate_name, port = port
            named_right = [p for p in self.plates if p.name == plate_name]
            plate = named_right[0]
        else:
            plate = self.plates[direction]

        plate.move(*map(int, self.wells[port].split()[1:]))
        self.wait()
        self.status = ("%s %s" % (plate.name, self.wells[port]), False)

    def get_wells(self):
        self.wells = []
        for plate in self.plates:
            for well in plate.locations():
                self.wells.append("Well %d %d" % (well[0], well[1]))
        return self.wells

    def get_plates(self):
        return [p.name for p in self.plates]

    def get_status(self):
        return self.status

    def get_configuration(self):
        return " ".join(self.get_plates())

    def close(self):
        pass

    def wait(self):
        pass

    def register_plate(self, plate):
        self.plates.append(plate)

    def write_config(self, path):
        with open(path, "w") as output_file:
            json.dump([p.save() for p in self.plates], output_file)
    
    def restore_config(self, path):
        with open(path) as input_file:
            self.plates = [Plate(self, plate) for plate in json.load(input_file)]


class CNC(MockCNC):
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
        assert crccheck.crc.Crc8DvbS2.calc(map(ord, msg[:-1])) == ord(msg[-1])
        self.endpoint_out.write(msg)
        return self.receive()

    def receive(self):
        return cnc_commands.parse_reply(self.endpoint_in.read(64))

    def coords(self, add_offset=True):
        received = self.receive()
        return (received["x"], received["y"], received["z"])

    def set(self, position = (0, 0, 0)):
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


class Plate(object):
    """This represents a container with edges (e.g. 96 well plate) you want to pick on."""
    def __init__(self, cnc=None, config={}):
        self.cnc = cnc
        self.name = config["name"] if "name"  in config else ""
        self.height = config["height"] if "height" in config else None
        self.positions = config["positions"] if "positions" in config else []
        if len(self.positions) > 2:
            self.freeze()
        else:
            self.triangulation = None
            self.interpolation = None

    def set_cnc(self, cnc):
        self.cnc = cnc

    def record_well(self, x = 0, y = 0):
        """Record the position of a single well for interpolation."""
        self.positions.append((x, y, self.cnc.coords(add_offset=True)))

    def record_height(self):
        """Go up to the current z height from now on when exiting wells."""
        self.height = self.cnc.coords(add_offset=True)[2]

    def freeze(self):
        """This takes the x, y, and z positions and solves the linear equations for positioning."""
        if len(self.positions) > 2:
            point = [p[:2] for p in self.positions]
            point_x, point_y = zip(*point)

            coords = [p[2] for p in self.positions]

            self.triangulation = matplotlib.tri.Triangulation(point_x, point_y)
            self.interpolation = [matplotlib.tri.LinearTriInterpolator(self.triangulation, coord) for coord in zip(*coords)]
            #self.interpolation = [matplotlib.tri.CubicTriInterpolator(self.triangulation, coord) for coord in zip(*coords)]
        else:
            raise Exception("Can't freeze positions with two or fewer!")
        
    def find_position(self, x=0, y=0):
        if len(self.positions) == 1:
            return numpy.array(self.positions[0][2])
        elif len(self.positions) > 2:
            if self.interpolation is None:
                print("Interpolator undefined, attempting to freeze positions matrix...")
                self.freeze()
            return numpy.array([interp(x, y) for interp in self.interpolation])
        else:
            # In theory you could support interpolation here
            raise Exception( "Can't find position if there are exactly two!")

    def move(self, x=0, y=0):
        target_position = self.find_position(x, y)
        self.cnc.step_through([(None, None, self.height), (target_position[0], target_position[1], self.height), target_position])

    def home(self):
        """Home is above the first well."""
        target_position = self.find_position(0, 0)
        self.cnc.step_through([(None, None, self.height), (target_position[0], target_position[1], self.height)])

    def save(self):
        return {"height": self.height, "positions": self.positions, "name": self.name}

    def locations(self):
        locations = []
        for i in range(0, 12):
            for j in range(0, 8):
                locations.append((i, j))
        return locations
