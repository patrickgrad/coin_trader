import tarfile
import os
from pathlib import Path
import datetime as dt
import re
import pandas as pd
import sys

def parse_date(date):
    return int(dt.datetime.timestamp(dt.datetime.strptime(date, "%Y%m%d")))

def parse_datetime(datetime_s):
    return int(dt.datetime.timestamp(dt.datetime.strptime(datetime_s, "%Y%m%d_%H%M%S")))

def parse_datetime_folder(folder_name):
    time = "_".join(folder_name.split("_")[1:])
    return parse_datetime(time)

def sort_fn(x):
    return x[0]

def line2dict(datetime_s, payload):
    elems = payload.split(" ")[1:]

    d = {}
    d["time"] = parse_datetime(datetime_s)
    for e in elems:
        key = e.split("(")[0]
        value = e.split("(")[1][:-1]

        d[key] = value

    return d

if __name__ == "__main__":
    pathtologs = Path(sys.argv[1])
    pathtooutput = Path(sys.argv[2])

    if not pathtologs.exists():
        print("{} does not exist!", pathtologs)
        sys.exit(1)

    if not pathtooutput.exists():
        pathtooutput.mkdir()

    # Max lookback parameter specifices oldest date to look at
    if "-ml" in sys.argv:
        max_lookback = parse_date(sys.argv[sys.argv.index("-ml")+1])
    else:
        max_lookback = parse_date("20210101")

    # Extract all log files and move to logs folder
    print("Extracting logs ...")
    archives_all = pathtologs.rglob('*logs_*_*.tar.gz')
    logs = pathtooutput/"logs"

    # Find the logs we've already extracted
    if logs.exists():
        archives = []
        log_folders = logs.rglob('*logs_*_*')
        for fldr in log_folders:
            found = False
            for i,arch in enumerate(archives_all):
                if fldr.name in str(arch):
                    found = True
                    break
            if not found:
                archives.append(fldr)
    else:
        archives = archives_all
        logs.mkdir()

    # Extract logs we don't have in out/logs already
    for arch in archives:
        if max_lookback <= parse_datetime_folder(arch.name.split(".")[0]):
            f = str(arch)
            try:        
                with tarfile.open(f, "r:gz") as logfile:
                    logfile.extractall(path=str(pathtologs))
                
                print("Extracting {}".format(f))
            
            except:
                print("{} is corrupted, deleting".format(f))
                os.remove(f)

    # Copy all log folders to logs directory
    temp_folders = pathtologs.rglob('*logs_*_*')
    for tmp in temp_folders:
        if tmp.is_dir():
            print("Moving {} to {}".format(str(tmp), str(logs/tmp.name)))
            tmp.rename(logs/tmp.name)

    # Recursively search out folder for our log folders
    log_folders = [path for path in pathtooutput.rglob('*logs_*_*') if path.is_dir()]

    # Parse date and time, convert to absolute integer time, and sort chronologically 
    log_folders = sorted([ [parse_datetime_folder(path.name), path] for path in log_folders], key=sort_fn)

    # Create mega logs for info, warn, and error
    print("Creating mega logs ...")
    for ll in ["info", "warn", "error"]:
        if not (pathtooutput/"{}.log".format(ll)).exists():
            info_log_arr = []
            print("Writing {}.log ...".format(ll))
            for _,path in log_folders:
                with open(path/"{}.log".format(ll)) as f:
                    info_log_arr.append(f.read())
            with open(pathtooutput/"{}.log".format(ll), "w") as f:
                f.write("".join(info_log_arr))


    # Create mega csv of all measurements with timestamps
    print("Creating mega CSVs ...")
    with open(pathtooutput/"info.log") as f:
        info_buf = f.read().split("\n")

    tick_sheet = []
    buyer_sheet = []
    seller_sheet = []

    log_regex = re.compile("\[([a-zA-Z]*)\]\[([a-zA-Z0-9]*),([0-9_]*)\]:(.*)")
    for i,line in enumerate(info_buf):
        res = log_regex.match(line)
        try:
            log_level, source, datetime_s, payload = res.groups()

            if log_level == "INFO":
                if "Exchange" in source:
                    if "tick" in payload:
                        tick_sheet.append(line2dict(datetime_s, payload))

                elif source == "Buyer":
                    if "noop" in payload or "new" in payload or "replace" in payload:
                        buyer_sheet.append(line2dict(datetime_s, payload))

                elif source == "Seller":
                    if "noop" in payload or "new" in payload or "replace" in payload:
                        seller_sheet.append(line2dict(datetime_s, payload))

        except AttributeError:
            print("Error on line {}".format(i))

    tick_sheet = pd.DataFrame(tick_sheet)
    buyer_sheet = pd.DataFrame(buyer_sheet)
    seller_sheet = pd.DataFrame(seller_sheet)

    tick_sheet.to_csv(pathtooutput/"tick.csv", index=False)
    buyer_sheet.to_csv(pathtooutput/"buyer.csv", index=False)
    seller_sheet.to_csv(pathtooutput/"seller.csv", index=False)
    