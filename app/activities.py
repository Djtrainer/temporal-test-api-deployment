from datetime import datetime, timezone

from temporalio import activity


@activity.defn
async def say_hello(name: str) -> str:
    activity.logger.info("say_hello called with name=%s", name)
    return f"Hello, {name}! (greeting generated at {datetime.now(timezone.utc).isoformat()})"
