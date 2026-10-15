"""Entry point: python -m worker"""
import logging
import signal
import sys

from . import handlers, logs, ops_server
from .config import settings
from .consumer import Consumer

logs.setup(settings.service_name, settings.version, settings.log_level)
log = logging.getLogger("worker")


def main() -> None:
    log.info("starting", extra=logs.fields(
        stream=settings.event_stream, group=settings.consumer_group, consumer=settings.consumer_name,
        orders_url=settings.orders_url, inventory_url=settings.inventory_url,
        max_deliveries=settings.max_deliveries, chaos_error_rate=settings.chaos_error_rate))
    consumer = Consumer()
    server = ops_server.start(consumer)

    def stop(signum, _frame):
        log.info("shutdown signal received, finishing current event", extra=logs.fields(signal=signum))
        consumer.stop()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    try:
        consumer.run()
    finally:
        server.shutdown()
        handlers.close()
        log.info("worker stopped")
    sys.exit(0)


if __name__ == "__main__":
    main()
