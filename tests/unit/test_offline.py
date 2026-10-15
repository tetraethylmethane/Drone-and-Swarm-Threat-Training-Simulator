"""No telemetry or external runtime dependencies (brief §11 offline operation)."""

from __future__ import annotations

import importlib.util
from importlib.metadata import distributions

TELEMETRY_EXPORTERS = ("opentelemetry-sdk", "opentelemetry-exporter", "sentry-sdk", "datadog", "newrelic", "posthog")


def test_no_telemetry_sdk_or_exporter_installed() -> None:
    # FastAPI depends on the opentelemetry *API* package, which is a no-op without an SDK.
    names = {d.metadata["Name"].lower() for d in distributions()}
    offenders = sorted(n for n in names if n.startswith(TELEMETRY_EXPORTERS))
    assert offenders == [], f"telemetry SDK/exporter installed: {offenders}"
    assert importlib.util.find_spec("opentelemetry.sdk") is None


def test_tracer_provider_is_noop() -> None:
    from opentelemetry import trace

    import drikr_api.main  # noqa: F401  (import the application as deployed)

    provider = trace.get_tracer_provider()
    assert type(provider).__name__ in {"ProxyTracerProvider", "NoOpTracerProvider"}
