import time
import threading
from threading import Thread

class LeakyBucket:
    def __init__(self, N, interval):
        self.cv = threading.Condition()
        self.N = N
        self.interval = interval
        self.tokens = 0
        self.acquired = False

        self.closed = False

        self.thread = Thread(target=self.add_tokens)
        self.thread.name = "LeakyBucket_{}_{}".format(N, interval)
        self.thread.start()

    # Just in case we forget to close
    def __del__(self):
        self.close()

    # Thread function, adds a token every interval up to a max of N tokens
    def add_tokens(self):
        while not self.closed:
            with self.cv:
                self.tokens += 1

                if self.tokens > self.N:
                    self.tokens = self.N

                self.cv.notify()

            time.sleep(self.interval)

    # Methods for acquiring and releasing the leaky bucket
    def acquire(self, tokens_to_consume=1):
        self.cv.acquire()
        while self.tokens < tokens_to_consume:
            self.cv.wait() # releases lock, waits until notify is called, then re-acquires the lock before returning
        self.tokens -= tokens_to_consume
        self.acquired = True

    def release(self):
        if self.acquired:
            self.acquired = False
            self.cv.release()

    # Stop the thread from running 
    def close(self):
        self.closed = True
        self.thread.join(self.interval*3)
