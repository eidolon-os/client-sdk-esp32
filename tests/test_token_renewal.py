"""Exercise production credential events, retry dispatch and ownership with ASan."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / 'components/livekit/core/engine.c').read_text()


def function(signature):
    begin = SOURCE.index(signature)
    end = SOURCE.index('{', begin) + 1
    depth = 1
    while depth:
        depth += (SOURCE[end] == '{') - (SOURCE[end] == '}')
        end += 1
    return SOURCE[begin:end]


class TokenRenewalTest(unittest.TestCase):
    def test_renewal_retry_close_and_superseded_connection(self):
        code = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#define ESP_LOGW(...) ((void)0)
#define ESP_LOGI(...) ((void)0)
#define SAFE_FREE(p) do { free(p); (p)=NULL; } while(0)
#define CONFIG_LK_MAX_RETRIES 3
#define esp_system_abort(message) abort()
typedef void *engine_handle_t;
typedef int engine_err_t;
enum { ENGINE_ERR_NONE, ENGINE_ERR_INVALID_ARG, ENGINE_ERR_NO_MEM, ENGINE_ERR_OTHER };
typedef int engine_state_t;
enum { ENGINE_STATE_DISCONNECTED, ENGINE_STATE_CONNECTING, ENGINE_STATE_CONNECTED, ENGINE_STATE_BACKOFF };
enum { EV_CMD_CONNECT, EV_CMD_CLOSE, EV_CMD_UPDATE_TOKEN, EV_SIG_RES, EV_PEER_SDP,
       _EV_STATE_ENTER, _EV_STATE_EXIT, EV_TIMER_EXP, EV_MAX_RETRIES_REACHED };
enum { LIVEKIT_PB_SIGNAL_RESPONSE_LEAVE_TAG, LIVEKIT_FAILURE_REASON_MAX_RETRIES };
typedef struct { int which_message; struct { struct { int reason; } leave; } message; } response_t;
typedef struct { int type; union {
 struct { char *server_url, *token; } cmd_connect;
 struct { char *expected, *token; } cmd_update_token;
 struct { char *sdp; } peer_sdp;
 response_t res;
} detail; } engine_event_t;
typedef struct { char *token, *server_url; int state, retry_count, failure_reason; void *signal_handle; } engine_t;
static void protocol_signal_response_free(response_t *r) { (void)r; }
static engine_event_t queue[8];
static int count, allocations, fail_at;
static bool queue_fail;
static char *test_strdup(const char *s) {
 if (++allocations==fail_at) return NULL;
 size_t n=strlen(s)+1; char *p=malloc(n); memcpy(p,s,n); return p;
}
#define strdup test_strdup
static bool event_enqueue(engine_t *eng, engine_event_t *ev, bool front) {
 (void)eng; assert(!front); // renewals must preserve FIFO, not reverse successive updates
 if(queue_fail) return false;
 assert(count<8); queue[count++]=*ev; return true;
}
static void cleanup_previous_connection(engine_t *e) { (void)e; }
static uint16_t backoff_ms_for_attempt(int attempt) { return (uint16_t)attempt; }
static void timer_start(engine_t *e,int ms) { (void)e;(void)ms; }
static void timer_stop(engine_t *e) { (void)e; }
static int map_disconnect_reason(int reason) { return reason; }
static const char *authorized_token;
static int joins;
static void signal_connect(void *h,const char *url,const char *token) {
 (void)h; (void)url; ++joins;
 // The fake signaling boundary rejects the original, now-expired credential.
 assert(!strcmp(token, authorized_token));
}
'''
        for signature in ['static void event_free(', 'static bool handle_token_update(',
                          'engine_err_t engine_update_token(', 'static bool handle_state_backoff(']:
            code += function(signature) + '\n'
        # Execute the actual production reconnect entry with isolated signaling IO.
        connecting = function('static bool handle_state_connecting(')
        entry = connecting.split('case _EV_STATE_ENTER:', 1)[1].split('break;', 1)[0]
        code += 'static bool handle_state_connecting(engine_t *eng,const engine_event_t *ev) {\n'
        code += 'if(ev->type==_EV_STATE_ENTER) {' + entry + '} return false; }\n'
        code += r'''
static bool handle_state_disconnected(engine_t *e,const engine_event_t *v) { (void)e;(void)v;return false; }
static bool handle_state_connected(engine_t *e,const engine_event_t *v) { (void)e;(void)v;return false; }
'''
        code += function('static inline bool handle_state(') + '\n'
        code += r'''
static void drain(engine_t *e) {
 for(int i=0;i<count;i++) { assert(!handle_state(e,&queue[i],e->state)); event_free(&queue[i]); }
 count=0;
}
int main(void) {
 engine_t e={.token=strdup("expired"),.server_url="wss://same",.state=ENGINE_STATE_CONNECTED};
 assert(engine_update_token(NULL,"old","new")==ENGINE_ERR_INVALID_ARG);
 assert(engine_update_token(&e,"", "new")==ENGINE_ERR_INVALID_ARG);
 assert(engine_update_token(&e,"expired", "")==ENGINE_ERR_INVALID_ARG);
 assert(engine_update_token(&e,"expired", "renewed")==ENGINE_ERR_NONE);
 assert(engine_update_token(&e,"renewed", "latest")==ENGINE_ERR_NONE);
 drain(&e);
 assert(e.state==ENGINE_STATE_CONNECTED && joins==0 && !strcmp(e.token,"latest"));
 // Network drops after renewal; existing backoff and reconnect use the latest token.
 e.state=ENGINE_STATE_BACKOFF; authorized_token="latest";
 engine_event_t retry={.type=EV_TIMER_EXP}, enter={.type=_EV_STATE_ENTER};
 handle_state(&e,&retry,e.state); assert(e.state==ENGINE_STATE_CONNECTING);
 handle_state(&e,&enter,e.state); assert(joins==1);
 // Renewal while backoff must preserve backoff and must not start a connection.
 e.state=ENGINE_STATE_BACKOFF;
 assert(engine_update_token(&e,"latest","next")==ENGINE_ERR_NONE); drain(&e);
 assert(e.state==ENGINE_STATE_BACKOFF && joins==1);
 authorized_token="next";handle_state(&e,&retry,e.state);handle_state(&e,&enter,e.state);
 assert(joins==2);
 // Priority revocation/close wins even when a renewal is queued.
 e.state=ENGINE_STATE_BACKOFF;
 assert(engine_update_token(&e,"next","after-close")==ENGINE_ERR_NONE);
 engine_event_t leave={.type=EV_SIG_RES,.detail.res={.which_message=LIVEKIT_PB_SIGNAL_RESPONSE_LEAVE_TAG,.message.leave={.reason=42}}};
 handle_state(&e,&leave,e.state);drain(&e);
 assert(e.state==ENGINE_STATE_DISCONNECTED && e.failure_reason==42 && joins==2);
 // An old queued update cannot overwrite a different connection's credentials.
 assert(engine_update_token(&e,"after-close","stale")==ENGINE_ERR_NONE);
 free(e.token);e.token=strdup("replacement");drain(&e);
 assert(!strcmp(e.token,"replacement") && e.state==ENGINE_STATE_DISCONNECTED);
 // Allocation and queue failures keep the old token and release all event memory.
 for(int offset=1;offset<=2;offset++) {
  fail_at=allocations+offset;
  assert(engine_update_token(&e,"replacement","failed")==ENGINE_ERR_NO_MEM);
  assert(!count && !strcmp(e.token,"replacement"));fail_at=0;
 }
 queue_fail=true;
 assert(engine_update_token(&e,"replacement","failed")==ENGINE_ERR_OTHER);
 assert(!count && !strcmp(e.token,"replacement"));queue_fail=false;
 // Pending renewal discarded at shutdown owns and frees both strings.
 assert(engine_update_token(&e,"replacement","discard")==ENGINE_ERR_NONE);
 event_free(&queue[0]);count=0;
 free(e.token);
}
'''
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)
            (p / 'test.c').write_text(code)
            subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                            '-fsanitize=address,undefined', str(p / 'test.c'),
                            '-o', str(p / 'test')], check=True)
            subprocess.run([str(p / 'test')], check=True, timeout=15)


if __name__ == '__main__':
    unittest.main()
