#pragma once
#include <Arduino.h>

// ABI shared with the unmodified backend library.
struct WebResource {
    const char* url;
    PGM_P data;
    uint32_t len;
    const char* mime;
};
extern const WebResource webResources_OSS[];
extern const uint16_t webResourcesCount_OSS;
