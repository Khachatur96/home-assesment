#!/usr/bin/python3


import json
import asyncio
import websockets
from loguru import logger

connected_clients = set()

async def broadcast(data):
    if connected_clients:  # Check if there are any connected websockets
        tasks = [asyncio.create_task(ws.send(data)) for ws in connected_clients]
        await asyncio.wait(tasks)
        # logger.info(f"Sent data to {len(connected_clients)} clients.")
    else:
        logger.warning("No active connections to send data to.")


async def do_add_instance():
    for i, zone in enumerate([
        "zone_1",
        "zone_2",
        "zone_3",
        "zone_4"
    ], start=1):
        data = {
            "type": "instance_add",
            "instance": i,
            "name": zone,
            "value": zone[-1]
        }
        await broadcast(json.dumps(data))

async def do_remove_instance(instance_id):
    data = {
        "type": "instance_remove",
        "instance": instance_id,
        "name": "zone_1", # doesn't matter
        "value": "1" # doesn't matter
    }
    await broadcast(json.dumps(data))

async def do_configure():
  data = {}
  JSON_FORMATTED_STRING = '''
    {
        "log-level": "info", 
        "audio-input": [
            {
                "name": "zone_1",
                "value": "1"
            },
            {
                "name": "zone_2", 
                "value": "2"
            },
            {
                "name": "zone_3",
                "value": "3"
            },
            {
                "name": "zone_4",  
                "value": "4"
            }
        ]
    }'''
  
  data["name"]     =  "configuration" 
  data["type"]     = "configuration"
  data["value"]    = JSON_FORMATTED_STRING

  for i in range(1, 5): 
    data["instance"] =  i
    msg = json.dumps(data)
    await broadcast(msg)

async def do_detect_user():
    users = open('users.txt', 'r') # contains json lines of messages to send
    users = users.read().splitlines()
    # await asyncio.sleep(1)

    for i, user in enumerate(users):
        user = json.loads(user)
        fields = []
        for key, value in user.items():
            fields.append({"name": key, "value": value})

        data = {
            "type": "object_struct_write",
            "name": "service_user_detected",
            "instance": i + 1,
            "fields": fields
        }
        await broadcast(json.dumps(data))

async def do_users_set():
    data = {
        "name": "service_users_set",
        "type": "method_void",
        "instance": -1
    }
    await broadcast(json.dumps(data))

async def do_enable_listener(flag):
    data = {
        "name": "service_enable_listener",
        "type": "object_write",
        "instance": 1,
        "value": str(flag).lower()
    }
    await broadcast(json.dumps(data))

async def do_tts_complted():
    data = {}
    data["name"] = "service_tts_completed"
    data["type"] = "method_void"
    data["instance"] = 1
    msg = json.dumps(data)
    await broadcast(msg)

async def do_reset():
    data = {}
    data["name"] = "service_reset"
    data["type"] = "method_void"
    data["instance"] =    -1
    msg = json.dumps(data)
    await broadcast(msg)
    await asyncio.sleep(1)
    await do_detect_user()



async def prepare():
    await do_configure()
    await do_add_instance()
    await do_detect_user()

async def handler(websocket):
    prepared = False
    connected_clients.add(websocket)
    try:
        async for message in websocket:
            logger.info(message)
            if not prepared:
                await prepare()
                prepared = True
    finally:
        connected_clients.remove(websocket)


async def do_agent_feature(step):
    data = {
        "name": "service_agent_feature",
        "type": "object_write",
        "instance": 1,
        "value": step
    }
    # assert data['value'] in ['dialog', 'email', 'avatar', 'exploration']
    await broadcast(json.dumps(data))


async def do_mail_start():
    data = {
     "name": "service_predefined_mail_transaction_start",
     "type": "method_void",
     "instance": -1
    }
    await broadcast(json.dumps(data))

async def do_mail_end():
    data = {
     "name": "service_predefined_mail_transaction_finished",
     "type": "method_void",
     "instance": -1
    }
    await broadcast(json.dumps(data))

async def do_add_email(data=None):
    if not data:
        data = {"fields":[{"name":"predefined","value":"true"},{"name":"receiver_name","value":"Renault User"},{"name":"receiver_email_address","value":"user@renault.com"},{"name":"sender_name","value":"Customer 1"},{"name":"sender_email_address","value":"customer_1@anywhere.com"},{"name":"date","value":"02-04-2024"},{"name":"time","value":"12:50"},{"name":"kind","value":"normal"},{"name":"unread","value":"true"},{"name":"object","value":"Invitation"},{"name":"content","value":"The CEO, Avi, invites all employees to a company event on 23.3.24 at 18:00 at the headquarters. The event will feature food, drinks, and games, offering an opportunity for employees to socialize and have fun."}],"instance":-1,"name":"service_add_email","type":"method_struct"}
    await broadcast(json.dumps(data))

async def do_mailing():
    await do_mail_start()
    emails = open('emails.txt', 'r') # contains json lines of messages to send
    emails = emails.read().splitlines()
    # await asyncio.sleep(1)
    for email in emails:
        await do_add_email(json.loads(email))
        # await asyncio.sleep(0.5)

    # await asyncio.sleep(1)
    await do_mail_end()

async def do_next_email():
    data = {
        "name": "service_next_email",
        "type": "method_void",
        "instance": 1
    }
    await broadcast(json.dumps(data))

async def do_summarize_email():
    data = {
        "name": "service_summarize_email",
        "type": "method_void",
        "value": "urgent",
        "instance": 1
    }
    await broadcast(json.dumps(data))

async def prompt(message):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, input, message)


async def interactive():
    await asyncio.sleep(1)

    while True:
        logger.info("Enable Listener .......1")
        logger.info("TTS Completed .........2")
        logger.info("Feature ...............3")
        logger.info("Mail ..................4")
        logger.info("Next email.............5")
        logger.info("Reset  ................7")
        ch = await prompt("Enter choice: ")
        match ch:
            case "1":
                sflag = input("flag [y/n]: ")
                flag = sflag == 'y' or sflag == 'Y' 
                await do_enable_listener(flag)
            case "2":
                await do_tts_complted()
            case "3":
                step = input("feature: ")
                await do_agent_feature(step)
            case "4":
                await do_mailing()
            case "5":
                await do_next_email()
            case "6":
                await do_summarize_email()
            case "7":
                await do_reset()



async def main():
    PORT = 9001
    server = await websockets.serve(handler, "", PORT)
    
    await asyncio.gather(
        server.wait_closed(),  # Wait for the server to be closed.
        interactive()  # Run the interactive function concurrently.
    )



if __name__ == "__main__":
    asyncio.run(main())


