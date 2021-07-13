import pandas as pd
import matplotlib
import matplotlib.pyplot as plt
from pathlib import Path

FEE_RATE = 0.001
usd_balance = 1000
btc_balance = 0

out = Path("out")
if not out.exists():
    print("out folder does not exist")
    exit()

buy_ticks = []
sell_ticks = []
all_ticks = []
tick_pct_chng = []

tick_sheet = pd.read_csv(out/"tick.csv")
for idx,row in tick_sheet.iterrows():
    if idx == 0:
        t0 = row["time"]
        t = 0
    else:
        t = row["time"] - t0

    tick_price = row["price"]
    size = row["size"]
    taker_side = row["taker_side"]

    # this is an uptick
    if taker_side == "buy":
        maker_side = "sell"
        sell_ticks.append([t, tick_price])
    # this is a downtick
    elif taker_side == "sell":
        maker_side = "buy"
        buy_ticks.append([t, tick_price])

    if idx > 0:
        tick_pct_chng.append((all_ticks[-1][1]-tick_price)/all_ticks[-1][1])

    all_ticks.append([t, tick_price])

    if idx == 199999:
        break

b_t, buy_prices = zip(*buy_ticks)
s_t, sell_prices = zip(*sell_ticks)
a_t, all_ticks = zip(*all_ticks)

fig, ax = plt.subplots()
ax.scatter(b_t, buy_prices, s=2)
ax.scatter(s_t, sell_prices, s=2)

ax.set(xlabel='time (s)', ylabel='tick price ($)', title='Tick Prices')

plt.show()
    
fig, ax = plt.subplots()
ax.scatter(a_t[1:], tick_pct_chng, s=2)

ax.set(xlabel='time (s)', ylabel='pct change in tick price (%$)', title='Tick Prices Percent Change')

plt.show()
    
