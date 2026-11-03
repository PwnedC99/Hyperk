#pragma once

namespace Peripheral {
    void init();
    bool enabled();
    bool storageReady();
    bool setEnabled(bool enabled);
}
