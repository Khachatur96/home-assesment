import json
import random
import constants as c
import asyncio
import websockets
import traceback
from model import Model
from enums import MessageName, LogLevel, DialogState, AgentFeature, EmailClass
from helpers import classify_urgency
from User import User
from loguru import logger

from EmailManager import EmailManager


class Device:

    def __init__(self, url: str):
        self.url = url
        self.ws: websockets.WebSocketClientProtocol | None = None
        self.em = EmailManager()
        self.models = {}  # dict to hold Model instances keyed by instance_id: {1: Model(), ...}
        self.user_map = {}  # dict to hold instance_id to user mapping: {1: User(), ...}
        self.instance2zone = {}  # dict to hold instance_id to zone_id mapping: {1: "mappo_ai_front_left_zone", ...}
        self.zone2card = {}  # dict to hold zone_id to card_id mapping: {"mappo_ai_front_left_zone": "mappo-front-left", ...}
        self.card2instance = {}  # dict to hold card_id to instance mapping: {"mappo-front-left": 1, ...}
        self.instance2card = {}  # dict to hold instance to card_id mapping: {1: "mappo-front-left", ...}
        self.agent_feature = None

    def is_connected(self):
        return self.ws and not self.ws.closed

    async def start(self):
        await asyncio.gather(
            self.connect_ws(),
            # self.log_states()
        )

    async def _reset(self):
        for instance_id in self.models:
            logger.info(f"Interrupting instance {instance_id}")
            await self.interrupt(instance_id)
        self.user_map = {}
        await self.send_agent_feature(AgentFeature.DIALOG, -1)

    async def connect_ws(self):
        try:
            async with websockets.connect(self.url) as ws:
                self.ws = ws
                await self.on_open()
                await self.listen_ws(ws)
        except Exception as e:
            logger.error(f"Failed to connect to local WebSocket: {e}")
            await self.on_close()

    async def listen_ws(self, ws: websockets.WebSocketClientProtocol):
        async for message in ws:
            await self.handle_ecu_message(message)

    async def handle_ecu_message(self, message_data):
        logger.info(f"Received message: {message_data}")
        try:
            clean_message = message_data.rstrip('\n\x00')
            message = json.loads(clean_message)
        except Exception as e:
            logger.error(f"Failed to parse message: {e} - {traceback.format_exc()}")
            return

        instance_id = message.get("instance")

        if message.get("type") == MessageName.INSTANCE_ADD:
            # Create a new Model instance if it doesn't exist already
            if instance_id not in self.models:
                self.models[instance_id] = Model(instance_id=instance_id)

                zone_id = message.get("value")
                self.instance2zone[instance_id] = zone_id

                # fill card2instance and instance2card maps
                card_id = self.zone2card.get(zone_id)
                self.card2instance[card_id] = instance_id
                self.instance2card[instance_id] = card_id

                await self.models[instance_id].set_device(self)
                logger.info(f"Created new Model instance for instance_id: {instance_id}")
        if message.get("name") == MessageName.ENABLE_LISTENER:
            value = message.get("value", False)
            if instance_id in self.models:
                await self.interrupt(instance_id)
                if value == "true":
                    await asyncio.sleep(0.2)
                    asyncio.create_task(self.models[instance_id].chat())

        if message.get("name") == MessageName.USER_DETECTED:
            user = User()
            fields = message.get("fields")
            message = {}
            for field in fields:
                message[field["name"]] = field["value"]

            for field_name in message:
                setattr(user, field_name, message[field_name])

            self.user_map[instance_id] = user.__dict__
            logger.info(f"New user detected. User map: {json.dumps(self.user_map, indent=2)}")

        if message.get("name") == MessageName.MAIL_START:
            pass

        if message.get("name") == MessageName.MAIL_END:
            self.em.step = 0
            asyncio.create_task(self.em.process_emails(),
                                name=f"email_task_{instance_id}_{random.randint(1, 1000)}")

        if message.get("name") == MessageName.EMAIL_ADD:
            fields = message.get("fields")
            message = {}
            for field in fields:
                message[field["name"]] = field["value"]

            logger.info(message)

            sender_name = message.get("sender_name")
            subject = message.get("object")
            content = message.get("content")
            kind = message.get("kind")
            self.em.add_email(sender_name, subject, content, kind)

        if message.get("name") == MessageName.NEXT_EMAIL:
            self.em.next_email = True

        if message.get("name") == MessageName.TTS_COMPLETED:
            self.models[instance_id].tts_completed = True
            if self.em.step == 2 and self.agent_feature == AgentFeature.WORK:
                await self.models[instance_id].disable_chat(idle=False)
                await asyncio.sleep(0.2)
                asyncio.create_task(self.models[instance_id].chat())

        if message.get("name") == MessageName.AGENT_FEATURE:
            value = message.get("value")
            self.agent_feature = value

            if value != AgentFeature.WORK:
                if self.em.step != -1:
                    self.em.step = 0

            if value == AgentFeature.WORK:
                # execute email workflow
                if self.em.step == 0:
                    await self.exec_work_flow(instance_id, 0)
                else:
                    logger.error("Email Workflow is not ready with processed emails")
                    return

        if message.get("name") == MessageName.RESET:
            await self._reset()

    async def on_open(self):
        await self.send_log_message("Connection Opened", LogLevel.INFO)
        for instance_id in self.models:
            await self.models[instance_id].set_device(self)
        await self.send_agent_feature(AgentFeature.DIALOG, -1)

    async def on_close(self):
        await self._reset()
        await self.em.reset()
        await self.send_log_message("Connection Closed", LogLevel.WARNING)

    async def on_error(self, ws: websockets.WebSocketClientProtocol | None, error: Exception):
        await self.send_log_message(f"WS Error: {error}", LogLevel.ERROR)
        if ws:
            await self.on_close()
            await ws.close()
        await self.connect_ws()

    async def interrupt(self, instance_id: int):
        await self.models[instance_id].disable_chat()

    async def exec_work_flow(self, instance_id: int, step: int, user_input: str = None):
        async def finish_work_flow():
            logger.info("Finishing email workflow.")
            self.em.step = 0

        logger.info(f"Executing workflow step {step}")
        message = None
        # Step 0: Resume Message Preparation
        if step == 0:
            # Check if there are urgent or not urgent emails
            if not self.em.urgent_emails:
                # If there are no urgent emails, prepare the report for not urgent emails
                await self.em.generate_report(EmailClass.NOT_URGENT)
                self.em.step = 2  # Skip to Step 2 directly
                step = 2  # Update step 2 to continue the execution
            elif not self.em.not_urgent_emails:
                # If there are no not urgent emails, prepare the report for urgent emails
                await self.em.generate_report(EmailClass.URGENT)
                self.em.step = 2  # skip to Step 2 directly
                step = 2  # update step  2 to continue the execution
            else:
                # If both types of emails are present, prepare and send the resume message
                message = await self.em.compose_resume_message()
                await self.send_text(message, instance_id)
                self.em.step += 1  # Proceed to Step 1

                # Start chat if not already enabled
                if not self.models[instance_id].chat_enabled:
                    asyncio.create_task(self.models[instance_id].chat(instant=False),
                                        name=f"chat_task_{instance_id}_{random.randint(1, 1000)}")
                return  # exit after setting up the prompt

        if step == 1:  # Step 1: User Input Processing
            assert user_input is not None, "User input must not be None"
            urgency = classify_urgency(user_input)
            success = await self.em.generate_report(urgency)
            message = self.em.report_msgs[0]
            await self.send_text(message, instance_id)
            self.em.report_msgs.pop(0)
            if success:
                self.em.step += 1
            return  # Exit after processing the user input

        # Step 2: Email Reading
        if step == 2:
            if self.em.report_msgs:
                message = self.em.report_msgs[0]
                if self.em.next_email and not message.lower().startswith("urgent") and not message.lower().startswith(
                        "less"):
                    message = "Next email: " + message
                await self.send_text(message, instance_id)
                self.em.report_msgs.pop(0)
                self.em.next_email = False
                if len(self.em.report_msgs) == 0:
                    await finish_work_flow()
            return  # Exit after reading the emails

        return message

    async def send_message(self, message: dict):
        if not self.is_connected():
            logger.error("Cannot send message: WebSocket is not connected.")
            return
        logger.info(f"Sending message: {message}")
        await self.ws.send(json.dumps(message) + '\0')

    async def send_dialog_state(self, state: DialogState, instance_id: int | None):
        message = {
            "name": MessageName.DIALOG_STATE.value,
            "type": "object_simple_signal",
            "instance": instance_id,
            "value": state.value if isinstance(state, DialogState) else state,
        }
        await self.send_message(message)

    async def send_log_message(self, text: str, level: LogLevel, instance_id: int = -1):
        message = {
            "name": MessageName.LOG.value,
            "type": "object_struct_signal",
            "instance": instance_id,
            "fields": [
                {
                    "name": "log_level",
                    "value": level.value if isinstance(level, LogLevel) else level
                },
                {"name": "message", "value": text},
            ],
        }
        await self.send_message(message)

    async def send_agent_feature(self, feature: AgentFeature, instance_id: int = -1):
        if feature != AgentFeature.WORK:
            if self.em.step != -1:
                self.em.step = 0
        if self.agent_feature == feature:
            return

        self.agent_feature = feature.value
        message = {
            "name": MessageName.AGENT_FEATURE.value,
            "type": "object_simple_signal",
            "instance": instance_id,
            "value": feature.value,
        }
        await self.send_message(message)

    async def send_text(self, text: str, instance_id: int):
        if not text:
            text = "Sorry, I couldn't understand that. Please try again."
            logger.warning("Text to be synthesized was empty, sending default message.")
            # return

        message_name = MessageName.TTS_TEXT.value
        message = {
            "name": message_name,
            "type": "object_struct_signal",
            "instance": instance_id,
            "fields": [
                {"name": "text", "value": text},
                {"name": "intonation", "value": "neutral"},
            ],
        }
        self.models[instance_id].tts_completed = False
        await self.send_message(message)

    async def send_ready_message(self, instance_id: int):
        message = {
            "name": MessageName.DEVICE_READY.value,
            "type": "object_void_signal",
            "instance": instance_id,
        }
        await self.send_message(message)

    async def log_states(self):
        while True:
            if self.models and self.is_connected():
                string = "\n" + "=" * 20
                for instance_id, model in self.models.items():
                    if model.state != DialogState.IDLE:
                        string += "\nModel " + str(instance_id) + ":"
                        string += "\n\tstate: " + str(model.state)
                        string += "\n\ttts copmpleted: " + str(model.tts_completed)
                        string += "\n\tidle on completion: " + str(model.idle_on_completion)
                        string += "\n\tchat enabled: " + str(model.chat_enabled)
                        break

                string += "\nAgent Feature: " + str(self.agent_feature)
                string += "\nEmail Manager Step: " + str(self.em.step)

                logger.info(string)

            await asyncio.sleep(5)
