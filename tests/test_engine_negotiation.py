"""Fault injection into production engine handlers; no ESP hardware required."""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1] / 'components/livekit/core/engine.c'


def function(source, signature):
    start = source.index(signature)
    end = source.index('{', start) + 1
    depth = 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


class NegotiationTest(unittest.TestCase):
    def test_negotiation_failures_use_existing_backoff(self):
        source = SOURCE.read_text()
        code = r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#define ESP_LOGW(...) ((void)0)
#define ESP_LOGE(...) ((void)0)
enum { ENGINE_STATE_DISCONNECTED, ENGINE_STATE_CONNECTING, ENGINE_STATE_CONNECTED, ENGINE_STATE_BACKOFF };
enum { _EV_STATE_ENTER, EV_CMD_CLOSE, EV_CMD_CONNECT, EV_SIG_RES, EV_SIG_STATE, EV_PEER_STATE, EV_PEER_SDP };
enum { LIVEKIT_PB_SIGNAL_RESPONSE_LEAVE_TAG, LIVEKIT_PB_SIGNAL_RESPONSE_ROOM_UPDATE_TAG,
 LIVEKIT_PB_SIGNAL_RESPONSE_UPDATE_TAG, LIVEKIT_PB_SIGNAL_RESPONSE_JOIN_TAG,
 LIVEKIT_PB_SIGNAL_RESPONSE_ANSWER_TAG, LIVEKIT_PB_SIGNAL_RESPONSE_OFFER_TAG,
 LIVEKIT_PB_SIGNAL_RESPONSE_TRICKLE_TAG };
enum { LIVEKIT_FAILURE_REASON_NONE, LIVEKIT_FAILURE_REASON_OTHER, LIVEKIT_FAILURE_REASON_RTC, LIVEKIT_FAILURE_REASON_SIGNAL_CLOSE };
enum { PEER_ROLE_PUBLISHER, PEER_ROLE_SUBSCRIBER };
enum { SIGNAL_STATE_CONNECTED=1, SIGNAL_STATE_DISCONNECTED=2, SIGNAL_STATE_FAILED_ANY=12, SIGNAL_STATE_FAILED_CLIENT_ANY=8 };
enum { CONNECTION_STATE_CONNECTED, CONNECTION_STATE_FAILED, CONNECTION_STATE_DISCONNECTED };
enum { PEER_ERR_NONE=0, SIGNAL_ERR_NONE=0 };
typedef int signal_state_t, connection_state_t, peer_role_t, peer_err_t, signal_err_t, peer_handle_t;
typedef struct { int reason; } livekit_pb_leave_request_t;
typedef struct { int unused; } livekit_pb_room_update_t, livekit_pb_participant_update_t, livekit_pb_join_response_t, livekit_pb_trickle_request_t;
typedef struct { const char *sdp; } livekit_pb_session_description_t;
typedef struct { int which_message; struct { livekit_pb_leave_request_t leave;
 livekit_pb_room_update_t room_update; livekit_pb_participant_update_t update;
 livekit_pb_join_response_t join; livekit_pb_trickle_request_t trickle;
 livekit_pb_session_description_t offer,answer; } message; } livekit_pb_signal_response_t;
typedef struct { int type; struct { livekit_pb_signal_response_t res; int sig_state;
 struct { int state,role; } peer_state; struct { const char* sdp; int role; } peer_sdp; } detail; } engine_event_t;
typedef struct { int state,failure_reason,retry_count,signal_handle,pub_peer_handle,sub_peer_handle;
 const char *server_url,*token; struct { bool is_subscriber_primary; } session; } engine_t;
static int peer_error,send_error,peer_calls,send_calls,last_peer,last_role;
static int peer_handle_sdp(int peer,const char* sdp) { assert(sdp);++peer_calls;last_peer=peer;return peer_error; }
static int signal_send_offer(int handle,const char* sdp) { assert(sdp);++send_calls;last_role=PEER_ROLE_PUBLISHER;return send_error; }
static int signal_send_answer(int handle,const char* sdp) { assert(sdp);++send_calls;last_role=PEER_ROLE_SUBSCRIBER;return send_error; }
static void signal_connect(int handle,const char* url,const char* token) {}
static void signal_send_leave(int handle) {}
static int map_disconnect_reason(int reason) { return reason; }
static void handle_room_update(engine_t* e,const livekit_pb_room_update_t* r) {}
static void handle_participant_update(engine_t* e,const livekit_pb_participant_update_t* r) {}
static bool handle_join(engine_t* e,const livekit_pb_join_response_t* r) { return true; }
static void handle_trickle(engine_t* e,const livekit_pb_trickle_request_t* r) {}
static void send_add_track_requests(engine_t* e) {}
static int map_signal_fail_state(int state) { return state; }
static void media_stream_begin(engine_t* e) {}
'''
        for signature in ('static void handle_remote_sdp(', 'static void send_local_sdp(',
                          'static bool handle_state_connecting(', 'static bool handle_state_connected('):
            code += '\n' + function(source, signature)
        code += r'''
int main(void) {
 for (int connected=0;connected<2;++connected) {
  bool (*handler)(engine_t*,const engine_event_t*)=connected ? handle_state_connected : handle_state_connecting;
  const int initial=connected ? ENGINE_STATE_CONNECTED : ENGINE_STATE_CONNECTING;
  for (int role=0;role<2;++role) {
   for (int error=0;error>=-3;--error) {
    engine_t e={.state=initial,.pub_peer_handle=11,.sub_peer_handle=22};
    engine_event_t ev={.type=EV_SIG_RES};
    ev.detail.res.which_message=role==PEER_ROLE_SUBSCRIBER ? LIVEKIT_PB_SIGNAL_RESPONSE_OFFER_TAG : LIVEKIT_PB_SIGNAL_RESPONSE_ANSWER_TAG;
    ev.detail.res.message.offer.sdp="offer";ev.detail.res.message.answer.sdp="answer";
    peer_error=error;peer_calls=0;
    assert(!handler(&e,&ev)); // ordinary event ownership remains with engine
    assert(peer_calls==1 && last_peer==(role==PEER_ROLE_SUBSCRIBER ? 22 : 11));
    assert(e.state==(error ? ENGINE_STATE_BACKOFF : initial));
    assert(e.failure_reason==(error ? LIVEKIT_FAILURE_REASON_RTC : LIVEKIT_FAILURE_REASON_NONE));
   }
   for (int error=0;error>=-6;--error) {
    engine_t e={.state=initial};
    engine_event_t ev={.type=EV_PEER_SDP,.detail.peer_sdp={.sdp="sdp",.role=role}};
    send_error=error;send_calls=0;
    assert(!handler(&e,&ev));
    if (connected && role==PEER_ROLE_PUBLISHER) { // retain existing publisher boundary
      assert(send_calls==0 && e.state==initial);continue;
    }
    assert(send_calls==1 && last_role==role);
    assert(e.state==(error ? ENGINE_STATE_BACKOFF : initial));
    assert(e.failure_reason==(error ? LIVEKIT_FAILURE_REASON_SIGNAL_CLOSE : LIVEKIT_FAILURE_REASON_NONE));
   }
  }
 }
}
'''
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)
            (path/'test.c').write_text(code)
            subprocess.run([os.environ.get('CC','cc'),'-std=c2x','-Wall','-Wextra','-Werror',
                            '-Wno-unused-parameter','-Wno-unused-variable','-fsanitize=address,undefined',
                            str(path/'test.c'),'-o',str(path/'test')],check=True)
            subprocess.run([str(path/'test')],check=True)


if __name__ == '__main__':
    unittest.main()
