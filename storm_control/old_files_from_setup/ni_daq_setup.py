from PyDAQmx import Task
import PyDAQmx
import numpy as np
import ctypes


data = np.array([1,0,0,0,1,1,0,1,0], dtype=np.uint8)

task = Task()
task.CreateDOChan("/Dev1/port0/line2","", PyDAQmx.DAQmx_Val_ChanPerLine)
# /Dev1/PFI0
task.CfgSampClkTiming(None,
                    1,
                    PyDAQmx.DAQmx_Val_Rising,
                    PyDAQmx.Val_ContSamps,
                    200)
# task.StartTask()
c_samples_written = ctypes.c_long(0)

task.WriteDigitalLines(data.size,1,-1,PyDAQmx.DAQmx_Val_GroupByChannel,data,ctypes.byref(c_samples_written),None)

# print(c_samples_written)

task.WaitUntilTaskDone(10)







# import nidaqmx
# from nidaqmx.constants import LineGrouping
# import time

# with nidaqmx.Task() as task:
#     data = [[False, False],
#             [True, False]]
    

#     task.do_channels.add_do_chan("Dev1/port0/line0:1", line_grouping=LineGrouping.CHAN_PER_LINE)
#     task.start()
#     task.write(data)

#     time.sleep(10)
#     task.stop()
    
    
    
#     # task.ai_channels.add_ai_voltage_chan("Dev1/ai1")
#     # print(task.read())