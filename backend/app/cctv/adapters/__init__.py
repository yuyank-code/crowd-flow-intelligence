from .base import CameraAdapter, Capabilities, TestResult
from .onvif import OnvifAdapter
from .rtsp import RtspAdapter
from .usb import UsbAdapter

ADAPTERS: dict[str, CameraAdapter] = {"rtsp": RtspAdapter(), "onvif": OnvifAdapter(), "usb": UsbAdapter()}

__all__ = ["ADAPTERS", "CameraAdapter", "Capabilities", "TestResult"]
