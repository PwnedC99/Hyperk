#pragma once
#include <cerrno>
#include <cctype>
#include <cstdlib>

namespace BoardPinPolicy {
    // Native UI format: start,data,clock,reversed, repeated per segment.
    inline bool invalidSegments(const char* cursor, int reservedPin) {
        unsigned field = 0;
        if (!*cursor) return true;
        while (*cursor) {
            char* end = nullptr;
            errno = 0;
            const long value = strtol(cursor, &end, 10);
            if (end == cursor || errno == ERANGE) return true;
            const unsigned part = field % 4;
            if (part == 1 || part == 2) {
                if (value < -1 || value > 48 || value == reservedPin) return true;
            }
            if (part == 0 && value < 0) return true;
            if (part == 3 && value != 0 && value != 1) return true;
            ++field;
            while (*end && std::isspace(static_cast<unsigned char>(*end))) ++end;
            if (!*end) break;
            if (*end != ',' || !end[1]) return true;
            cursor = end + 1;
        }
        return field % 4 != 0;
    }
}
