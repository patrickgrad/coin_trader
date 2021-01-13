import numpy as np
import asyncio
import cbpro
import time
import collections as col
import dateutil.parser
import inspect

def lineno():
    """Returns the current line number in our program."""
    return inspect.currentframe().f_back.f_lineno

LOG_ERROR = 1
LOG_WARN  = 2
LOG_INFO  = 3
LOG_OFF   = 4

TICK_LOOKBACK_TIME = (15 * 1000)

async def noop():
    return

class TickerClient(cbpro.WebsocketClient):
    def on_open(self):
        self.url =  "wss://ws-feed-public.sandbox.pro.coinbase.com" # "wss://ws-feed.pro.coinbase.com/"
        self.products = ["BTC-USD"]
        self.channels = ["ticker", "status", "user"]

        self.auth = True
        self.api_key = "29ac1db14d0842c65b6a0af7d4db2a4f"
        self.api_secret = "eGw/OKZeUIWKbrT4ehDN3gkPMFJqHavuEDT8D/QQ2Si/pXB/olKUcExnQ0SwhlSMVmA4JIxZZi2ScWEsX4NDXg=="
        self.api_passphrase = "afm8rcw81x"

        self.samples = col.deque()
        
        self.logger.log_info("TickerClient", "-- Match Socket Opened --")

    def on_error(self, e, data=None):
        self.error = e
        self.stop = True
        self.logger.log_error("TickerClient", "{} - data: {}".format(e, data))

    def on_message(self, msg):

        if msg["type"] == "ticker":
            ts = msg["side"]

            if ts == "buy":
                ms = "sell"
            else:
                ms = "buy"

            msg["taker_side"] = ts
            msg["maker_side"] = ms

            # Update list of samples and get rolling average volume and price
            ts = int(dateutil.parser.parse(msg["time"]).timestamp() * 1000)
            self.samples.append([ ts, float(msg["price"]) ]) # tuple of time, volume, price

            # print([ ts, float(msg["last_size"]), float(msg["price"]) ])

            while len(self.samples) > 0 and (ts - self.samples[0][0]) > TICK_LOOKBACK_TIME:
                # print("sample is {}ms old ({} {})".format(ts - self.samples[0][0], self.samples[0][0], ts))
                self.samples.popleft()

            # print(len(self.samples))

            avg_price = 0
            for e in self.samples:
                avg_price += e[1]
            self.exchange.avg_price = avg_price / len(self.samples)

            asyncio.run(self.on_message_async(msg))

        elif msg["type"] == "status":
            products = msg["products"]
            for product in products:
                if product["id"] == "BTC-USD":
                    self.exchange.product = product

                    self.exchange.product["base_min_size"] = float(self.exchange.product["base_min_size"])
                    self.exchange.product["quote_increment"] = abs(int(np.log10(float(self.exchange.product["quote_increment"]))))
                    self.exchange.product["base_increment"] = abs(int(np.log10(float(self.exchange.product["base_increment"]))))

        elif msg["type"] == "match":
            try:
                self.exchange.maker_fee_rate = float(msg["maker_fee_rate"])
                asyncio.run(self.on_fill_async(msg))
            except KeyError:
                self.exchange.log_warn("We were not the maker (GUI manual order or rebalance order?)")

    async def on_fill_async(self, msg):
        # Kick off on fill tasks
        if msg["side"] == "buy":
            bof = asyncio.create_task( self.buyer.on_fill(msg) )
        else:
            bof = asyncio.create_task( noop() )

        if msg["side"] == "sell":
            sof = asyncio.create_task( self.seller.on_fill(msg) )
        else:
            sof = asyncio.create_task( noop() )

        # Wait until they're done before continuing
        await bof
        await sof
       
    async def on_message_async(self, msg):       
        # Kick off on tick tasks
        bot = asyncio.create_task( self.buyer.on_tick(msg) )
        sot = asyncio.create_task( self.seller.on_tick(msg) )

        # Wait until they're done before continuing
        await bot
        await sot

    def on_close(self):
        self.logger.log_info("TickerClient", "-- Match Socket Closed --")

