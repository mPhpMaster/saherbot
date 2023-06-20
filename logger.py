import time
import logging

log_filename = "logs/" + time.strftime("%d-%m-%Y") + '.log'
open(log_filename,"a").close()
logging.basicConfig(filename=log_filename, level=logging.INFO,format='%(asctime)s [%(levelname)s]: %(message)s')

def log(message, type: str = "info"):
    global logging
    _time = time.strftime("%d-%m-%Y %H:%M:%S")
    print(f"{_time} [{type}]: {message}")
    if type == "error":
        logging.error(message)
    elif type == "info":
        logging.info(message)
    else:
        logging.debug(message)
