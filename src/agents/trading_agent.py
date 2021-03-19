import numpy as np
import time
from src.order import Order

P_DIFF_THRESH = 0.0010
V_DIFF_THRESH = 0.25
LONG_TIME_MS = (5 * 60 * 1000)
SHORT_TIME_MS = (30 * 1000)
MILLI = (10**-6)

class TradingAgent:
    def __init__(self, config):
        self.order = Order()
        self.last_alpha_update = time.time_ns()*MILLI
        self.alpha = config["AlphaAvg"]

        self.product_id = config["Product"]
        self.target_currency, self.base_currency = self.product_id.split("-")
        self.alpha_avg = config["AlphaAvg"]
        self.alpha_std = config["AlphaStd"]
        self.alpha_upper = config["AlphaUpperBound"]
        self.alpha_lower = config["AlphaLowerBound"]
        self.alpha_up_tick = config["AlphaUpTick"]
        self.alpha_down_tick = config["AlphaDownTick"]

    def __del__(self):
        pass

    def close(self):
        if self.order.opened():
            self.exchange.cancel_order(self.order.order_id, product_id=self.product_id)

    def log_error(self, msg):
        raise Exception("log_error not implemented")
    
    def log_warn(self, msg):
        raise Exception("log_warn not implemented")

    def log_info(self, msg):
        raise Exception("log_info not implemented")

    def is_buyer(self):
        raise Exception("is_buyer not implemented")

    def on_tick(self, msg, mid_price):
        alpha_updated = False
        try:
            # If we haven't been trading, lower alpha
            time_since_last_update = time.time_ns()*MILLI - self.last_alpha_update
            try:
                time_since_last_trade = time.time_ns()*MILLI - self.last_trade_ms
                if time_since_last_update >= LONG_TIME_MS and time_since_last_trade >= LONG_TIME_MS:
                    self.alpha = self.alpha_limits(self.alpha/1.25)
                    self.last_alpha_update = time.time_ns()*MILLI
                    alpha_updated = True
            except AttributeError:
                if time_since_last_update >= LONG_TIME_MS:
                    self.alpha = self.alpha_limits(self.alpha/1.25)
                    self.last_alpha_update = time.time_ns()*MILLI   
                    alpha_updated = True

            # Calculate price and volume we would trade at for a new order
            new_order_price = self.calculate_price(msg, mid_price)
            new_order_size = self.calculate_size(new_order_price)

            # If order is not opened, order price will be -1 and this will always be false
            price_threshold = abs( new_order_price - self.order.price ) / self.order.price >= P_DIFF_THRESH
            
            try:
                size_threshold = abs( self.order.outstanding_order_size - new_order_size) / self.order.outstanding_order_size >= V_DIFF_THRESH
            # If outstanding order volume is 0, then order was filled and we need to put a new one on
            except ZeroDivisionError:
                size_threshold = True

            self.log_info("OPENED {}".format(self.order.opened()))
            self.log_info("{} {}".format(price_threshold, size_threshold))

            # Check if we haven't placed an order yet and if so place one
            if not self.order.opened():
                self.order = Order(price=new_order_price, order_size=new_order_size, outstanding_order_size=new_order_size)
                self.place_limit_order(new_order_price, new_order_size)
                self.log_info("new alpha({}) last_update_t({})".format(self.alpha, time_since_last_update))
                
            # Check if we need to update our order and if so replace our order
            elif price_threshold or size_threshold:
                self.order = Order(price=new_order_price, order_size=new_order_size, outstanding_order_size=new_order_size)
                self.replace_limit_order(new_order_price, new_order_size)
                self.log_info("replace alpha({}) last_update_t({})".format(self.alpha, time_since_last_update))

            # No action needed right now
            else:
                self.log_info("noop alpha({}) last_update_t({})".format(self.alpha, time_since_last_update))

        except (AttributeError, KeyError) as e:
            self.log_info("data structures not ready yet")
            print(e)

    def alpha_limits(self, a):
        return np.clip(a, self.alpha_lower, self.alpha_upper)

    def place_limit_order(self, price, size):
        raise Exception("place_limit_order not implemented")

    def replace_limit_order(self, price, size):
        raise Exception("replace_limit_order not implemented")

    def calculate_price(self, msg, mid_price):
        raise Exception("calculate_price not implemented")       

    def calculate_size(self, price):
        raise Exception("calculate_size not implemented")       

    # Validate that the order we placed had no errors, or respond to the error
    def on_order_placed_limit(self, resp):
        raise Exception("on_order_placed_limit not implemented")       

    # This is only used when we run out of coin and have to emergency buy some
    def on_order_placed_market(self, resp):
        raise Exception("on_order_placed_market not implemented")       

    def on_fill(self, msg):
        self.log_info("fill size({}) price({}) side({}) maker_fee_rate({})".format(msg["size"], msg["price"], msg["side"], msg["maker_fee_rate"]))

        # Decrease the outstanding_order_size
        self.order.outstanding_order_size -= float(msg["size"])

        # Increse alpha on each fill
        self.alpha = self.alpha_limits(self.alpha*1.0075)
        self.last_alpha_update = time.time_ns()*MILLI

        # # If we have been trading too much, increse alpha
        # try:
        #     # Only count as a trade when we fill the whole order
        #     if self.order.filled():
        #         time_since_last_trade = time.time_ns()*MILLI - self.last_trade_ms

        #         if time_since_last_trade <= SHORT_TIME_MS:
        #             self.alpha = self.alpha_limits(self.alpha*5)

        # except AttributeError:
        #     self.log_info("first trade, can't update alpha yet")  

        # Update time of last trade
        self.last_trade_ms = time.time_ns()*MILLI

    # Match channel doesn't guarantee delivery so we need to watch our open orders
    # and make sure we stay in a good state
    def on_order_watchdog(self, orders):
        # Order got filled or closed and we missed it
        # so we need to make sure we place an order
        if len(orders) == 0:
            self.order = Order()
        # Check consistency of open orders with the information we have stored
        else:
            cancelled_orders = 0
            for order in orders:
                if not order["id"] == self.order.order_id:
                    self.exchange.cancel_order(order_id=order["id"])
                    cancelled_orders += 1

            # This is bad news, it means all outstanding orders
            # were unknown by our trading algorithm
            if cancelled_orders == len(orders):
                self.order = Order()