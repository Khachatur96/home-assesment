from enum import Enum


class MessageName(str, Enum):
    #------- ECU 2 Agent -----------------------------
    INSTANCE_ADD = "instance_add"
    INSTANCE_REMOVE = "instance_remove"
    CONFIGURATION = "configuration"
    USER_DETECTED = "service_user_detected"
    USERS_SET = "service_users_set"
    ENABLE_LISTENER = "service_enable_listener"
    RESET = "service_reset"
    MAIL_START = "service_predefined_mail_transaction_start"
    MAIL_END = "service_predefined_mail_transaction_finished"
    EMAIL_ADD = "service_add_email"
    NEXT_EMAIL = "service_next_email"
    SUMMARIZE_EMAIL = "service_summarize_email"
    AGENT_FEATURE = "service_agent_feature"
    TTS_COMPLETED = "service_tts_completed"
    #------- Agent 2 ECU -----------------------------
    DEVICE_READY = "service_device_is_ready"
    DIALOG_STATE = "service_dialog_state"
    LOG = "service_log"
    TTS_TEXT = "service_tts_text"
    TTS_INTERRUPT = "service_tts_interrupt"
    USER_ORDER = "service_user_order"

class LogLevel(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"

class DialogState(str, Enum):
    IDLE = "idle"
    PROCESSING = "processing"
    RESPONDING = "responding"
    LISTENING = "listening"
    PROCESS_INTERRUPTED = "process_interrupted"

class EmailClass(str, Enum):
    URGENT = "CONTAIN"
    NOT_URGENT = "NOT_CONTAIN"


class AgentFeature(str, Enum):
    DIALOG = "dialog"
    WORK = "email"
    GAME = "avatar"
    EXPLORATION = "exploration"


class WORK_CMDS(str, Enum):
    NEXT_EMAIL = "[NEXT EMAIL]"