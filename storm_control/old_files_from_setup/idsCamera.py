import ctypes.wintypes
from ids_peak import ids_peak as peak
import ids_peak_ipl.ids_peak_ipl as ids_ipl
import ids_peak.ids_peak_ipl_extension as ids_ipl_extension
import threading
import time
import queue
import numpy as np

Handle = ctypes.wintypes.HANDLE


import storm_control.sc_library.hdebug as hdebug

# Import fitting libraries.

# Numpy fitter, this should always be available.
import storm_control.sc_hardware.utility.np_lock_peak_finder as npLPF

# Finding/fitting using the storm-analysis project.
saLPF = None
try:
    import storm_control.sc_hardware.utility.sa_lock_peak_finder as saLPF
except ModuleNotFoundError as mnfe:
    print(">> Warning! Storm analysis lock fitting module not found. <<")
    print(mnfe)
    pass

# Finding using the storm-analysis project, fitting using image correlation.
cl2DG = None
try:
    import storm_control.sc_hardware.utility.corr_lock_c2dg as cl2DG
except ModuleNotFoundError as mnfe:
    # Only need one warning about the lack of storm-analysis.
    pass
except OSError as ose:
    print(">> Warning! Correlation lock fitting C library not found. <<")
    print(ose)
    pass




class Camera():
    # def __init__(self, camera_id, ini_file = "idsCamera_settings.ini"):
    def __init__(self):
        # super().__init__(camera_id)
        self.nbits = 8
        self.n_full = 0
        peak.Library.Initialize()
        self.device_manager = peak.DeviceManager.Instance()
        self.device_manager.Update()
        self.devices = self.device_manager.Devices()
        print(len(self.devices))

        if len(self.devices) == 0:
            raise RuntimeError('No IDS peak cameras found')

        device_number = 0
        self.device = self.devices[device_number].OpenDevice(peak.DeviceAccessType_Control)
        serial_number = self.device.SerialNumber()
        model_name = self.device.ModelName()
        print(f'IDS peak camera {model_name} opened, serial number {serial_number}')

        # get the remote device 'node map'
        self._node_map = self.device.RemoteDevice().NodeMaps()[0]
        
        self._data_stream = self.device.DataStreams()[0].OpenDataStream()
        self._data_stream_node_map = self._data_stream.NodeMaps()[0]
        # set to FIFO
        self._data_stream_node_map.FindNode("StreamBufferHandlingMode").SetCurrentEntry("OldestFirst")


        _offset_x_min = self._node_map.FindNode("OffsetX").Minimum()
        _offset_y_min = self._node_map.FindNode("OffsetY").Minimum()
        _offset_x_max = self._node_map.FindNode("OffsetX").Maximum()
        _offset_y_max = self._node_map.FindNode("OffsetY").Maximum()
        _width_min = self._node_map.FindNode("Width").Minimum()
        _height_min = self._node_map.FindNode("Height").Minimum()
        _width_max = self._node_map.FindNode("Width").Maximum()
        _height_max = self._node_map.FindNode("Height").Maximum()
        _width_increment = self._node_map.FindNode("Width").Increment()
        _height_increment = self._node_map.FindNode("Height").Increment()
       # set ROI to full sensor size:
        self._node_map.FindNode("OffsetX").SetValue(_offset_x_min)
        self._node_map.FindNode("OffsetY").SetValue(_offset_y_min)
        self._node_map.FindNode("Width").SetValue(_width_max)
        self._node_map.FindNode("Height").SetValue(_height_max)
        # self._node_map.FindNode("TriggerSelector").SetCurrentEntry("ExposureStart")
        # self._node_map.FindNode("TriggerSource").SetCurrentEntry("Software")
        # self._node_map.FindNode("TriggerMode").SetCurrentEntry("On")

        self._buffer_poll_wait_time_ms = 500  # [ms]


        self.poll_thread = threading.Thread(target=self._poll_loop)
        self._poll = False
        self.poll_loop_active = True
        self.poll_thread.start()


        # self.setBuffers()

    def _poll_loop(self):
        while self.poll_loop_active:
            if self._poll: # only poll if an acquisition is running
                try:
                    self._poll_buffer()
                except Exception as e:
                    print(str(e))
            else:
                time.sleep(.05)
    
    def _poll_buffer(self):
        try:
            buffer = self._data_stream.WaitForFinishedBuffer(self._buffer_poll_wait_time_ms)
            # copy over
            ctypes.memmove(self.transfer_buffer, int(buffer.BasePtr()), int(buffer.Size()))
            arr = np.frombuffer(self.transfer_buffer, dtype=self.transfer_buffer_dtype)
            # return camera buffer to queue
            self._data_stream.QueueBuffer(buffer)
            arr = arr.reshape((self.curr_height, self.curr_width))
            self.full_buffers.put(arr)
            self.n_full += 1
        except Exception as e:
            print(f'Error polling buffer: {e}')

    

    def Close(self):
        self.StopAq()
        self.DestroyBuffers()
        peak.Library.Close()
    
    def DestroyBuffers(self):
        self.n_full = 0

        # remove camera-side buffers
        for b in self._data_stream.AnnouncedBuffers():
            try:
                self._data_stream.RevokeBuffer(b)
            except Exception as e:
                print(f'Error revoking buffer: {e}')
            
        # computer RAM: destroy free and full buffer queues
        while not self.full_buffers.empty():
            try:
                self.full_buffers.get_nowait()
            except queue.Empty:
                pass
        
        while not self.free_buffers.empty():
            try:
                self.free_buffers.get_nowait()
            except queue.Empty:
                pass
    
    def allocate_buffers(self, n_buffers=50):
        self._n_cam_buffers = n_buffers
        # camera side
        try:
            # self._data_stream.Flush(peak.DataStreamFlushMode_DiscardAll)
            # for b in self._data_stream.AnnouncedBuffers():
            #     self._data_stream.RevokeBuffer(b)
            # # get current payload size
            self._payload_size = self._node_map.FindNode('PayloadSize').Value()


            # allocate buffers
            for ind in range(n_buffers):
                b = self._data_stream.AllocAndAnnounceBuffer(self._payload_size)
                self._data_stream.QueueBuffer(b)
        except Exception as e:
            print(f'Error allocating buffers: {e}')
            raise e
        
        # computer RAM

        # transfer buffer
        if self.nbits == 8:
            bufferdtype = np.uint8
        else: # 10 & 12 bits
            bufferdtype = np.uint16
        
        self.curr_height, self.curr_width = self.GetPicHeight(), self.GetPicWidth()
        self.transfer_buffer_size = self.curr_height * self.curr_width * bufferdtype().itemsize
        self.transfer_buffer_dtype = bufferdtype
        self.transfer_buffer = ctypes.create_string_buffer(self.transfer_buffer_size)
        self.transfer_buffer_memory_v = ctypes.c_char()
        self.transfer_buffer_memory = ctypes.pointer(self.transfer_buffer_memory_v)
        self.transfer_buffer_id = ctypes.c_int()
        # others
        self.free_buffers = queue.Queue()
        self.full_buffers = queue.Queue()
        for ind in range(n_buffers):
            self.free_buffers.put(np.zeros((self.GetPicHeight(), self.GetPicWidth()), 
                                           dtype=np.uint16))
        self._poll = False
    
    def StopAq(self):
        self._poll = False
        try:
            # tell the camera to stop
            self._node_map.FindNode('AcquisitionStop').Execute()

            # stop the datastream
            self._data_stream.KillWait()  # interrupts 1 WaitForFinishedBuffer call
            self._data_stream.StopAcquisition(peak.AcquisitionStopMode_Default)
            # flush TODO - do we really want to flush immediately?
            self._data_stream.Flush(peak.DataStreamFlushMode_DiscardAll)

            # unlock parameters
            self._node_map.FindNode('TLParamsLocked').SetValue(0)
        except Exception as e:
            print(f'Error stopping acquisition: {e}')
            raise e
        self.DestroyBuffers()
    
    def StartExposure(self):
        print('StartAq')
        if self._poll:
            # stop, we'll allocate buffers and restart
            self.StopAq()
        # allocate at least 2 seconds of buffers
        buffer_size = int(max(2 * self.GetFPS(), 50))
        print('Allocating {} buffers'.format(buffer_size))
        self.allocate_buffers(buffer_size)

        print('StartAq', '')
        try:
            if True:
                # continuous acq only for now:
                self._data_stream.StartAcquisition(peak.AcquisitionStartMode_Default,
                                                peak.DataStream.INFINITE_NUMBER)
                print('made it here')
                self._node_map.FindNode('TLParamsLocked').SetValue(1)
                self._node_map.FindNode('AcquisitionStart').Execute()
            else:
                raise NotImplementedError('Single shot mode not implemented')
        except Exception as e:
            print(f'Error starting acquisition: {e}')
            raise e
        self._poll = True
        return 0
    
    def captureImage(self):
        return self.full_buffers.get()
    
    def GetIntegTime(self):
        """
        Get the current exposure time.

        Returns
        -------
        float
            The exposure time in s

        See Also
        --------
        SetIntegTime
        """
        exposure_time = self._node_map.FindNode("ExposureTime").Value()  # [us]
        return exposure_time / 1e6  # [s]
    
    def SetIntegTime(self, exposure_time):
        """
        Set the exposure time.

        Parameters
        ----------
        exposure_time : float
            The exposure time in s

        See Also
        --------
        GetIntegTime
        """
        # get acceptable range, in units of microseconds
        lower = self._node_map.FindNode("ExposureTime").Minimum()  # [us]
        upper = self._node_map.FindNode("ExposureTime").Maximum()  # [us]
        exp_time = np.clip(exposure_time * 1e6, lower, upper)  # [us]
        print(f'Setting exposure time to {exp_time} us')
        self._node_map.FindNode("ExposureTime").SetValue(exp_time)

    def GetPicWidth(self):
        """
        Returns the width (in pixels) of the currently selected ROI.

        Returns
        -------
        int
            Width of ROI (pixels)
        """
        x0, _, x1, _ = self.GetROI()
        return x1 - x0

    def GetPicHeight(self):
        """
        Returns the height (in pixels) of the currently selected ROI
        
        Returns
        -------
        int
            Height of ROI (pixels)
        """
        _, y0, _, y1 = self.GetROI()
        return y1 - y0

    def GetROI(self):
        """
        Returns the current ROI as a tuple of (x0, y0, x1, y1).

        Returns
        -------
        tuple
            (x0, y0, x1, y1)
        """
        x0 = self._node_map.FindNode("OffsetX").Value()
        y0 = self._node_map.FindNode("OffsetY").Value()
        x1 = x0 + self._node_map.FindNode("Width").Value()
        y1 = y0 + self._node_map.FindNode("Height").Value()
        return (x0, y0, x1, y1)
    

    def GetFPS(self):
        """
        Returns the current frame rate (in frames per second).

        Returns
        -------
        float
            Frame rate (fps)
        """
        return self._node_map.FindNode("AcquisitionFrameRate").Value()
    
    def SetAOI(self, x1, y1, x2, y2):
        """
        Set the ROI via coordinates (as opposed to via an index).

        Parameters
        ----------
        x1 : int
            Left x-coordinate, zero-indexed
        y1 : int
            Top y-coordinate, zero-indexed
        x2 : int
            Right x-coordinate, (excluded from ROI)
        y2 : int
            Bottom y-coordinate, (excluded from ROI)

        Returns
        -------
        None


        """
        print('setting ROI: %d, %d, %d, %d' % (x1, y1, x2, y2))
        x1 = int(np.clip(x1, self._offset_x_min, self._offset_x_max))
        y1 = int(np.clip(y1, self._offset_y_min, self._offset_y_max))
        x2 = int(np.clip(x2, x1 + self._width_min, self._width_max))
        y2 = int(np.clip(y2, y1 + self._height_min, self._height_max))
        x2 -= (x2 - x1) % self._width_increment  # ROI must be a multiple of increment
        y2 -= (y2 - y1) % self._height_increment
        print('adjusted ROI: %d, %d, %d, %d' % (x1, y1, x2, y2))

        self._node_map.FindNode("OffsetX").SetValue(x1)
        self._node_map.FindNode("OffsetY").SetValue(y1)
        self._node_map.FindNode("Width").SetValue(x2 - x1)
        self._node_map.FindNode("Height").SetValue(y2 - y1)
        # using ueye api we used to have to set integration time after adjusting
        # ROI. Not sure if we need that here or not. Leave it for not just in case.
        self.SetIntegTime(self.GetIntegTime())


