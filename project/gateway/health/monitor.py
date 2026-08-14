"""
monitor.py

Background loop that periodically executes active health probes for idle providers.
"""

import asyncio
from project.gateway.health.config import HealthConfig
from project.gateway.health.service import HealthService


class HealthMonitorLoop:
    """
    Background loop running periodic health checks every 30 seconds.
    """

    def __init__(self, config: HealthConfig | None = None):
        self.config = config or HealthConfig()
        self.service = HealthService(self.config)
        self._running = False
        self._task: asyncio.Task | None = None

    async def _run_loop(self):
        while self._running:
            try:
                await self.service.check_idle_and_probe_all()
            except Exception:
                pass

            await asyncio.sleep(self.config.probe_interval_seconds)

    def start(self):
        if not self._running:
            self._running = True
            self._task = asyncio.create_task(self._run_loop())

    def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
