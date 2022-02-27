import time
import threading
import logging

from flask import *

from app_settings import AppSettings
from app_instance import AppInstance

from util import *
from rvn_rpc import *

from swap_transaction import SwapTransaction

app = Flask(__name__)
jobs = []

BASE_FEE = 0.1
PERCENT_FEE = 0.01 

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
          bal = do_rpc('getaddressbalance', addresses=job['recv_addr'])['balance']

          if bal >= job['total'] - 0.001:
            logging.info(str(job['total']) + f' RVN received! Sending output to {customer_addr}')

            st = SwapTransaction.decode_swap(job['sp'])[1] # have to re create to prevent txn-mempool-conflict
            try:
              do_rpc('sendrawtransaction', hexstring=st.complete_order(customer_addr))
              logging.info('Completed order ' + job['sp'] + ' -> ' + customer_addr)
            except Exception as e:
              logging.error(e)
              logging.info(do_rpc('sendtoaddress', customer_addr, bal - 0.1))

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
            try:
              do_rpc('sendrawtransaction', hexstring=st.complete_order(customer_addr))
              logging.info('Completed order ' + job['sp'] + ' -> ' + customer_addr)
            except Exception as e:
              logging.error(e)
              logging.info(do_rpc('sendtoaddress', customer_addr, fee - 0.1))
              logging.info(do_rpc('transfer', st.asset(), amount, customer_addr))

            time.sleep(5) # give time to broadcast txn!
            rm.append(i)
    
    for i in rm[::-1]:
      print(f'Removing job #{i}')
      jobs.pop(i)
      rm.pop(-1)
    
    time.sleep(20)

@app.route('/')
def index():
  msg = request.args.get('msg', '')
  sp = request.args.get('sp', '')
  return render_template('index.html', msg=msg, sp=sp)

@app.route('/order')
def order():
  if request.args.get('addr') == None or request.args.get('sp') == None:
    return redirect('/')
  else:
    customer_addr = request.args.get('addr', '')
    sp = request.args.get('sp', '')
    valid, st = SwapTransaction.decode_swap(sp)

    if not valid:
      return redirect('/?msg=Invalid+Signed+Partial')
    elif not do_rpc('validateaddress', address=customer_addr)['isvalid']:
      return redirect('/?msg=Invalid+Ravencoin+Address')
    
    recv_addr = do_rpc('getnewaddress')
    if st.type == 'buy':
      fee = round(st.total_price() * (PERCENT_FEE) + BASE_FEE, 4)
      jobs.append({
        'recv_addr': recv_addr,
        'customer_addr': customer_addr,
        'timestamp': time.time(),
        'type': st.type,
        'sp': sp
      })
      logging.info(f'Created Order: recv_addr = {recv_addr}, customer_addr = {customer_addr}, sp = {sp}')
      return render_template('order.html', inpt=f'{st.quantity()} {st.asset()} + {fee} RVN', output=f'{st.total_price()} RVN', addr=recv_addr, c_addr=customer_addr)
    elif st.type == 'sell':
      total = round(st.total_price() * (PERCENT_FEE + 1) + BASE_FEE, 4)
      jobs.append({
        'total': total,
        'recv_addr': recv_addr,
        'customer_addr': customer_addr,
        'timestamp': time.time(),
        'type': st.type,
        'sp': sp
      })
      logging.info(f'Created Order: recv_addr = {recv_addr}, customer_addr = {customer_addr}, sp = {sp}')
      return render_template('order.html', inpt=f'{total} RVN', output=f'{st.quantity()} {st.asset()}', addr=recv_addr, c_addr=customer_addr)
    else:
      return redirect('/?msg=Unsupported+Swap+Type.+Supported+Types:+Buy,+Sell')

def main():
  logging.basicConfig(filename='ravenswap.log', level=logging.DEBUG)

  AppInstance.settings = AppSettings()
  AppInstance.settings.on_load()

  AppInstance.on_init()

  t = threading.Thread(target=work)
  t.start()

  app.run(port=6889, debug=False)

if __name__ == "__main__":
  main()
