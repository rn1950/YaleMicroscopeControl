# https://github.com/python-microscopy/python-microscopy/blob/68b228a103f51f5069d38733a24ebd2462b82beb/PYME/Acquire/Hardware/ids_peak_cam.py#L31
# Most code taken from pyme acquire 


# It seems like IDS used to have this library called pyUeye 
# Now, it seems like they recommend using uEye cameras with IDS Peak (their new SDK)
# Make sure to install IDS peak and the IDS software suite from their website
# During the installation of IDS peak, there will be a checkbox for using uEye camera (not checked by default)
# Make sure to check this box!


from ids_peak import ids_peak as peak
peak.Library.Close()

peak.Library.Initialize()
device_manager = peak.DeviceManager.Instance()
device_manager.Update()
devices = device_manager.Devices()
print(len(devices))

if len(devices) == 0:
    raise RuntimeError('No IDS peak cameras found')

device_number = 0
device = devices[device_number].OpenDevice(peak.DeviceAccessType_Control)
serial_number = device.SerialNumber()
model_name = device.ModelName()
print(f'IDS peak camera {model_name} opened, serial number {serial_number}')




# get the remote device 'node map'
_node_map = device.RemoteDevice().NodeMaps()[0]

# open a datastream
# _data_stream = device.DataStreams()[0]


# _data_stream = device.DataStreams()[0].OpenDataStream()
# _data_stream_node_map = _data_stream.NodeMaps()[0]
# # set to FIFO
# _data_stream_node_map.FindNode("StreamBufferHandlingMode").SetCurrentEntry("OldestFirst")

# set ROI size to full usable sensor size ---------------------
# get min offsets. Note that some IDS cameras do not use the full chip.
_offset_x_min = _node_map.FindNode("OffsetX").Minimum()
_offset_y_min = _node_map.FindNode("OffsetY").Minimum()
_offset_x_max = _node_map.FindNode("OffsetX").Maximum()
_offset_y_max = _node_map.FindNode("OffsetY").Maximum()
_width_min = _node_map.FindNode("Width").Minimum()
_height_min = _node_map.FindNode("Height").Minimum()
_width_max = _node_map.FindNode("Width").Maximum()
_height_max = _node_map.FindNode("Height").Maximum()
_width_increment = _node_map.FindNode("Width").Increment()
_height_increment = _node_map.FindNode("Height").Increment()


# set ROI to full sensor size:
_node_map.FindNode("OffsetX").SetValue(_offset_x_min)
_node_map.FindNode("OffsetY").SetValue(_offset_y_min)
_node_map.FindNode("Width").SetValue(_width_max)
_node_map.FindNode("Height").SetValue(_height_max)



_node_map.FindNode("TriggerSelector").SetCurrentEntry("ExposureStart")
_node_map.FindNode("TriggerSource").SetCurrentEntry("Software")
_node_map.FindNode("TriggerMode").SetCurrentEntry("On")



datastream = device.DataStreams()[0].OpenDataStream()
payload_size = _node_map.FindNode("PayloadSize").Value()
for i in range(datastream.NumBuffersAnnouncedMinRequired()):
    buffer = datastream.AllocAndAnnounceBuffer(payload_size)
    datastream.QueueBuffer(buffer)
    
datastream.StartAcquisition()
_node_map.FindNode("AcquisitionStart").Execute()
_node_map.FindNode("AcquisitionStart").WaitUntilDone()

_node_map.FindNode("ExposureTime").SetValue(19000)



# _data_stream.StartAcquisition(peak.AcquisitionStartMode_Default,
#                         peak.DataStream.INFINITE_NUMBER)

# _node_map.FindNode('TLParamsLocked').SetValue(1)
# _node_map.FindNode('AcquisitionStart').Execute()






_node_map.FindNode("TriggerSoftware").Execute()
buffer = datastream.WaitForFinishedBuffer(1000)

# convert to RGB
import ids_peak_ipl.ids_peak_ipl as ids_ipl
import ids_peak.ids_peak_ipl_extension as ids_ipl_extension
raw_image = ids_ipl_extension.BufferToImage(buffer)
color_image = raw_image.ConvertTo(ids_ipl.PixelFormatName_RGB8)
datastream.QueueBuffer(buffer)

import numpy as np
picture = color_image.get_numpy_3D()

# display the image
from matplotlib import pyplot as plt
plt.figure(figsize = (15,15))
plt.imshow(picture)

plt.savefig('testplot.png')


print('made it here')


















peak.Library.Close()