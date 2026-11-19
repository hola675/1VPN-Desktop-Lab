/*
 * OneTunnel WFP connect-redirection callout (kernel-mode).
 *
 * This driver registers callout functions only. User mode must explicitly add
 * FWPM callout/filter/provider-context objects for selected applications.
 * It is not installed or loaded automatically by CI or the desktop app yet.
 *
 * Target: Windows 11 x64. TCP only. Fail-closed for a selected PROXY filter
 * if the redirect cannot be applied; unrelated traffic is never seen unless
 * user mode installs a matching filter.
 */
#include <ntddk.h>
#include <fwpsk.h>
#include <fwpmk.h>
#include <ws2def.h>
#include <ws2ipdef.h>

#include "../wfp/redirect_contract.h"
#include "../wfp/redirect_ids.h"

#define OT_POOL_TAG 'rtTO'

static PDEVICE_OBJECT g_deviceObject = NULL;
static HANDLE g_redirectHandle = NULL;
static UINT32 g_calloutIdV4 = 0;
static UINT32 g_calloutIdV6 = 0;

static BOOLEAN OtConfigFromFilter(
    _In_ const FWPS_FILTER0* filter,
    _Out_ OneTunnelRedirectConfig* config)
{
    if (!filter || !filter->providerContext ||
        filter->providerContext->type != FWPM_GENERAL_CONTEXT ||
        !filter->providerContext->dataBuffer ||
        filter->providerContext->dataBuffer->size != sizeof(*config) ||
        !filter->providerContext->dataBuffer->data) {
        return FALSE;
    }

    RtlCopyMemory(config,
                  filter->providerContext->dataBuffer->data,
                  sizeof(*config));
    return config->magic == ONETUNNEL_CONFIG_MAGIC &&
           config->version == ONETUNNEL_CONFIG_VERSION &&
           config->relayPort != 0 &&
           config->relayProcessId != 0;
}

static BOOLEAN OtCaptureDestination(
    _In_ const SOCKADDR_STORAGE* address,
    _Out_ OneTunnelRedirectContext* context)
{
    RtlZeroMemory(context, sizeof(*context));
    context->magic = ONETUNNEL_REDIRECT_MAGIC;
    context->version = ONETUNNEL_REDIRECT_VERSION;

    if (address->ss_family == AF_INET) {
        const SOCKADDR_IN* v4 = (const SOCKADDR_IN*)address;
        context->family = AF_INET;
        context->remotePort = RtlUshortByteSwap(v4->sin_port);
        RtlCopyMemory(context->remoteAddress, &v4->sin_addr, 4);
        return context->remotePort != 0;
    }

    if (address->ss_family == AF_INET6) {
        const SOCKADDR_IN6* v6 = (const SOCKADDR_IN6*)address;
        context->family = AF_INET6;
        context->remotePort = RtlUshortByteSwap(v6->sin6_port);
        RtlCopyMemory(context->remoteAddress, &v6->sin6_addr, 16);
        return context->remotePort != 0;
    }

    return FALSE;
}

static BOOLEAN OtAlreadyTargetsRelay(
    _In_ const SOCKADDR_STORAGE* address,
    _In_ OT_U16 relayPort)
{
    const USHORT port = RtlUshortByteSwap(relayPort);

    if (address->ss_family == AF_INET) {
        const SOCKADDR_IN* v4 = (const SOCKADDR_IN*)address;
        return v4->sin_port == port &&
               v4->sin_addr.S_un.S_addr == RtlUlongByteSwap(INADDR_LOOPBACK);
    }

    if (address->ss_family == AF_INET6) {
        const SOCKADDR_IN6* v6 = (const SOCKADDR_IN6*)address;
        static const UCHAR loopback[16] =
            {0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1};
        return v6->sin6_port == port &&
               RtlCompareMemory(&v6->sin6_addr, loopback, 16) == 16;
    }

    return FALSE;
}

static VOID OtSetRelayAddress(
    _Inout_ SOCKADDR_STORAGE* address,
    _In_ OT_U16 relayPort)
{
    if (address->ss_family == AF_INET) {
        SOCKADDR_IN* v4 = (SOCKADDR_IN*)address;
        v4->sin_port = RtlUshortByteSwap(relayPort);
        v4->sin_addr.S_un.S_addr = RtlUlongByteSwap(INADDR_LOOPBACK);
    } else if (address->ss_family == AF_INET6) {
        SOCKADDR_IN6* v6 = (SOCKADDR_IN6*)address;
        static const UCHAR loopback[16] =
            {0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1};
        v6->sin6_port = RtlUshortByteSwap(relayPort);
        RtlCopyMemory(&v6->sin6_addr, loopback, 16);
    }
}

