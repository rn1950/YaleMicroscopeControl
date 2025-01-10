
#include <inttypes.h>
#include <stdio.h>
#include "NIDAQmx.h"


int main(void)
{
    printf("hello\n");
    int32   error=0;
    printf("hello\n");
    printf("hello\n");

    TaskHandle  taskHandle=0;
    DAQmxCreateTask("", &taskHandle);
    DAQmxCreateDOChan(&taskHandle, "Dev1/port0/line0", "", DAQmx_Val_ChanPerLine );
    DAQmxCfgSampClkTiming(&taskHandle, "", 1000, DAQmx_Val_Rising, DAQmx_Val_ContSamps, 8);
    int32_t written; 
    int8_t arr[] = {1, 1, 0, 0, 1, 0, 1, 0}; 
    DAQmxWriteDigitalLines(&taskHandle, 8, 1, -1, DAQmx_Val_GroupByChannel, arr, &written, NULL); 

    return 0;
}




