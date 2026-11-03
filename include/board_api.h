#pragma once
#ifdef HYPERK_BOARD_UI
class AsyncWebServer;
namespace BoardApi {
    void init();
    void registerRoutes(AsyncWebServer& server);
}
#endif
