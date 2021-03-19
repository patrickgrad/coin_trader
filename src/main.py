from exchange.cbpro_exchange import CBProExchange
from agents.buyer import Buyer
from agents.seller import Seller
from logger import Logger
import threading

import asyncio
import time 
import pickle as pkl
import sys
import pathlib
import pandas as pd
import warnings

async def main(logger, exchange):
    loop = asyncio.get_running_loop()
    loop.set_exception_handler(logger.exception_handler)

    logger.open()
    exchange.open()

    for thread in threading.enumerate(): 
        print("THREAD : {}".format(thread.name))

    while loop.is_running():
        print("Active tasks count: ", len([task for task in asyncio.all_tasks() if not task.done()]))
        for thread in threading.enumerate(): 
            print("THREAD : {}".format(thread.name))
        await asyncio.sleep(0.5)

if __name__ == "__main__":
    if len(sys.argv) <= 1:
        print("USAGE : python main.py PATH_TO_CONFIG <PATH_TO_CHECKPOINT>")
    else:
        logger = Logger()
        config = pd.read_csv(pathlib.Path(sys.argv[1]))
        exchange = CBProExchange(logger, config)

        if len(sys.argv) > 2:
                logger.restore_checkpoint(sys.argv[2])

        try:
            asyncio.run(main(logger, exchange))
        # When we hit Ctrl + C we pop out of main(), into the
        # exception handler where we close connections and shut down
        except KeyboardInterrupt:
            exchange.close()
            logger.log_info("Main", "Interrupted!")
            logger.close()
            sys.exit(0)
            
    exchange.close()
    logger.log_error("Main", "Crashed!")
    logger.close()
    sys.exit(1)

        

        

    