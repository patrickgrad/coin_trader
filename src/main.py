from exchange.cbpro.cbpro_exchange import CBProExchange
from exchange.backtest.backtest_exchange import BacktestExchange
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
import argparse

async def main(logger, exchange):
    loop = asyncio.get_running_loop()
    loop.set_exception_handler(logger.exception_handler)

    logger.open()
    exchange.open()

    all_threads_alive = True
    all_threads = threading.enumerate()
    while loop.is_running() and all_threads_alive:
        print("Active tasks count: ", len([task for task in asyncio.all_tasks() if not task.done()]))
        all_threads_alive = True
        for thread in all_threads: 
            if not thread.is_alive():
                all_threads_alive = False

        await asyncio.sleep(1.0)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('config_path', help='path to config file')
    parser.add_argument('--backtest', '-b', action='store_true', help='backtest instead of live trade')
    parser.add_argument('--checkpoint', '-c', help='path to checkpoint to restore from')
    args = parser.parse_args()

    logger = Logger()
    config = pd.read_csv(pathlib.Path(args.config_path))

    if args.backtest:
        exchange =  BacktestExchange(logger, config)
    else:
        exchange = CBProExchange(logger, config)

    if not args.checkpoint == None:
        logger.restore_checkpoint(args.checkpoint)

    try:
        asyncio.run(main(logger, exchange))
    # When we hit Ctrl + C we pop out of main(), into the exception
    # handler where we close connections and shut down
    except KeyboardInterrupt:
        exchange.close()
        logger.log_info("Main", "Interrupted!")
        logger.close()
        sys.exit(0)
    # This will happen when any exception other than KeyboardInterrupt
    # is raised, which means we actually crashed
    except Exception:
        exchange.close()
        logger.log_error("Main", "Crashed!")
        logger.close()
        sys.exit(1)
    # This only happens when we are backtesting, when we are live
    # trading the program runs forever/until the user hits Ctrl + C
    else:
        exchange.close()
        logger.log_info("Main", "Finished!")
        logger.close()
        sys.exit(0)
