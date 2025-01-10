import PyDAQmx
import numpy
import ctypes
import threading
from PyDAQmx.DAQmxTypes import *


class NIDAQTask(PyDAQmx.Task):
    """
    A thin wrapper on PyDAQmx because we think that we need
    thread locks, and we also want to get NI status errors.
    """

    def __init__(self, **kwds):
        with getLock():
            super().__init__(**kwds)

    def clearTask(self):
        with getLock():
            super().ClearTask()

    def startTask(self):
        with getLock():
            super().StartTask()

    def stopTask(self):
        with getLock():
            super().StopTask()

    def taskIsDone(self):
        done = ctypes.c_long(0)
        with getLock():
            self.IsTaskDone(ctypes.byref(done))
        return done.value




class DigitalOutput(PyDAQmx.Task):
    """
    Digital output task (for simple non-triggered digital output).
    """
    def __init__(self, source = None, **kwds):

    # task = Task()
    # task.CreateDOChan("/TestDevice/port0/line0:7","",PyDAQmx.DAQmx_Val_ChanForAllLines)
        from PyDAQmx import Task
        data = numpy.array([0,1,1,0,1,0,1,0], dtype=numpy.uint8)
        task = Task()
        task.CreateDOChan("/Dev1/port0/line0:7","", PyDAQmx.DAQmx_Val_ChanForAllLines)
        task.StartTask()
        task.WriteDigitalLines(1,1,10.0,PyDAQmx.DAQmx_Val_GroupByChannel,data,None,None)
        task.StopTask()
        print(source)

        super().CreateDOChan("/Dev1/port0/line0:7","", PyDAQmx.DAQmx_Val_ChanForAllLines)
        # super.CreateDOChan(source, "", PyDAQmx.DAQmx_Val_ChanPerLine)

    def output(self, state = None):
        if bool(state):
            data = numpy.array([1], dtype = numpy.uint8)
        else:
            data = numpy.array([0], dtype = numpy.uint8)

        c_written = ctypes.c_int32(0)

        self.WriteDigitalLines(1,
                                1,
                                timeout,
                                PyDAQmx.DAQmx_Val_GroupByChannel,
                                data,
                                ctypes.byref(c_written),
                                None)



daqoutput = DigitalOutput(source='Dev1/port0/line0:1')
