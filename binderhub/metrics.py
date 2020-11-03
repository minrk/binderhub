from prometheus_client import CONTENT_TYPE_LATEST
from prometheus_client import generate_latest
from prometheus_client import REGISTRY

from .base import BaseHandler


class MetricsHandler(BaseHandler):
    # demote logging of 200 responses to debug-level
    log_success_debug = True

    async def get(self):
        self.set_header("Content-Type", CONTENT_TYPE_LATEST)
        self.write(generate_latest(REGISTRY))
