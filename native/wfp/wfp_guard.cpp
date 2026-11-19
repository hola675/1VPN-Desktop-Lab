// OneTunnel native WFP blocker — Windows SDK only (no Windows Firewall cmdlets).
// Explicit user consent + administrator rights required. No persistent WFP rules.
// Upon process death, the dynamic session automatically removes its filters.
// PROXY redirection requires a separate signed WFP callout driver — not here.

#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <fwpmu.h>
#include <rpc.h>
#include <algorithm>
#include <cwctype>
#include <iostream>
#include <string>
#include <vector>

namespace {
struct Engine {
    HANDLE handle = nullptr;
    ~Engine() { if (handle) FwpmEngineClose0(handle); }
    Engine(const Engine&) = delete;
    Engine& operator=(const Engine&) = delete;
    Engine() = default;
};
struct AppId {
    FWP_BYTE_BLOB* data = nullptr;
    ~AppId() { if (data) FwpmFreeMemory0(reinterpret_cast<void**>(&data)); }
    AppId(const AppId&) = delete;
    AppId& operator=(const AppId&) = delete;
    AppId() = default;
};

std::wstring basename(std::wstring p) {
    auto slash = p.find_last_of(L"\\/");
    if (slash != std::wstring::npos) p = p.substr(slash + 1);
    std::transform(p.begin(), p.end(), p.begin(), [](wchar_t c) {
        return static_cast<wchar_t>(towlower(c));
    });
    return p;
}

bool safe_exe(const std::wstring& path) {
    if (path.size() < 7 || path[1] != L':' ||
        (path[2] != L'\\' && path[2] != L'/')) return false;
    if (path.find(L'\"') != path.npos || path.find(L'\n') != path.npos ||
        path.find(L'\r') != path.npos) return false;
    auto name = basename(path);
    if (name.size() < 5 || name.substr(name.size() - 4) != L".exe") return false;
    constexpr const wchar_t* forbidden[] = {
        L"onetunnel-wfp-guard.exe", L"1vpn-desktop-lab.exe",
        L"proxifyre.exe", L"xray.exe", L"python.exe", L"pythonw.exe",
        L"svchost.exe", L"lsass.exe", L"services.exe", L"winlogon.exe",
        L"smss.exe", L"csrss.exe", L"dwm.exe",
        L"system.exe", L"systemsettings.exe"
    };
    for (auto item : forbidden) if (name == item) return false;
    DWORD attrs = GetFileAttributesW(path.c_str());
    return attrs != INVALID_FILE_ATTRIBUTES && !(attrs & FILE_ATTRIBUTE_DIRECTORY);
}

DWORD add_app_block(HANDLE engine, const GUID& sublayer, const std::wstring& path) {
    AppId app;
    DWORD result = FwpmGetAppIdFromFileName0(path.c_str(), &app.data);
    if (result != ERROR_SUCCESS) return result;
    FWPM_FILTER_CONDITION0 condition{};
    condition.fieldKey = FWPM_CONDITION_ALE_APP_ID;
    condition.matchType = FWP_MATCH_EQUAL;
    condition.conditionValue.type = FWP_BYTE_BLOB_TYPE;
    condition.conditionValue.byteBlob = app.data;

    for (const GUID* layer : {&FWPM_LAYER_ALE_AUTH_CONNECT_V4,
                               &FWPM_LAYER_ALE_AUTH_CONNECT_V6}) {
        FWPM_FILTER0 filter{};
        filter.displayData.name = const_cast<wchar_t*>(L"OneTunnel temporary outbound application block");
        filter.layerKey = *layer;
        filter.subLayerKey = sublayer;
        filter.action.type = FWP_ACTION_BLOCK;
        filter.weight.type = FWP_EMPTY;
        filter.numFilterConditions = 1;
        filter.filterCondition = &condition;
        result = FwpmFilterAdd0(engine, &filter, nullptr, nullptr);
        if (result != ERROR_SUCCESS) return result;
    }
    return ERROR_SUCCESS;
}
}

int wmain(int argc, wchar_t** argv) {
    // This first native milestone deliberately implements BLOCK only.
    // It MUST NOT be used to claim transparent TCP/UDP redirect or kill switch.
    if (argc == 2 && std::wstring(argv[1]) == L"--version") {
        std::wcout << L"OneTunnel Native WFP Guard 0.1 (BLOCK only)\n";
        return 0;
    }
    bool dry_run = argc > 2 && std::wstring(argv[1]) == L"--dry-run";
    bool block = argc > 2 && std::wstring(argv[1]) == L"--block";
    if (!dry_run && !block) {
        std::wcerr << L"Usage: onetunnel-wfp-guard --dry-run|--block absolute.exe [...]\n";
        return 2;
    }
    if (argc > 27) {
        std::wcerr << L"Too many target executables.\n";
        return 2;
    }
    std::vector<std::wstring> paths;
    for (int i = 2; i < argc; ++i) {
        std::wstring path(argv[i]);
        if (!safe_exe(path)) {
            std::wcerr << L"Refusing missing, system, or unsafe EXE.\n";
            return 2;
        }
        paths.push_back(path);
    }
    if (paths.empty()) return 2;
    if (dry_run) {
        std::wcout << L"VALID " << paths.size() << L" (no filters installed)\n";
        return 0;
    }

    Engine engine;
    FWPM_SESSION0 session{};
    session.flags = FWPM_SESSION_FLAG_DYNAMIC;
    session.displayData.name = const_cast<wchar_t*>(L"OneTunnel ephemeral blocker");
    DWORD error = FwpmEngineOpen0(nullptr, RPC_C_AUTHN_WINNT, nullptr,
                                  &session, &engine.handle);
    if (error != ERROR_SUCCESS) {
        std::wcerr << L"WFP engine unavailable or requires administrator: " << error << L"\n";
        return 3;
    }

    FWPM_SUBLAYER0 sublayer{};
    RPC_STATUS uuid = UuidCreate(&sublayer.subLayerKey);
    if (uuid != RPC_S_OK && uuid != RPC_S_UUID_LOCAL_ONLY) return 3;
    sublayer.displayData.name = const_cast<wchar_t*>(L"OneTunnel temporary isolation");
    sublayer.weight = 0x4000;

    error = FwpmTransactionBegin0(engine.handle, 0);
    if (error != ERROR_SUCCESS) return 4;
    error = FwpmSubLayerAdd0(engine.handle, &sublayer, nullptr);
    for (const auto& path : paths) {
        if (error != ERROR_SUCCESS) break;
        error = add_app_block(engine.handle, sublayer.subLayerKey, path);
    }
    if (error == ERROR_SUCCESS) error = FwpmTransactionCommit0(engine.handle);
    else FwpmTransactionAbort0(engine.handle);
    if (error != ERROR_SUCCESS) {
        std::wcerr << L"WFP could not install temporary filters, code " << error << L"\n";
        return 4;
    }

    // Parent owns our stdin pipe. On explicit STOP or parent crash/EOF,
    // the process ends and BFE removes all dynamic filters automatically.
    std::wcout << L"READY " << paths.size() << std::endl;
    std::wstring input;
    while (std::getline(std::wcin, input)) {
        if (input == L"stop") break;
    }
    return 0;
}
