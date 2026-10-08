"""Compile the production lifecycle handlers with deterministic IO fakes."""
import pathlib
import subprocess
import tempfile
import unittest

SOURCE = pathlib.Path(__file__).parents[1] / 'components/livekit/core/engine.c'

def function(source, name):
    start = source.index('static ', source.index('// MARK: - State: Backoff')) if name == 'handle_state_backoff' else source.index('static void ' + name + '(')
    opening = source.index('{', start)
    depth = 1
    end = opening + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]

class LifecycleTest(unittest.TestCase):
    def test_close_and_remote_leave_are_terminal_even_during_backoff(self):
        source = SOURCE.read_text()
        code = r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <inttypes.h>
#define CONFIG_LK_MAX_RETRIES 3
#define ESP_LOGI(...) ((void)0)
enum { ENGINE_STATE_DISCONNECTED, ENGINE_STATE_CONNECTING, ENGINE_STATE_BACKOFF };
enum { _EV_STATE_ENTER, _EV_STATE_EXIT, EV_MAX_RETRIES_REACHED, EV_TIMER_EXP, EV_CMD_CLOSE, EV_SIG_RES };
enum { LIVEKIT_PB_SIGNAL_RESPONSE_LEAVE_TAG, LIVEKIT_FAILURE_REASON_MAX_RETRIES };
typedef struct { int reason; } livekit_pb_leave_request_t;
typedef struct { int which_message; struct { livekit_pb_leave_request_t leave; } message; } livekit_pb_signal_response_t;
typedef struct { int type; struct { livekit_pb_signal_response_t res; } detail; } engine_event_t;
typedef struct { int state, retry_count, failure_reason; } engine_t;
static void cleanup_previous_connection(engine_t *e) {}
static void event_enqueue(engine_t *e,const engine_event_t *v,bool front) {}
static uint16_t backoff_ms_for_attempt(int attempt) { return 10; }
static void timer_start(engine_t *e,int ms) {}
static void timer_stop(engine_t *e) {}
static int map_disconnect_reason(int reason) { return reason; }
'''
        code += function(source, 'handle_state_backoff')
        code += r'''
int main(void) {
 engine_t e = {.state=ENGINE_STATE_BACKOFF};
 engine_event_t close = {.type=EV_CMD_CLOSE};
 handle_state_backoff(&e,&close);
 assert(e.state==ENGINE_STATE_DISCONNECTED);
 e.state=ENGINE_STATE_BACKOFF;
 engine_event_t leave={.type=EV_SIG_RES,.detail.res={.which_message=LIVEKIT_PB_SIGNAL_RESPONSE_LEAVE_TAG,.message.leave={.reason=42}}};
 handle_state_backoff(&e,&leave);
 assert(e.state==ENGINE_STATE_DISCONNECTED && e.failure_reason==42);
 e.state=ENGINE_STATE_BACKOFF;
 engine_event_t timer={.type=EV_TIMER_EXP};
 handle_state_backoff(&e,&timer);
 assert(e.state==ENGINE_STATE_CONNECTING);
}
'''
        with tempfile.TemporaryDirectory() as d:
            path=pathlib.Path(d)
            (path/'test.c').write_text(code)
            subprocess.run(['cc','-std=c11',str(path/'test.c'),'-o',str(path/'test')],check=True)
            subprocess.run([str(path/'test')],check=True)

    def test_transition_exits_old_state_before_entering_new_state(self):
        code = r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#define ESP_LOGD(...) ((void)0)
#define ESP_LOGE(...) ((void)0)
#define portMAX_DELAY 0
typedef int engine_state_t;
typedef int livekit_connection_state_t;
enum { OLD_STATE, NEW_STATE };
enum { CLOSE, _EV_STATE_ENTER, _EV_STATE_EXIT };
typedef struct { int type; } engine_event_t;
typedef struct { bool is_running; int state, event_queue, task_done_sem;
 struct { void (*on_state_changed)(int,void*); void *ctx; } options;
} engine_t;
static int order;
static bool xQueueReceive(int q,engine_event_t *ev,int delay) { ev->type=CLOSE; return true; }
static bool handle_state(engine_t *e,engine_event_t *ev,int state) {
 if(ev->type==CLOSE) { e->state=NEW_STATE; e->is_running=false; }
 else if(ev->type==_EV_STATE_EXIT) { assert(state==OLD_STATE && order++==0); }
 else if(ev->type==_EV_STATE_ENTER) { assert(state==NEW_STATE && order++==1); }
 return false;
}
static void event_free(engine_event_t *ev) {}
static bool map_engine_state(engine_t *e,int *out) { return false; }
static void flush_event_queue(engine_t *e) {}
static void cleanup_previous_connection(engine_t *e) { assert(order==2); }
static void xSemaphoreGive(int sem) {}
static void vTaskDelete(void *task) {}
'''
        code += function(SOURCE.read_text(), 'engine_task')
        code += 'int main(void) { engine_t e={.is_running=true,.state=OLD_STATE}; engine_task(&e); assert(order==2); }'
        with tempfile.TemporaryDirectory() as d:
            path=pathlib.Path(d)
            (path/'test.c').write_text(code)
            subprocess.run(['cc','-std=c11',str(path/'test.c'),'-o',str(path/'test')],check=True)
            subprocess.run([str(path/'test')],check=True)

if __name__ == '__main__': unittest.main()
