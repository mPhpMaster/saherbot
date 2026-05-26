import time
import logging
import os
from logging.handlers import RotatingFileHandler

# Ensure logs directory exists
os.makedirs("logs", exist_ok=True)

log_filename = "logs/" + time.strftime("%d-%m-%Y") + '.log'

# Set up rotating file handler (max 10MB, keep 5 backup files)
file_handler = RotatingFileHandler(log_filename, maxBytes=10*1024*1024, backupCount=5)
file_handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s [%(levelname)s]: %(message)s')
file_handler.setFormatter(formatter)

# Configure root logger
logging.basicConfig(level=logging.INFO, handlers=[file_handler])

def log(message, type: str = "info"):
    """Log a message to both console and file with rotation support.
    
    Args:
        message: The message to log
        type: Log level ('info', 'error', 'debug', etc.)
    """
    _time = time.strftime("%d-%m-%Y %H:%M:%S")
    print(f"{_time} [{type}]: {message}")
    
    if type == "error":
        logging.error(message)
    elif type == "warning":
        logging.warning(message)
    elif type == "debug":
        logging.debug(message)
    else:
        logging.info(message)


def setup_logging():
    """Reinitialize logging for new day (call at midnight or on demand)."""
    global log_filename, file_handler
    
    new_log_filename = "logs/" + time.strftime("%d-%m-%Y") + '.log'
    
    if new_log_filename != log_filename:
        # Close old handler
        file_handler.close()
        
        # Create new handler for new day
        log_filename = new_log_filename
        file_handler = RotatingFileHandler(log_filename, maxBytes=10*1024*1024, backupCount=5)
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(formatter)
        
        # Get root logger and add new handler
        root_logger = logging.getLogger()
        root_logger.addHandler(file_handler)
