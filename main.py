import os
import asyncio
import constants as c
from Device import Device

ecu_host = "localhost"
ecu_port = 9001


async def main():
    url = f"ws://{ecu_host}:{ecu_port}"

    device = Device(url=url)

    await device.start()


if __name__ == "__main__":
    asyncio.run(main())
