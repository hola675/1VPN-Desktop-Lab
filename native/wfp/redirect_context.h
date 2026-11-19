#pragma once
#include <cstdint>

constexpr std::uint32_t ONETUNNEL_REDIRECT_MAGIC = 0x4352544f; // "OTRC" LE
constexpr std::uint16_t ONETUNNEL_REDIRECT_VERSION = 1;

#pragma pack(push, 1)
struct OneTunnelRedirectContext {
    std::uint32_t magic;
    std::uint16_t version;
    std::uint16_t family;       // AF_INET or AF_INET6
    std::uint16_t remotePort;   // host byte order
    std::uint16_t reserved;
    std::uint8_t remoteAddress[16]; // network-order bytes; IPv4 uses first 4
};
#pragma pack(pop)

static_assert(sizeof(OneTunnelRedirectContext) == 28, "redirect context ABI changed");
