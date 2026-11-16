from contextlib import asynccontextmanager
import logging
import structlog
import requests
from random import randint
from opentelemetry import context
import sys
import psycopg2
from fastapi import FastAPI, HTTPException
from opentelemetry import trace, metrics, baggage
from opentelemetry.trace import SpanKind
from opentelemetry._logs import set_logger_provider
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import (
    PeriodicExportingMetricReader,
)
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.instrumentation.psycopg2 import Psycopg2Instrumentor
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from opentelemetry.baggage.propagation import W3CBaggagePropagator

tracer_provider = TracerProvider()
tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))

metric_reader = PeriodicExportingMetricReader(OTLPMetricExporter())
metrics_provider = MeterProvider(metric_readers=[metric_reader])

metrics.set_meter_provider(metrics_provider)

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

log = structlog.get_logger(__name__)

meter = metrics.get_meter(__name__)

tracer = trace.get_tracer(__name__)

conn_params = {
    "host": "postgres",
    "database": "demodb",
    "user": "postgres",
    "password": "demopassword",
    "port": 5432,
}

connection = None
cursor = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    FastAPIInstrumentor.instrument_app(app)
    LoggingInstrumentor().instrument(set_logging_format=True)
    Psycopg2Instrumentor().instrument()
    yield


app = FastAPI(
    lifespan=lifespan,
    title="FastAPI Demo App",
    description="A simple FastAPI app with OpenTelemetry instrumentation",
    version="1.0.0",
    # telemetry={"tracer_provider": tracer_provider},
)


@app.get("/")
def read_root():
    log.info("read_root")
    return {"message": "Hello, OpenTelemetry"}


@app.get("/items/{item_id}")
async def read_item(item_id: int):
    with tracer.start_as_current_span("read_items") as span:
        span.set_attribute("item.id", item_id)
        log.info("read_items", item_id=item_id)
        return {"item_id": item_id}


@app.get("/catfacts")
async def cat_facts():
    log.info("Calling Cat Facts")
    current_context = context.get_current()
    result = cat_facts(ctx=current_context)
    return result


def cat_facts(ctx: context.Context):
    url = "https://catfact.ninja/fact"
    token = context.attach(ctx)
    try:
        with tracer.start_as_current_span("cat_facts", kind=SpanKind.INTERNAL) as span:
            response = requests.get(url, timeout=10)
            response.raise_for_status()

            data = response.json()
            log.info("GET Success! Retrieved data structure type:", type=type(data))
            fact = data["fact"]
            span.set_attribute("fact", fact)
            return fact

    except requests.exceptions.HTTPError as http_err:
        log.error(f"HTTP error occurred: {http_err}")
    except requests.exceptions.RequestException as err:
        log.error(f"An error occurred: {err}")
    finally:
        context.detach(token)


@app.get("/users")
async def read_users():
    log.info("Getting users list")
    result = read_users()
    return result


def read_users():
    cnx = psycopg2.connect(**conn_params)
    cursor = cnx.cursor()
    query = "SELECT name, email FROM users;"
    cursor.execute(query)

    rows = cursor.fetchall()
    cursor.close()
    cnx.close()

    return rows


@app.get(
    "/hello",
    summary="API endpoint that demonstrated context propagation. "
    "It queries the Flask app where it will add additional spans "
    "and then passes that context back to the FastAPI endpoint",
)
def hello():
    with tracer.start_as_current_span("fastapi_span") as span:
        ctx = baggage.set_baggage("Hello", "world")

        headers = {}
        W3CBaggagePropagator().inject(headers, ctx)
        TraceContextTextMapPropagator().inject(headers, ctx)
        log.info(headers)

        response = requests.get("http://flask:8081/hello", headers=headers)
        return f"Hello from FastAPI! Response from Flask API: {response.text}"


@app.get("/users/{user_name}")
async def get_user(user_name: str):
    user_data = get_user(user_name)
    result = user_data[0]
    return result


def get_user(user_name: str):
    cnx = psycopg2.connect(**conn_params)
    cursor = cnx.cursor()
    query = f"SELECT name, email FROM users WHERE name = '{user_name}';"
    cursor.execute(query)
    rows = cursor.fetchall()
    cursor.close()
    cnx.close()

    return rows


@app.get("/generror")
async def gen_error():
    with tracer.start_as_current_span("generror") as span:
        span.set_attribute("error.type", "User Initiated Error")
        raise HTTPException(status_code=500, detail="Internal Server Error")
