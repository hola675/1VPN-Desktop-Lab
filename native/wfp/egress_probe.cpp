// OneTunnel transparent-WFP certification probe.
// Makes one HTTPS request with WinHTTP explicitly configured as NO_PROXY.
// It does not accept proxy settings and does not modify Windows networking.

#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <winhttp.h>
#include <ws2tcpip.h>

#include <algorithm>
#include <cctype>
#include <iostream>
#include <string>
#include <vector>

#pragma comment(lib, "winhttp.lib")
#pragma comment(lib, "ws2_32.lib")

namespace {
struct InternetHandle {
    HINTERNET value = nullptr;
    explicit InternetHandle(HINTERNET h = nullptr) : value(h) {}
    InternetHandle(const InternetHandle&) = delete;
    InternetHandle& operator=(const InternetHandle&) = delete;
    ~InternetHandle() { if (value) WinHttpCloseHandle(value); }
    explicit operator bool() const { return value != nullptr; }
};

std::string trim_ascii(std::string value) {
    while (!value.empty() && std::isspace(static_cast<unsigned char>(value.front())))
        value.erase(value.begin());
    while (!value.empty() && std::isspace(static_cast<unsigned char>(value.back())))
        value.pop_back();
    return value;
}

bool valid_ip(const std::string& text) {
    IN_ADDR v4{};
    IN6_ADDR v6{};
    return InetPtonA(AF_INET, text.c_str(), &v4) == 1 ||
           InetPtonA(AF_INET6, text.c_str(), &v6) == 1;
}

int self_test() {
    if (!valid_ip("203.0.113.10")) return 1;
    if (!valid_ip("2001:db8::1")) return 2;
    if (valid_ip("not-an-ip")) return 3;
    if (trim_ascii("  203.0.113.10\r\n") != "203.0.113.10") return 4;
    std::cout << "PASS no-proxy HTTPS probe self-test\n";
    return 0;
}

int run_probe() {
    InternetHandle session(WinHttpOpen(
        L"OneTunnel-Egress-Probe/0.1",
        WINHTTP_ACCESS_TYPE_NO_PROXY,
        WINHTTP_NO_PROXY_NAME,
        WINHTTP_NO_PROXY_BYPASS,
        0));
    if (!session) return 10;

    DWORD timeout = 15000;
    WinHttpSetTimeouts(session.value, timeout, timeout, timeout, timeout);

    InternetHandle connect(WinHttpConnect(
        session.value, L"api.ipify.org", INTERNET_DEFAULT_HTTPS_PORT, 0));
    if (!connect) return 11;

    InternetHandle request(WinHttpOpenRequest(
        connect.value, L"GET", L"/",
        nullptr, WINHTTP_NO_REFERER,
        WINHTTP_DEFAULT_ACCEPT_TYPES, WINHTTP_FLAG_SECURE));
    if (!request) return 12;

    const wchar_t headers[] = L"Accept: text/plain\r\nConnection: close\r\n";
    if (!WinHttpSendRequest(
            request.value, headers, static_cast<DWORD>(-1L),
            WINHTTP_NO_REQUEST_DATA, 0, 0, 0))
        return 13;
    if (!WinHttpReceiveResponse(request.value, nullptr)) return 14;

    DWORD status = 0;
    DWORD statusSize = sizeof(status);
    if (!WinHttpQueryHeaders(
            request.value, WINHTTP_QUERY_STATUS_CODE | WINHTTP_QUERY_FLAG_NUMBER,
            WINHTTP_HEADER_NAME_BY_INDEX, &status, &statusSize,
            WINHTTP_NO_HEADER_INDEX) || status != 200)
        return 15;

    std::string body;
    while (body.size() < 128) {
        DWORD available = 0;
        if (!WinHttpQueryDataAvailable(request.value, &available)) return 16;
        if (available == 0) break;
        const DWORD want = std::min<DWORD>(available, 128 - static_cast<DWORD>(body.size()));
        std::vector<char> buffer(want);
        DWORD read = 0;
        if (!WinHttpReadData(request.value, buffer.data(), want, &read)) return 17;
        body.append(buffer.data(), read);
        if (read == 0) break;
    }

    body = trim_ascii(body);
    if (!valid_ip(body)) return 18;
    std::cout << "PASS " << body << "\n";
    return 0;
}
}

int wmain(int argc, wchar_t** argv) {
    if (argc == 2 && std::wstring(argv[1]) == L"--self-test") return self_test();
    if (argc == 2 && std::wstring(argv[1]) == L"--version") {
        std::wcout << L"OneTunnel Egress Probe 0.1 (WinHTTP NO_PROXY)\n";
        return 0;
    }
    if (argc != 1) {
        std::wcerr << L"Usage: onetunnel-egress-probe [--self-test|--version]\n";
        return 2;
    }
    return run_probe();
}
