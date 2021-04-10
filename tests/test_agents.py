from src.agents.buyer import Buyer
import time

def get_test_agent():
    config = {}
    config["Product"] = "BTC-USD"
    config["AlphaAvg"] = 0.05
    config["AlphaStd"] = 0.0005
    config["AlphaUpperBound"] = 0.09
    config["AlphaLowerBound"] = 0.00009
    config["AlphaUpTick"] = 1.0075
    config["AlphaDownTick"] = 0.8

    return Buyer(config)

# Test constructor
def test_constructor():
    agent = get_test_agent()

    assert agent.order.opened() == False
    assert time.time_ns()*(10**-6) - agent.last_alpha_update < 10**-1
    
    assert agent.product_id == "BTC-USD"
    assert agent.alpha == 0.05
    assert agent.target_currency == "BTC"
    assert agent.base_currency == "USD"
    assert agent.alpha_upper == 0.09
    assert agent.alpha_lower == 0.00009
    
# Test alpha_limits
def test_alpha_limits():
    agent = get_test_agent()

    # Within range, expect no change
    test_alpha = (agent.alpha_lower + agent.alpha_upper)/2
    assert agent.alpha_limits(test_alpha) == test_alpha

    # Too high, bring down to upper limit
    test_alpha = agent.alpha_upper + 1
    assert agent.alpha_limits(test_alpha) == agent.alpha_upper

    # Too low, bring up to lower limit
    test_alpha = agent.alpha_lower - 1
    assert agent.alpha_limits(test_alpha) == agent.alpha_lower

# Test on_tick

# Test on_fill

# Test on_order_watchdog