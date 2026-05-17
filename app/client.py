from temporalio.client import Client

from app.config import settings


async def get_temporal_client() -> Client:
    return await Client.connect(
        settings.temporal_host,
        namespace=settings.temporal_namespace,
        tls=settings.temporal_tls,
    )
