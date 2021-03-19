class Order:
    def __init__(self, price=-1, order_id="", order_size=0, outstanding_order_size=0):
        self.price = price
        self.order_id = order_id
        self.order_size = order_size
        self.outstanding_order_size = outstanding_order_size

    def opened(self):
        return not self.order_id == ""

    def filled(self):
        return abs(self.outstanding_order_size) < 10**-8