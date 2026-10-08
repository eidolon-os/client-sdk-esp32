"""Exercise production shutdown functions with delayed worker completion."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def function(file, signature):
    source = (ROOT / "components/livekit/core" / file).read_text()
    start = source.index(signature)
    end = source.index("{", start) + 1
    depth = 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


def run(code):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory)
        (path / "test.c").write_text(code)
        subprocess.run(["cc", "-std=c11", "-g", "-O1", "-pthread",
                        "-fsanitize=address,undefined", str(path / "test.c"),
                        "-o", str(path / "test")], check=True)
        subprocess.run([str(path / "test")], check=True, timeout=15)


class ShutdownOwnershipTest(unittest.TestCase):
    def test_destroy_joins_peer_after_delayed_loop_and_failed_connect(self):
        code = r"""
#include <assert.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <time.h>
#define PC_EXIT_BIT 1
#define PC_PAUSED_BIT 2
#define PC_RESUME_BIT 4
#define MEDIA_LIB_MAX_LOCK_TIME 0xffffffff
#define ESP_LOGE(...) ((void)0)
#define TAG(p) "peer"
#define ESP_PEER_ERR_NONE 0
#define PEER_ROLE_SUBSCRIBER 1
#define PEER_ERR_NONE 0
#define PEER_ERR_INVALID_ARG 1
#define PEER_ERR_RTC 2
typedef int peer_err_t;
typedef void *peer_handle_t;
typedef pthread_t media_lib_thread_handle_t;
typedef struct { atomic_bool running; bool pause; void *wait_event,*connection;
 struct { int role; } options; } peer_t;
static pthread_mutex_t lock=PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t cv=PTHREAD_COND_INITIALIZER;
static bool entered, released, loop_done, exit_bit;
static atomic_bool destroyed;
static int closed, fail_create, fail_connect;
static pthread_t worker;
static void esp_peer_main_loop(void *p) {
 pthread_mutex_lock(&lock); entered=true; pthread_cond_broadcast(&cv);
 while(!released) pthread_cond_wait(&cv,&lock);
 loop_done=true; pthread_mutex_unlock(&lock);
}
static void media_lib_thread_sleep(int t) {}
static void media_lib_thread_destroy(void *p) {pthread_exit(NULL);}
static void media_lib_event_group_set_bits(void *p,int bits) {
 pthread_mutex_lock(&lock); if(bits==PC_EXIT_BIT)exit_bit=true;
 pthread_cond_broadcast(&cv);pthread_mutex_unlock(&lock);
}
static void media_lib_event_group_clr_bits(void *p,int bits) {}
static void media_lib_event_group_wait_bits(void *p,int bits,uint32_t timeout) {
 assert(bits==PC_EXIT_BIT);pthread_mutex_lock(&lock);
 while(!exit_bit)pthread_cond_wait(&cv,&lock);
 pthread_mutex_unlock(&lock);
}
static void media_lib_event_group_destroy(void *p) {free(p);}
static int esp_peer_close(void *p) {assert(loop_done || fail_create);++closed;return 0;}
static int esp_peer_new_connection(void *p) {return fail_connect;}
static void (*entry)(void*);
static void *start(void *p) {entry(p);return NULL;}
static int media_lib_thread_create_from_scheduler(pthread_t *t,const char *name,void (*fn)(void*),void *p) {
 if(fail_create)return -1;entry=fn;assert(!pthread_create(t,NULL,start,p));worker=*t;return 0;
}
peer_err_t peer_disconnect(peer_handle_t);
"""
        code += function("peer.c", "static void peer_task(")
        code += function("peer.c", "peer_err_t peer_connect(")
        code += function("peer.c", "peer_err_t peer_disconnect(")
        code += function("peer.c", "peer_err_t peer_destroy(")
        code += r"""
static void *destroy(void *p) {peer_destroy(p);destroyed=true;return NULL;}
int main(void) {
 for(int i=0;i<32;i++) {
  entered=released=loop_done=exit_bit=false;destroyed=false;closed=0;
  fail_connect=i%2;fail_create=0;
  peer_t *p=calloc(1,sizeof(*p));p->connection=(void*)1;p->wait_event=malloc(8);
  assert(peer_connect(p)==(fail_connect?PEER_ERR_RTC:PEER_ERR_NONE));
  pthread_mutex_lock(&lock);while(!entered)pthread_cond_wait(&cv,&lock);pthread_mutex_unlock(&lock);
  pthread_t closer;assert(!pthread_create(&closer,NULL,destroy,p));
  struct timespec wait={0,1000000};nanosleep(&wait,NULL);assert(!destroyed);
  pthread_mutex_lock(&lock);released=true;pthread_cond_broadcast(&cv);pthread_mutex_unlock(&lock);
  pthread_join(closer,NULL);pthread_join(worker,NULL);assert(destroyed && closed==1);
 }
 fail_create=1;closed=0;
 peer_t *p=calloc(1,sizeof(*p));p->connection=(void*)1;p->wait_event=malloc(8);
 assert(peer_connect(p)==PEER_ERR_RTC);assert(!p->running);
 peer_disconnect(p);peer_destroy(p);assert(closed==1);
}
"""
        run(code)

    def test_engine_timeout_preserves_every_owned_resource_until_retry(self):
        code = r"""