#################################################################################

class CameraQPD(object):
    """
    QPD emulation class. The default camera ROI of 200x200 pixels.
    The focus lock is configured so that there are two laser spots on the camera.
    The distance between these spots is fit and the difference between this distance and the
    zero distance is returned as the focus lock offset. The maximum value of the camera
    pixels is returned as the focus lock sum.
    """
    def __init__(self,
                 allow_single_fits = False,
                 background = None,                 
                 camera_id = 1,
                 ini_file = None,
                 offset_file = None,
                 pixel_clock = None,
                 sigma = None,
                 x_width = None,
                 y_width = None,
                 **kwds):
        super().__init__(**kwds)

        self.allow_single_fits = allow_single_fits
        self.background = background
        self.fit_mode = 1
        self.fit_size = int(1.5 * sigma)
        self.image = None
        self.last_power = 0
        self.offset_file = offset_file
        self.sigma = sigma
        self.x_off1 = 0.0
        self.y_off1 = 0.0
        self.x_off2 = 0.0
        self.y_off2 = 0.0
        self.zero_dist = 0.5 * x_width

        # Add path information to files that should be in the same directory.
        # ini_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ini_file)

        # Open camera
        self.cam = Camera()

        # Set timeout
        # self.cam.setTimeout(1)

        # Set camera AOI x_start, y_start.
        with open(self.offset_file) as fp:
            [self.x_start, self.y_start] = map(int, fp.readline().split(",")[:2])

        # Set camera AOI.
        self.x_width = x_width
        self.y_width = y_width
        self.setAOI()

        # Run at maximum speed.
        # self.cam.setPixelClock(pixel_clock)
        # self.cam.setFrameRate(verbose = True)

        # Some derived parameters
        self.half_x = int(self.x_width/2)
        self.half_y = int(self.y_width/2)
        self.X = np.arange(self.y_width) - 0.5*float(self.y_width)

    def adjustAOI(self, dx, dy):
        # self.x_start += dx
        # self.y_start += dy
        # if(self.x_start < 0):
        #     self.x_start = 0
        # if(self.y_start < 0):
        #     self.y_start = 0
        # if((self.x_start + self.x_width + 2) > self.cam.info.nMaxWidth):
        #     self.x_start = self.cam.info.nMaxWidth - (self.x_width + 2)
        # if((self.y_start + self.y_width + 2) > self.cam.info.nMaxHeight):
        #     self.y_start = self.cam.info.nMaxHeight - (self.y_width + 2)
        self.setAOI()

    def adjustZeroDist(self, inc):
        self.zero_dist += inc

    def capture(self):
        """
        Get the next image from the camera.
        """
        self.image = self.cam.captureImage()
        return self.image

    def changeFitMode(self, mode):
        """
        mode 1 = gaussian fit, any other value = first moment calculation.
        """
        self.fit_mode = mode

    def doMoments(self, data):
        """
        Perform a moment based calculation of the distances.
        """
        self.x_off1 = 1.0e-6
        self.y_off1 = 0.0
        self.x_off2 = 1.0e-6
        self.y_off2 = 0.0

        total_good = 0
        data_band = data[self.half_y-15:self.half_y+15,:]

        # Moment for the object in the left half of the picture.
        x = np.arange(self.half_x)
        data_ave = np.average(data_band[:,:self.half_x], axis = 0)
        power1 = np.sum(data_ave)

        dist1 = 0.0
        if (power1 > 0.0):
            total_good += 1
            self.y_off1 = np.sum(x * data_ave) / power1 - self.half_x
            dist1 = abs(self.y_off1)

        # Moment for the object in the right half of the picture.
        data_ave = np.average(data_band[:,self.half_x:], axis = 0)
        power2 = np.sum(data_ave)

        dist2 = 0.0
        if (power2 > 0.0):
            total_good += 1
            self.y_off2 = np.sum(x * data_ave) / power2
            dist2 = abs(self.y_off2)

        # The moment calculation is too fast. This is to slow things
        # down so that (hopefully) the camera doesn't freeze up.
        time.sleep(0.02)
        
        return [total_good, dist1, dist2]

    def getImage(self):
        return [self.image, self.x_off1, self.y_off1, self.x_off2, self.y_off2, self.sigma]

    def getZeroDist(self):
        return self.zero_dist

    def qpdScan(self, reps = 4):
        """
        Returns [power, offset, is_good]
        """
        power_total = 0.0
        offset_total = 0.0
        good_total = 0.0
        for i in range(reps):
            [power, n_good, offset] = self.singleQpdScan()
            power_total += power
            good_total += n_good
            offset_total += offset
            
        power_total = power_total/float(reps)
        if (good_total > 0):
            return [power_total, offset_total/good_total, True]
        else:
            return [power_total, 0, False]

    def setAOI(self):
        """
        Set the camera AOI to current AOI.
        """
        self.cam.setAOI(100,
                        100,
                        500,
                        500)

    def shutDown(self):
        """
        Save the current camera AOI location and offset. Shutdown the camera.
        """
        if self.offset_file:
            with open(self.offset_file, "w") as fp:
                fp.write(str(self.x_start) + "," + str(self.y_start))
        self.cam.Close()

    def singleQpdScan(self):
        """
        Perform a single measurement of the focus lock offset and camera sum signal.
        Returns [power, total_good, offset]
        """
        data = self.capture().copy()

        # The power number is the sum over the camera AOI minus the background.
        power = np.sum(data.astype(np.int64)) - self.background
        
        # (Simple) Check for duplicate frames.
        if (power == self.last_power):
            #print("> UC480-QPD: Duplicate image detected!")
            time.sleep(0.05)
            return [self.last_power, 0, 0]

        self.last_power = power

        # Determine offset by fitting gaussians to the two beam spots.
        # In the event that only beam spot can be fit then this will
        # attempt to compensate. However this assumes that the two
        # spots are centered across the mid-line of camera ROI.
        #
        if (self.fit_mode == 1):
            [total_good, dist1, dist2] = self.doFit(data)

        # Determine offset by moments calculation.
        else:
            [total_good, dist1, dist2] = self.doMoments(data)
                        
        # Calculate offset.
        #

        # No good fits.
        if (total_good == 0):
            return [power, 0.0, 0.0]

        # One good fit.
        elif (total_good == 1):
            if self.allow_single_fits:
                return [power, 1.0, ((dist1 + dist2) - 0.5*self.zero_dist)]
            else:
                return [power, 0.0, 0.0]

        # Two good fits. This gets twice the weight of one good fit
        # if we are averaging.
        else:
            return [power, 2.0, 2.0*((dist1 + dist2) - self.zero_dist)]


