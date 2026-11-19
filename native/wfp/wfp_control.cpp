// OneTunnel WFP user-mode control plane.
// Adds only dynamic (non-persistent) BFE objects for explicitly supplied EXE paths.
// It NEVER installs/loads a driver and refuses to add filters if the kernel
// callouts are not already registered.

#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <winsock2.h>
#include <windows.h>
#include <fwpmu.h>
#include <rpc.h>

#include <algorithm>
#include <cstdint>
#include <iostream>
#include <set>
#include <string>
#include <vector>

#include "redirect_contract.h"
#include "redirect_ids.h"

#pragma comment(lib, "Fwpuclnt.lib")
#pragma comment(lib, "Rpcrt4.lib")

namespace {
struct Engine {
    HANDLE value = nullptr;
    ~Engine() { if (value) FwpmEngineClose0(value); }
    Engine(const Engine&) = delete;
    Engine& operator=(const Engine&) = delete;
    Engine() = default;
};

bool valid_exe(const std::wstring& path) {
    if (path.size() < 7 || path[1] != L':' ||
        (path[2] != L'\\' && path[2] != L'/')) return false;
    if (path.find(L'"') != std::wstring::npos ||
        path.find(L'\n') != std::wstring::npos ||
        path.find(L'\r') != std::wstring::npos) return false;
    auto dot = path.size() >= 4 ? path.substr(path.size() - 4) : L"";
    std::transform(dot.begin(), dot.end(), dot.begin(), towlower);
    if (dot != L".exe") return false;
    DWORD attrs = GetFileAttributesW(path.c_str());
    return attrs != INVALID_FILE_ATTRIBUTES && !(attrs & FILE_ATTRIBUTE_DIRECTORY);
}

bool parse_u16(const wchar_t* raw, std::uint16_t& value) {
    try {
        unsigned long parsed = std::stoul(raw);
        if (!parsed || parsed > 65535) return false;
        value = static_cast<std::uint16_t>(parsed);
        return true;
    } catch (...) { return false; }
}

bool parse_u64(const wchar_t* raw, std::uint64_t& value) {
    try {
        unsigned long long parsed = std::stoull(raw);
        if (!parsed) return false;
        value = static_cast<std::uint64_t>(parsed);
        return true;
    } catch (...) { return false; }
}

DWORD add_provider_and_callouts(HANDLE engine) {
    FWPM_PROVIDER0 provider{};
    provider.providerKey = ONETUNNEL_WFP_PROVIDER;
    provider.displayData.name = const_cast<wchar_t*>(L"OneTunnel Native WFP");
    provider.displayData.description =
        const_cast<wchar_t*>(L"Dynamic per-application redirect provider");
    DWORD error = FwpmProviderAdd0(engine, &provider, nullptr);
    if (error != ERROR_SUCCESS) return error;

    FWPM_SUBLAYER0 sublayer{};
    sublayer.subLayerKey = ONETUNNEL_WFP_SUBLAYER;
    sublayer.displayData.name =
        const_cast<wchar_t*>(L"OneTunnel per-application redirect");
    sublayer.providerKey = const_cast<GUID*>(&ONETUNNEL_WFP_PROVIDER);
    sublayer.weight = 0x4000;
    error = FwpmSubLayerAdd0(engine, &sublayer, nullptr);
    if (error != ERROR_SUCCESS) return error;

    struct Pair { const GUID* key; const GUID* layer; const wchar_t* name; };
    const Pair pairs[] = {
        {&ONETUNNEL_CALLOUT_CONNECT_V4, &FWPM_LAYER_ALE_CONNECT_REDIRECT_V4,
         L"OneTunnel TCP connect redirect IPv4"},
        {&ONETUNNEL_CALLOUT_CONNECT_V6, &FWPM_LAYER_ALE_CONNECT_REDIRECT_V6,
         L"OneTunnel TCP connect redirect IPv6"},
    };
    for (const auto& pair : pairs) {
        FWPM_CALLOUT0 callout{};
        callout.calloutKey = *pair.key;
        callout.displayData.name = const_cast<wchar_t*>(pair.name);
        callout.flags = FWPM_CALLOUT_FLAG_USES_PROVIDER_CONTEXT;
        callout.providerKey = const_cast<GUID*>(&ONETUNNEL_WFP_PROVIDER);
        callout.applicableLayer = *pair.layer;
        error = FwpmCalloutAdd0(engine, &callout, nullptr, nullptr);
        if (error != ERROR_SUCCESS) return error;
    }
    return ERROR_SUCCESS;
}

bool callout_registered(HANDLE engine, const GUID& key) {
    FWPM_CALLOUT0* result = nullptr;
    DWORD error = FwpmCalloutGetByKey0(engine, &key, &result);
    if (error != ERROR_SUCCESS || !result) return false;
    const bool registered =
        (result->flags & FWPM_CALLOUT_FLAG_REGISTERED) != 0;
    FwpmFreeMemory0(reinterpret_cast<void**>(&result));
    return registered;
}

DWORD add_context_and_filters(
    HANDLE engine,
    const GUID& contextKey,
    OneTunnelRedirectConfig& config,
    const std::vector<std::wstring>& apps)
{
    FWP_BYTE_BLOB blob{};
    blob.size = sizeof(config);
    blob.data = reinterpret_cast<UINT8*>(&config);

    FWPM_PROVIDER_CONTEXT0 context{};
    context.providerContextKey = contextKey;
    context.displayData.name =
        const_cast<wchar_t*>(L"OneTunnel relay session context");
    context.providerKey = const_cast<GUID*>(&ONETUNNEL_WFP_PROVIDER);
    context.type = FWPM_GENERAL_CONTEXT;
    context.dataBuffer = &blob;
    DWORD error = FwpmProviderContextAdd0(engine, &context, nullptr, nullptr);
    if (error != ERROR_SUCCESS) return error;

    struct Layer {
        const GUID* layer;
        const GUID* callout;
        const wchar_t* name;
    };
    const Layer layers[] = {
        {&FWPM_LAYER_ALE_CONNECT_REDIRECT_V4,
         &ONETUNNEL_CALLOUT_CONNECT_V4,
         L"OneTunnel PROXY TCP IPv4"},
        {&FWPM_LAYER_ALE_CONNECT_REDIRECT_V6,
         &ONETUNNEL_CALLOUT_CONNECT_V6,
         L"OneTunnel PROXY TCP IPv6"},
    };

    for (const auto& app : apps) {
        FWP_BYTE_BLOB* appId = nullptr;
        error = FwpmGetAppIdFromFileName0(app.c_str(), &appId);
        if (error != ERROR_SUCCESS || !appId) return error;

        for (const auto& layer : layers) {
            FWPM_FILTER_CONDITION0 conditions[2]{};
            conditions[0].fieldKey = FWPM_CONDITION_ALE_APP_ID;
            conditions[0].matchType = FWP_MATCH_EQUAL;
            conditions[0].conditionValue.type = FWP_BYTE_BLOB_TYPE;
            conditions[0].conditionValue.byteBlob = appId;

            conditions[1].fieldKey = FWPM_CONDITION_IP_PROTOCOL;
            conditions[1].matchType = FWP_MATCH_EQUAL;
            conditions[1].conditionValue.type = FWP_UINT8;
            conditions[1].conditionValue.uint8 = IPPROTO_TCP;

            FWPM_FILTER0 filter{};
            filter.displayData.name = const_cast<wchar_t*>(layer.name);
            filter.flags = FWPM_FILTER_FLAG_HAS_PROVIDER_CONTEXT;
            filter.providerKey = const_cast<GUID*>(&ONETUNNEL_WFP_PROVIDER);
            filter.layerKey = *layer.layer;
            filter.subLayerKey = ONETUNNEL_WFP_SUBLAYER;
            filter.weight.type = FWP_EMPTY;
            filter.numFilterConditions = ARRAYSIZE(conditions);
            filter.filterCondition = conditions;
            filter.action.type = FWP_ACTION_CALLOUT_TERMINATING;
            filter.action.calloutKey = *layer.callout;
            filter.providerContextKey = contextKey;

            error = FwpmFilterAdd0(engine, &filter, nullptr, nullptr);
            if (error != ERROR_SUCCESS) break;
        }

        FwpmFreeMemory0(reinterpret_cast<void**>(&appId));
        if (error != ERROR_SUCCESS) return error;
    }
    return ERROR_SUCCESS;
}

DWORD configure_session(
    Engine& engine,
    std::uint64_t relayPid,
    std::uint16_t relayPort,
    const std::vector<std::wstring>& apps)
{
    FWPM_SESSION0 session{};
    session.displayData.name =
        const_cast<wchar_t*>(L"OneTunnel dynamic PROXY session");
    session.flags = FWPM_SESSION_FLAG_DYNAMIC;
    session.txnWaitTimeoutInMSec = 5000;

    DWORD error = FwpmEngineOpen0(
        nullptr, RPC_C_AUTHN_WINNT, nullptr, &session, &engine.value);
    if (error != ERROR_SUCCESS) return error;

    error = FwpmTransactionBegin0(engine.value, 0);
    if (error != ERROR_SUCCESS) return error;
    error = add_provider_and_callouts(engine.value);
    if (error == ERROR_SUCCESS) error = FwpmTransactionCommit0(engine.value);
    else FwpmTransactionAbort0(engine.value);
    if (error != ERROR_SUCCESS) return error;

    // Never create traffic filters unless the .sys callouts are already loaded.
    if (!callout_registered(engine.value, ONETUNNEL_CALLOUT_CONNECT_V4) ||
        !callout_registered(engine.value, ONETUNNEL_CALLOUT_CONNECT_V6)) {
        return ERROR_SERVICE_NOT_ACTIVE;
    }

    GUID contextKey{};
    RPC_STATUS uuidStatus = UuidCreate(&contextKey);
    if (uuidStatus != RPC_S_OK && uuidStatus != RPC_S_UUID_LOCAL_ONLY)
        return ERROR_GEN_FAILURE;

    OneTunnelRedirectConfig config{};
    config.magic = ONETUNNEL_CONFIG_MAGIC;
    config.version = ONETUNNEL_CONFIG_VERSION;
    config.relayPort = relayPort;
    config.relayProcessId = relayPid;

    error = FwpmTransactionBegin0(engine.value, 0);
    if (error != ERROR_SUCCESS) return error;
    error = add_context_and_filters(
        engine.value, contextKey, config, apps);
    if (error == ERROR_SUCCESS) error = FwpmTransactionCommit0(engine.value);
    else FwpmTransactionAbort0(engine.value);
    return error;
}

int self_test() {
    if (sizeof(OneTunnelRedirectConfig) != 16 ||
        sizeof(OneTunnelRedirectContext) != 28) return 1;
    if (ONETUNNEL_CONFIG_MAGIC == ONETUNNEL_REDIRECT_MAGIC) return 2;
    std::uint16_t port = 0;
    std::uint64_t pid = 0;
    if (!parse_u16(L"10900", port) || port != 10900) return 3;
    if (!parse_u64(L"1234", pid) || pid != 1234) return 4;
    std::wcout << L"PASS WFP control-plane offline self-test\n";
    return 0;
}
}

