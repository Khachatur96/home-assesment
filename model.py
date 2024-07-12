import asyncio
import re


from loguru import logger

from Listener import Listener
from enums import DialogState, AgentFeature
import constants as c

class NoQueryDetected(Exception):
    pass

class Model:
    """
    Represents the core logic of the conversational agent.
    Handles speech recognition, dialog state management, text generation, and interaction with external systems.
    """

    def __init__(self, instance_id: str):
        """
        Initializes the Model instance.

        Args:
            instance_id: Unique identifier for the agent instance.
        """
        logger.info(f"Initializing Model for instance_id: {instance_id}")

        self.instance_id = instance_id

        self.listener = None
        self.device = None
        self.state = None
        self.n_sents_chunk = 1

        self.chat_task = None
        self.ongoing_tasks = []
        self.chat_enabled = False
        self.tts_completed = True
        self.idle_on_completion = False

        self.context = []

    async def _init_listener(self) -> bool:
        """Initializes the speech-to-text engine."""
        self.listener = Listener()
        return True

    async def stop_tasks(self, idle: bool = True):
        """Cancels ongoing tasks and optionally resets the dialog state to idle."""
        for task in [t for t in self.ongoing_tasks if not t.done()]:
            await self._safe_cancel_task(task)

        if self.listener:
            await self.listener.stop()

        self.ongoing_tasks = []

        if idle:
            self.context = []
            if self.state != DialogState.IDLE:
                await self._set_state(DialogState.IDLE)

    async def _safe_cancel_task(self, task: asyncio.Task):
        """Cancels a task with error handling."""
        try:
            task.cancel()
            await task
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Error while cancelling task: {e}")

    async def set_device(self, device):
        """Associates the model with a device and initializes it."""
        self.device = device
        if not await self._init_listener():
            logger.error("Failed to initialize Listener")
            return
        await self._set_state(DialogState.IDLE)
        await self.device.send_ready_message(self.instance_id)

    async def _set_state(self, state: DialogState):
        """Sets the dialog state and notifies the device."""
        if isinstance(state, DialogState):
            state = state.value
        if state == self.state:
            return
        assert state in c.STATES, f"Invalid state: {state}, must be one of {c.STATES}"
        self.state = state
        if self.device:
            await self.device.send_dialog_state(state, self.instance_id)

    async def _listen(self, timeout: int = None) -> dict:
        """Listens for user speech input."""
        await self._set_state(DialogState.LISTENING)
        try:
            transcribe_task = asyncio.create_task(self.listener.start())
            query = await asyncio.wait_for(transcribe_task, timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning("Listen operation timed out")
            query = None
        except asyncio.CancelledError:
            logger.info("Listen operation was cancelled")
            query = None
        except Exception as e:
            logger.error(f"Error during listen operation: {e}", exc_info=True)
            query = None
        finally:
            await self.listener.stop()
        return query

    async def get_response(self):
        """Generates a response from the language model."""
        await self._set_state(DialogState.RESPONDING)
        response = "This is a placeholder response."
        await self.device.send_text(response, self.instance_id)
        return response

    async def process_work_query(self, query: dict):
        if isinstance(query, dict):
            transcript = query.get('transcript', '')  # Extract transcript, default to '' if not found
        else:
            transcript = query

        if not transcript:
            transcript = ''

        if re.search(r'\bnext\b', transcript, re.IGNORECASE):
            logger.warning("User said next")
            self.device.em.next_email = True
        elif re.search(r'\bstop\b', transcript, re.IGNORECASE):
            logger.warning("User said stop")
            await self.device.send_agent_feature(AgentFeature.DIALOG, self.instance_id)
            await self.disable_chat()
        else:
            return await self.process_work_query(await self._listen(300))

    async def chat_iteration(self) -> None:
        logger.info("Performing chat iteration")
        """Performs a single iteration of the chat loop."""
        if not await self._init_listener():
            logger.warning("Failed to initialize new Listener instance")

        
        # Handle special case for last step of 'work' feature
        if self.device.em.step == 2 and self.device.agent_feature == AgentFeature.WORK:
            await self._set_state(DialogState.RESPONDING)
            ai_msg = await self.device.exec_work_flow(self.instance_id, step=self.device.em.step)
            self.context.append(ai_msg)
            if self.device.em.step == 0:  # Last step executed
                while not self.tts_completed:
                    await asyncio.sleep(0.2)
                    logger.debug("Waiting for TTS to complete")
                await self.device.send_agent_feature(AgentFeature.DIALOG, self.instance_id)
                await self.disable_chat()
                return

        listen_task = asyncio.create_task(self._listen())
        self.ongoing_tasks.append(listen_task)

        listen_result = await listen_task
        if not listen_result:
            raise asyncio.CancelledError("No query")

        query = listen_result
        logger.info(f'User said: {query}')

        # Process query based on current agent feature
        await self._process_query_by_feature(query)

    async def _process_query_by_feature(self, query: str):
        """Processes the user query based on the active agent feature."""
        if self.device.agent_feature == AgentFeature.WORK:
            await self._handle_work_feature(query)
        else:
            await self._handle_dialog()

    async def _handle_work_feature(self, query: str):
        """Handles user interactions within the 'work' agent feature."""
        if re.search(r'\bstop\b', query, re.IGNORECASE):
            logger.warning("User said stop")
            await self.device.send_agent_feature(AgentFeature.DIALOG, self.instance_id)
            await self.disable_chat()
            return

        if self.device.em.step == 1:
            await self._set_state(DialogState.RESPONDING)
            ai_msg = await self.device.exec_work_flow(self.instance_id, step=self.device.em.step, user_input=query.lower())
            self.context.append(ai_msg)
        elif self.device.em.step == 2:
            await self.process_work_query(query) 

    async def _handle_dialog(self):
        """Handles user interactions in dialog or exploration modes."""
        gen_task = asyncio.create_task(self.get_response())
        self.ongoing_tasks.append(gen_task) 
        response = await gen_task
        self.context.append(response)


    async def chat(self, instant: bool = True):
        """Initiates and manages the main chat loop."""
        self.chat_enabled = True
        self.tts_completed = instant

        while self.chat_enabled:
            if not self.device or not self.device.is_connected():
                logger.error("WebSocket connection is not established or is closed. Going idle.")
                await self._set_state(DialogState.IDLE)
                await asyncio.sleep(0.2)
                continue

            if self.tts_completed:
                if self.idle_on_completion:
                    await self.disable_chat()
                    break
                try:
                    await self.chat_iteration()
                except asyncio.CancelledError as e:
                    logger.warning(f"Chat cancelled: {e}")
                    idle = False if self.device.em.step == 2 else True
                    await self.disable_chat(idle=idle)
                    break
                except Exception as e:
                    logger.exception(f'Exception: {e}')
                    await self.disable_chat()
                    break
            else:
                await asyncio.sleep(0.2)

    async def disable_chat(self, idle: bool = True):
        """Disables the chat loop and performs cleanup."""
        self.chat_enabled = False
        self.tts_completed = True
        self.idle_on_completion = False
        await self.stop_tasks(idle=idle)
        await asyncio.sleep(0.1)