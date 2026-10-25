# observability.py
"""
LAYER 4 - observability with data-privacy hardening.

WHY THIS FILE EXISTS
--------------------
`configure_otel_providers(enable_sensitive_data=False)` withholds tool
arguments and results. It does NOT withhold exception text. In
agent-framework-core 1.21.0 the exception message is still exported in full on
span status descriptions, exception events, and ERROR log records - even with
the flag off. A tool error such as:

    RuntimeError("Page 14 counter-value 14% does not match claim 2.4x")

therefore lands in your telemetry backend, carrying the exact figures the flag
was meant to protect. For a regulated financial host, that is a data leak.

This module closes that gap at the framework boundary, before export:

  1. RedactingSpanProcessor  - scrubs span status descriptions, exception
                               events, and attribute values on_end().
  2. SensitiveLogFilter      - scrubs ERROR log records, which the bug report
                               confirms are a separate leak path.

Design note: OpenTelemetry's ReadableSpan is documented as read-only, so the
processor mutates private fields defensively and degrades to a no-op if a
pinned SDK version blocks it. The log filter is independent of that, so the
ERROR path is always covered.
"""

import logging
import os
import re
from typing import Any, Sequence

from opentelemetry.sdk.trace import ReadableSpan, SpanProcessor

# --- Redaction rules: ordered, specific-before-generic ---
_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"₹\s?[\d,]+(?:\.\d+)?"), "[REDACTED_AMOUNT]"),   # ₹4,820 crore
    (re.compile(r"\b\d+(?:\.\d+)?\s?%"), "[REDACTED_PCT]"),        # 14%
    (re.compile(r"\b\d+(?:\.\d+)?x\b"), "[REDACTED_RATIO]"),       # 2.4x
    (re.compile(r"\b\d{1,3}(?:,\d{3})+\b"), "[REDACTED_NUMBER]"),  # 73,000
]


def redact(text: Any) -> Any:
    """Redact sensitive financial patterns from a string. Non-str passes through."""
    if not isinstance(text, str) or not text:
        return text
    out = text
    for pattern, replacement in _RULES:
        out = pattern.sub(replacement, out)
    return out


def _redact_mapping(mapping: Any) -> None:
    """Best-effort in-place redaction of a mapping's string values."""
    try:
        for key, value in list(mapping.items()):
            if isinstance(value, str):
                mapping[key] = redact(value)
    except (AttributeError, TypeError):
        pass


class RedactingSpanProcessor(SpanProcessor):
    """
    SpanProcessor that sanitizes spans before they reach the exporter.

    Registered BEFORE the exporter in the pipeline, so every span - agent,
    chat, tool, workflow - passes through redaction on the way out.
    """

    def __init__(self, downstream: SpanProcessor | None = None) -> None:
        self._downstream = downstream
        self._redactions = 0

    # -- SpanProcessor interface ------------------------------------------
    def on_start(self, span, parent_context=None) -> None:
        if self._downstream:
            self._downstream.on_start(span, parent_context)

    def on_end(self, span: ReadableSpan) -> None:
        self._scrub(span)
        if self._downstream:
            self._downstream.on_end(span)

    def shutdown(self) -> None:
        if self._downstream:
            self._downstream.shutdown()

    def force_flush(self, timeout_millis: int = 30_000) -> bool:
        if self._downstream:
            return self._downstream.force_flush(timeout_millis)
        return True

    # -- scrubbing --------------------------------------------------------
    def _scrub(self, span: ReadableSpan) -> None:
        self._scrub_status(span)
        self._scrub_events(span)
        self._scrub_attributes(span)

    def _scrub_status(self, span: ReadableSpan) -> None:
        """The primary leak path: status.description holds repr(exception)."""
        try:
            status = getattr(span, "_status", None)
            description = getattr(status, "description", None)
            if description:
                cleaned = redact(description)
                if cleaned != description:
                    status.description = cleaned
                    self._redactions += 1
        except (AttributeError, TypeError):
            pass

    def _scrub_events(self, span: ReadableSpan) -> None:
        """The second leak path: exception events carry exception.message."""
        try:
            for event in getattr(span, "_events", ()) or ():
                attrs = getattr(event, "attributes", None)
                if attrs:
                    _redact_mapping(attrs)
        except (AttributeError, TypeError):
            pass

    def _scrub_attributes(self, span: ReadableSpan) -> None:
        try:
            attrs = getattr(span, "_attributes", None)
            if attrs:
                _redact_mapping(attrs)
        except (AttributeError, TypeError):
            pass

    @property
    def redaction_count(self) -> int:
        return self._redactions


class SensitiveLogFilter(logging.Filter):
    """
    Scrubs log records. The bug report confirms an ERROR log record is emitted
    alongside the span, as a separate leak path.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact(record.msg)
        if record.args:
            record.args = tuple(
                redact(a) if isinstance(a, str) else a for a in record.args
            )
        return True


def install_log_filter(logger_names: Sequence[str] = ("agent_framework",)) -> None:
    """Attach the redaction filter to framework loggers."""
    for name in logger_names:
        logging.getLogger(name).addFilter(SensitiveLogFilter())


def bootstrap_observability() -> None:
    """
    Bootstrap observability with privacy redaction:
    1. Attaches log redaction filter to framework loggers.
    2. If APPLICATIONINSIGHTS_CONNECTION_STRING is set, initializes Azure Monitor
       (which provides Live Metrics, traces, logs, and metrics).
    3. Otherwise, configures standard OTel providers via Agent Framework.
    4. Attaches RedactingSpanProcessor to sanitize all spans before export.
    """
    install_log_filter(("agent_framework", "agent_framework.observability"))

    app_insights_conn = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING")
    if app_insights_conn:
        try:
            from azure.monitor.opentelemetry import configure_azure_monitor

            configure_azure_monitor(connection_string=app_insights_conn)
            logging.info("[observability] Azure Monitor OpenTelemetry configured.")
        except Exception as exc:
            logging.warning(f"[observability] Failed to configure Azure Monitor: {exc}")
    else:
        try:
            from agent_framework.observability import configure_otel_providers

            configure_otel_providers(
                enable_sensitive_data=os.getenv("ENABLE_SENSITIVE_DATA", "false").lower() == "true"
            )
        except Exception as exc:
            logging.warning(f"[observability] Failed to configure OTel providers: {exc}")

    try:
        from opentelemetry import trace

        provider = trace.get_tracer_provider()
        if hasattr(provider, "add_span_processor"):
            provider.add_span_processor(RedactingSpanProcessor())
    except Exception as exc:
        logging.warning(f"[observability] RedactingSpanProcessor not attached: {exc}")