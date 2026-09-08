"""
GCP Observability Integration — Cloud Trace + Cloud Profiler + Cloud Monitoring

Initializes OpenTelemetry with Cloud Trace exporter and Cloud Profiler
for production observability on Cloud Run.

Usage in main.py:
    from infrastructure.services.gcp_observability import init_observability
    init_observability(app)
"""

import os
import logging

logger = logging.getLogger(__name__)

_INITIALIZED = False


def init_observability(app=None):
    """
    Initialize GCP observability stack:
    1. Cloud Trace via OpenTelemetry (distributed tracing)
    2. Cloud Profiler (CPU/wall profiling)
    3. Cloud Monitoring custom metrics (optional)

    Safe to call in any environment — gracefully degrades if libs are missing.
    """
    global _INITIALIZED
    if _INITIALIZED:
        return
    _INITIALIZED = True

    is_production = os.environ.get("FLASK_ENV") == "production"
    project_id = os.environ.get("GCP_PROJECT_ID")

    if not is_production:
        logger.info("⏭️  Observability: skipped (not production)")
        return

    # ── 1. Cloud Trace via OpenTelemetry ──────────────────────────
    _init_cloud_trace(project_id, app)

    # ── 2. Cloud Profiler ─────────────────────────────────────────
    _init_cloud_profiler(project_id)

    # ── 3. Cloud Monitoring (custom metrics) ──────────────────────
    _init_cloud_monitoring(project_id)


def _init_cloud_trace(project_id: str | None, app=None):
    """Initialize OpenTelemetry with Cloud Trace exporter."""
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter

        if os.environ.get("DISABLE_CLOUD_TRACE") == "1":
            logger.info("⏭️  Cloud Trace: disabled via env var")
            return

        resource = Resource.create({
            "service.name": "tivit-cu002-backend",
            "service.version": "3.0",
            "deployment.environment": "production",
        })

        tracer_provider = TracerProvider(resource=resource)
        cloud_trace_exporter = CloudTraceSpanExporter(project_id=project_id)
        tracer_provider.add_span_processor(
            BatchSpanProcessor(cloud_trace_exporter)
        )
        trace.set_tracer_provider(tracer_provider)

        # Auto-instrument Flask if available
        if app is not None:
            try:
                from opentelemetry.instrumentation.flask import FlaskInstrumentor
                FlaskInstrumentor().instrument_app(app)
                logger.info("✅ Cloud Trace: Flask auto-instrumented")
            except ImportError:
                logger.info("✅ Cloud Trace: initialized (manual instrumentation)")
        else:
            logger.info("✅ Cloud Trace: initialized")

    except ImportError as e:
        logger.warning(f"⏭️  Cloud Trace: skipped (missing deps: {e})")
    except Exception as e:
        logger.error(f"❌ Cloud Trace: init failed: {e}")


def _init_cloud_profiler(project_id: str | None):
    """Initialize Cloud Profiler for CPU/wall profiling (non-blocking)."""
    import threading

    def _start():
        try:
            import googlecloudprofiler

            googlecloudprofiler.start(
                service="tivit-cu002-backend",
                service_version="3.0",
                verbose=0,
                project_id=project_id,
            )
            logger.info("✅ Cloud Profiler: initialized")

        except ImportError:
            logger.warning("⏭️  Cloud Profiler: skipped (pip install google-cloud-profiler)")
        except Exception as e:
            # Profiler can fail in some environments (e.g., missing /proc)
            logger.warning(f"⏭️  Cloud Profiler: not available ({e})")

    t = threading.Thread(target=_start, daemon=True, name="cloud-profiler-init")
    t.start()


def _init_cloud_monitoring(project_id: str | None):
    """
    Initialize Cloud Monitoring custom metrics.
    Replaces Prometheus+Grafana for Cloud Run workloads.
    Cloud Run already exports request count/latency/memory to Cloud Monitoring
    automatically — this adds custom business metrics.
    """
    try:
        from google.cloud import monitoring_v3

        client = monitoring_v3.MetricServiceClient()
        # Verify connectivity — don't create metrics here,
        # they're created on-demand via record_metric()
        logger.info("✅ Cloud Monitoring: client initialized")

    except ImportError:
        logger.warning("⏭️  Cloud Monitoring: skipped (pip install google-cloud-monitoring)")
    except Exception as e:
        logger.warning(f"⏭️  Cloud Monitoring: not available ({e})")


def record_custom_metric(
    metric_type: str,
    value: float,
    labels: dict | None = None,
):
    """
    Record a custom metric to Cloud Monitoring.

    Args:
        metric_type: e.g. "video_processing_duration_seconds"
        value: Metric value
        labels: Optional labels dict
    
    Example:
        record_custom_metric("video_processing_duration_seconds", 43.2, {"module": "security"})
    """
    project_id = os.environ.get("GCP_PROJECT_ID")
    if not project_id:
        return

    try:
        from google.cloud import monitoring_v3
        from google.protobuf import timestamp_pb2
        import time

        client = monitoring_v3.MetricServiceClient()
        project_name = f"projects/{project_id}"

        series = monitoring_v3.TimeSeries()
        series.metric.type = f"custom.googleapis.com/tivit_cu002/{metric_type}"

        if labels:
            for k, v in labels.items():
                series.metric.labels[k] = str(v)

        series.resource.type = "cloud_run_revision"
        series.resource.labels["project_id"] = project_id

        now = time.time()
        seconds = int(now)
        nanos = int((now - seconds) * 10**9)

        interval = monitoring_v3.TimeInterval(
            end_time={"seconds": seconds, "nanos": nanos}
        )
        point = monitoring_v3.Point(
            interval=interval,
            value={"double_value": value},
        )
        series.points = [point]

        client.create_time_series(
            request={"name": project_name, "time_series": [series]}
        )
    except Exception as e:
        logger.debug(f"Metric write failed (non-critical): {e}")