class CameraQPDCorrFit(CameraQPD):
    """
    This version uses storm-analyis to do the peak finding and
    image correlation to do the peak fitting.
    """
    def __init__(self, **kwds):
        super().__init__(**kwds)

        assert (cl2DG is not None), "Correlation fitting not available."

        self.fit_hl = None
        self.fit_hr = None

    def doFit(self, data):
        dist1 = 0
        dist2 = 0
        self.x_off1 = 0.0
        self.y_off1 = 0.0
        self.x_off2 = 0.0
        self.y_off2 = 0.0

        if self.fit_hl is None:
            roi_size = int(3.0 * self.sigma)
            self.fit_hl = cl2DG.CorrLockFitter(roi_size = roi_size,
                                               sigma = self.sigma,
                                               threshold = 10)
            self.fit_hr = cl2DG.CorrLockFitter(roi_size = roi_size,
                                               sigma = self.sigma,
                                               threshold = 10)

        total_good = 0
        [x1, y1, status] = self.fit_hl.findFitPeak(data[:,:self.half_x])
        if status:
            total_good += 1
            self.x_off1 = x1 - self.half_y
            self.y_off1 = y1 - self.half_x
            dist1 = abs(self.y_off1)
                
        [x2, y2, status] = self.fit_hr.findFitPeak(data[:,-self.half_x:])
        if status:
            total_good += 1
            self.x_off2 = x2 - self.half_y
            self.y_off2 = y2
            dist2 = abs(self.y_off2)

        return [total_good, dist1, dist2]

    def shutDown(self):
        super().shutDown()
        
        if self.fit_hl is not None:
            self.fit_hl.cleanup()
            self.fit_hr.cleanup()
            

