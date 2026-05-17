from datetime import timedelta

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from app.activities import say_hello


@workflow.defn
class HelloWorkflow:
    @workflow.run
    async def run(self, name: str) -> str:
        first = await workflow.execute_activity(
            say_hello,
            name,
            start_to_close_timeout=timedelta(seconds=30),
        )
        await workflow.sleep(timedelta(seconds=2))
        second = await workflow.execute_activity(
            say_hello,
            name[::-1],
            start_to_close_timeout=timedelta(seconds=30),
        )
        return f"{first} | {second}"
