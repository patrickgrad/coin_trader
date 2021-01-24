import os
import os.path as pth
import sys
from datetime import datetime
import pickle as pkl
import subprocess as subp
import shutil
import copy
import hashlib

LOG_ERROR = 1
LOG_WARN  = 2
LOG_INFO  = 3
LOG_OFF   = 4

class Logger:
    def __init__(self, loop):
        self.log_folder = pth.join(os.getcwd(), "logs_{}".format(datetime.now().strftime("%Y%m%d_%H%M%S")))
        self.info_path = pth.join(self.log_folder, "info.log")
        self.warn_path = pth.join(self.log_folder, "warn.log")
        self.error_path = pth.join(self.log_folder, "error.log")

        os.mkdir(self.log_folder)

        self.info_fp = open(self.info_path, "w")
        self.warn_fp = open(self.warn_path, "w")
        self.error_fp = open(self.error_path, "w")

        self.loop = loop
        self.loop.call_later(15 * 60, self.new_log_folder)

    def __del__(self):
        self.close()

    def close(self):
        self.info_fp.close()
        self.warn_fp.close()
        self.error_fp.close()

    def log_error(self, prefix, msg):
        time = datetime.now().strftime("%Y%m%d_%H%M%S")
        line = "[ERR][{},{}]:{}\n".format(prefix, time, msg)

        print(line[:-1])
        self.error_fp.write(line)
        self.warn_fp.write(line)
        self.info_fp.write(line)

    def log_warn(self, prefix, msg):
        time = datetime.now().strftime("%Y%m%d_%H%M%S")
        line = "[WARN][{},{}]:{}\n".format(prefix, time, msg)

        print(line[:-1])
        self.warn_fp.write(line)
        self.info_fp.write(line)

    def log_info(self, prefix, msg):
        time = datetime.now().strftime("%Y%m%d_%H%M%S")
        line = "[INFO][{},{}]:{}\n".format(prefix, time, msg)

        print(line[:-1])
        self.info_fp.write(line)


    def new_log_folder(self):
        # Make data structure checkpoint before switching log folder
        self.make_checkpoint("end_chk.pkl")

        old_log_folder = copy.copy(self.log_folder)
        self.log_folder = pth.join(os.getcwd(), "logs_{}".format(datetime.now().strftime("%Y%m%d_%H%M%S")))
        self.info_path = pth.join(self.log_folder, "info.log")
        self.warn_path = pth.join(self.log_folder, "warn.log")
        self.error_path = pth.join(self.log_folder, "error.log")

        os.mkdir(self.log_folder)

        self.close()

        self.info_fp = open(self.info_path, "w")
        self.warn_fp = open(self.warn_path, "w")
        self.error_fp = open(self.error_path, "w")

        # Make a checkpoint when we start the new log folder
        self.make_checkpoint("start_chk.pkl")

        # Compress old log folder and delete logs
        old_log_compressed = "{}.tar.gz".format(old_log_folder)
        subp.run(["tar", "cvzf", old_log_compressed, old_log_folder])

        with open(old_log_compressed, "rb") as f:
            cksum = hashlib.sha256(f.read()).hexdigest()
        
        subp.run(["uplink", "cp", "--metadata", '{"cksum":"{}"}'.format(cksum), old_log_compressed, "sj://logs"])
        os.remove(old_log_compressed)
        shutil.rmtree(old_log_folder)

        self.loop.call_later(15 * 60, self.new_log_folder)

    def make_checkpoint(self, fn):
        save_data = {}

        try:
            save_data["available_usd"] = self.exchange.available_usd
            save_data["hold_usd"] = self.exchange.hold_usd
            save_data["balance_usd"] = self.exchange.balance_usd
            save_data["available_btc"] = self.exchange.available_btc
            save_data["hold_btc"] = self.exchange.hold_btc
            save_data["balance_btc"] = self.exchange.balance_btc
        except AttributeError:
            self.log_info("Logger", "Save, no wallet data")

        buyer = {}
        buyer["alpha"] = self.buyer.alpha
        buyer["last_alpha_update"] = self.buyer.last_alpha_update
        try:
            buyer["last_trade_ms"] = self.buyer.last_trade_ms
        except:
            pass
        save_data["buyer"] = buyer

        seller = {}
        seller["alpha"] = self.seller.alpha
        seller["last_alpha_update"] = self.seller.last_alpha_update
        try:
            seller["last_trade_ms"] = self.seller.last_trade_ms
        except:
            pass
        save_data["seller"] = seller

        with open(pth.join(self.log_folder, fn), 'wb') as cfg:
            pkl.dump(save_data, cfg)

    def restore_checkpoint(self, path):
        with open(path, 'rb') as cfg:
            save_data = pkl.loads(cfg.read())

        try:
            self.exchange.available_usd = save_data["available_usd"]
            self.exchange.hold_usd = save_data["hold_usd"]
            self.exchange.balance_usd = save_data["balance_usd"]
            self.exchange.available_btc = save_data["available_btc"]
            self.exchange.hold_btc = save_data["hold_btc"]
            self.exchange.balance_btc = save_data["balance_btc"]
        except AttributeError:
            self.log_info("Logger", "Restore, no wallet data")

        buyer = save_data["buyer"]
        self.buyer.alpha = buyer["alpha"]
        self.buyer.last_alpha_update = buyer["last_alpha_update"]
        try:
            self.buyer.last_trade_ms = buyer["last_trade_ms"]
        except:
            pass

        seller = save_data["seller"]
        self.seller.alpha = seller["alpha"]
        self.seller.last_alpha_update = seller["last_alpha_update"]
        try:
            self.seller.last_trade_ms = seller["last_trade_ms"]
        except:
            pass

    def exception_handler(self, loop, context):
        self.exchange.close()
        self.loop.stop()
        
        self.log_error("Main", "Exception handler called in asyncio")
        self.log_error("Main", context["message"])
        self.log_error("Main", context["exception"])




# 
# subp.call(["tar", "xzcf"], shell=True)



        