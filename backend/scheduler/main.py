"""Scheduler entry point — runs reaper and materializer concurrently."""
import asyncio
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

from scheduler.scheduler import materializer_loop, reaper_loop


async def main():
    await asyncio.gather(reaper_loop(), materializer_loop())


if __name__ == "__main__":
    asyncio.run(main())
