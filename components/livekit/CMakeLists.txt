# IDF 6 moved the bundled cJSON out of the tree into the espressif/cjson
# managed component; IDF 5.x still provides it as the builtin 'json'.
if(IDF_VERSION_MAJOR GREATER_EQUAL 6)
    set(LIVEKIT_CJSON_REQ espressif__cjson)
else()
    set(LIVEKIT_CJSON_REQ json)
endif()

idf_component_register(
    SRC_DIRS ./core ./protocol
    PRIV_INCLUDE_DIRS ./core ./protocol
    INCLUDE_DIRS ./include
    REQUIRES
        av_render
        esp_capture
        media_lib_sal
    PRIV_REQUIRES
        esp_netif
        esp_peer
        esp_websocket_client
        ${LIVEKIT_CJSON_REQ}
        khash
        mbedtls
        nanopb
)

idf_component_get_property(LIVEKIT_SDK_VERSION ${COMPONENT_NAME} COMPONENT_VERSION)
target_compile_definitions(${COMPONENT_LIB} PUBLIC "LIVEKIT_SDK_VERSION=\"${LIVEKIT_SDK_VERSION}\"")

# -Wconversion is this SDK's own quality gate, but IDF builds with -Werror and
# IDF's own RISC-V headers (riscv/rv_utils.h, riscv/csr.h) trip
# -Wsign-conversion. On Xtensa that never showed. Keep the warning, but do not
# fail the build on diagnostics originating in IDF headers we do not own.
target_compile_options(${COMPONENT_LIB} PRIVATE "-Wconversion" "-Wno-error=sign-conversion")