static VOID NTAPI OtClassifyConnectRedirect(
    _In_ const FWPS_INCOMING_VALUES0* inFixedValues,
    _In_ const FWPS_INCOMING_METADATA_VALUES0* inMetaValues,
    _Inout_opt_ VOID* layerData,
    _In_opt_ const VOID* classifyContext,
    _In_ const FWPS_FILTER0* filter,
    _In_ UINT64 flowContext,
    _Inout_ FWPS_CLASSIFY_OUT0* classifyOut)
{
    UINT64 classifyHandle = 0;
    PVOID writableData = NULL;
    OneTunnelRedirectConfig config = {0};
    OneTunnelRedirectContext* context = NULL;
    FWPS_CONNECT_REQUEST0* request = NULL;
    NTSTATUS status;
    BOOLEAN writableAcquired = FALSE;
    BOOLEAN applied = FALSE;

    UNREFERENCED_PARAMETER(layerData);
    UNREFERENCED_PARAMETER(flowContext);

    if (!inFixedValues || !inMetaValues || !filter || !classifyOut ||
        !(classifyOut->rights & FWPS_RIGHT_ACTION_WRITE)) {
        return;
    }

    /* Only TCP can use the current OneTunnel SOCKS5 CONNECT dataplane. */
    if (inFixedValues->layerId == FWPS_LAYER_ALE_CONNECT_REDIRECT_V4) {
        if (inFixedValues->incomingValue[
                FWPS_FIELD_ALE_CONNECT_REDIRECT_V4_IP_PROTOCOL].value.uint8
            != IPPROTO_TCP) {
            classifyOut->actionType = FWP_ACTION_PERMIT;
            return;
        }
    } else if (inFixedValues->layerId == FWPS_LAYER_ALE_CONNECT_REDIRECT_V6) {
        if (inFixedValues->incomingValue[
                FWPS_FIELD_ALE_CONNECT_REDIRECT_V6_IP_PROTOCOL].value.uint8
            != IPPROTO_TCP) {
            classifyOut->actionType = FWP_ACTION_PERMIT;
            return;
        }
    } else {
        classifyOut->actionType = FWP_ACTION_PERMIT;
        return;
    }

    if (!OtConfigFromFilter(filter, &config) ||
        !g_redirectHandle ||
        !classifyContext) {
        classifyOut->actionType = FWP_ACTION_BLOCK;
        return;
    }

    /* Never redirect a connection already handled by this redirector. */
    if (FWPS_IS_METADATA_FIELD_PRESENT(
            inMetaValues, FWPS_METADATA_FIELD_REDIRECT_RECORD_HANDLE)) {
        PVOID oldContext = NULL;
        FWPS_CONNECTION_REDIRECT_STATE state =
            FwpsQueryConnectionRedirectState0(
                inMetaValues->redirectRecords,
                g_redirectHandle,
                &oldContext);
        if (state != FWPS_CONNECTION_NOT_REDIRECTED) {
            classifyOut->actionType = FWP_ACTION_PERMIT;
            return;
        }
    }

    status = FwpsAcquireClassifyHandle0(
        (PVOID)classifyContext, 0, &classifyHandle);
    if (!NT_SUCCESS(status)) goto FailClosed;

    status = FwpsAcquireWritableLayerDataPointer0(
        classifyHandle,
        filter->filterId,
        0,
        &writableData,
        classifyOut);
    if (!NT_SUCCESS(status) || !writableData) goto FailClosed;
    writableAcquired = TRUE;
    request = (FWPS_CONNECT_REQUEST0*)writableData;

    if (OtAlreadyTargetsRelay(&request->remoteAddressAndPort,
                              config.relayPort)) {
        status = FwpsApplyModifiedLayerData0(classifyHandle, request, 0);
        applied = NT_SUCCESS(status);
        goto Permit;
    }

    context = (OneTunnelRedirectContext*)ExAllocatePool2(
        POOL_FLAG_NON_PAGED, sizeof(*context), OT_POOL_TAG);
    if (!context ||
        !OtCaptureDestination(&request->remoteAddressAndPort, context)) {
        goto FailClosed;
    }

    OtSetRelayAddress(&request->remoteAddressAndPort, config.relayPort);
    request->localRedirectHandle = g_redirectHandle;
    request->localRedirectTargetPID = config.relayProcessId;
    request->localRedirectContext = context;
    request->localRedirectContextSize = sizeof(*context);

    status = FwpsApplyModifiedLayerData0(classifyHandle, request, 0);
    if (!NT_SUCCESS(status)) goto FailClosed;

    /* WFP owns localRedirectContext after successful apply. */
    context = NULL;
    applied = TRUE;

Permit:
    classifyOut->actionType = FWP_ACTION_PERMIT;
    classifyOut->rights &= ~FWPS_RIGHT_ACTION_WRITE;
    goto Exit;

FailClosed:
    /*
     * Once FwpsAcquireWritableLayerDataPointer succeeds, pair it with Apply.
     * If a prior error occurred, apply the unmodified request only to complete
     * writable-layer bookkeeping, then still BLOCK this selected PROXY flow.
     */
    if (writableAcquired && !applied && request) {
        (VOID)FwpsApplyModifiedLayerData0(classifyHandle, request, 0);
    }
    classifyOut->actionType = FWP_ACTION_BLOCK;
    classifyOut->rights &= ~FWPS_RIGHT_ACTION_WRITE;

Exit:
    if (context) ExFreePoolWithTag(context, OT_POOL_TAG);
    if (classifyHandle) FwpsReleaseClassifyHandle0(classifyHandle);
}

