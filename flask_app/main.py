from random import randint
from flask import Flask, request

from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry._logs import set_logger_provider
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.baggage.propagation import W3CBaggagePropagator
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
import sys
import logging
import structlog
from opentelemetry import trace, metrics, baggage

logger_provider = LoggerProvider()
set_logger_provider(logger_provider)
logger_provider.add_log_record_processor(BatchLogRecordProcessor(OTLPLogExporter()))
handler = LoggingHandler(level=logging.INFO, logger_provider=logger_provider)

logging.basicConfig(
    format="%(message)s",
    stream=sys.stdout,
    level=logging.INFO,
)
logging.getLogger().addHandler(handler)

structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(key="ts", fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

# Acquire a tracer
tracer = trace.get_tracer(__name__)
# Acquire a meter.
meter = metrics.get_meter(__name__)

log = structlog.get_logger(__name__)

trace.set_tracer_provider(TracerProvider())

app = Flask(__name__)


FlaskInstrumentor().instrument_app(app)


@app.route("/hello")
def hello():
    # Example: Log headers received in the request in API 2
    headers = dict(request.headers)
    print(f"Received headers: {headers}")
    carrier = {"traceparent": headers["Traceparent"]}
    ctx = TraceContextTextMapPropagator().extract(carrier=carrier)
    print(f"Received context: {ctx}")

    b2 = {"baggage": headers["Baggage"]}
    ctx2 = W3CBaggagePropagator().extract(b2, context=ctx)
    print(f"Received context2: {ctx2}")

    # Start a new span
    with tracer.start_span("flask_span", context=ctx2):
        # Use propagated context
        print(baggage.get_baggage("hello", ctx2))
        return "Hello from FlaskAPI!"