#include <assert.h>
#include <stdbool.h>
#include <stdlib.h>
#define ESP_LOGW(...) ((void)0)
#define pdMS_TO_TICKS(x) (x)
#define ENGINE_TASK_JOIN_TIMEOUT_MS 5000
#define pdTRUE 1
#define portMAX_DELAY 0xffffffff
#define ENGINE_ERR_NONE 0
#define ENGINE_ERR_INVALID_ARG 1
#define ENGINE_ERR_OTHER 2
#define _EV_STOP 1
#define SAFE_FREE(x) free(x)
typedef void *engine_handle_t;
typedef int engine_err_t;
typedef struct { int type; } engine_event_t;
typedef struct {bool is_running;void *task_handle,*task_done_sem,*timer,*signal_handle,
 *pub_peer_handle,*sub_peer_handle,*event_queue;char *server_url,*token;} engine_t;
static bool done;
static int released;
static void event_enqueue(engine_t *e,engine_event_t *v,bool front) {}
static int xSemaphoreTake(void *p,int ms){return done;}
static void vTaskDelete(void *p){assert(!"must never force-delete an engine");}
static void vSemaphoreDelete(void *p){released++;}
static void xTimerDelete(void *p,unsigned t){released++;}
static void media_stream_end(engine_t *e){released++;}
static void signal_destroy(void *p){released++;}
static void peer_destroy(void *p){released++;}
static void flush_event_queue(engine_t *e){}
static void vQueueDelete(void *p){released++;}
"""
        code += function("engine.c", "engine_err_t engine_destroy(")
        code += r"""
int main(void){
 engine_t *e=calloc(1,sizeof(*e));e->is_running=true;
 e->task_handle=e->task_done_sem=e->timer=e->signal_handle=e->pub_peer_handle=e->sub_peer_handle=e->event_queue=(void*)1;
 assert(engine_destroy(e)==ENGINE_ERR_OTHER);assert(!e->is_running && released==0);
 assert(e->task_handle && e->task_done_sem && e->pub_peer_handle && e->signal_handle);
 done=true;assert(engine_destroy(e)==ENGINE_ERR_NONE);assert(released==7);
}
"""
        run(code)

    def test_room_destroy_propagates_pending_engine_without_freeing_context(self):
        code = r"""
#include <assert.h>
#include <stdbool.h>
#include <stdlib.h>
#define LIVEKIT_ERR_NONE 0
#define LIVEKIT_ERR_INVALID_ARG 1
#define LIVEKIT_ERR_ENGINE 2
#define ENGINE_ERR_NONE 0
typedef void *livekit_room_handle_t;
typedef int livekit_err_t;
typedef struct {void *engine,*rpc_manager,*data_stream_reader,*data_stream_writer;} livekit_room_t;
static bool done;static int freed;
static void livekit_room_close(void *p){}
static int engine_destroy(void *p){return done?0:1;}
static void rpc_manager_destroy(void *p){freed++;}
static void data_stream_reader_destroy(void *p){freed++;}
static void data_stream_writer_destroy(void *p){freed++;}
"""
        code += function("livekit.c", "livekit_err_t livekit_room_destroy(")
        code += r"""
int main(void){livekit_room_t *r=calloc(1,sizeof(*r));r->engine=(void*)1;
 assert(livekit_room_destroy(r)==LIVEKIT_ERR_ENGINE);assert(freed==0 && r->engine);
 done=true;assert(livekit_room_destroy(r)==0);assert(freed==3);}
"""
        run(code)

    def test_signalling_send_is_bounded_and_close_stops_even_connecting(self):
        code = r"""
#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdlib.h>
#define SIGNAL_ERR_NONE 0
#define SIGNAL_ERR_INVALID_ARG 1
#define SIGNAL_ERR_MESSAGE 2
#define SIGNAL_ERR_NO_MEM 3
#define SIGNAL_WS_NETWORK_TIMEOUT_MS 10000
#define pdMS_TO_TICKS(x) (x)
typedef int signal_err_t;
typedef void *signal_handle_t;
typedef struct {void *ws;} signal_t;
typedef struct {int unused;} livekit_pb_signal_request_t;
static int stops, sends;
static size_t protocol_signal_request_encoded_size(void *p){return 4;}
static bool protocol_signal_request_encode(void *p,void *b,size_t n){return true;}
static int esp_websocket_client_send_bin(void *ws,const char *p,int n,unsigned timeout){
 assert(timeout==SIGNAL_WS_NETWORK_TIMEOUT_MS);++sends;return -1;
}
static int esp_websocket_client_stop(void *ws){++stops;return 0;}
"""
        code += function("signaling.c", "static signal_err_t send_request(")
        code += function("signaling.c", "signal_err_t signal_close(")
        code += r"""
int main(void){signal_t s={.ws=(void*)1};livekit_pb_signal_request_t r={0};
 assert(send_request(&s,&r)==SIGNAL_ERR_MESSAGE && sends==1);
 assert(signal_close(&s)==SIGNAL_ERR_NONE && stops==1);
 assert(signal_close(NULL)==SIGNAL_ERR_INVALID_ARG && stops==1);}
"""
        run(code)


if __name__ == "__main__":
    unittest.main()
