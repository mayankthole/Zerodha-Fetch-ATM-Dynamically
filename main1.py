import logging
from kiteconnect import KiteConnect
import pandas as pd
import os
import datetime
import numpy as np

logging.basicConfig(level=logging.INFO)

api_key = "dkae5abnsn99r5qm"
api_secret = "xc271bh072g9q2v4e03onkjvbhjbbyta"
access_token_file = "access_token.txt"

kite = KiteConnect(api_key=api_key)

def set_access_token_from_file():
    if os.path.exists(access_token_file):
        with open(access_token_file, "r") as f:
            token = f.read().strip()
            if token:
                try:
                    kite.set_access_token(token)
                    kite.profile()
                    logging.info("Using saved access token.")
                    return True
                except Exception:
                    pass
    return False

if not set_access_token_from_file():
    print("Login URL:", kite.login_url())
    request_token = input("Enter the request_token from the URL: ")
    data = kite.generate_session(request_token, api_secret=api_secret)
    access_token = data["access_token"]
    kite.set_access_token(access_token)
    with open(access_token_file, "w") as f:
        f.write(access_token)
    logging.info("Access token saved to access_token.txt")

# Load instruments once
instruments = pd.read_csv("instruments.csv")

# Get BANKNIFTY index LTP
idx_row = instruments[(instruments['segment'] == 'INDICES') & (instruments['name'] == 'NIFTY BANK')]
ltp_key = f"{idx_row['exchange'].iloc[0]}:{idx_row['tradingsymbol'].iloc[0]}"
ltp = kite.ltp(ltp_key)[ltp_key]['last_price']
strike = int(round(ltp / 100.0) * 100)
logging.info(f"BANKNIFTY LTP: {ltp}, Rounded Strike: {strike}")

# Find nearest expiry for BANKNIFTY options
bn_opts = instruments[
    (instruments["name"] == "BANKNIFTY") &
    (instruments["segment"] == "NFO-OPT") &
    (instruments["instrument_type"].isin(["CE", "PE"]))
]
today = datetime.date.today()
expiries = sorted(bn_opts["expiry"].unique())
nearest_expiry = next(
    (e for e in expiries if datetime.datetime.strptime(str(e), "%Y-%m-%d").date() >= today), None
)
if not nearest_expiry:
    logging.error("No valid future expiry found for BANKNIFTY options.")
    exit(1)
logging.info(f"Nearest expiry: {nearest_expiry}")

# Construct option symbol
expiry_dt = datetime.datetime.strptime(nearest_expiry, "%Y-%m-%d")
# Place orders for both CE and PE
for option_type in ["CE", "PE"]:
    bn_symbol = f"BANKNIFTY{expiry_dt.strftime('%y%b').upper()}{int(strike)}{option_type}"
    contract = bn_opts[
        (bn_opts['tradingsymbol'] == bn_symbol) &
        (bn_opts['expiry'] == nearest_expiry) &
        (bn_opts['strike'] == strike) &
        (bn_opts['instrument_type'] == option_type)
    ]
    if not contract.empty:
        lot_size = int(contract['lot_size'].iloc[0])
        logging.info(f"Lot size for {bn_symbol}: {lot_size}")
    else:
        logging.error(f"Could not find lot size for {bn_symbol}.")
        continue  # Skip to next option_type

    # Place order
    try:
        order_id = kite.place_order(
            tradingsymbol=bn_symbol,
            exchange=kite.EXCHANGE_NFO,
            transaction_type=kite.TRANSACTION_TYPE_BUY,
            quantity=lot_size,
            variety=kite.VARIETY_REGULAR,
            order_type=kite.ORDER_TYPE_MARKET,
            product=kite.PRODUCT_MIS,
            validity=kite.VALIDITY_DAY
        )
        logging.info(f"Order placed for {bn_symbol}. ID is: {order_id}")
    except Exception as e:
        logging.info(f"Order placement failed for {bn_symbol}: {str(e)}")