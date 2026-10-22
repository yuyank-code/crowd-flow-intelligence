from .base import CameraAdapter, Capabilities, TestResult


class UsbAdapter(CameraAdapter):
    """USB cameras live on the operator's machine; a local agent (Phase 4/5) must expose them.

    The backend cannot enumerate or open a remote user's USB device, so until an agent is connected the
    honest status is 'agent_offline'.
    """
    source_type = "usb"
    capabilities = Capabilities()

    async def test(self, endpoint, creds, timeout):
        return TestResult("agent_offline", "local_agent_required", "no local agent is connected for this USB camera")
