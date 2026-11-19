// OneTunnel transparent relay (user mode).
// Accepts ONLY sockets redirected by our future WFP ALE_CONNECT_REDIRECT callout,
// obtains the original destination from SIO_QUERY_WFP_CONNECTION_REDIRECT_CONTEXT,
// and sends TCP through OneTunnel's local SOCKS5 listener.
//
// This binary does NOT install filters or drivers. Without the signed callout
// driver, it has no transparent interception function.

#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <winsock2.h>
#include <ws2tcpip.h>
#include <mstcpip.h>
#include <windows.h>

#include <algorithm>
#include <array>
#include <atomic>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <string>
#include <thread>
#include <vector>

#include "redirect_context.h"

#pragma comment(lib, "Ws2_32.lib")

namespace {
constexpr std::uint16_t kDefaultListenPort = 10900;
constexpr std::uint16_t kDefaultSocksPort = 1080;
constexpr long kHandshakeTimeoutMs = 15000;
constexpr int kMaxConcurrent = 128;

struct Winsock {
    bool ok = false;
    Winsock() {
        WSADATA data{};
        ok = WSAStartup(MAKEWORD(2, 2), &data) == 0;
    }
    ~Winsock() { if (ok) WSACleanup(); }
};

struct Socket {
    SOCKET value = INVALID_SOCKET;
    Socket() = default;
    explicit Socket(SOCKET s) : value(s) {}
    Socket(const Socket&) = delete;
    Socket& operator=(const Socket&) = delete;
    Socket(Socket&& other) noexcept : value(other.value) {
        other.value = INVALID_SOCKET;
    }
    Socket& operator=(Socket&& other) noexcept {
        if (this != &other) {
            if (value != INVALID_SOCKET) closesocket(value);
            value = other.value;
            other.value = INVALID_SOCKET;
        }
        return *this;
    }
    ~Socket() { if (value != INVALID_SOCKET) closesocket(value); }
    explicit operator bool() const { return value != INVALID_SOCKET; }
};

bool send_all(SOCKET s, const std::uint8_t* data, std::size_t size) {
    while (size) {
        int sent = send(s, reinterpret_cast<const char*>(data),
                        static_cast<int>(std::min<std::size_t>(size, 1 << 20)), 0);
        if (sent <= 0) return false;
        data += sent;
        size -= static_cast<std::size_t>(sent);
    }
    return true;
}

bool recv_exact(SOCKET s, std::uint8_t* data, std::size_t size) {
    while (size) {
        int got = recv(s, reinterpret_cast<char*>(data),
                       static_cast<int>(std::min<std::size_t>(size, 1 << 20)), 0);
        if (got <= 0) return false;
        data += got;
        size -= static_cast<std::size_t>(got);
    }
    return true;
}

std::vector<std::uint8_t> socks_request(const OneTunnelRedirectContext& ctx) {
    if (ctx.magic != ONETUNNEL_REDIRECT_MAGIC ||
        ctx.version != ONETUNNEL_REDIRECT_VERSION ||
        ctx.remotePort == 0 ||
        (ctx.family != AF_INET && ctx.family != AF_INET6)) {
        return {};
    }
    std::vector<std::uint8_t> out{0x05, 0x01, 0x00};
    if (ctx.family == AF_INET) {
        out.push_back(0x01);
        out.insert(out.end(), ctx.remoteAddress, ctx.remoteAddress + 4);
    } else {
        out.push_back(0x04);
        out.insert(out.end(), ctx.remoteAddress, ctx.remoteAddress + 16);
    }
    out.push_back(static_cast<std::uint8_t>((ctx.remotePort >> 8) & 0xff));
    out.push_back(static_cast<std::uint8_t>(ctx.remotePort & 0xff));
    return out;
}

bool query_redirect_context(SOCKET client, OneTunnelRedirectContext& ctx) {
    DWORD returned = 0;
    std::memset(&ctx, 0, sizeof(ctx));
    const int result = WSAIoctl(
        client, SIO_QUERY_WFP_CONNECTION_REDIRECT_CONTEXT,
        nullptr, 0, &ctx, sizeof(ctx), &returned, nullptr, nullptr);
    return result == 0 && returned == sizeof(ctx) &&
           ctx.magic == ONETUNNEL_REDIRECT_MAGIC &&
           ctx.version == ONETUNNEL_REDIRECT_VERSION;
}

bool query_redirect_records(SOCKET client, std::vector<std::uint8_t>& records) {
    for (std::size_t size = 2048; size <= 65536; size *= 2) {
        records.assign(size, 0);
        DWORD returned = 0;
        const int result = WSAIoctl(
            client, SIO_QUERY_WFP_CONNECTION_REDIRECT_RECORDS,
            nullptr, 0, records.data(), static_cast<DWORD>(records.size()),
            &returned, nullptr, nullptr);
        if (result == 0) {
            records.resize(returned);
            return !records.empty();
        }
        const int error = WSAGetLastError();
        if (error != WSAEFAULT && error != WSAENOBUFS && error != WSAEINVAL)
            break;
    }
    records.clear();
    return false;
}

bool apply_redirect_records(SOCKET outgoing, const std::vector<std::uint8_t>& records) {
    if (records.empty()) return false;
    DWORD returned = 0;
    return WSAIoctl(
        outgoing, SIO_SET_WFP_CONNECTION_REDIRECT_RECORDS,
        const_cast<std::uint8_t*>(records.data()),
        static_cast<DWORD>(records.size()),
        nullptr, 0, &returned, nullptr, nullptr) == 0;
}

Socket connect_local_socks(std::uint16_t port,
                           const std::vector<std::uint8_t>& records) {
    Socket sock(WSASocketW(AF_INET, SOCK_STREAM, IPPROTO_TCP, nullptr, 0, 0));
    if (!sock) return {};
    if (!apply_redirect_records(sock.value, records)) return {};

    sockaddr_in address{};
    address.sin_family = AF_INET;
    address.sin_port = htons(port);
    address.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    if (connect(sock.value, reinterpret_cast<sockaddr*>(&address),
                sizeof(address)) != 0) return {};
    return sock;
}

bool socks5_connect(SOCKET socket, const OneTunnelRedirectContext& context) {
    const std::array<std::uint8_t, 3> hello{0x05, 0x01, 0x00};
    if (!send_all(socket, hello.data(), hello.size())) return false;
    std::array<std::uint8_t, 2> choice{};
    if (!recv_exact(socket, choice.data(), choice.size()) ||
        choice[0] != 0x05 || choice[1] != 0x00) return false;

    auto request = socks_request(context);
    if (request.empty() || !send_all(socket, request.data(), request.size()))
        return false;

    std::array<std::uint8_t, 4> header{};
    if (!recv_exact(socket, header.data(), header.size()) ||
        header[0] != 0x05 || header[1] != 0x00 || header[2] != 0x00)
        return false;

    std::size_t tail = 0;
    if (header[3] == 0x01) tail = 4 + 2;
    else if (header[3] == 0x04) tail = 16 + 2;
    else if (header[3] == 0x03) {
        std::uint8_t length = 0;
        if (!recv_exact(socket, &length, 1)) return false;
        tail = static_cast<std::size_t>(length) + 2;
    } else return false;
    std::vector<std::uint8_t> discard(tail);
    return recv_exact(socket, discard.data(), discard.size());
}

void pump(SOCKET a, SOCKET b) {
    std::array<char, 32768> buffer{};
    while (true) {
        fd_set read{};
        FD_ZERO(&read);
        FD_SET(a, &read);
        FD_SET(b, &read);
        const int ready = select(0, &read, nullptr, nullptr, nullptr);
        if (ready <= 0) break;
        for (SOCKET source : {a, b}) {
            if (!FD_ISSET(source, &read)) continue;
            const SOCKET target = source == a ? b : a;
            const int got = recv(source, buffer.data(),
                                 static_cast<int>(buffer.size()), 0);
            if (got <= 0) return;
            if (!send_all(target,
                reinterpret_cast<const std::uint8_t*>(buffer.data()),
                static_cast<std::size_t>(got))) return;
        }
    }
}

void handle_client(Socket client, std::uint16_t socksPort,
                   std::atomic<int>& concurrent) {
    struct Count {
        std::atomic<int>& value;
        ~Count() { --value; }
    } count{concurrent};

    DWORD timeout = kHandshakeTimeoutMs;
    setsockopt(client.value, SOL_SOCKET, SO_RCVTIMEO,
               reinterpret_cast<const char*>(&timeout), sizeof(timeout));
    setsockopt(client.value, SOL_SOCKET, SO_SNDTIMEO,
               reinterpret_cast<const char*>(&timeout), sizeof(timeout));

    OneTunnelRedirectContext context{};
    std::vector<std::uint8_t> records;
    // Fail closed: this listener must never become a generic localhost proxy.
    if (!query_redirect_context(client.value, context) ||
        !query_redirect_records(client.value, records)) return;

    Socket upstream = connect_local_socks(socksPort, records);
    if (!upstream || !socks5_connect(upstream.value, context)) return;

    timeout = 0;
    setsockopt(client.value, SOL_SOCKET, SO_RCVTIMEO,
               reinterpret_cast<const char*>(&timeout), sizeof(timeout));
    setsockopt(upstream.value, SOL_SOCKET, SO_RCVTIMEO,
               reinterpret_cast<const char*>(&timeout), sizeof(timeout));
    pump(client.value, upstream.value);
}

Socket make_listener(int family, std::uint16_t port) {
    Socket listener(WSASocketW(family, SOCK_STREAM, IPPROTO_TCP, nullptr, 0, 0));
    if (!listener) return {};
    BOOL exclusive = TRUE;
    setsockopt(listener.value, SOL_SOCKET, SO_EXCLUSIVEADDRUSE,
               reinterpret_cast<const char*>(&exclusive), sizeof(exclusive));
    if (family == AF_INET) {
        sockaddr_in address{};
        address.sin_family = AF_INET;
        address.sin_port = htons(port);
        address.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
        if (bind(listener.value, reinterpret_cast<sockaddr*>(&address),
                 sizeof(address)) != 0) return {};
    } else {
        sockaddr_in6 address{};
        address.sin6_family = AF_INET6;
        address.sin6_port = htons(port);
        address.sin6_addr = in6addr_loopback;
        if (bind(listener.value, reinterpret_cast<sockaddr*>(&address),
                 sizeof(address)) != 0) return {};
    }
    if (listen(listener.value, SOMAXCONN) != 0) return {};
    return listener;
}

bool parse_port(const wchar_t* value, std::uint16_t& port) {
    try {
        unsigned long parsed = std::stoul(value);
        if (parsed == 0 || parsed > 65535) return false;
        port = static_cast<std::uint16_t>(parsed);
        return true;
    } catch (...) { return false; }
}

int self_test() {
    OneTunnelRedirectContext v4{};
    v4.magic = ONETUNNEL_REDIRECT_MAGIC;
    v4.version = ONETUNNEL_REDIRECT_VERSION;
    v4.family = AF_INET;
    v4.remotePort = 443;
    v4.remoteAddress[0] = 1; v4.remoteAddress[1] = 2;
    v4.remoteAddress[2] = 3; v4.remoteAddress[3] = 4;
    const std::vector<std::uint8_t> expected{
        0x05,0x01,0x00,0x01,1,2,3,4,0x01,0xbb
    };
    if (socks_request(v4) != expected) return 1;

    OneTunnelRedirectContext invalid = v4;
    invalid.magic = 0;
    if (!socks_request(invalid).empty()) return 2;

    OneTunnelRedirectContext v6 = v4;
    v6.family = AF_INET6;
    std::fill(std::begin(v6.remoteAddress), std::end(v6.remoteAddress), 0);
    v6.remoteAddress[15] = 1;
    if (socks_request(v6).size() != 22) return 3;

    std::cout << "PASS redirect-context/socks5 self-test\n";
    return 0;
}
}

