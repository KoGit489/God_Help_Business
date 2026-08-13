from __future__ import annotations

import os
from dataclasses import asdict, dataclass


@dataclass
class CameraAdapterStatus:
    provider: str
    mode: str
    supports_web_browser: bool = True
    supports_native_app: bool = False
    sdk_available: bool = False
    supports_direct_sdk: bool = False
    browser_upload_supported: bool = True
    manual_upload_supported: bool = True
    real_time_feed_supported: bool = False
    integration_ready: bool = False
    recommended_action: str = "Use the browser upload path for now."
    reason: str | None = None

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


class Insta360CameraAdapter:
    """Thin adapter layer for the Insta360 ONE X2 capture flow.

    The app keeps the browser workflow as the default and makes any direct SDK
    integration opt-in via environment configuration. This avoids blocking web-based
    testing while leaving a clean extension point for future SDK use.
    """

    def __init__(self, mode: str | None = None):
        configured = (mode or os.getenv("INSTA360_MODE", "manual_upload")).strip().lower()
        self.mode = configured if configured in {"manual_upload", "sdk", "native_app", "disabled"} else "manual_upload"
        self.sdk_enabled = os.getenv("INSTA360_SDK_ENABLED", "false").strip().lower() in {"1", "true", "yes"}
        self.native_app_enabled = os.getenv("INSTA360_NATIVE_APP_ENABLED", "false").strip().lower() in {"1", "true", "yes"}
        self.real_time_feed_enabled = os.getenv("INSTA360_REALTIME_FEED_ENABLED", "false").strip().lower() in {"1", "true", "yes"}

    @property
    def supports_direct_sdk(self) -> bool:
        return self.mode == "sdk" and self.sdk_enabled

    @property
    def supports_real_time_feed(self) -> bool:
        return self.supports_direct_sdk and self.real_time_feed_enabled

    def status(self) -> CameraAdapterStatus:
        if self.mode == "disabled":
            return CameraAdapterStatus(
                provider="insta360",
                mode="disabled",
                supports_web_browser=True,
                supports_native_app=False,
                sdk_available=False,
                browser_upload_supported=True,
                manual_upload_supported=True,
                real_time_feed_supported=False,
                integration_ready=False,
                recommended_action="Disable the camera integration and keep the web upload workflow active for testing.",
                reason="Camera integration is turned off by configuration.",
            )

        if self.supports_direct_sdk:
            return CameraAdapterStatus(
                provider="insta360",
                mode="sdk",
                supports_web_browser=True,
                supports_native_app=self.native_app_enabled,
                sdk_available=True,
                supports_direct_sdk=True,
                browser_upload_supported=True,
                manual_upload_supported=True,
                real_time_feed_supported=self.supports_real_time_feed,
                integration_ready=self.supports_real_time_feed,
                recommended_action="Use direct SDK access only when the camera SDK is available and authenticated.",
                reason="Direct API integration is configured and ready for SDK-backed capture.",
            )

        if self.mode == "native_app":
            return CameraAdapterStatus(
                provider="insta360",
                mode="native_app",
                supports_web_browser=True,
                supports_native_app=self.native_app_enabled,
                sdk_available=self.sdk_enabled,
                supports_direct_sdk=False,
                browser_upload_supported=True,
                manual_upload_supported=True,
                real_time_feed_supported=False,
                integration_ready=False,
                recommended_action="Keep the browser workflow active. Native app support is optional and should not block the ONE X2 testing path.",
                reason="Native app support is enabled, but direct SDK access is not configured.",
            )

        return CameraAdapterStatus(
            provider="insta360",
            mode="manual_upload",
            supports_web_browser=True,
            supports_native_app=self.native_app_enabled,
            sdk_available=self.sdk_enabled,
            supports_direct_sdk=False,
            browser_upload_supported=True,
            manual_upload_supported=True,
            real_time_feed_supported=False,
            integration_ready=False,
            recommended_action="Use the browser upload flow for now and preserve the original .insp capture for downstream processing.",
            reason="Browser-first upload mode is active; direct SDK integration is not required for testing.",
        )

    def upload_strategy(self) -> str:
        if self.supports_direct_sdk:
            return "sdk"
        if self.mode == "native_app":
            return "native_app"
        return "manual_upload"