int wmain(int argc, wchar_t** argv) {
    if (argc == 2 && std::wstring(argv[1]) == L"--self-test")
        return self_test();
    if (argc == 2 && std::wstring(argv[1]) == L"--version") {
        std::wcout << L"OneTunnel WFP Control 0.1 (dynamic session)\n";
        return 0;
    }

    std::uint16_t relayPort = 0;
    std::uint64_t relayPid = 0;
    std::vector<std::wstring> apps;
    for (int i = 1; i < argc; ++i) {
        const std::wstring arg(argv[i]);
        if (arg == L"--relay-port" && i + 1 < argc) {
            if (!parse_u16(argv[++i], relayPort)) return 2;
        } else if (arg == L"--relay-pid" && i + 1 < argc) {
            if (!parse_u64(argv[++i], relayPid)) return 2;
        } else if (arg == L"--app" && i + 1 < argc) {
            std::wstring path(argv[++i]);
            if (!valid_exe(path)) return 2;
            apps.push_back(path);
        } else {
            std::wcerr << L"Usage: onetunnel-wfp-control --relay-pid PID "
                          L"--relay-port PORT --app C:\\path\\app.exe [--app ...]\n";
            return 2;
        }
    }
    if (!relayPort || !relayPid || apps.empty() || apps.size() > 24) return 2;

    std::set<std::wstring> unique;
    std::vector<std::wstring> normalized;
    for (const auto& app : apps) {
        std::wstring key = app;
        std::transform(key.begin(), key.end(), key.begin(), towlower);
        if (unique.insert(key).second) normalized.push_back(app);
    }

    Engine engine;
    DWORD error = configure_session(
        engine, relayPid, relayPort, normalized);
    if (error != ERROR_SUCCESS) {
        std::wcerr << L"WFP control plane failed: " << error << L"\n";
        return error == ERROR_SERVICE_NOT_ACTIVE ? 4 : 3;
    }

    std::wcout << L"READY " << normalized.size() << std::endl;
    std::wstring command;
    while (std::getline(std::wcin, command)) {
        if (command == L"stop") break;
    }
    // Closing the dynamic engine session removes all filters/callouts/context.
    return 0;
}
