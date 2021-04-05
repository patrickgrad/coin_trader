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

    print("DELAY : {}ms".format((t1 - t0)*(10**-6)))
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

# Test to see that acquire and release are working properly
def test_lb_acquire_and_release():
    lb = LeakyBucket(N=10, interval=1)
    time.sleep(0.25)
    lb.close() # close the lb at this point to stop accumulating tokens during the rest of the test
    assert lb.tokens == 1

    # test default acquire
    lb.acquire()
    assert lb.tokens == 0
    lb.release()
    assert lb.tokens == 0

    # test that we wait if there are no tokens available
    helper_thread = threading.Thread(target=wake_lb, args=(lb,))
    helper_thread.start()
    t0 = time.time_ns()
    lb.acquire() # this acquire is forced to wait ~0.50s
    t1 = time.time_ns()
    lb.release()
    helper_thread.join()
    print("DELAY : {}ms".format((t1 - t0)*(10**-6)))
    assert (t1 - t0)*(10**-6) > 0.50*1000

    lb = LeakyBucket(N=10, interval=0.25)
    time.sleep(0.50)
    lb.close()
    assert lb.tokens == 2 or lb.tokens == 3

    # test acquire using 2 tokens
    start_tokens = lb.tokens
    lb.acquire(2)
    assert lb.tokens == start_tokens - 2
    lb.release()
    assert lb.tokens == start_tokens - 2

# Helper to add a token to the lb after some delay then wake it up so it can continue
def wake_lb(lb):
    # artifically delay a bit so we know we had to wait
    time.sleep(0.50)
    
    # acquire the underlying lock, add a token, and notify the cv
    with lb.cv:
        lb.tokens = 1
        lb.cv.notify()