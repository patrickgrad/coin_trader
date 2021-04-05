import time
from agents.trading_agent import TradingAgent
from order import Order
from logger import Logger

class Buyer(TradingAgent):
    def __init__(self, config):
        super().__init__(config)
        self.our_bid = -1

    def log_error(self, msg):
        self.logger.log_error("Buyer,{}".format(self.product_id), msg)
    
    def log_warn(self, msg):
        self.logger.log_warn("Buyer,{}".format(self.product_id), msg)

    def log_info(self, msg):
        self.logger.log_info("Buyer,{}".format(self.product_id), msg)

    def is_buyer(self):
        return True

    def place_limit_order(self, price, size):
        self.exchange.place_limit_order(product_id=self.product_id, side="buy", price=price, size=size, post_only=True, on_order_placed=self.on_order_placed_limit)

    def replace_limit_order(self, price, size):
        self.exchange.replace_limit_order(prev_order=self.order, product_id=self.product_id, side="buy", price=price, size=size, post_only=True, on_order_placed=self.on_order_placed_limit)

    def calculate_price(self, msg, mid_price):
        bid = min(mid_price * (1 - (self.alpha / 100)), float(msg["best_bid"]) + self.quote_increment)     # make sure our calculated price isn't more than 1 cent better than the best price being offered currently (fail-safe)
        return round(bid, self.quote_increment) 

    def calculate_size(self, price):
        base = self.exchange.balance[self.base_currency]
        target = self.exchange.balance[self.target_currency]

        ratio = base / (base + (target * price))
        if ratio <= 0.5:
            calc_size = (0.005 + ratio * (0.0075 / 0.5)) * (base / price)
        else:
            calc_size = (0.085 * ratio - 0.035) * (base / price)

        size = max(min(calc_size, self.exchange.available[self.base_currency]/price), self.base_min_size)
        return round(size, self.base_increment)

    # Validate that the order we placed had no errors, or respond to the error
    def on_order_placed_limit(self, resp):
        self.log_info("ON ORDER PLACED LIMIT")
        try:
            # Save order id and update balances of wallet
            self.order = Order(price=float(resp["price"]), order_id=resp["id"], order_size=float(resp["size"]), outstanding_order_size=float(resp["size"])-float(resp["filled_size"]))

            self.exchange.hold[self.base_currency] += float(resp["size"]) * float(resp["price"])
            self.exchange.available[self.base_currency] -= float(resp["size"]) * float(resp["price"])
            self.log_info("buy {} @ {} success".format(resp["size"], resp["price"]))
        except KeyError:
            self.log_warn("buy order failed to be placed!")

            # Re-initalize order to empty state
            self.order = Order()

            # Determine what went wrong and take remedial action
            if resp["message"] == "Post only mode":
                self.log_warn("order failed because of post only mode")
            # We absolutly ran out of USD, need to sell some coin and back off alpha
            elif resp["message"] == "Insufficient funds":
                self.exchange.place_market_order(product_id=self.product_id, side="sell", size=self.base_min_size*3, on_order_placed=self.on_order_placed_market)
            elif resp["message"] == "Order rejected":
                self.log_warn("Order rejected, try again")
            elif resp["message"] == "ServiceUnavailable":
                self.log_error("ServiceUnavailable, try again")
            else:
                self.log_error("order failed for unknown reason")
                self.log_error(resp)

    # This is only used when we run out of USD and have to emergency sell some coin
    def on_order_placed_market(self, resp):
        try:
            self.log_info("sell {} @ {} success".format(resp["size"], resp["price"]))
        except KeyError:
            self.log_error("market sell failed")
            self.log_error(resp)
