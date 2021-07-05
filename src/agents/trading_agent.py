from src.order import Order
import abc

MILLI = (10**-6)

class TradingAgent(metaclass=abc.ABCMeta):
    def __init__(self, config):
        self.order = Order()

        self.product_id = config["PRODUCT"]
        self.target_currency, self.base_currency = self.product_id.split("-")
        self.p_diff_thresh = config["P_DIFF_THRESH"]
        self.v_diff_thresh = config["V_DIFF_THRESH"]

        self.base_pct_chng_mean = config["BPCM"]
        self.base_thresh_multiplier = config["BTM"]
        self.dynamic_thresh_multiplier = config["DTM"]
        self.portfolio_ratio = config["PR"]

        self.closed = False

    def close(self):
        if self.order.opened() and self.closed == False:
            self.exchange.cancel_order(self.order.order_id, product_id=self.product_id)
            self.order = Order()
            self.closed = True

    def __del__(self):
        self.close()

    @abc.abstractmethod
    def log_error(self, msg):
        return

    @abc.abstractmethod
    def log_warn(self, msg):
        return

    @abc.abstractmethod
    def log_info(self, msg):
        return

    @abc.abstractmethod
    def is_buyer(self):
        return

    def on_tick(self, msg, tick_price, tick_price_changes):
        try:
            # Calculate price and volume we would trade at for a new order
            new_order_price = self.calculate_price(msg, tick_price, tick_price_changes)
            new_order_size = self.calculate_size(new_order_price)

            # If order is not opened, order price will be -1 and this will always be false
            price_threshold = abs( new_order_price - self.order.price ) / self.order.price >= self.p_diff_thresh
            
            try:
                size_threshold = abs( self.order.outstanding_order_size - new_order_size) / self.order.outstanding_order_size >= self.v_diff_thresh
            # If outstanding order volume is 0, then order was filled and we need to put a new one on
            except ZeroDivisionError:
                self.order = Order()

            # Check if we haven't placed an order yet and if so place one
            if not self.order.opened():
                self.order = Order(price=new_order_price, order_size=new_order_size, outstanding_order_size=new_order_size)
                self.place_limit_order(new_order_price, new_order_size)
                self.log_info("new order_price({}) order_size({})".format(new_order_price, new_order_size))
                
            # Check if we need to update our order and if so replace our order
            elif price_threshold or size_threshold:
                self.order = Order(price=new_order_price, order_size=new_order_size, outstanding_order_size=new_order_size)
                self.replace_limit_order(new_order_price, new_order_size)
                self.log_info("replace order_price({}) order_size({})".format(new_order_price, new_order_size))

            # No action needed right now
            else:
                self.log_info("noop order_price({}) order_size({})".format(new_order_price, new_order_size))

        except (AttributeError, KeyError) as e:
            self.log_info("data structures not ready yet")
            print(e)

    @abc.abstractmethod
    def place_limit_order(self, price, size):
        return

    @abc.abstractmethod
    def replace_limit_order(self, price, size):
        return

    @abc.abstractmethod
    def calculate_price(self, msg, tick_price, tick_price_changes):
        return

    @abc.abstractmethod
    def calculate_size(self, price):
        return

    # Validate that the order we placed had no errors, or respond to the error
    @abc.abstractmethod
    def on_order_placed_limit(self, resp):
        return

    # This is only used when we run out of coin and have to emergency buy some
    @abc.abstractmethod
    def on_order_placed_market(self, resp):
        return

    # When we get an order filled, log info about it and decrease the outstanding order size
    def on_fill(self, msg):
        self.log_info("fill size({}) price({}) side({}) maker_fee_rate({})".format(msg["size"], msg["price"], msg["side"], msg["maker_fee_rate"]))
        self.order.outstanding_order_size -= float(msg["size"])

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