class Exchange:
    def __init__(self, loop, logger, buyer, seller):
        self.rest_client = cbpro.AuthenticatedClient("29ac1db14d0842c65b6a0af7d4db2a4f", "eGw/OKZeUIWKbrT4ehDN3gkPMFJqHavuEDT8D/QQ2Si/pXB/olKUcExnQ0SwhlSMVmA4JIxZZi2ScWEsX4NDXg==", "afm8rcw81x", api_url="https://api-public.sandbox.pro.coinbase.com")
        self.rest_client.cancel_all()
        self.rest_tokens = 0                
        self.ws_tickers = TickerClient()
        self.ws_tickers.exchange = self
        self.ws_tickers.buyer = buyer
        self.ws_tickers.seller = seller
        self.ws_tickers.logger = logger
        self.ws_tickers.start()

        self.logger = logger
        self.logger.exchange = self
        self.logger.buyer = buyer
        self.logger.seller = seller

        self.buyer = buyer
        self.buyer.exchange = self
        self.buyer.logger = self.logger
        self.seller = seller
        self.seller.exchange = self
        self.seller.logger = self.logger

        self.closed = False
        self.loop = loop

        self.get_accounts()
        self.add_rest_tokens()
        self.order_watchdog()
        self.exception_watchdog()


    def __del__(self):
        self.close()

    def close(self):
        self.closed = True
        self.ws_tickers.close()

    def log_error(self, msg):
        self.logger.log_error("Exchange", msg)
    
    def log_warn(self, msg):
        self.logger.log_warn("Exchange", msg)

    def log_info(self, msg):
        self.logger.log_info("Exchange", msg)

    # Every 2 seconds we need to get the balance of our funds
    def get_accounts(self):
        # Need a token to do this operation, if we don't have it abort
        if self.rest_tokens >= 1:
            resp = self.rest_client.get_accounts()
            self.rest_tokens -= 1

            for acct in resp:
                if acct["currency"] == "USD":
                    self.available_usd = float(acct["available"]) # shared memory
                    self.hold_usd = float(acct["hold"])
                    self.balance_usd = float(acct["balance"])

                if acct["currency"] == "BTC":
                    self.available_btc = float(acct["available"]) # shared memory
                    self.hold_btc = float(acct["hold"])
                    self.balance_btc = float(acct["balance"])

            self.log_info("BTC available({}) hold({}) balance({})".format(self.available_btc, self.hold_btc, self.balance_btc))
            self.log_info("USD available({}) hold({}) balance({})".format(self.available_usd, self.hold_usd, self.balance_usd))

        self.loop.call_later(5.0, self.get_accounts)

    # Average of 5 REST requests per second max
    # Can burst up to 10 requests per second
    def add_rest_tokens(self):
        self.rest_tokens += 1

        if self.rest_tokens > 10:
            self.rest_tokens = 10

        if self.rest_tokens < 10:
            self.log_info("tokens : {}".format(self.rest_tokens))

        self.loop.call_later(0.2, self.add_rest_tokens)

    # Periodically list our open order to see if we have 0 or >1 orders open and act accordingly
    def order_watchdog(self):
        if self.rest_tokens >= 2:
            orders_gen = self.rest_client.get_orders()
            orders = list(orders_gen)

            self.rest_tokens -= 2

            # Kick off on order watchdog tasks
            self.buyer.on_order_watchdog( [ e for e in orders if e["side"] == "buy"] )
            self.seller.on_order_watchdog( [ e for e in orders if e["side"] == "sell"] )

            self.loop.call_later(10.0, self.order_watchdog)
        else:
            # If no tokens are availible wait 3 seconds and try again
            self.loop.call_later(3.0, self.order_watchdog)

    # Periodically check that we haven't hit an unhandled exception
    def exception_watchdog(self):
        if self.seller.unhandled_exception or self.buyer.unhandled_exception or self.ws_tickers.stop:
            self.close()
            self.loop.stop()
        # No exceptions, continue as usual
        else:
            self.loop.call_later(1.0, self.exception_watchdog)
            
        

