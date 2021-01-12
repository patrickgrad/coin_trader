import time

LOG_ERROR = 1
LOG_WARN  = 2
LOG_INFO  = 3
LOG_OFF   = 4

P_DIFF_THRESH = 0.0005
V_DIFF_THRESH = 0.0010
LONG_TIME_MS = (5 * 60 * 1000)
SHORT_TIME_MS = (30 * 1000)

def volume_fn(usd, btc, price):
    ratio = usd / (usd + (btc * price))

    if ratio <= 0.5:
        return (0.005 + ratio * (0.0075 / 0.5)) * (usd / price)
    else:
        return (0.085 * ratio - 0.035) * (usd / price)

class Buyer:
    def __init__(self):
        # percent from 0 to 100 the buyer places the order above the last fill
        self.alpha = 2
        self.our_price = -1
        self.our_bid = -1
        self.open_order_id = ""
        self.outstanding_order_vol = 0
        self.last_alpha_update = time.time_ns()*(10**-6)

    def __del__(self):
        pass          

    def close(self):
        if not self.our_price == -1:
            self.exchange.rest_client.cancel_order(self.open_order_id)

    def log_error(self, msg):
        self.logger.log_error("Buyer", msg)
    
    def log_warn(self, msg):
        self.logger.log_warn("Buyer", msg)

    def log_info(self, msg):
        self.logger.log_info("Buyer", msg)

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

            size_target = max(min(volume_fn(self.exchange.balance_usd, self.exchange.balance_btc, self.exchange.avg_price), self.exchange.available_usd/self.our_bid), self.exchange.product["base_min_size"])
            price_threshold = abs( self.our_price - self.exchange.avg_price ) / self.our_price >= P_DIFF_THRESH
            
            try:
                size_threshold = abs( self.outstanding_order_vol - size_target) / self.outstanding_order_vol >= V_DIFF_THRESH
            # If outstanding order volume is 0, then order was filled and we need to put a new one on
            except ZeroDivisionError:
                size_threshold = True

            # Check if we haven't placed an order yet
            if abs(self.outstanding_order_vol) < 10**-8:
                # Need 1 token to do this operation, if we don't have it abort
                if self.exchange.rest_tokens >= 1:
                    self.place_order(msg)

                    self.log_info("new {} {}".format(self.alpha, time_since_last_update))
                
            # Check if we need to update our order
            elif alpha_updated or price_threshold or size_threshold:
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
            self.our_bid = -1
            self.open_order_id = ""
            self.outstanding_order_vol = 0

    def place_order(self, msg):
        # Send new order 
        self.our_price = self.exchange.avg_price

        self.our_bid = min(self.our_price * (1 - (self.alpha / 100)), float(msg["best_bid"]) + 0.01 )     # make sure our calculated price isn't more than 1 cent better than the best price being offered currently (fail-safe)
        self.our_bid = round(self.our_bid, self.exchange.product["quote_increment"])        

        size = max(min(volume_fn(self.exchange.balance_usd, self.exchange.balance_btc, self.exchange.avg_price), self.exchange.available_usd/self.our_bid), self.exchange.product["base_min_size"])
        size = round(size, self.exchange.product["base_increment"])

        resp = self.exchange.rest_client.place_limit_order(product_id="BTC-USD", side="buy", price=self.our_bid, size=size, post_only=True)
        self.exchange.rest_tokens -= 1

        try:
            # Save order id and update balances of wallet
            self.open_order_id = resp["id"]
            self.outstanding_order_vol = float(resp["size"])
            self.exchange.hold_usd += float(resp["size"]) * float(resp["price"])
            self.exchange.available_usd -= float(resp["size"]) * float(resp["price"])
            self.log_info("buy {} @ {} success".format(resp["size"], resp["price"]))
        except KeyError:
            self.log_warn("buy {} @ {} failed".format(size, self.our_bid))
            self.log_info(resp)

            # Make sure we try to place order again quickly
            self.our_price = -1
            self.our_bid = -1
            self.open_order_id = ""
            self.outstanding_order_vol = 0

            # We weren't quick enough to get our order in, but we already cancelled our old order
            # So now we need to reinitalize some stuff to get it to place an order right away
            if resp["message"] == "Post only mode":
                self.log_warn("order failed because of post only mode")
            # We absolutly ran out of USD, need to sell some coin and back off alpha by factor of 1.1
            elif resp["message"] == "Insufficient funds":
                if self.exchange.rest_tokens >= 1:
                    resp = self.exchange.rest_client.place_market_order(product_id="BTC-USD", side="sell", size=self.exchange.product["base_min_size"]*3)
                    self.exchange.rest_tokens -= 1

                    try:
                        self.log_info("sell {} @ {} success".format(resp["size"], resp["price"]))
                    except KeyError:
                        self.log_warn("sell failed")
                        self.log_info(resp)

                self.alpha *= 1.05
                self.last_alpha_update = time.time_ns()*(10**-6)
            else:
                self.log_error("order failed for unknown reason")
                self.log_error(resp)
                

    async def on_fill(self, msg):
        self.log_info("fill {} {} {} {}".format(msg["size"], msg["price"], msg["side"], msg["maker_fee_rate"]))

        # Decrease the outstanding_order_vol
        self.outstanding_order_vol -= float(msg["size"])

        # Increse alpha on each fill
        self.alpha *= 1.0075
        self.last_alpha_update = time.time_ns()*(10**-6)

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
        self.exchange.hold_usd -= float(msg["size"]) * float(msg["price"])
        self.exchange.available_usd -= self.exchange.maker_fee_rate * ( float(msg["size"]) * float(msg["price"]) )
        self.exchange.available_btc += float(msg["size"])

        self.exchange.balance_usd = self.exchange.hold_usd + self.exchange.available_usd
        self.exchange.balance_btc = self.exchange.hold_btc + self.exchange.available_btc

    def on_order_watchdog(self, orders):
        # Order got filled or closed and we missed it
        # so we need to make sure we place an order
        if len(orders) == 0:
            self.our_price = -1
            self.our_bid = -1
            self.open_order_id = ""
            self.outstanding_order_vol = 0
        # Check consistency of open orders with the 
        # information we have stored
        else:
            cancelled_orders = 0
            for order in orders:
                if not order["id"] == self.open_order_id:
                    if self.exchange.rest_tokens >= 1:
                        self.exchange.rest_client.cancel_order(order["id"])
                        self.exchange.rest_tokens -= 1
                        cancelled_orders += 1

            # This is bad news, it means all outstanding orders
            # were unknown by the trading software
            if cancelled_orders == len(orders):
                self.our_price = -1
                self.our_bid = -1
                self.open_order_id = ""
                self.outstanding_order_vol = 0



