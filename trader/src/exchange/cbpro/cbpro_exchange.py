import os
import cbpro
import asyncio
import sys
import traceback
from datetime import datetime
from pathlib import Path
from src.agents.buyer import Buyer
from src.agents.seller import Seller
from src.exchange.leaky_bucket import LeakyBucket
from src.exchange.cbpro.cbpro_websocket import TickerClient

class CBProExchange:
    def __init__(self, logger, config):
        self.opened = False
        self.closed = False

        self.logger = logger
        self.logger.exchange = self

        self.api_key = self.get_system_variable("KEY")
        self.api_secret = self.get_system_variable("B64SECRET")
        self.api_passphrase = self.get_system_variable("PASSPHRASE")
        self.rest_url = self.get_system_variable("REST_URL")
        self.ws_url = self.get_system_variable("WS_URL")

        self.product_ids = []
        self.configs = {}
        for row in config.to_dict(orient="records"):
            self.product_ids.append(row["PRODUCT"])
            self.configs[row["PRODUCT"]] = row
        self.currency_ids = self.products_to_currencies(self.product_ids)

        self.available = {}
        self.hold = {}
        self.balance = {}

        self.rest_client = cbpro.AuthenticatedClient(self.api_key, self.api_secret, self.api_passphrase, api_url=self.rest_url)
        self.rest_client.cancel_all()

        self.agents = []
        self.prodid_to_agents = {}
        for prod_id in self.product_ids:
            # Only add trading agents for products we actually want to trade, we can also just gather data
            if self.configs[prod_id]["TRADE"]:
                b = Buyer(self.configs[prod_id])
                s = Seller(self.configs[prod_id])
                b.exchange = self
                b.logger = logger
                s.exchange = self
                s.logger = logger
                self.agents.append(b)
                self.agents.append(s)
                self.prodid_to_agents[prod_id] = [b, s]

    def exception_handler(func):
        def ret(self, *args, **kwargs):
            try:
                func(self, *args, **kwargs)
            except:
                # Gather all the info we want to log
                exc_type, exc_value, exc_traceback = sys.exc_info()
                exception_dump_file = Path(self.logger.log_folder)/"exception_{}.txt".format(datetime.now().strftime("%Y%m%d_%H%M%S"))
                out = "Exception Type: {}\n".format(exc_type)
                out += "Exception Value: {}\n".format(exc_value)

                # Print the exception info
                print(out)
                traceback.print_tb(exc_traceback)

                # Save exception info to a file
                with open(exception_dump_file, "w") as f:
                    f.write(out)
                    traceback.print_tb(exc_traceback, file=f)

                # Make sure that we release the leaky bucket in case the exception is thrown after we have acquired it
                self.lb.release()
        return ret

    # Delay loop based initialization until we are in asyncio context
    def open(self):
        if not self.opened:
            self.loop = asyncio.get_running_loop()

            # Max of 5 tokens, new token every 0.2 seconds
            # Limits average request rate to 5/s with max bursts of 10/s 
            self.lb = LeakyBucket(5, 0.2)

            self.ws_tickers = TickerClient()
            self.ws_tickers.exchange = self
            self.ws_tickers.logger = self.logger
            self.ws_tickers.loop = self.loop
            self.ws_tickers.start()

            self.get_accounts()
            self.order_watchdog()

            self.opened = True

    # Safety net in case we forget to call close
    def __del__(self):
        self.close()

    # Tear down object
    def close(self):
        if not self.closed:
            self.lb.close()
            self.ws_tickers.close()

            self.closed = True

    def log_error(self, msg):
        self.logger.log_error("CBProExchange", msg)
    
    def log_warn(self, msg):
        self.logger.log_warn("CBProExchange", msg)

    def log_info(self, msg):
        self.logger.log_info("CBProExchange", msg)

    def products_to_currencies(self, products):
        ret = set()
        for p in products:
            curs = p.split("-")
            
            for c in curs:
                ret.add(c)

        return ret

    def get_system_variable(self, name):
        try:
            return os.environ[name]
        except KeyError:
            self.log_warn('"{}" does not exist!'.format(name))
            val = input("{}:".format(name))
            return val

    @exception_handler
    def cancel_order(self, order_id):
        # Use leaky bucket regulator when making REST call
        self.lb.acquire()
        self.rest_client.cancel_order(order_id)
        self.lb.release()
        
    @exception_handler
    def place_market_order(self, on_order_placed, **kwargs):
        # Use leaky bucket regulator when making REST call
        self.lb.acquire()
        resp = self.rest_client.place_market_order(**kwargs)
        self.lb.release()
        on_order_placed(resp)
        
    @exception_handler
    def place_limit_order(self, on_order_placed, **kwargs):
        # Use leaky bucket regulator when making REST call
        self.lb.acquire()
        resp = self.rest_client.place_limit_order(**kwargs)
        self.lb.release()
        on_order_placed(resp)
        
    @exception_handler
    def replace_limit_order(self, prev_order, on_order_placed, **kwargs):
        self.lb.acquire(2)
        resp = self.rest_client.place_limit_order(**kwargs)
        self.rest_client.cancel_order(prev_order.order_id) #TODO : need to update wallet when we cancel the order
        self.lb.release()
        on_order_placed(resp)

    # Every so often we need to get the balance of our funds just to make sure our local representation matches what the exchange thinks we have
    @exception_handler
    def get_accounts(self):
        # Schedule the next call to this function before we do anything else in case we hit an exception
        self.loop.call_later(5.0, self.get_accounts)

        # Use leaky bucket regulator when making REST call
        self.lb.acquire()
        resp = self.rest_client.get_accounts()
        self.lb.release()

        # Save wallet info 
        for acct in resp:
            if acct["currency"] in self.currency_ids:
                self.available[acct["currency"]] = float(acct["available"]) 
                self.hold[acct["currency"]] = float(acct["hold"])
                self.balance[acct["currency"]] = float(acct["balance"])

                self.log_info("{} available({}) hold({}) balance({})".format(acct["currency"], self.available[acct["currency"]], self.hold[acct["currency"]], self.balance[acct["currency"]]))
        
    # Periodically list our open order to see if we have 0 or >1 orders open and act accordingly
    @exception_handler
    def order_watchdog(self):
        # Schedule the next call to this function before we do anything else in case we hit an exception
        self.loop.call_later(15.0, self.order_watchdog)

        self.lb.acquire(2)
        orders = list(self.rest_client.get_orders())
        self.lb.release()

        # Kick off on order watchdog tasks
        buy_orders = [ e for e in orders if e["side"] == "buy"]
        sell_orders = [ e for e in orders if e["side"] == "sell"]
        for agent in self.agents:
            if agent.is_buyer():
                agent.on_order_watchdog( [ e for e in buy_orders if e["product_id"] == agent.product_id] )
            else:
                agent.on_order_watchdog( [ e for e in sell_orders if e["product_id"] == agent.product_id] )