int wmain(int argc, wchar_t** argv) {
    if (argc == 2 && std::wstring(argv[1]) == L"--self-test") return self_test();
    if (argc == 2 && std::wstring(argv[1]) == L"--version") {
        std::wcout << L"OneTunnel Transparent Relay 0.1 (driver required)\n";
        return 0;
    }

    std::uint16_t listenPort = kDefaultListenPort;
    std::uint16_t socksPort = kDefaultSocksPort;
    for (int i = 1; i < argc; ++i) {
        const std::wstring arg(argv[i]);
        if (arg == L"--listen-port" && i + 1 < argc) {
            if (!parse_port(argv[++i], listenPort)) return 2;
        } else if (arg == L"--socks-port" && i + 1 < argc) {
            if (!parse_port(argv[++i], socksPort)) return 2;
        } else {
            std::wcerr << L"Usage: onetunnel-transparent-relay "
                          L"[--listen-port N] [--socks-port N]\n";
            return 2;
        }
    }

    Winsock winsock;
    if (!winsock.ok) return 3;
    Socket v4 = make_listener(AF_INET, listenPort);
    Socket v6 = make_listener(AF_INET6, listenPort);
    if (!v4 || !v6) {
        std::wcerr << L"Could not bind transparent relay loopback listeners.\n";
        return 4;
    }

    std::atomic<int> concurrent{0};
    std::wcout << L"READY " << listenPort << L" " << socksPort << std::endl;
    while (true) {
        fd_set read{};
        FD_ZERO(&read);
        FD_SET(v4.value, &read);
        FD_SET(v6.value, &read);
        if (select(0, &read, nullptr, nullptr, nullptr) <= 0) break;
        for (SOCKET listener : {v4.value, v6.value}) {
            if (!FD_ISSET(listener, &read)) continue;
            Socket client(accept(listener, nullptr, nullptr));
            if (!client) continue;
            if (concurrent.load() >= kMaxConcurrent) continue;
            ++concurrent;
            std::thread(handle_client, std::move(client),
                        socksPort, std::ref(concurrent)).detach();
        }
    }
    return 0;
}
