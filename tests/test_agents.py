from src.agents.buyer import Buyer
import time

def get_test_agent():
    config = {}
    config["PRODUCT"] = "BTC-USD"
    config["TRADE"] = "True"
    config["P_DIFF_THRESH"] = 0.001
    config["V_DIFF_THRESH"] = 0.25
    config["BPCM"] = 0.0001
    config["BTM"] = 175.0
    config["DTM"] = 9.0
    config["PR"] = 0.15

    return Buyer(config)

# Test constructor
def test_constructor():
    agent = get_test_agent()

    assert agent.order.opened() == False
    
    assert agent.product_id == "BTC-USD"
    assert agent.target_currency == "BTC"
    assert agent.base_currency == "USD"
    assert agent.p_diff_thresh == 0.001
    assert agent.v_diff_thresh == 0.25

    assert agent.base_pct_chng_mean == 0.0001
    assert agent.base_thresh_multiplier == 175.0
    assert agent.dynamic_thresh_multiplier == 9.0
    assert agent.portfolio_ratio == 0.15

# Test on_tick

# Test on_fill

# Test on_order_watchdog