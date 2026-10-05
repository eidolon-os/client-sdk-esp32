"""Compile production peer_create and inspect its native configurations."""
import pathlib, subprocess, tempfile, unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]

def definition(source, start):
    begin=source.index(start); opening=source.index('{',begin);depth=1;end=opening+1
    while depth:
        depth+=(source[end]=='{')-(source[end]=='}');end+=1
    return source[begin:end]

class ReceiveOnlyTest(unittest.TestCase):
    def test_receive_only_preserves_no_publish_and_other_peer_modes(self):
        source=(ROOT/'components/livekit/core/peer.c').read_text()
        code=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#define ESP_LOGD(...) ((void)0)
#define ESP_LOGE(...) ((void)0)
#define ESP_PEER_ERR_NONE 0
#define ESP_PEER_ROLE_CONTROLLED 0
#define ESP_PEER_ROLE_CONTROLLING 1
#define ESP_PEER_ICE_TRANS_POLICY_RELAY 0
#define ESP_PEER_ICE_TRANS_POLICY_ALL 1
#define CONNECTION_STATE_DISCONNECTED 0
#define STREAM_ID_INVALID 0xffff
typedef enum { ESP_PEER_MEDIA_DIR_NONE=0, ESP_PEER_MEDIA_DIR_SEND_ONLY=1, ESP_PEER_MEDIA_DIR_RECV_ONLY=2, ESP_PEER_MEDIA_DIR_SEND_RECV=3 } esp_peer_media_dir_t;
typedef enum { PEER_ROLE_PUBLISHER, PEER_ROLE_SUBSCRIBER } peer_role_t;
typedef enum { ESP_PEER_AUDIO_CODEC_NONE, ESP_PEER_AUDIO_CODEC_G711A, ESP_PEER_AUDIO_CODEC_G711U, ESP_PEER_AUDIO_CODEC_OPUS } esp_peer_audio_codec_t;
enum { ESP_PEER_VIDEO_CODEC_NONE, ESP_PEER_VIDEO_CODEC_MJPEG };
typedef struct { esp_peer_audio_codec_t codec; uint32_t sample_rate; uint8_t channel; } esp_peer_audio_stream_info_t;
typedef struct { int codec,width,height,fps; } video_info_t;
typedef struct { esp_peer_media_dir_t audio_dir,video_dir; esp_peer_audio_stream_info_t audio_info; video_info_t video_info; } media_t;
typedef struct { peer_role_t role; void *on_state_changed,*on_sdp,*ctx,*server_list; media_t *media; int server_count; bool force_relay,enable_data_channel; } peer_options_t;
typedef void *peer_handle_t;
typedef struct { peer_options_t options; int ice_role,state; void *connection,*wait_event; uint16_t reliable_stream_id,lossy_stream_id; bool tcp_support,ipv6_support; } peer_t;
typedef int peer_err_t;
enum { PEER_ERR_NONE, PEER_ERR_INVALID_ARG, PEER_ERR_NO_MEM, PEER_ERR_RTC };
typedef struct { struct { int cache_timeout,send_cache_size,recv_cache_size; } data_ch_cfg; bool tcp_support,ipv6_support; } esp_peer_default_cfg_t;
typedef struct { void *server_lists; int server_num,ice_trans_policy; esp_peer_media_dir_t audio_dir,video_dir; esp_peer_audio_stream_info_t audio_info; video_info_t video_info; bool enable_data_channel,manual_ch_create,no_auto_reconnect; void *extra_cfg; int extra_size; void *on_state,*on_msg,*on_video_info,*on_audio_info,*on_video_data,*on_audio_data,*on_channel_open,*on_channel_close,*on_data,*ctx; int role; } esp_peer_cfg_t;
static esp_peer_cfg_t received;
static void media_lib_event_group_create(void **handle) { *handle=(void*)1; }
static void media_lib_event_group_destroy(void *handle) {}
static void *esp_peer_get_default_impl(void) { return NULL; }
static int esp_peer_open(esp_peer_cfg_t *cfg,void *impl,void **handle) {
 received=*cfg;
 if(cfg->audio_dir && cfg->audio_info.codec==ESP_PEER_AUDIO_CODEC_NONE) return -1;
 *handle=(void*)1; return 0;
}
'''
        code+='static void *on_state,*on_msg,*on_video_info,*on_audio_info,*on_video_data,*on_audio_data,*on_channel_open,*on_channel_close,*on_data;\n'
        code+=definition(source,'static esp_peer_media_dir_t get_media_direction(')
        code+=definition(source,'peer_err_t peer_create(')
        code+=r'''
static void create(peer_options_t *o) { peer_handle_t h=NULL; assert(peer_create(&h,o)==PEER_ERR_NONE); assert(h); free(h); }
int main(void) {
 media_t m={.audio_dir=ESP_PEER_MEDIA_DIR_RECV_ONLY};
 peer_options_t o={.role=PEER_ROLE_PUBLISHER,.enable_data_channel=true,.media=&m,.on_state_changed=(void*)1,.on_sdp=(void*)1};
 create(&o); assert(received.audio_dir==ESP_PEER_MEDIA_DIR_NONE); assert(received.audio_info.codec==ESP_PEER_AUDIO_CODEC_NONE);
 o.role=PEER_ROLE_SUBSCRIBER; o.enable_data_channel=false;
 create(&o); assert(received.audio_dir==ESP_PEER_MEDIA_DIR_RECV_ONLY); assert(received.audio_info.codec==ESP_PEER_AUDIO_CODEC_OPUS); assert(received.audio_info.sample_rate==48000 && received.audio_info.channel==1);
 assert(m.audio_info.codec==ESP_PEER_AUDIO_CODEC_NONE && m.audio_dir==ESP_PEER_MEDIA_DIR_RECV_ONLY);
 m.audio_dir=ESP_PEER_MEDIA_DIR_SEND_RECV; m.audio_info=(esp_peer_audio_stream_info_t){.codec=ESP_PEER_AUDIO_CODEC_G711U,.sample_rate=8000,.channel=1};
 create(&o); assert(received.audio_info.codec==ESP_PEER_AUDIO_CODEC_G711U && received.audio_info.sample_rate==8000);
 o.role=PEER_ROLE_PUBLISHER; create(&o); assert(received.audio_dir==ESP_PEER_MEDIA_DIR_SEND_ONLY && received.audio_info.codec==ESP_PEER_AUDIO_CODEC_G711U);
 m=(media_t){0}; create(&o); assert(received.audio_dir==ESP_PEER_MEDIA_DIR_NONE && received.audio_info.codec==ESP_PEER_AUDIO_CODEC_NONE);
}
'''
        with tempfile.TemporaryDirectory() as d:
            p=pathlib.Path(d);(p/'test.c').write_text(code)
            subprocess.run(['cc','-std=c11','-fsanitize=address,undefined',str(p/'test.c'),'-o',str(p/'test')],check=True)
            subprocess.run([str(p/'test')],check=True)

if __name__=='__main__':unittest.main()
