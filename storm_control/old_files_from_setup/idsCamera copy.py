import ctypes.wintypes
from ids_peak import ids_peak as peak
import ids_peak_ipl.ids_peak_ipl as ids_ipl
import ids_peak.ids_peak_ipl_extension as ids_ipl_extension
import threading
import time
import queue
import numpy as np

Handle = ctypes.wintypes.HANDLE

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








































    
    # def getImage(self):
    #     self._node_map.FindNode("TriggerSoftware").Execute()
    #     self.buffer = self.datastream.WaitForFinishedBuffer(1000)
    #     raw_image = ids_ipl_extension.BufferToImage(self.buffer)
    #     color_image = raw_image.ConvertTo(ids_ipl.PixelFormatName_RGB8)
    #     return color_image

    # def setBuffers(self):
    #     self.datastream = self.device.DataStreams()[0].OpenDataStream()
    #     self._data_stream_node_map = self._data_stream.NodeMaps()[0]
    #     # set to FIFO
    #     self._data_stream_node_map.FindNode("StreamBufferHandlingMode").SetCurrentEntry("OldestFirst")
    #     payload_size = self._node_map.FindNode("PayloadSize").Value()
    #     for i in range(self.datastream.NumBuffersAnnouncedMinRequired()):
    #         self.buffer = self.datastream.AllocAndAnnounceBuffer(payload_size)
    #         self.datastream.QueueBuffer(self.buffer)
    #     self.datastream.StartAcquisition()
    #     self._node_map.FindNode("AcquisitionStart").Execute()
    #     self._node_map.FindNode("AcquisitionStart").WaitUntilDone()
    #     self._node_map.FindNode("ExposureTime").SetValue(19000)

        

























































from matplotlib import pyplot as plt
ids_cam = Camera()
ids_cam.allocate_buffers()
ids_cam.StartExposure()

while True:
    img = ids_cam.full_buffers.get()
    plt.imshow(img)
    plt.savefig('testplot1.png')
    # print(img)
    time.sleep(1)


# c_void_pointer = ctypes.c_void_p
# ids_cam = Camera()


# from matplotlib import pyplot as plt
# import numpy as np

# picture = ids_cam.getImage().get_numpy_3D()
# plt.figure(figsize = (15,15))
# plt.imshow(picture)


# plt.savefig('testplot1.png')
# print('made it here')
