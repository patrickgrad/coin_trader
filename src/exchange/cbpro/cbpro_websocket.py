import collections as col
import numpy as np
import cbpro

TICK_LOOKBACK_SAMPLES = 6

# WARNING : many callbackes in this class are called from the thread in the
#           WebsocketClient class, not the main thread
class TickerClient(cbpro.WebsocketClient):
    # Called from MainThread
    def on_open(self):
        # Need to hold the exchange credentials
        self.auth = True
        self.api_key = self.exchange.api_key
        self.api_secret = self.exchange.api_secret
        self.api_passphrase = self.exchange.api_passphrase
        self.url =  self.exchange.ws_url
        self.products = self.exchange.product_ids
        self.channels = ["ticker", "status", "user"]

        # Set up data structures to hold the recent samples
        self.samples = {}
        for product_id in self.products:
            self.samples[product_id] = col.deque()
        
        self.logger.log_info("TickerClient", "-- Match Socket Opened --")

    # Called from WebsocketClient thread
    def on_error(self, e, data=None):
        self.error = e
        self.stop = True
        self.logger.log_error("TickerClient", "{} - data: {}".format(e, data))

    # Called from WebsocketClient thread
    def on_message(self, msg):
        if msg["type"] == "ticker":
            product_id = msg["product_id"]
            ts = msg["side"]

            if ts == "buy":
                ms = "sell"
            else:
                ms = "buy"

            msg["taker_side"] = ts
            msg["maker_side"] = ms

            # Update list of samples and get rolling average volume and price
            self.samples[product_id].append(float(msg["price"]))

            if len(self.samples[product_id]) > TICK_LOOKBACK_SAMPLES:
                self.samples[product_id].popleft()
            elif len(self.samples[product_id]) == 1:
                return

            tick_price_changes = 0
            for i,p in enumerate(self.samples[product_id]):
                if i == 0:
                    prev_p = p
                else:
                    tick_price_changes += (p-prev_p)/prev_p
                    prev_p = p
            tick_price_changes /= len(self.samples[product_id])-1

            self.exchange.log_info("tick product_id({}) tick_price_changes({}) price({}) taker_side({}) size({}) bid({}) ask({})".format(product_id, tick_price_changes, msg["price"], msg["side"], msg["last_size"], msg["best_bid"], msg["best_ask"]))

            # Only need to do this part if we have a trading agent associated with this product
            if product_id in self.exchange.prodid_to_agents:
                # Look at agents for this product id only and kick off on tick tasks
                for agent in self.exchange.prodid_to_agents[product_id]:
                    # Want to launch this in the main thread, so need to use threadsafe version of call soon
                    self.loop.call_soon_threadsafe(agent.on_tick, msg, float(msg["price"]), tick_price_changes)

        elif msg["type"] == "match":
            try:
                self.exchange.maker_fee_rate = float(msg["maker_fee_rate"])
                self.on_fill(msg)
            except KeyError:
                self.exchange.log_warn("We were not the maker (GUI manual order or rebalance order?)")

        elif msg["type"] == "status":
            # Only way to do this without changing the WebsocketClient, do it in a path not triggered too often
            self.thread.name = "TickerClient"

            # Grab the product meta-data for our trading agents
            products = msg["products"]
            for product in products:
                if product["id"] in self.exchange.prodid_to_agents:
                    for agent in self.exchange.prodid_to_agents[product["id"]]:
                        agent.base_min_size = float(product["base_min_size"])
                        agent.quote_increment = abs(int(np.log10(float(product["quote_increment"]))))
                        agent.base_increment = abs(int(np.log10(float(product["base_increment"]))))

        

    # Called from WebsocketClient thread (actually called from on_message)
    def on_fill(self, msg):
        # Look at agents for this product id only and kick off on fill tasks
        target, base = msg["product_id"].split("-")
        for agent in self.exchange.prodid_to_agents[msg["product_id"]]:
            # Adjust wallet (fee comes out of base currency)
            if msg["side"] == "buy":
                self.exchange.hold[base] -= float(msg["size"]) * float(msg["price"])
                self.exchange.available[base] -= self.exchange.maker_fee_rate * ( float(msg["size"]) * float(msg["price"]) )
                self.exchange.available[target] += float(msg["size"])
            if msg["side"] == "sell":
                self.exchange.hold[target] -= float(msg["size"]) 
                self.exchange.available[base] -= self.exchange.maker_fee_rate * ( float(msg["size"]) * float(msg["price"]) )
                self.exchange.available[base] += float(msg["size"]) * float(msg["price"])
            self.exchange.balance[base] = self.exchange.hold[base] + self.exchange.available[base]
            self.exchange.balance[target] = self.exchange.hold[target] + self.exchange.available[target]

            # Kick off on_fill callback
            # Want to launch this in the main thread, so need to use threadsafe version of call soon
            self.loop.call_soon_threadsafe(agent.on_fill, msg)

    # Called from MainThread
    def on_close(self):
        self.logger.log_info("TickerClient", "-- Match Socket Closed --")