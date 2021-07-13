import os
import asyncio
from agents.buyer import Buyer
from agents.seller import Seller
import pandas as pd
import random
from threading import Thread
import time
from functools import partial

class BacktestExchange:
    def __init__(self, logger, config):
        self.opened = False
        self.closed = False

        self.logger = logger
        self.logger.exchange = self

        self.tick_sheet = pd.read_csv(self.get_system_variable("PATH_TO_TICKS_CSV"))
        self.wallet_sheet = pd.read_csv(self.get_system_variable("PATH_TO_WALLET_CSV"))

        # Get list of currencies we are trading
        self.product_ids = []
        self.configs = {}
        for row in config.to_dict(orient="records"):
            self.product_ids.append(row["Product"])
            self.configs[row["Product"]] = row
        self.currency_ids = self.products_to_currencies(self.product_ids)

        # Setup agents for trading
        self.agents = []
        self.prodid_to_agents = {}
        for prod_id in self.product_ids:
            # Only add trading agents for products we actually want to trade, we can also just gather data
            if self.configs[prod_id]["Trade"]:
                b = Buyer(self.configs[prod_id])
                s = Seller(self.configs[prod_id])
                b.exchange = self
                b.logger = logger
                b.quote_increment = 5
                b.base_increment = 2
                b.base_min_size = 0.0001
                s.exchange = self
                s.logger = logger
                s.quote_increment = 5
                s.base_increment = 2
                s.base_min_size = 0.0001
                self.agents.append(b)
                self.agents.append(s)
                self.prodid_to_agents[prod_id] = [b, s]

        # Setup wallet with data from our wallet csv
        self.available = {}
        self.hold = {}
        self.balance = {}
        for row in self.wallet_sheet.to_dict(orient="records"):
            self.available[row["Currency"]] = row["Available"]
            self.hold[row["Currency"]] = row["OnHold"]
            self.balance[row["Currency"]] = row["Available"] + row["OnHold"]

        # Set fee rates
        self.maker_fee_rate = 0.001
        self.taker_fee_rate = 0.002

        # Data structure to hold future events we want to do
        # Each element is a tuple of (simulation_time, callback)
        self.sim_event_loop_tasks = []

        # Data structure holding our open orders
        # Key is order id, value is dict of info
        self.open_orders = {}

        # Setup simulation time and row pointer
        self.i = 0
        self.t = self.tick_sheet["time"][0]

        # Simulation thread that will call do_time_step() until we run out of data in ticks.csv
        self.thread = Thread(target=self.simulate)
        self.thread.name = "BacktestExchange"

    # Delay loop based initialization until we are in asyncio context
    # Not important for the backtest environment, but needs to be
    # compatible with the main way of running things
    def open(self):
        if not self.opened:
            self.loop = asyncio.get_running_loop()
            self.order_watchdog()
            self.thread.start()
            self.opened = True

    # Safety net in case we forget to call close
    def __del__(self):
        self.close()

    # Tear down object, not much to do here
    def close(self):
        if not self.closed:
            self.thread.join()
            self.closed = True

    def log_error(self, msg):
        self.logger.log_error("BacktestExchange", msg)
    
    def log_warn(self, msg):
        self.logger.log_warn("BacktestExchange", msg)

    def log_info(self, msg):
        self.logger.log_info("BacktestExchange", msg)

    def products_to_currencies(self, products):
        ret = set()
        for p in products:
            curs = p.split("-")
            
            for c in curs:
                ret.add(c)

        return ret

    def get_system_variable(self, name):
        try:
            return os.environ[name]
        except KeyError:
            self.log_warn('"{}" does not exist!'.format(name))
            val = input("{}:".format(name))
            return val

    def calculate_fill(self, side, size, price, product_id):
        target, base = product_id.split("-")

        if side == "buy":
            # subtract from base, add to target
            self.available[base] -= price*size
            self.available[target] += size
        
        elif side == "sell":
            # subtract from target, add to base
            self.available[target] -= size
            self.available[base] += price*size
        else:
            raise Exception("side argument must be either buy or sell")   

        # take fee out of base
        self.available[base] -= price*size*self.taker_fee_rate    

        # recalculate total balances
        self.balance[target] = self.available[target] + self.hold[target]
        self.balance[base] = self.available[base] + self.hold[base]     

    def cancel_order(self, order_id):
        # delete key if it exists from open orders
        self.open_orders.pop(order_id, None)
        
    def place_market_order(self, on_order_placed, size, side, product_id, **kwargs):
        last_bid = self.tick_sheet["bid"][self.i]
        last_ask = self.tick_sheet["ask"][self.i]

        if side == "buy":
            price = last_ask
        elif side == "sell":
            price = last_bid
        else:
            raise Exception("side argument must be either buy or sell")

        self.calculate_fill(side=side, size=size, price=price, product_id=product_id)

        resp = {}
        resp["size"] = size
        resp["price"] = price
        on_order_placed(resp)
        
    def place_limit_order(self, on_order_placed, size, side, price, product_id, **kwargs):
        order = {}
        order["size"] = size
        order["side"] = side
        order["price"] = price
        order["product_id"] = product_id

        new_id = random.randint(0, 1000000)
        while new_id in self.open_orders:
            new_id = random.randint(0, 1000000)

        new_id = str(new_id)
        order["id"] = new_id
        self.open_orders[new_id] = order

        resp = {}
        resp["id"] = new_id
        resp["price"] = price
        resp["size"] = size
        resp["filled_size"] = 0.0
        on_order_placed(resp)

    def replace_limit_order(self, prev_order, on_order_placed, size, side, price, product_id, **kwargs):
        self.place_limit_order(size=size, side=side, price=price, product_id=product_id, on_order_placed=on_order_placed)
        self.cancel_order(prev_order.order_id)
        
    # Periodically list our open order to see if we have 0 or >1 orders open and act accordingly
    def order_watchdog(self):
        # Kick off on order watchdog tasks
        buy_orders = [ v for k,v in self.open_orders.items() if v["side"] == "buy"]
        sell_orders = [ v for k,v in self.open_orders.items() if v["side"] == "sell"]
        for agent in self.agents:
            if agent.is_buyer():
                agent.on_order_watchdog( [ e for e in buy_orders if e["product_id"] == agent.product_id] )
            else:
                agent.on_order_watchdog( [ e for e in sell_orders if e["product_id"] == agent.product_id] )

        # Reschedule callback to trigger after 15 seconds of simulation time have passed
        FIFTEEN_S_IN_MS = 15 * 1000
        self.sim_event_loop_tasks.append((self.t + FIFTEEN_S_IN_MS, self.order_watchdog))

    # Can increse delta_t for faster simulations, decrese delta_t for more accurate simulations
    def do_time_step(self, delta_t=1):
        print(self.t, self.i)
        # print(len(self.agents))

        # Check sim event loop for tasks we need to do
        del_list = []
        for i,task in enumerate(self.sim_event_loop_tasks):
            if task[0] <= self.t:
                task[1]()
                del_list.append(i)
        
        new_list = []
        for i,task in enumerate(self.sim_event_loop_tasks):
            if i not in del_list:
                new_list.append(task)

        self.sim_event_loop_tasks = new_list

        # Process the ticks that have come in
        while self.t == int(self.tick_sheet["time"][self.i]/delta_t):
            # Check if any open orders filled 
            for order_id,order in self.open_orders.items():
                # The taker has to be on the other side of our order
                if not (order["side"] == self.tick_sheet["taker_side"][self.i]):
                    # Iff we have a order with worse price than the tick, our order gets executed
                    if (order["side"] == "buy" and self.tick_sheet["price"][self.i] < order["price"]) or (order["side"] == "sell" and self.tick_sheet["price"][self.i] > order["price"]):
                        fill_size = max(order["size"], self.tick_sheet["size"][self.i])
                        print("fill size {}".format(fill_size))
                        # self.tick_sheet["size"] = self.tick_sheet["size"][self.i] - fill_size
                        self.calculate_fill(side=order["side"], size=fill_size, price=order["price"], product_id=order["product_id"])

                        # Reduce size of order by fill size
                        self.open_orders[order_id]["size"] -= fill_size

                        # Transmit fill to agents (function call should go into the sim event loop tasks list, with a small delay)
                        fill_msg = {}
                        fill_msg["size"] = fill_size
                        fill_msg["price"] = order["price"]
                        fill_msg["side"] = order["side"]
                        fill_msg["maker_fee_rate"] = self.maker_fee_rate
                        agents_for_this_product = [ a for a in self.agents if a.product_id == order["product_id"] ]
                        for agent in agents_for_this_product:
                            if (agent.is_buyer() and order["side"] == "buy") or (not agent.is_buyer() and order["side"] == "sell"):
                                self.sim_event_loop_tasks.append((self.t + delta_t, partial(agent.on_fill, fill_msg)))

            # Check to see if any of the open orders were fully filled
            new_oos = {}
            for k,v in self.open_orders.items():
                if v["size"] > 0 and abs(v["size"]) > 10**-8:
                    new_oos[k] = v
            self.open_orders = new_oos

            # Transmit tick to agents (function call should go into the sim event loop tasks list, with a small delay)
            tick_msg = {}
            tick_msg["price"] = self.tick_sheet["price"][self.i]
            tick_msg["taker_side"] = self.tick_sheet["taker_side"][self.i]
            tick_msg["size"] = self.tick_sheet["size"][self.i]
            tick_msg["best_bid"] = self.tick_sheet["bid"][self.i]
            tick_msg["best_ask"] = self.tick_sheet["ask"][self.i]

            # agents_for_this_product = [ a for a in self.agents if a.product_id == order["product_id"] ]
            for agent in self.agents:
                self.sim_event_loop_tasks.append((self.t + delta_t, partial(agent.on_tick, tick_msg, self.tick_sheet["avg_price"][self.i])))

            # Look at the next entry in the tick sheet
            self.i += 1

        # Increment time by delta_t
        self.t += delta_t

        # Print the current value of the portfolio
        print("usd bal {} btc bal {}".format(self.balance["USD"], self.balance["BTC"]))
        self.log_info("portfolio value : {}".format(self.balance["USD"]+self.balance["BTC"]*self.tick_sheet["avg_price"][self.i]))

    def simulate(self):
        k = 0
        while self.i < self.tick_sheet.shape[0] and k < 10000:
            self.do_time_step()
            k += 1        