import crccheck
import struct

def cmd_int(value):
    '''In python2 it was necessary to apply ord to the outpur of struct.pack to get the integer representation instead of unicode. In python3, struct.pack gives integers by default not unicode.  so in place of `map(ord,stuff)` just use list(stuff)
    see here: https://stackoverflow.com/questions/45269456/understanding-struct-pack-in-python-2-7-and-3-5
    original command:
    `return map(ord, struct.pack("i", int(value)))`
    new command:
    
    '''
    output = list(struct.pack("i", int(value)))
    return output
    
def cmd_checksum(cmd):
    return crccheck.crc.Crc8DvbS2.calc(cmd)

def cmd_append_checksum(cmd):
    if len(cmd) < 63:
        cmd += [0] * (63 - len(cmd))
    return cmd_to_binary(cmd + [cmd_checksum(cmd)])

def cmd_speed(speed):
    rate = (460780 * 2000/speed)
    integral = cmd_int(rate)
    beginning_part = [0xBF, 0, 0, 0, 0x80, 0]
    return cmd_append_checksum(beginning_part + integral * 3)

def cmd_init_1(speed = 200):
    integral = cmd_int(speed)
    beginning_part = [0x9F, 0, 0, 0, 0x80, 0xB0]
    return cmd_append_checksum(beginning_part + integral * 4)

def cmd_init_2():
    beginning_part = [0xA0, 0, 0, 0, 0x80, 0x92]
    cmd_channel = [0x9f, 0x8C, 0x00, 0x00] * 4
    cmd_gap = [0x00] * 20
    cmd_something = [0x60, 0x09, 0x00, 0x00]
    cmd_rest = [0x00] * 10 + [0x00, 0xff, 0x01, 0x00]
    return cmd_append_checksum(beginning_part + cmd_channel + cmd_gap + cmd_something + cmd_rest)

def cmd_init_3():
    integral = cmd_int(18)
    beginning_part = [0xA1, 0, 0, 0, 0x80, 0x00]
    return cmd_append_checksum(beginning_part + integral * 4)

def cmd_init_4():
    integral = [0x00, 0x10, 0x0E, 0x00] #cmd_int(33)
    beginning_part = [0xBF, 0, 0, 0, 0x80, 0x00]
    return cmd_append_checksum(beginning_part + integral * 4)

def cmd_init_5():
    beginning_part = [0xB5, 0, 0, 0, 0x80, 0x01, 0x01, 0x00, 0x00, 0x00, 0xff, 0xff, 0x04]
    return cmd_append_checksum(beginning_part)

def cmd_init_6():
    beginning_part = [0xB6, 0, 0, 0, 0x80, 0x01, 0x02, 0x01, 0x03]
    return cmd_append_checksum(beginning_part)

def cmd_init_7():
    beginning_part = [0xC2, 0, 0, 0, 0x80, 0x01]
    return cmd_append_checksum(beginning_part)

def cmd_init_8():
    beginning_part = [0x9D, 0, 0, 0, 0x80, 0x01]
    return cmd_append_checksum(beginning_part)

def cmd_init_9():
    beginning_part = [0x9E, 0, 0, 0, 0x80, 0x00]
    return cmd_append_checksum(beginning_part)

def cmd_init_10():
    beginning_part = [0x9E, 0, 0, 0, 0x80, 0x00]
    return cmd_append_checksum(beginning_part)

def cmd_zero(speed):
    rate = (460780 * 2000/speed)
    integral = cmd_int(rate)
    beginning_part = [0xBF, 0, 0, 0, 0x80, 0]
    return cmd_append_checksum(beginning_part + integral * 3)

def parse_reply(msg):
    x, y, z = struct.unpack("iii", msg[24:36])
    return {"x": x*0.05, "y": y*0.05, "z": z*0.05, "busy": msg[1] == 0x0D, "zeroed": msg[24] == 0x13}

def cmd_mill():
    return cmd_append_checksum([0xAB, 0, 0, 0, 0x80, 0])

def cmd_stop():
    return cmd_append_checksum([0xAA, 0, 0, 0, 0x80, 0])

def cmd_zero():
    return cmd_append_checksum([0xCA, 0, 0, 0, 0, 0x39])

def cmd_zero_xy():
    return cmd_append_checksum([0xCA, 0, 0, 0, 0, 0x39] + [0] * 37 + [0x23, 0x07])

def cmd_pos_slow(x=0, y=0, z=0):
    return cmd_append_checksum([0xCA, 0, 0, 0, 0, 0x39] + cmd_int(x/0.05) + cmd_int(y/0.05) + cmd_int(z/0.05) + [0] * 26 + [0x08, 0x07])

def cmd_pos_fast(x=0, y=0, z=0):
    return cmd_append_checksum([0xCA, 0, 0, 0, 0, 0x39] + cmd_int(x/0.05) + cmd_int(y/0.05) + cmd_int(z/0.05) + [0] * 26 + [0xA4, 0x07])
#     that second-to-last byte seems uninterpreted so far.

def cmd_move(dir="none", step=False):
    dirs = {"right": 0x01, "left": 0x02, "back": 0x04, "forward": 0x08, "up": 0x10, "down": 0x20, "none": 0, "stop": 0}
    return cmd_append_checksum([0xBE, 0, 0, 0, 0x80, 1 if step else 0] + [dirs[dir]] + [0, 0, 0, 0x10, 0x0E] + [0] * 10 + [0x14 if step else 0])

def cmd_set_offset(x=0, y=0, z=0):
    return cmd_append_checksum([0xC8, 0, 0, 0, 0, 0] + cmd_int(x/0.05) + cmd_int(y/0.05) + cmd_int(z/0.05))

def cmd_to_binary(cmd):
    assert len(cmd) == 64
    assert max(cmd) < 256
    return struct.pack("B" * 64, *[c for c in cmd])

def cmd_spindle_on():
    return cmd_append_checksum([0xB5, 0, 0, 0, 0x80, 0x02, 0x01, 0, 0, 0, 0x5F, 0xF0])

def cmd_spindle_off():
    return cmd_append_checksum([0xB5, 0, 0, 0, 0x80, 0x01, 0x01, 0, 0, 0, 0x5F, 0xF0])
