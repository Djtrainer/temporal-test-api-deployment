import asyncio
import logging

from temporalio.worker import Worker

from app.activities import say_hello
from app.client import get_temporal_client
from app.config import settings
from app.workflows import HelloWorkflow


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("worker")

    client = await get_temporal_client()
    worker = Worker(
        client,
        task_queue=settings.temporal_task_queue,
        workflows=[HelloWorkflow],
        activities=[say_hello],
    )
    logger.info(
        "worker starting: host=%s namespace=%s task_queue=%s tls=%s",
        settings.temporal_host,
        settings.temporal_namespace,
        settings.temporal_task_queue,
        settings.temporal_tls,
    )
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
