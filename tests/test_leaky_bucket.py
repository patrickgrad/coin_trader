from src.exchange.leaky_bucket import LeakyBucket
import threading
import time

# Test that thread can be started and ended properly
def test_lb_lifecycle():
    threads_before = len(threading.enumerate())
    lb = LeakyBucket(N=10, interval=0.25)
    threads_after = len(threading.enumerate())
    lb.close()
    threads_end = len(threading.enumerate())

    assert threads_before + 1 == threads_after
    assert threads_before == threads_end

# Test that the thread is closed relatively quickly
def test_lb_close_quick():
    lb = LeakyBucket(N=10, interval=0.25)
    t0 = time.time_ns()
    lb.close()
    t1 = time.time_ns()

    assert (t1 - t0)*(10**-6) < 3*0.25*1000

# Test to see if tokens are accumulating properly
def test_lb_token_accumulate():
    lb = LeakyBucket(N=10, interval=1)
    time.sleep(0.25)
    lb.close()
    assert lb.tokens == 1

    lb = LeakyBucket(N=10, interval=0.01)
    time.sleep(0.25)
    lb.close()
    assert lb.tokens == 10

    lb = LeakyBucket(N=10, interval=0.25)
    time.sleep(0.50)
    lb.close()
    assert lb.tokens == 2 or lb.tokens == 3
