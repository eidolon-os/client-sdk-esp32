#include "ice_candidate_transport.h"
#include <assert.h>
int main(void) {
    assert(ice_candidate_uses_tcp("candidate:123 1 tcp 1234 192.168.3.230 7881 typ host tcptype passive"));
    assert(ice_candidate_uses_tcp("candidate:123 1 TCP 1234 ::1 7881 typ host"));
    assert(ice_candidate_uses_tcp("candidate:123   1  TcP 1234 host.local 9 typ host"));
    assert(!ice_candidate_uses_tcp("candidate:123 1 udp 1234 192.168.3.230 59972 typ host"));
    assert(!ice_candidate_uses_tcp("candidate:123 1 UDP 1234 ::1 59972 typ host"));
    assert(!ice_candidate_uses_tcp("candidate:123 1 tcp-extra 1234 192.168.3.230 9 typ host"));
    assert(!ice_candidate_uses_tcp("candidate:123"));
    assert(!ice_candidate_uses_tcp("candidate:123 1"));
    assert(!ice_candidate_uses_tcp("candidate:123 1 "));
    assert(!ice_candidate_uses_tcp(""));
    assert(!ice_candidate_uses_tcp(0));
    assert(!ice_candidate_uses_tcp("malformed 1 tcp"));
    assert(ice_candidate_uses_ipv6("candidate:123 1 UDP 1234 2001:db8::5 59972 typ host"));
    assert(ice_candidate_uses_ipv6("candidate:123  1 UDP 1234 ::1 59972 typ host"));
    assert(!ice_candidate_uses_ipv6("candidate:123 1 UDP 1234 192.168.3.1 59972 typ srflx raddr ::1 rport 9"));
    assert(!ice_candidate_uses_ipv6("candidate:123 1 UDP 1234 host.local 59972 typ host"));
    assert(!ice_candidate_uses_ipv6("candidate:123 1 UDP"));
    assert(!ice_candidate_uses_ipv6(NULL));
}
