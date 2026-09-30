#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <string.h>

// Inspect only the transport token of the standard bare trickle candidate.
// The peer library remains responsible for parsing and validating the candidate.
static inline bool ice_candidate_uses_tcp(const char *candidate)
{
    if (!candidate || strncmp(candidate, "candidate:", 10) != 0) return false;
    const char *token = candidate;
    for (int field = 0; field < 2; ++field) {
        token = strchr(token, ' ');
        if (!token) return false;
        while (*token == ' ') ++token;
        if (!*token) return false;
    }
    const size_t length = strcspn(token, " \r\n\t");
    return length == 3 && (token[0] == 't' || token[0] == 'T') &&
           (token[1] == 'c' || token[1] == 'C') &&
           (token[2] == 'p' || token[2] == 'P');
}
