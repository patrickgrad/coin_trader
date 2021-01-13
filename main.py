import asyncio
import time 
import exchange as e
import buyer as b
import seller as s
import logger as l
import pickle as pkl
import sys
import signal

if __name__ == "__main__":
    loop = asyncio.new_event_loop()

    logger = l.Logger(loop)
    buyer = b.Buyer()
    seller = s.Seller()
    exchange = e.Exchange(loop, logger, buyer, seller)

    loop.set_exception_handler(logger.exception_handler)

    if len(sys.argv) > 1:
        logger.restore_checkpoint(sys.argv[1])

    try:
        loop.run_forever()
    except KeyboardInterrupt:
        logger.make_checkpoint("end_chk.pkl")
        exchange.close()
        loop.close()
        logger.log_info("Main", "Interrupted!")
        sys.exit(0)

    loop.close()
    logger.log_error("Main", "Crashed!")
    sys.exit(1)

    