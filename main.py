import time
import threading

from app_settings import AppSettings
from app_instance import AppInstance

from util import *
from rvn_rpc import *

from swap_transaction import SwapTransaction
from app_storage import AppStorage
from wallet_manager import WalletManager

jobs = []

def work():
  global jobs 
  while True:
    rm = []
    timestamp = time.time()
    for i, job in enumerate(jobs):
      if job['timestamp'] > timestamp + 1200:
        rm.append(i)
      else:
        AppInstance.wallet.update_wallet()

        if job['type'] == 'sell':
          customer_addr = job['customer_addr']
          
          if do_rpc('getaddressbalance', addresses=job['recv_addr'])['balance'] >= job['total'] - 0.001:
            print(f'Payment received! Sending output to {customer_addr}')

            st = SwapTransaction.decode_swap(job['sp'])[1] # have to re create to prevent txn-mempool-conflict
            do_rpc('sendrawtransaction', hexstring=st.complete_order(customer_addr))

            time.sleep(5) # give time to broadcast txn!
            rm.append(i)

        elif job['type'] == 'buy':
          st = SwapTransaction.decode_swap(job['sp'])[1]
          assets = do_rpc('getaddressbalance', addresses=job['recv_addr'], includeAssets=True)
          amount = 0
          for a in assets:
            if a['assetName'] == st.asset():
              amount = float(a['balance'])

          fee = st.total_price() * 0.01 + 0.1

          if amount >= st.quantity() and fee - 0.001 <= do_rpc('getaddressbalance', addresses=job['recv_addr'])['balance']:
            do_rpc('sendrawtransaction', hexstring=st.complete_order(job['customer_addr']))

            time.sleep(5) # give time to broadcast txn!
            rm.append(i)
    
    for i in rm[::-1]:
      print(f'Removing job #{i}')
      jobs.pop(i)
      rm.pop(-1)
    
    time.sleep(20)

def do_swaps():
  global jobs
  while True:
    sp = input('Signed Partial > ')
    st = SwapTransaction.decode_swap(sp)[1]

    recv_addr = do_rpc('getnewaddress')
    customer_addr = do_rpc('getnewaddress')

    if st.type == 'sell':
      total = round(st.total_price() * 1.01 + 0.1, 4)
      print(f'Please send {total} RVN to {recv_addr}')

      jobs.append({
        'total': total,
        'recv_addr': recv_addr,
        'customer_addr': customer_addr,
        'timestamp': time.time(),
        'type': st.type,
        'sp': sp
      })

    elif st.type == 'buy':
      print(f'Please send {st.quantity()} {st.asset()} + {round(st.total_price() * 0.01 + 0.1, 4)} RVN to {recv_addr}')

      jobs.append({
        'recv_addr': recv_addr,
        'customer_addr': customer_addr,
        'timestamp': time.time(),
        'type': st.type,
        'sp': sp
      })

def main():
  AppInstance.settings = AppSettings()
  AppInstance.settings.on_load()

  AppInstance.on_init()

  t1 = threading.Thread(target=do_swaps, daemon=True)
  t2 = threading.Thread(target=work)

  t1.start()
  t2.start()

if __name__ == "__main__":
  main()