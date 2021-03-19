from src.order import Order

# Completely empty order
def test_order_opened_empty():
    assert Order().opened() == False

# Scenario when an order is placed but haven't gotten an response back yet
def test_order_opened_placed():
    o = Order(price=100, order_size=1, outstanding_order_size=1)
    assert o.opened() == False and o.filled() == False

# Scenario when an order is placed and we received the response and it was a success
def test_order_opened_placed():
    o = Order(price=100, order_size=1, order_id="blah-blah-blah", outstanding_order_size=1)
    assert o.opened() == True and o.filled() == False

# Completely empty order
def test_order_opened_partial_fill():
    o = Order(price=100, order_size=1, order_id="blah-blah-blah", outstanding_order_size=0.5)
    assert o.opened() == True and o.filled() == False 

# Completely empty order
def test_order_opened_full_fill():
    o = Order(price=100, order_size=1, order_id="blah-blah-blah", outstanding_order_size=10**-12)
    assert o.opened() == True and o.filled() == True 