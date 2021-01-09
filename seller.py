import time

LOG_ERROR = 1
LOG_WARN  = 2
LOG_INFO  = 3
LOG_OFF   = 4

P_DIFF_THRESH = 0.0005
LONG_TIME_MS = (3 * 60 * 1000)
SHORT_TIME_MS = (30 * 1000)

class Seller:
    def __init__(self):
        # percent from 0 to 100 the buyer places the order above the last fill
        self.alpha = 3
        self.our_price = -1
        self.our_ask = -1
        self.open_order_id = ""
        self.outstanding_order_vol = -1
        self.last_alpha_update = time.time_ns()*(10**-6)

    def __del__(self):
        pass

    def close(self):
        if not self.our_price == -1:
            self.exchange.rest_client.cancel_order(self.open_order_id)

    def log_error(self, msg):
        self.logger.log_error("Seller", msg)
    
    def log_warn(self, msg):
        self.logger.log_warn("Seller", msg)

    def log_info(self, msg):
        self.logger.log_info("Seller", msg)

    async def on_tick(self, msg):
        alpha_updated = False
        try:
            # If we haven't been trading, lower alpha
            time_since_last_update = time.time_ns()*(10**-6) - self.last_alpha_update
            try:
                time_since_last_trade = time.time_ns()*(10**-6) - self.last_trade_ms
                if time_since_last_update >= LONG_TIME_MS and time_since_last_trade >= LONG_TIME_MS:
                    self.alpha /= 1.25
                    self.last_alpha_update = time.time_ns()*(10**-6)
                    alpha_updated = True
            except AttributeError:
                if time_since_last_update >= LONG_TIME_MS:
                    self.alpha /= 1.25
                    self.last_alpha_update = time.time_ns()*(10**-6)   
                    alpha_updated = True     

            # Check if we haven't placed an order yet
            if self.our_price == -1:
                # Need 1 token to do this operation, if we don't have it abort
                if self.exchange.rest_tokens >= 1:
                    self.place_order(msg)

                    self.log_info("new {} {}".format(self.alpha, time_since_last_update))

            # Check if we need to update our order
            elif alpha_updated or abs( self.our_price - float(msg["price"]) ) / self.our_price >= P_DIFF_THRESH:

                # Need 2 tokens to do this operation, if we don't have it abort
                if self.exchange.rest_tokens >= 2:

                    # Cancel previous order
                    resp = self.exchange.rest_client.cancel_order(self.open_order_id)
                    #TODO : need to update wallet when we cancel the order
                    self.exchange.rest_tokens -= 1

                    self.place_order(msg)

                    self.log_info("replace {} {}".format(self.alpha, time_since_last_update))

            else:
                self.log_info("noop {} {}".format(self.alpha, time_since_last_update))
        except AttributeError:
            self.log_info("data structures not ready yet")
            self.our_price = -1
            self.our_ask = -1
            self.open_order_id = ""
            self.outstanding_order_vol = -1

    def place_order(self, msg):
        # Send new order 
        self.our_price = self.exchange.avg_price

        self.our_ask = max(self.our_price * (1 + (self.alpha / 100)), float(msg["best_ask"]) - 0.01 )     # make sure our calculated price isn't more than 1 cent better than the best price being offered currently (fail-safe)
        self.our_ask = round(self.our_ask, self.exchange.product["quote_increment"])        

        size = max(min(self.exchange.avg_volume, self.exchange.available_btc), self.exchange.product["base_min_size"])
        size = round(size, self.exchange.product["base_increment"])

        resp = self.exchange.rest_client.place_limit_order(product_id="BTC-USD", side="sell", price=self.our_ask, size=size, post_only=True)
        self.exchange.rest_tokens -= 1

        try:
            # Save order id and update balances of wallet
            self.open_order_id = resp["id"]
            self.outstanding_order_vol = float(resp["size"])
            self.exchange.hold_btc += float(resp["size"]) 
            self.exchange.available_btc -= float(resp["size"]) 
            self.log_info("sell {} @ {} success".format(size, self.our_ask))
        except KeyError:
            self.log_warn("sell {} @ {} failed".format(size, self.our_ask))
            self.log_info(resp)

            # We weren't quick enough to get our order in, but we already cancelled our old order
            # So now we need to reinitalize some stuff to get it to place an order right away
            if resp["message"] == "Post only mode":
                self.our_price = -1
                self.our_ask = -1
                self.open_order_id = "" 
                self.outstanding_order_vol = -1

                self.log_warn("order failed because of post only mode")
            else:
                self.log_error("order failed for unknown reason")
                self.log_error(resp)


    async def on_fill(self, msg):
        self.log_info("fill {} {} {} {}".format(msg["size"], msg["price"], msg["side"], msg["maker_fee_rate"]))

        # Decrease the outstanding_order_vol
        self.outstanding_order_vol -= float(msg["size"])

        # If we have been trading too much, increse alpha
        try:
            # Only count as a trade when we fill the whole order
            if abs(self.outstanding_order_vol) < 10**-8:
                time_since_last_trade = time.time_ns()*(10**-6) - self.last_trade_ms

                if time_since_last_trade <= SHORT_TIME_MS:
                    self.alpha *= 5

                if self.alpha > 50:
                    self.alpha = 50
        except AttributeError:
            self.log_info("first trade, can't update alpha yet")  

        # Update time of last trade
        self.last_trade_ms = time.time_ns()*(10**-6)

        # Adjust wallet stats now (fee comes out of USD)
        self.exchange.hold_btc -= float(msg["size"]) 
        self.exchange.available_usd -= self.exchange.maker_fee_rate * ( float(msg["size"]) * float(msg["price"]) )
        self.exchange.available_usd += float(msg["size"]) * float(msg["price"])

        self.exchange.balance_btc = self.exchange.hold_btc + self.exchange.available_btc
        self.exchange.balance_usd = self.exchange.hold_usd + self.exchange.available_usd

