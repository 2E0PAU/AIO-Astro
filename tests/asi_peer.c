/* Local test SDK peer. No hardware access; compiled only by the automated tests. */
#include "ASICamera2.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

static int opened = -1, state = 0, polls = 0;
static int width = 32, height = 24, binning = 1, format = ASI_IMG_RAW16, x = 0, y = 0;
static long values[32] = { [ASI_GAIN]=100, [ASI_EXPOSURE]=1000, [ASI_OFFSET]=10,
    [ASI_TEMPERATURE]=200, [ASI_TARGET_TEMP]=-10, [ASI_COOLER_POWER_PERC]=37 };
static int types[] = {ASI_GAIN, ASI_EXPOSURE, ASI_OFFSET, ASI_TEMPERATURE,
    ASI_FLIP, ASI_TARGET_TEMP, ASI_COOLER_ON, ASI_COOLER_POWER_PERC};

static void record(const char *operation, long value) {
    const char *path = getenv("AIO_ASI_TEST_LOG");
    if (path) { FILE *f = fopen(path, "a"); if (f) { fprintf(f, "%s %ld\n", operation, value); fclose(f); } }
}
int ASIGetNumOfConnectedCameras(void) { return 2; }
char *ASIGetSDKVersion(void) { return "LOCAL-TEST-SDK"; }
ASI_ERROR_CODE ASIGetCameraProperty(ASI_CAMERA_INFO *info, int index) {
    if (index < 0 || index > 1) return ASI_ERROR_INVALID_INDEX;
    memset(info, 0, sizeof(*info));
    strcpy(info->Name, index ? "ASI120MM Mini TEST" : "ASI2600MC Pro TEST");
    info->CameraID = index ? 23 : 17; info->MaxWidth = 32; info->MaxHeight = 24;
    info->IsColorCam = !index; info->BayerPattern = getenv("AIO_ASI_TEST_BAYER") ? atoi(getenv("AIO_ASI_TEST_BAYER")) : 0;
    info->SupportedBins[0] = 1; info->SupportedBins[1] = 2;
    info->SupportedVideoFormat[0] = ASI_IMG_RAW8;
    info->SupportedVideoFormat[1] = ASI_IMG_RAW16;
    info->SupportedVideoFormat[2] = ASI_IMG_END;
    info->PixelSize = 3.76; info->BitDepth = 16; info->IsCoolerCam = !index;
    info->IsUSB3Camera = 1; info->IsUSB3Host = 1; return ASI_SUCCESS;
}
ASI_ERROR_CODE ASIOpenCamera(int id) { record("open", id); opened = id; return ASI_SUCCESS; }
ASI_ERROR_CODE ASIInitCamera(int id) { record("init", id); return id == opened ? ASI_SUCCESS : ASI_ERROR_INVALID_ID; }
ASI_ERROR_CODE ASICloseCamera(int id) { record("close", id); opened = -1; return ASI_SUCCESS; }
ASI_ERROR_CODE ASIGetSerialNumber(int id, ASI_SN *serial) { for (int i=0;i<8;i++) serial->id[i] = id+i; return ASI_SUCCESS; }
ASI_ERROR_CODE ASIGetNumOfControls(int id, int *count) { *count = sizeof(types)/sizeof(types[0]); return ASI_SUCCESS; }
ASI_ERROR_CODE ASIGetControlCaps(int id, int index, ASI_CONTROL_CAPS *caps) {
    memset(caps, 0, sizeof(*caps)); caps->ControlType = types[index]; caps->IsWritable = 1;
    caps->MinValue = 0; caps->MaxValue = 600;
    if (caps->ControlType == ASI_EXPOSURE) { caps->MinValue=1; caps->MaxValue=86400000000L; }
    if (caps->ControlType == ASI_TARGET_TEMP) { caps->MinValue=-40; caps->MaxValue=30; }
    if (caps->ControlType == ASI_COOLER_ON) caps->MaxValue=1;
    if (caps->ControlType == ASI_OFFSET) caps->MaxValue=100;
    if (caps->ControlType == ASI_TEMPERATURE || caps->ControlType == ASI_COOLER_POWER_PERC) caps->IsWritable=0;
    return ASI_SUCCESS;
}
ASI_ERROR_CODE ASIGetControlValue(int id, ASI_CONTROL_TYPE type, long *value, ASI_BOOL *automatic) {
    *value = type == ASI_FLIP && getenv("AIO_ASI_TEST_FLIP") ? atoi(getenv("AIO_ASI_TEST_FLIP")) : values[type];
    *automatic=0; return ASI_SUCCESS;
}
ASI_ERROR_CODE ASISetControlValue(int id, ASI_CONTROL_TYPE type, long value, ASI_BOOL automatic) {
    char operation[40]; snprintf(operation, sizeof(operation), "set-%d", type); record(operation, value);
    values[type] = value + (type == ASI_GAIN && getenv("AIO_ASI_TEST_MISMATCH") ? 1 : 0); return ASI_SUCCESS;
}
ASI_ERROR_CODE ASIGetROIFormat(int id, int *w, int *h, int *b, ASI_IMG_TYPE *kind) { *w=width; *h=height; *b=binning; *kind=format; return ASI_SUCCESS; }
ASI_ERROR_CODE ASISetROIFormat(int id, int w, int h, int b, ASI_IMG_TYPE kind) { record("roi", b); width=w; height=h; binning=b; format=kind; return ASI_SUCCESS; }
ASI_ERROR_CODE ASIGetStartPos(int id, int *px, int *py) { *px=x; *py=y; return ASI_SUCCESS; }
ASI_ERROR_CODE ASISetStartPos(int id, int px, int py) { record("origin", px); x=px; y=py; return ASI_SUCCESS; }
ASI_ERROR_CODE ASIStartExposure(int id, ASI_BOOL dark) { record("expose", dark); state=1; polls=0; return ASI_SUCCESS; }
ASI_ERROR_CODE ASIStopExposure(int id) { record("abort", id); state=0; return ASI_SUCCESS; }
ASI_ERROR_CODE ASIGetExpStatus(int id, ASI_EXPOSURE_STATUS *status) {
    if (state == 1 && !getenv("AIO_ASI_TEST_WORKING") && ++polls >= 3) state=2;
    *status=state; return ASI_SUCCESS;
}
ASI_ERROR_CODE ASIGetDataAfterExp(int id, unsigned char *buffer, long size) {
    record("download", size);
    if (getenv("AIO_ASI_TEST_HANG")) sleep(30);
    int flip = getenv("AIO_ASI_TEST_FLIP") ? atoi(getenv("AIO_ASI_TEST_FLIP")) : 0;
    for (int row=0;row<height;row++) for (int col=0;col<width;col++) {
        int sy = flip & 2 ? height-1-row : row, sx = flip & 1 ? width-1-col : col;
        unsigned short value = 1000 + sy*width + sx;
        if (format == ASI_IMG_RAW16) ((unsigned short*)buffer)[row*width+col] = value;
        else buffer[row*width+col] = value % 256;
    }
    state=0; return ASI_SUCCESS;
}