static NTSTATUS NTAPI OtNotify(
    _In_ FWPS_CALLOUT_NOTIFY_TYPE notifyType,
    _In_ const GUID* filterKey,
    _Inout_ FWPS_FILTER0* filter)
{
    UNREFERENCED_PARAMETER(notifyType);
    UNREFERENCED_PARAMETER(filterKey);
    UNREFERENCED_PARAMETER(filter);
    return STATUS_SUCCESS;
}

static VOID OtUnregister(VOID)
{
    if (g_calloutIdV6) {
        FwpsCalloutUnregisterById0(g_calloutIdV6);
        g_calloutIdV6 = 0;
    }
    if (g_calloutIdV4) {
        FwpsCalloutUnregisterById0(g_calloutIdV4);
        g_calloutIdV4 = 0;
    }
    if (g_redirectHandle) {
        FwpsRedirectHandleDestroy0(g_redirectHandle);
        g_redirectHandle = NULL;
    }
}

static VOID OtUnload(_In_ PDRIVER_OBJECT driverObject)
{
    UNREFERENCED_PARAMETER(driverObject);
    OtUnregister();
    if (g_deviceObject) {
        IoDeleteDevice(g_deviceObject);
        g_deviceObject = NULL;
    }
}

NTSTATUS DriverEntry(
    _In_ PDRIVER_OBJECT driverObject,
    _In_ PUNICODE_STRING registryPath)
{
    UNICODE_STRING deviceName =
        RTL_CONSTANT_STRING(L"\\Device\\OneTunnelWfpRedirect");
    FWPS_CALLOUT0 callout = {0};
    NTSTATUS status;

    UNREFERENCED_PARAMETER(registryPath);

    driverObject->DriverUnload = OtUnload;

    status = IoCreateDevice(
        driverObject, 0, &deviceName,
        FILE_DEVICE_NETWORK, 0, FALSE, &g_deviceObject);
    if (!NT_SUCCESS(status)) return status;

    status = FwpsRedirectHandleCreate0(
        &ONETUNNEL_WFP_PROVIDER, 0, &g_redirectHandle);
    if (!NT_SUCCESS(status)) goto Fail;

    callout.calloutKey = ONETUNNEL_CALLOUT_CONNECT_V4;
    callout.classifyFn = OtClassifyConnectRedirect;
    callout.notifyFn = OtNotify;
    status = FwpsCalloutRegister0(
        g_deviceObject, &callout, &g_calloutIdV4);
    if (!NT_SUCCESS(status)) goto Fail;

    RtlZeroMemory(&callout, sizeof(callout));
    callout.calloutKey = ONETUNNEL_CALLOUT_CONNECT_V6;
    callout.classifyFn = OtClassifyConnectRedirect;
    callout.notifyFn = OtNotify;
    status = FwpsCalloutRegister0(
        g_deviceObject, &callout, &g_calloutIdV6);
    if (!NT_SUCCESS(status)) goto Fail;

    return STATUS_SUCCESS;

Fail:
    OtUnregister();
    if (g_deviceObject) {
        IoDeleteDevice(g_deviceObject);
        g_deviceObject = NULL;
    }
    return status;
}
