from src.agents.trading_agent import TradingAgent
from src.order import Order

class Seller(TradingAgent):
    def __init__(self, config):
        super().__init__(config)

    def log_error(self, msg):
        self.logger.log_error("Seller,{}".format(self.product_id), msg)
    
    def log_warn(self, msg):
        self.logger.log_warn("Seller,{}".format(self.product_id), msg)

    def log_info(self, msg):
        self.logger.log_info("Seller,{}".format(self.product_id), msg)
    
    def is_buyer(self):
        return False

    def place_limit_order(self, price, size):
        self.exchange.place_limit_order(product_id=self.product_id, side="sell", price=price, size=size, post_only=True, on_order_placed=self.on_order_placed_limit)

    def replace_limit_order(self, price, size):
        self.exchange.replace_limit_order(prev_order=self.order, product_id=self.product_id, side="sell", price=price, size=size, post_only=True, on_order_placed=self.on_order_placed_limit)

    def calculate_price(self, msg, tick_price, tick_price_changes):
        # Calculate our custom alpha offset that we want to buy at
        alpha = max(tick_price_changes*self.dynamic_thresh_multiplier, self.base_pct_chng_mean*self.base_thresh_multiplier)

        # Make sure our calculated price isn't more than 1 step better than the best price being offered currently (fail-safe)
        ask = max(tick_price * (1 + alpha), float(msg["best_ask"]) - self.quote_increment)
        
        return round(ask, self.quote_increment)        

    def calculate_size(self, price):
        # Use portfolio ratio's worth of our target currency to sell
        target = self.exchange.balance[self.target_currency]
        calc_size = self.portfolio_ratio * target
        size = max(min(calc_size, self.exchange.available[self.target_currency]), self.base_min_size)
        return round(size, self.base_increment)

    # Validate that the order we placed had no errors, or respond to the error
    def on_order_placed_limit(self, resp):
        try:
            # Save order id and update balances of wallet
            self.order = Order(price=float(resp["price"]), order_id=resp["id"], order_size=float(resp["size"]), outstanding_order_size=float(resp["size"])-float(resp["filled_size"]))

            self.exchange.hold[self.target_currency] += float(resp["size"]) 
            self.exchange.available[self.target_currency] -= float(resp["size"]) 
            self.log_info("sell {} @ {} success".format(resp["size"], resp["price"]))
        except KeyError:
            self.log_warn("sell order failed to be placed!")

            # Re-initalize order to empty state
            self.order = Order()

            # Determine what went wrong and take remedial action
            if resp["message"] == "Post only mode":
                self.log_warn("order failed because of post only mode")
            # We absolutly ran out of coin, need to buy some BTC and back off alpha 
            elif resp["message"] == "Insufficient funds":
                # self.exchange.place_market_order(product_id=self.product_id, side="buy", size=self.base_min_size*3, on_order_placed=self.on_order_placed_market)
                self.log_warn("Seller, insufficient funds")
            elif resp["message"] == "Order rejected":
                self.log_warn("Order rejected, try again")
            elif resp["message"] == "ServiceUnavailable":
                self.log_error("ServiceUnavailable, try again")
            else:
                self.log_error("order failed for unknown reason")
                self.log_error(resp)

    # This is only used when we run out of coin and have to emergency buy some
    def on_order_placed_market(self, resp):
        try:
            self.log_info("buy {} @ {} success".format(resp["size"], resp["price"]))
        except KeyError:
            self.log_error("market buy failed")
            self.log_error(resp)
    