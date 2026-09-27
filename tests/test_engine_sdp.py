"""Exercise production SDP handlers with failed IO and explicit copy ownership."""
import pathlib
import subprocess
import tempfile
import unittest
from test_engine_lifecycle import SOURCE, function


class SdpTest(unittest.TestCase):
    def test_sdp_failures_and_queue_ownership(self):
        code = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>
#define ESP_LOGI(...) ((void)0)
#define ESP_LOGE(...) ((void)0)
enum { ENGINE_STATE_CONNECTING, ENGINE_STATE_CONNECTED, ENGINE_STATE_BACKOFF };
enum { LIVEKIT_FAILURE_REASON_RTC=10, LIVEKIT_FAILURE_REASON_OTHER };
enum { PEER_ROLE_PUBLISHER, PEER_ROLE_SUBSCRIBER, EV_PEER_SDP };
enum { PEER_ERR_NONE, SIGNAL_ERR_NONE=0 };
typedef int peer_role_t;
typedef int peer_err_t;
typedef int signal_err_t;
typedef void *peer_handle_t;
typedef struct { int state, failure_reason; void *pub_peer_handle, *sub_peer_handle, *signal_handle; } engine_t;
typedef struct { int type; struct { struct { char *sdp; int role; } peer_sdp; } detail; } engine_event_t;
static int peer_error, send_error, calls, outstanding, freed, allocation_fails;
static bool queue_accepts;
static engine_event_t queued;
static void *last_peer;
static int sent_role;
static char *copy_sdp(const char *sdp) {
 if(allocation_fails) return NULL;
 char *p=malloc(strlen(sdp)+1); assert(p); strcpy(p,sdp); outstanding++; return p;
}
static void release_sdp(void *p) { assert(p); free(p); outstanding--; freed++; }
#define strdup copy_sdp
#define free release_sdp
static bool event_enqueue(engine_t *e,engine_event_t *v,bool front) {
 calls++; assert(v->detail.peer_sdp.sdp); if(queue_accepts) queued=*v; return queue_accepts;
}
static int peer_handle_sdp(void *peer,const char *sdp) { last_peer=peer; return peer_error; }
static int signal_send_offer(void *signal,const char *sdp) { sent_role=PEER_ROLE_PUBLISHER; return send_error; }
static int signal_send_answer(void *signal,const char *sdp) { sent_role=PEER_ROLE_SUBSCRIBER; return send_error; }
'''
        for name in ('on_peer_sdp', 'handle_remote_sdp', 'send_local_sdp'):
            code += function(SOURCE.read_text(), name)
        code += r'''
int main(void) {
 engine_t e={.pub_peer_handle=(void*)1,.sub_peer_handle=(void*)2};
 for(int state=ENGINE_STATE_CONNECTING;state<=ENGINE_STATE_CONNECTED;state++) {
  for(int role=PEER_ROLE_PUBLISHER;role<=PEER_ROLE_SUBSCRIBER;role++) {
   e.state=state; peer_error=0; handle_remote_sdp(&e,role,"v=0");
   assert(e.state==state && last_peer==(role==PEER_ROLE_PUBLISHER?(void*)1:(void*)2));
   peer_error=-4; handle_remote_sdp(&e,role,"v=0");
   assert(e.state==ENGINE_STATE_BACKOFF && e.failure_reason==LIVEKIT_FAILURE_REASON_RTC);
   e.state=state; send_error=0; send_local_sdp(&e,role,"v=0");
   assert(e.state==state && sent_role==role);
   send_error=-3; send_local_sdp(&e,role,"v=0");
   assert(e.state==ENGINE_STATE_BACKOFF && e.failure_reason==LIVEKIT_FAILURE_REASON_OTHER);
  }
 }
 e.state=ENGINE_STATE_CONNECTED;
 on_peer_sdp(NULL,PEER_ROLE_SUBSCRIBER,&e);
 on_peer_sdp("",PEER_ROLE_SUBSCRIBER,&e); assert(calls==0);
 allocation_fails=1; on_peer_sdp("v=0",PEER_ROLE_SUBSCRIBER,&e); assert(calls==0);
 allocation_fails=0; queue_accepts=false;
 on_peer_sdp("v=0",PEER_ROLE_SUBSCRIBER,&e); assert(outstanding==0 && freed==1);
 queue_accepts=true;
 char original[]="v=0";
 on_peer_sdp(original,PEER_ROLE_SUBSCRIBER,&e);
 original[0]='x'; assert(strcmp(queued.detail.peer_sdp.sdp,"v=0")==0);
 assert(outstanding==1 && freed==1 && e.state==ENGINE_STATE_CONNECTED);
 free(queued.detail.peer_sdp.sdp); assert(outstanding==0 && freed==2);
}
'''
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory)
            (path / 'test.c').write_text(code)
            subprocess.run(['cc', '-std=c11', '-fsanitize=address,undefined',
                            str(path / 'test.c'), '-o', str(path / 'test')], check=True)
            subprocess.run([str(path / 'test')], check=True)


if __name__ == '__main__':
    unittest.main()
