import os
import os.path as pth
import sys
from datetime import datetime
import pickle as pkl
import subprocess as subp
import shutil
import copy
import hashlib
import asyncio

LOG_ERROR = 1
LOG_WARN  = 2
LOG_INFO  = 3
LOG_OFF   = 4

class Logger:
    def __init__(self):
        self.opened = False
        self.closed = False

        self.log_drive = self.get_system_variable("LOG_DRIVE")

        self.log_folder = pth.join(os.getcwd(), "logs_{}".format(datetime.now().strftime("%Y%m%d_%H%M%S")))
        self.info_path = pth.join(self.log_folder, "info.log")
        self.warn_path = pth.join(self.log_folder, "warn.log")
        self.error_path = pth.join(self.log_folder, "error.log")

        os.mkdir(self.log_folder)

        self.info_fp = open(self.info_path, "w")
        self.warn_fp = open(self.warn_path, "w")
        self.error_fp = open(self.error_path, "w")

    def get_system_variable(self, name):
        try:
            return os.environ[name]
        except KeyError:
            self.log_warn("Logger", '"{}" does not exist!'.format(name))
            val = input("{}:".format(name))
            return val

    # Delay loop based initialization until we are in asyncio context
    def open(self):
        if not self.opened:
            self.loop = asyncio.get_running_loop()
            self.loop.call_later(15 * 60, self.new_log_folder)

            self.opened = True

    # Safety net in case we forget to call close
    def __del__(self):
        self.close()

    # Tear down object
    def close(self):
        if not self.closed:
            self.info_fp.close()
            self.warn_fp.close()
            self.error_fp.close()

            self.closed = True

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

    def save_logs(self, log_folder_path):
        # Compress old log folder and delete logs
        old_log_compressed = "{}.tar.gz".format(log_folder_path)
        subp.run(["tar", "cvzf", old_log_compressed, log_folder_path])

        # Calculate checksum for archived logs
        with open(old_log_compressed, "rb") as f:
            cksum = hashlib.sha256(f.read()).hexdigest()
    
        # Backup logs to Storj and delete the log folder
        subp.run(["uplink", "cp", "--metadata", '{\"cksum\":\"'+cksum+'\"}', old_log_compressed, "sj://{}".format(self.log_drive)])
        shutil.rmtree(log_folder_path)

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
        self.save_logs(old_log_folder)

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

        # buyer = {}
        # buyer["alpha"] = self.buyer.alpha
        # buyer["last_alpha_update"] = self.buyer.last_alpha_update
        # try:
        #     buyer["last_trade_ms"] = self.buyer.last_trade_ms
        # except:
        #     pass
        # save_data["buyer"] = buyer

        # seller = {}
        # seller["alpha"] = self.seller.alpha
        # seller["last_alpha_update"] = self.seller.last_alpha_update
        # try:
        #     seller["last_trade_ms"] = self.seller.last_trade_ms
        # except:
        #     pass
        # save_data["seller"] = seller

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

        # buyer = save_data["buyer"]
        # self.buyer.alpha = buyer["alpha"]
        # self.buyer.last_alpha_update = buyer["last_alpha_update"]
        # try:
        #     self.buyer.last_trade_ms = buyer["last_trade_ms"]
        # except:
        #     pass

        # seller = save_data["seller"]
        # self.seller.alpha = seller["alpha"]
        # self.seller.last_alpha_update = seller["last_alpha_update"]
        # try:
        #     self.seller.last_trade_ms = seller["last_trade_ms"]
        # except:
        #     pass


    # If we get here, we have an unrecoverable exception
    # and the only solution is to exit and restart
    def exception_handler(self, loop, context):
        # Try to close references to objects as nicely as possible
        self.close()
        self.exchange.close()

        # Upload last log folder we were just working on
        self.save_logs(self.log_folder)
        
        # Print exception information
        self.log_error("Main", "Exception handler called in asyncio")
        self.log_error("Main", context["message"])
        self.log_error("Main", context["exception"])

        # Restart process
        sys.exit(1)
