from pathlib import Path
import numpy as np
import sys
import pickle as pkl
import pandas as pd
import matplotlib.pyplot as plt

def load_ticks(tick_csv):
    all_ticks = []
    train_ticks = []
    validation_ticks = []

    tick_sheet = pd.read_csv(tick_csv, low_memory=False)
    N_train = int(tick_sheet.shape[0] * 0.80)
    for idx,row in tick_sheet.iterrows():
        if idx == 0:
            t0 = row["time"]
            t = 0
        else:
            t = row["time"] - t0

        tick_price = row["price"]
        size = row["size"]

        all_ticks.append([t, tick_price])

        if idx < N_train:
            train_ticks.append(all_ticks[-1])
        else:
            validation_ticks.append(all_ticks[-1])
            
    a_t, all_ticks = zip(*all_ticks)
    t_t, train_ticks = zip(*train_ticks)
    v_t, validation_ticks = zip(*validation_ticks)
                
    return np.array(all_ticks), np.array(a_t), np.array(train_ticks), np.array(t_t), np.array(validation_ticks), np.array(v_t)

def calculate_ticks_pct_chng(arr):
    return np.diff(arr) / arr[:-1]

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

        print("Loading data ...")
        all_ticks, a_t, train_ticks, t_t, validation_ticks, v_t = load_ticks(pathtologs/"tick.csv")
        train_ticks_pct_chng = calculate_ticks_pct_chng(train_ticks)

        print("Saving back as pkls ...")
        with open(pathtooutput/"all_ticks.pkl", "wb") as f:
            pkl.dump(all_ticks, f)
        with open(pathtooutput/"a_t.pkl", "wb") as f:
            pkl.dump(a_t, f)
        with open(pathtooutput/"train_ticks.pkl", "wb") as f:
            pkl.dump(train_ticks, f)
        with open(pathtooutput/"t_t.pkl", "wb") as f:
            pkl.dump(t_t, f)
        with open(pathtooutput/"validation_ticks.pkl", "wb") as f:
            pkl.dump(validation_ticks, f)
        with open(pathtooutput/"v_t.pkl", "wb") as f:
            pkl.dump(v_t, f)

        print("Making plots ...")
        fig, ax = plt.subplots()
        ax.scatter(t_t, train_ticks, s=2)

        ax.set(xlabel='time (s)', ylabel='tick price ($)', title='Tick Prices')
        plt.savefig(pathtooutput/"ticks.png")
        # plt.show()
            
        fig, ax = plt.subplots()
        ax.scatter(t_t[1:], train_ticks_pct_chng, s=2)

        ax.set(xlabel='time (s)', ylabel='change in tick price', title='Tick Prices Change Timeseries')
        plt.savefig(pathtooutput/"ticks_chng_timeseries.png")
        # plt.show()

        # Tick prices change histogram
        fig, ax = plt.subplots()
        ax.hist(train_ticks_pct_chng, bins=100, density=True)
        ax.set(xlabel='% Change From Last Tick', ylabel='Frequency', title='Tick Prices Change PDF')
        plt.savefig(pathtooutput/"ticks_chng_histogram1.png")
        # plt.show()
        print("Mean:{} Std:{}".format(np.mean(train_ticks_pct_chng), np.std(train_ticks_pct_chng)))

        fig, ax = plt.subplots()
        tick_pct_chng_clip = np.clip(train_ticks_pct_chng, -0.005, 0.005)
        ax.hist(tick_pct_chng_clip, bins=100, density=True)
        ax.set(xlabel='% Change From Last Tick', ylabel='Frequency', title='Tick Prices Change PDF')
        plt.savefig(pathtooutput/"ticks_chng_histogram2.png")
        # plt.show()
        print("Mean:{} Std:{}".format(np.mean(tick_pct_chng_clip), np.std(tick_pct_chng_clip)))

        sys.exit(0)