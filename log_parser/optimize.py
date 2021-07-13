from pathlib import Path
import numpy as np
import sys
import pickle as pkl
import pandas as pd
import matplotlib.pyplot as plt
from scipy import stats
from process_csvs import calculate_ticks_pct_chng

def pct_chng(o, n):
    return (n-o)/o

def simulation(ticks, ticks_pct_chng, base_thresh_multiplier, dynamic_thresh_multiplier, portfolio_ratio):
    usd_balance = 5000
    btc_balance = 0.05
    wallet_value = [usd_balance + btc_balance*ticks[0]]
#    fee_rate = 0.001 # 0.1% maker fee rate (100k - 1M in monthly volume)
    # fee_rate = 0.0008 # 0.08% maker fee rate (1M - 10M in monthly volume)
    fee_rate = 0.0005 # 0.05% maker fee rate (10M - 50M in monthly volume)
    # fee_rate = 0 # 0.0% maker fee rate (50M+ in monthly volume)

    base_pct_chng = fee_rate
    threshold = base_pct_chng*base_thresh_multiplier

    transactions = 0
    cant_sell = 0
    cant_buy = 0
    for i,tick_cng in enumerate(ticks_pct_chng):
        prev_price = ticks[i]
        curr_price = ticks[i+1]
        
        # sell if tick change blows over sell order threshold
        if tick_cng > 0 and tick_cng > threshold:
            sell_size = max(portfolio_ratio*btc_balance, 0.001)
            buy_size = max(portfolio_ratio*usd_balance/(prev_price*(1-threshold)), 0.001)

            if i > 5:
                threshold = max(np.mean(abs(ticks_pct_chng[i-5:i]))*dynamic_thresh_multiplier, base_pct_chng*base_thresh_multiplier)

            # can only sell if we have enough bitcoin
            if btc_balance > 0.001:
                # make sure sell size is <= balance
                sell_size = min(sell_size, btc_balance)
                
                btc_balance -= sell_size
                usd_balance += sell_size*prev_price*(1+threshold)
                usd_balance -= sell_size*prev_price*(1+threshold)*fee_rate
                transactions += 1
            else:
                cant_sell += 1
        # buy if tick change blows under buy order threshold
        elif tick_cng < 0 and tick_cng < -threshold:
            sell_size = max(portfolio_ratio*btc_balance, 0.001)
            buy_size = max(portfolio_ratio*usd_balance/(prev_price*(1-threshold)), 0.001)

            if i > 5:
                threshold = max(np.mean(abs(ticks_pct_chng[i-5:i]))*dynamic_thresh_multiplier, base_pct_chng*base_thresh_multiplier)

            # can only buy if we have enough usd
            if usd_balance >= buy_size*prev_price*(1-threshold):
                # make sure buy size is <= usd balance / price
                buy_size = min(buy_size, usd_balance/(prev_price*(1-threshold)))
                
                btc_balance += buy_size
                usd_balance -= buy_size*prev_price*(1-threshold)
                usd_balance -= buy_size*prev_price*(1-threshold)*fee_rate
                transactions += 1
            else:
                cant_buy += 1

        wallet_value.append(usd_balance + btc_balance*curr_price)

    return wallet_value

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("USAGE : python process_csvs.py PATH2INPUT PATH2OUTPUT")
        sys.exit(1)
    else:
        pathtologs = Path(sys.argv[1])
        pathtooutput = Path(sys.argv[2])

        if not pathtologs.exists():
            print("{} does not exist!", pathtologs)
            sys.exit(1)

        if not pathtooutput.exists():
            pathtooutput.mkdir()

        # Load a bunch of data up
        with open(pathtologs/"train_ticks.pkl", "rb") as f:
            train_ticks = pkl.load(f)
        with open(pathtologs/"t_t.pkl", "rb") as f:
            t_t = pkl.load(f)
        with open(pathtologs/"validation_ticks.pkl", "rb") as f:
            validation_ticks = pkl.load(f)
        with open(pathtologs/"v_t.pkl", "rb") as f:
            v_t = pkl.load(f)

        # Mirror our 2 data sets 
        train_ticks = np.append(train_ticks, np.flip(train_ticks))
        validation_ticks = np.append(validation_ticks, np.flip(validation_ticks))

        ticks_pct_chng_train = calculate_ticks_pct_chng(train_ticks)
        ticks_pct_chng_val = calculate_ticks_pct_chng(validation_ticks)

        # Training, grid search over parameters
        results = []
        for btm in np.arange(0, 3, 0.25):
            for dtm in np.arange(0, 12, 0.5):
                for pr in np.arange(0.01, 0.51, 0.01):
                    wallet_value = simulation(train_ticks, ticks_pct_chng_train, btm, dtm, pr)
                    returns = pct_chng(wallet_value[0], wallet_value[-1])
                    results.append((returns, btm, dtm, pr))

                    print("[Training] Done btm={} dtm={} pr={} returns={}".format(btm,dtm,pr,returns))
                
        results.sort(key=lambda x : x[0], reverse=True)
        
        # Print best and worst result
        print(results[0])
        print(results[-1])

        # Dump our results from training phase
        with open(pathtooutput/"training_results.pkl", "wb") as f:
            pkl.dump(results, f)

        # Calculate the final parameters
        results_numpy = np.array(results[:10])
        avg_returns = np.mean(results_numpy[:,0])
        avg_btm = stats.mode(results_numpy[:,1])[0][0]
        avg_dtm = stats.mode(results_numpy[:,2])[0][0]
        avg_pr = stats.mode(results_numpy[:,3])[0][0]

        final_params = {}
        final_params["btm"] = avg_btm
        final_params["dtm"] = avg_dtm
        final_params["pr"] = avg_pr

        with open(pathtooutput/"final_params.pkl", "wb") as f:
            pkl.dump(final_params, f)

        print(avg_returns, avg_btm, avg_dtm, avg_pr)
    

        # Run final params on training set
        wallet_value = simulation(train_ticks, ticks_pct_chng_train, avg_btm, avg_dtm, avg_pr)
        returns = pct_chng(wallet_value[0], wallet_value[-1])
        print("[Train Final] Done btm={} dtm={} pr={} returns={}".format(avg_btm, avg_dtm, avg_pr, returns))

        fig, ax = plt.subplots()
        t_t_mirrored = np.append(t_t, t_t[-1] + t_t)
        ax.scatter(t_t_mirrored, wallet_value, s=2)

        ax.set(xlabel="Time", ylabel="Wallet Value", title="Wallet Value vs Time")
        plt.savefig(pathtooutput/"train_final_params.png")
        # plt.show()

        # Run final params on validation set
        wallet_value = simulation(validation_ticks, ticks_pct_chng_val, avg_btm, avg_dtm, avg_pr)
        returns = pct_chng(wallet_value[0], wallet_value[-1])
        print("[Validation] Done btm={} dtm={} pr={} returns={}".format(avg_btm, avg_dtm, avg_pr, returns))

        fig, ax = plt.subplots()
        v_t_mirrored = np.append(v_t, v_t[-1] + v_t)
        ax.scatter(v_t_mirrored, wallet_value, s=2)

        ax.set(xlabel="Time", ylabel="Wallet Value", title="Wallet Value vs Time")
        plt.savefig(pathtooutput/"validation.png")
        # plt.show()