class CameraQPDSAFit(CameraQPD):
    """
    This version uses the storm-analysis project to do the fitting.
    """
    def __init__(self, **kwds):
        super().__init__(**kwds)

        assert (saLPF is not None), "Storm-analysis fitting not available."

        self.fit_hl = None
        self.fit_hr = None

    def doFit(self, data):
        dist1 = 0
        dist2 = 0
        self.x_off1 = 0.0
        self.y_off1 = 0.0
        self.x_off2 = 0.0
        self.y_off2 = 0.0

        if self.fit_hl is None:
            self.fit_hl = saLPF.LockPeakFinder(offset = 5.0,
                                               sigma = self.sigma,
                                               threshold = 10)
            self.fit_hr = saLPF.LockPeakFinder(offset = 5.0,
                                               sigma = self.sigma,
                                               threshold = 10)

        total_good = 0
        [x1, y1, status] = self.fit_hl.findFitPeak(data[:,:self.half_x])
        if status:
            total_good += 1
            self.x_off1 = x1 - self.half_y
            self.y_off1 = y1 - self.half_x
            dist1 = abs(self.y_off1)
                
        [x2, y2, status] = self.fit_hr.findFitPeak(data[:,-self.half_x:])
        if status:
            total_good += 1
            self.x_off2 = x2 - self.half_y
            self.y_off2 = y2
            dist2 = abs(self.y_off2)

        return [total_good, dist1, dist2]

    def shutDown(self):
        super().shutDown()
        
        if self.fit_hl is not None:
            self.fit_hl.cleanup()
            self.fit_hr.cleanup()

            
