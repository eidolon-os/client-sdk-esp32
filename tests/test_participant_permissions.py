"""Compile the production public participant converter and verify permission edges."""
import pathlib,subprocess,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
def definition(s,needle):
 a=s.index(needle);p=s.index('{',a)+1;depth=1
 while depth:
  depth+=(s[p]=='{')-(s[p]=='}');p+=1
 return s[a:p]
class ParticipantPermissionsTest(unittest.TestCase):
 def test_public_callback_retains_locality_and_permissions(self):
  h=(ROOT/'components/livekit/include/livekit.h').read_text()
  end=h.index('} livekit_participant_info_t;')+len('} livekit_participant_info_t;')
  begin=h.rfind('typedef struct {',0,end)
  code='''#include <stdbool.h>
#include <stddef.h>
#include <assert.h>
#include <string.h>
typedef int livekit_participant_kind_t;
typedef int livekit_participant_state_t;
'''+h[begin:end]+'''
typedef struct { const char *sid,*identity,*name,*metadata; int kind,state; struct { bool can_publish,can_subscribe,can_publish_data; } permission; } livekit_pb_participant_info_t;
typedef struct { struct { void (*on_participant_info)(const livekit_participant_info_t*,void*); void *ctx; } options; } livekit_room_t;
static livekit_participant_info_t received;
static int calls;
static void collect(const livekit_participant_info_t *info,void *ctx) { assert(ctx==(void*)7);received=*info;++calls; }
'''+definition((ROOT/'components/livekit/core/livekit.c').read_text(),'static void on_eng_participant_info(')+'''
int main(void) {
 livekit_room_t room={.options={.on_participant_info=collect,.ctx=(void*)7}};
 livekit_pb_participant_info_t p={.sid="PA_local",.identity="device",.name="name",.metadata="metadata",.kind=0,.state=2,.permission={.can_publish=true,.can_subscribe=true,.can_publish_data=true}};
 on_eng_participant_info(&p,true,&room);
 assert(calls==1 && received.is_local && received.can_publish && received.can_subscribe && received.can_publish_data);
 assert(received.identity==p.identity && received.sid==p.sid && received.metadata==p.metadata && received.state==2);
 p.permission.can_publish=false;on_eng_participant_info(&p,true,&room);
 assert(calls==2 && received.is_local && !received.can_publish && received.can_subscribe && received.can_publish_data);
 p.permission.can_subscribe=false;p.permission.can_publish_data=false;on_eng_participant_info(&p,false,&room);
 assert(calls==3 && !received.is_local && !received.can_subscribe && !received.can_publish_data);
 room.options.on_participant_info=NULL;on_eng_participant_info(&p,true,&room);assert(calls==3);
}
'''
  with tempfile.TemporaryDirectory() as d:
   p=pathlib.Path(d);(p/'test.c').write_text(code)
   subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',str(p/'test.c'),'-o',str(p/'test')],check=True)
   subprocess.run([str(p/'test')],check=True)
if __name__=='__main__':unittest.main()
