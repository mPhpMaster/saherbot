from logger import log

botName = "SaherBot"
# Monitored chats and auto-replies are always resolved from the database (see config_store).
USE_DASHBOARD_CHATS = True
USE_DASHBOARD_REPLIES = True
# أنواع الرسائل المسموحة لكل محادثة: عمود ``chats.allowed_content_types`` والافتراضي في ``config_store.DEFAULT_ALLOWED_CONTENT_TYPES``.
LIST = {}

log("Dashboard-backed chats and replies; list/ seeds new chats and /help catalog only.", "info")