class CameraQPDScipyFit(CameraQPD):
    """
    This version uses scipy to do the fitting.
    """
    def __init__(self, fit_mutex = False, **kwds):
        super().__init__(**kwds)

        self.fit_mutex = fit_mutex

    def doFit(self, data):
        dist1 = 0
        dist2 = 0
        self.x_off1 = 0.0
        self.y_off1 = 0.0
        self.x_off2 = 0.0
        self.y_off2 = 0.0

        # numpy finder/fitter.
        #
        # Fit first gaussian to data in the left half of the picture.
        total_good =0
        [max_x, max_y, params, status] = self.fitGaussian(data[:,:self.half_x])
        if status:
            total_good += 1
            self.x_off1 = float(max_x) + params[2] - self.half_y
            self.y_off1 = float(max_y) + params[3] - self.half_x
            dist1 = abs(self.y_off1)

        # Fit second gaussian to data in the right half of the picture.
        [max_x, max_y, params, status] = self.fitGaussian(data[:,-self.half_x:])
        if status:
            total_good += 1
            self.x_off2 = float(max_x) + params[2] - self.half_y
            self.y_off2 = float(max_y) + params[3]
            dist2 = abs(self.y_off2)

        return [total_good, dist1, dist2]
        
    def fitGaussian(self, data):
        if (np.max(data) < 25):
            return [False, False, False, False]
        x_width = data.shape[0]
        y_width = data.shape[1]
        max_i = data.argmax()
        max_x = int(max_i/y_width)
        max_y = int(max_i%y_width)
        if (max_x > (self.fit_size-1)) and (max_x < (x_width - self.fit_size)) and (max_y > (self.fit_size-1)) and (max_y < (y_width - self.fit_size)):
            if self.fit_mutex:
                self.fit_mutex.lock()
            #[params, status] = npLPF.fitSymmetricGaussian(data[max_x-self.fit_size:max_x+self.fit_size,max_y-self.fit_size:max_y+self.fit_size], 8.0)
            #[params, status] = npLPF.fitFixedEllipticalGaussian(data[max_x-self.fit_size:max_x+self.fit_size,max_y-self.fit_size:max_y+self.fit_size], 8.0)
            [params, status] = npLPF.fitFixedEllipticalGaussian(data[max_x-self.fit_size:max_x+self.fit_size,max_y-self.fit_size:max_y+self.fit_size], self.sigma)
            if self.fit_mutex:
                self.fit_mutex.unlock()
            params[2] -= self.fit_size
            params[3] -= self.fit_size
            return [max_x, max_y, params, status]
        else:
            return [False, False, False, False]












# from matplotlib import pyplot as plt
# ids_cam = Camera()
# ids_cam.allocate_buffers()
# ids_cam.StartExposure()

# while True:
#     img = ids_cam.full_buffers.get()
#     plt.imshow(img)
#     plt.savefig('testplot1.png')
#     # print(img)
#     time.sleep(1)
