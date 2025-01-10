import PyDAQmx
import numpy
import ctypes
import threading

timeout = -1

class NIDAQTask(PyDAQmx.Task):
    """
    A thin wrapper on PyDAQmx because we think that we need
    thread locks, and we also want to get NI status errors.
    """

    def __init__(self, **kwds):
            super().__init__(**kwds)

    def clearTask(self):
            super().ClearTask()

    def startTask(self):
            super().StartTask()

    def stopTask(self):
            super().StopTask()

    def taskIsDone(self):
        done = ctypes.c_long(0)
        self.IsTaskDone(ctypes.byref(done))
        return done.value

class DigitalWaveformOutput(NIDAQTask):
    """
    Digital waveform output class.
    """
    def __init__(self, source = None, **kwds):
        super().__init__(**kwds)
        self.channels = 1
        self.CreateDOChan(source,
                            "",
                            PyDAQmx.DAQmx_Val_ChanPerLine)
            
    def addChannel(self, source = None):
        """
        Add a channel to the task. I'm pretty sure that the channels have to be added
        sequentially in order of increasing line number (at least on the same board).
        """
        self.channels += 1
        self.CreateDOChan(source,
                            "",
                            PyDAQmx.DAQmx_Val_ChanPerLine)
            
    def setWaveforms(self, waveforms = None, sample_rate = None, clock = None, finite = False, rising = True):
        """
        The output waveforms for all the digital channels are expected
        to be a list of equal length numpy arrays of type numpy.uint8.

        You need to add all your channels first before calling this.
        """
        assert isinstance(waveforms, list)
        assert isinstance(waveforms[0], numpy.ndarray)
        assert (waveforms[0].dtype == numpy.uint8)

        waveform_len = waveforms[0].size

        # Set the timing for the waveform.
        if finite:
            sample_mode = PyDAQmx.DAQmx_Val_FiniteSamps
        else:
            sample_mode = PyDAQmx.DAQmx_Val_ContSamps
        
        if rising:
            rising = PyDAQmx.DAQmx_Val_Rising
        else:
            rising = PyDAQmx.DAQmx_Val_Falling
        
        # https://www.ni.com/docs/en-US/bundle/ni-daqmx-c-api-ref/page/daqmxcfunc/daqmxcfgsampclktiming.html
        print(waveform_len)
        self.CfgSampClkTiming(clock,
                                sample_rate,
                                rising,
                                sample_mode,
                                waveform_len)

        # Transfer the waveform data to the DAQ board buffer.
        waveform = numpy.ascontiguousarray(numpy.concatenate(waveforms), dtype = numpy.uint8)
        c_samples_written = ctypes.c_long(0)

        # hopefully corresponds directly to the NI C documentation
        # https://www.ni.com/docs/en-US/bundle/ni-daqmx-c-api-ref/page/daqmxcfunc/daqmxwritedigitallines.html 
        self.WriteDigitalLines(waveform_len,
                                1,
                                timeout,
                                PyDAQmx.DAQmx_Val_GroupByChannel,
                                waveform,
                                ctypes.byref(c_samples_written),
                                None)
        
        
        print(c_samples_written.value)

        if (c_samples_written.value != waveform_len):
            msg = "Failed to write the right number of samples "
            msg += str(c_samples_written.value) + " " + str(waveform_len)
            breakpoint()





dwo = DigitalWaveformOutput(source='Dev1/port0/line0:1')
# 
# dwo.addChannel(source='Dev1/port0/line0')
# dwo.addChannel(source='Dev1/port0/line1')
waveform = [numpy.array([1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 1, 1, 0, 1], dtype = numpy.uint8), numpy.array([1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0], dtype = numpy.uint8)]

dwo.setWaveforms(waveforms=waveform, sample_rate=100, clock = None, finite = False, rising = True)