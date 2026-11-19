#pragma once

#if defined(_KERNEL_MODE) || defined(_NTDDK_) || defined(_NTIFS_)
#include <ntddk.h>
typedef UINT8  OT_U8;
typedef UINT16 OT_U16;
typedef UINT32 OT_U32;
typedef UINT64 OT_U64;
#else
#include <cstdint>
typedef std::uint8_t  OT_U8;
typedef std::uint16_t OT_U16;
typedef std::uint32_t OT_U32;
typedef std::uint64_t OT_U64;
#endif

#define ONETUNNEL_REDIRECT_MAGIC   ((OT_U32)0x4352544f) /* "OTRC" little-endian */
#define ONETUNNEL_REDIRECT_VERSION ((OT_U16)1)
#define ONETUNNEL_CONFIG_MAGIC     ((OT_U32)0x4643544f) /* "OTCF" little-endian */
#define ONETUNNEL_CONFIG_VERSION   ((OT_U16)1)

#pragma pack(push, 1)
typedef struct _OneTunnelRedirectContext {
    OT_U32 magic;
    OT_U16 version;
    OT_U16 family;          /* AF_INET / AF_INET6 */
    OT_U16 remotePort;      /* host byte order */
    OT_U16 reserved;
    OT_U8  remoteAddress[16]; /* network-order bytes; IPv4 uses first 4 */
} OneTunnelRedirectContext;

typedef struct _OneTunnelRedirectConfig {
    OT_U32 magic;
    OT_U16 version;
    OT_U16 relayPort;       /* host byte order */
    OT_U64 relayProcessId;  /* user-mode transparent relay PID */
} OneTunnelRedirectConfig;
#pragma pack(pop)

#ifdef __cplusplus
static_assert(sizeof(OneTunnelRedirectContext) == 28, "redirect context ABI changed");
static_assert(sizeof(OneTunnelRedirectConfig) == 16, "redirect config ABI changed");
#endif
