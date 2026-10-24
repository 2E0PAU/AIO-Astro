// Local USB SDK peer compiled against the unmodified vendor header. No hardware.
#include "EAF_focuser.h"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <unistd.h>

static bool opened = false;
static int position = 5100, target = 5100, polls = 0;
static bool flag(const char *name) { return std::getenv(name) != nullptr; }
static void record(const char *name, int value = 0) {
    const char *path = std::getenv("AIO_EAF_TEST_LOG");
    if (path) { FILE *f = std::fopen(path, "a"); std::fprintf(f, "%s %d\n", name, value); std::fclose(f); }
}
static EAF_ERROR_CODE valid(int id) {
    return id != 17 ? EAF_ERROR_INVALID_ID : (!opened ? EAF_ERROR_CLOSED : EAF_SUCCESS);
}
int EAFGetNum() { return 1; }
const char *EAFGetSDKVersion() { return "LOCAL-EAF-PEER"; }
EAF_ERROR_CODE EAFGetID(int index, int *id) {
    if (index != 0) return EAF_ERROR_INVALID_INDEX;
    *id = 17; return EAF_SUCCESS;
}
EAF_ERROR_CODE EAFGetProperty(int id, EAF_INFO *info) {
    if (id != 17) return EAF_ERROR_INVALID_ID;
    info->ID = id; std::strcpy(info->Name, "EAF original peer"); info->MaxStep = 65535;
    return EAF_SUCCESS;
}
EAF_ERROR_CODE EAFOpen(int id) { record("open", id); opened = id == 17; return valid(id); }
EAF_ERROR_CODE EAFClose(int id) { record("close", id); opened = false; return EAF_SUCCESS; }
EAF_ERROR_CODE EAFGetPosition(int id, int *value) {
    if (valid(id)) return valid(id);
    *value = position; return EAF_SUCCESS;
}
EAF_ERROR_CODE EAFGetMaxStep(int id, int *value) {
    if (valid(id)) return valid(id);
    if (polls) return EAF_ERROR_MOVING;
    *value = 60000; return EAF_SUCCESS;
}
EAF_ERROR_CODE EAFGetTemp(int id, float *value) {
    if (valid(id)) return valid(id);
    if (flag("AIO_EAF_TEST_TEMP_ERROR")) return EAF_ERROR_REMOVED;
    if (flag("AIO_EAF_TEST_NO_TEMP")) return EAF_ERROR_GENERAL_ERROR;
    *value = 12.5; return EAF_SUCCESS;
}
EAF_ERROR_CODE EAFGetSerialNumber(int id, EAF_SN *sn) {
    if (valid(id)) return valid(id);
    if (flag("AIO_EAF_TEST_NO_SERIAL")) return EAF_ERROR_NOT_SUPPORTED;
    std::memset(sn, 17, sizeof(*sn)); return EAF_SUCCESS;
}
EAF_ERROR_CODE EAFIsMoving(int id, bool *moving, bool *hand) {
    if (valid(id)) return valid(id);
    *hand = flag("AIO_EAF_TEST_HAND");
    if (polls && !flag("AIO_EAF_TEST_STUCK")) {
        --polls;
        if (!polls) position = target + (flag("AIO_EAF_TEST_BAD_READBACK") ? 1 : 0);
    }
    *moving = polls > 0; return EAF_SUCCESS;
}
EAF_ERROR_CODE EAFMove(int id, int value) {
    if (valid(id)) return valid(id);
    record("move", value); target = value; polls = 3;
    if (flag("AIO_EAF_TEST_HANG")) sleep(30);
    return flag("AIO_EAF_TEST_LOST_ACK") ? EAF_ERROR_GENERAL_ERROR : EAF_SUCCESS;
}
EAF_ERROR_CODE EAFStopAndWait(int id, int timeoutMs) {
    if (valid(id)) return valid(id);
    record("stop", id); polls = 0; return EAF_SUCCESS;
}
