import pprint
import time
from binance.client import Client
import matplotlib.pyplot as plt
from copy import copy
import pandas as pd
import numpy as np
import Helper
from Bot_Class import Bot
from Config_File import API_KEY, API_SECRET
from Helper import Trade

####################### Settings #####################################
account_balance = 1000  ##Starting Account Balance
leverage = 10  ##leverage we want to use on the account, *Check valid leverages for coins*
order_Size = .1  ##percent of Effective account to risk ie. (leverage X Account Balance) X order_size
fee = .00036  ##binance fees for backtesting

## WHEN PICKING START AND END ENSURE YOU HAVE AT LEAST 300 CANDLES OR ELSE YOU WILL GET AN ERROR
start = '02-04-22'  ##start of backtest dd/mm/yy
end = '09-04-22'  ##end of backtest   dd/mm/yy

TIME_INTERVAL = '1m'  ##Candlestick interval in minutes, valid options: 1m,3m,5m,15m,30m,1hr,2hr,4ht,6hr,8hr,12hr,1d,3d,1w,1M I think...
Number_Of_Trades = 1  ## allowed to open 5 positions at a time
generate_heikin_ashi = False  ## generate Heikin ashi candles that can be consumed by your strategy in Bot Class
printing_on = True
add_delay = False  ## If true when printing we will sleep for 1 second to see the output clearer
Trade_All_Symbols = False
symbol = ['BTCUSDT', 'ETHUSDT']  ## If Above is false strategy will only trade the list of coins specified here
use_trailing_stop = 0 ##(NOT IN USE Causing rounding error I think)  flag to use trailing stop, If on when the takeprofitval margin is reached a trailing stop will be set with the below percentage distance
trailing_stop_distance = .01 ## 1% trailing stop activated by hitting the takeprofitval for a coin
####################################################################################################

client = Client(api_key=API_KEY, api_secret=API_SECRET)
if Trade_All_Symbols:
    symbol = []  ## reset symbol before we fill with all symbols below
    x = client.futures_ticker()  # [0]
    for y in x:
        symbol.append(y['symbol'])
    symbol = [x for x in symbol if 'USDT' in x]
    symbol = [x for x in symbol if not '_' in x]
print(f"Coins Tradeable : {symbol}")
winning_trades = []
losing_trades = []
profitgraph = []  # for graphing the profit change over time
pp = pprint.PrettyPrinter()
profitgraph.append(account_balance)
originalBalance = copy(account_balance)

time_CAGR = Helper.get_CAGR(start, end)

Date_1min, High_1min, Low_1min, Close_1min, Open_1min, Date, Open, Close, High, Low, Volume, symbol = \
    Helper.get_aligned_candles([], [], [], [], [], [], [], [], [], [], [], symbol, TIME_INTERVAL, start, end)

print(symbol)
##variables for sharpe ratio
day_start_equity = account_balance
month_return = 0
monthly_return = []
Daily_return = []
if printing_on:
    print(f"{TIME_INTERVAL} OHLC Candle Sticks from {start} to {end}")

Bots: [Bot] = []
y = client.futures_exchange_info()['symbols']
coin_info = []
for x in y:
    coin_info.append([x['pair'], x['pricePrecision'], x['quantityPrecision'], x['filters'][0]['tickSize'],
                      x['filters'][0]['minPrice']])

original_time_interval = copy(TIME_INTERVAL)
TIME_INTERVAL = Helper.get_TIME_INTERVAL(TIME_INTERVAL)  ##Convert string to an integer for the rest of the script
if len(Open[0]) < 300:
    print("Not Enough Candles Increase the period over which you are running a backtest")
    time.sleep(20)

for k in range(len(symbol)):
    Coin_precision_temp = -99
    Order_precision_temp = -99
    tick_temp = -99
    min_price_temp = -99
    for x in coin_info:
        if x[0] == symbol[k]:
            Coin_precision_temp = int(x[1])
            Order_precision_temp = int(x[2])
            tick_temp = float(x[3])
            min_price_temp = float(x[4])
            flag = 1
            break
    Bots.append(
        Bot(symbol[k], Open[k][:300], Close[k][:300], High[k][:300], Low[k][:300], Volume[k][:300], Date[k][:300],
            Order_precision_temp, Coin_precision_temp, k, generate_heikin_ashi, tick_temp))
    Bots[k].add_hist_complete = 1
tradeNO = 0  ##number of trades
active_trades: [Trade] = []
new_trades = []
if printing_on:
    print("Account Balance: ", account_balance)
for i in range(301, len(Close_1min[0]) - 1):
    if account_balance < 0:
        if printing_on:
            print("Negative Balance")
        break
    ##give each coin next piece of data
    if i % TIME_INTERVAL == 0 or TIME_INTERVAL == 1:
        for k in range(len(symbol)):
            Bots[k].handle_socket_message(-99, Date[k][int(i / TIME_INTERVAL) - 1],
                                          float(Close[k][int(i / TIME_INTERVAL) - 1]),
                                          float(Volume[k][int(i / TIME_INTERVAL) - 1]),
                                          float(Open[k][int(i / TIME_INTERVAL) - 1]),
                                          float(High[k][int(i / TIME_INTERVAL) - 1]),
                                          float(Low[k][int(i / TIME_INTERVAL) - 1]))

        for k in range(len(Bots)):
            trade_flag = 0
            for t in active_trades:
                if t.index == k:
                    trade_flag = 1
                    break
            if trade_flag == 0 and Bots[k].Date[-1] != 'Data Set hasn\'t started yet':
                temp_dec = Bots[k].Make_decision()
                if temp_dec[0] != -99:
                    new_trades.append([k, temp_dec])

    if len(active_trades) == Number_Of_Trades:
        new_trades = []
        ##Sort out new trades to be opened
    while len(new_trades) > 0 and len(active_trades) < Number_Of_Trades:
        [index, [trade_direction, stop_loss, take_profit]] = new_trades.pop(0)

        Order_Notional = account_balance * leverage * order_Size
        order_qty, entry_price, account_balance = Helper.open_trade(Bots[index].symbol, Order_Notional,
                                                                             account_balance, Open_1min[index][i + 1],
                                                                             fee, Bots[index].OP)

        take_profit_val = -99
        stop_loss_val = -99
        ## Calculate the prices for TP and SL
        if trade_direction == 1:
            take_profit_val = take_profit + entry_price
            stop_loss_val = entry_price - stop_loss
        elif trade_direction == 0:
            take_profit_val = entry_price - take_profit
            stop_loss_val = entry_price + stop_loss

        ## Round to the coins specific coin precision
        if Bots[index].CP == 0:
            take_profit_val = round(take_profit_val)
            stop_loss_val = round(stop_loss_val)
        else:
            take_profit_val = round(take_profit_val, Bots[index].CP)
            stop_loss_val = round(stop_loss_val, Bots[index].CP)
        if order_qty != 0:
            tradeNO += 1
            ## Append new trade, to our trade list
            ## (index, position_size, tp_val, stop_loss_val, trade_direction, order_id_temp, symbol)
            active_trades.append(Trade(index, order_qty, take_profit_val, stop_loss_val, trade_direction, '', Bots[index].symbol))
            active_trades[-1].entry_price = entry_price
            active_trades[-1].trade_start = Date[index][i + 1]
            ##Empty the list of trades
            if len(active_trades) == Number_Of_Trades:
                new_trades = []

    for t in active_trades:
        ## Check SL Hit
        if t.trade_status == 1:
            t, account_balance = Helper.check_SL(t, account_balance, High_1min[t.index][i],
                                                          Low_1min[t.index][i], fee)
        ##Check if TP Hit
        if t.trade_status == 1:
            t, account_balance = Helper.check_TP(t, account_balance, High_1min[t.index][i],
                                                          Low_1min[t.index][i], fee)

    ## Check PNL here as well as print the current trades:
    if printing_on:
        trade_price = []
        for t in active_trades:
            trade_price.append(Bots[t.index].Close[-1])
        pnl, negative_balance_flag = Helper.print_trades(active_trades, trade_price, Bots[0].Date[-1], account_balance)
        if negative_balance_flag:
            print("**************** You have been liquidated *******************")
            profitgraph.append(0)
            account_balance = 0
            break ## break out of loop as weve been liquidated
        if add_delay:
            time.sleep(1)

    k = 0
    while k < len(active_trades):
        if active_trades[k].trade_status == 2:
            ## Win
            winning_trades.append([active_trades[k].symbol, f'{active_trades[k].trade_start}'])
            active_trades.pop(k)
            profitgraph.append(account_balance)
        elif active_trades[k].trade_status == 3:
            ## Loss
            losing_trades.append([active_trades[k].symbol, f'{active_trades[k].trade_start}'])
            active_trades.pop(k)
            profitgraph.append(account_balance)
        else:
            if active_trades[k].trade_status == 0:
                active_trades[k].trade_status = 1
            k += 1



    if i == len(Close[0]) - 2:
        for x in Date:
            print(f"Data Set Finished: {x[i]}")
    if i % 1440 == 0 and i != 0:
        Daily_return.append(account_balance)  # (day_return/day_start_equity)
        # day_return=0
        # day_start_equity=AccountBalance
    elif i == len(Close[0]) - 1:
        Daily_return.append(account_balance)  # (day_return/day_start_equity)

average = 0
num_wins = 0
for i in range(1, len(profitgraph)):
    if profitgraph[i] > profitgraph[i - 1]:
        num_wins += 1
        average += (profitgraph[i] - profitgraph[i - 1]) / profitgraph[i]
average /= num_wins

risk_free_rate = 1.41  ##10 year treasury rate
df = pd.DataFrame({'Account_Balance': Daily_return})
df['daily_return'] = df['Account_Balance'].pct_change()
df['cum_return'] = (1 + df['daily_return']).cumprod()
df['cum_roll_max'] = df['cum_return'].cummax()
df['drawdown'] = df['cum_roll_max'] - df['cum_return']
df['drawdown %'] = df['drawdown'] / df['cum_roll_max']
max_dd = df['drawdown %'].max() * 100

# cum_ret = np.array(df['cum_return'])
CAGR = ((df['cum_return'].iloc[-1]) ** (1 / time_CAGR) - 1) * 100  # ((df['cum_return'].iloc[-1])**(1/time_CAGR)-1)*100
vol = (df['daily_return'].std() * np.sqrt(365)) * 100
neg_vol = (df[df['daily_return'] < 0]['daily_return'].std() * np.sqrt(365)) * 100
Sharpe_ratio = (CAGR - risk_free_rate) / vol
sortino_ratio = (CAGR - risk_free_rate) / neg_vol
calmar_ratio = CAGR / max_dd

print("\nSettings:")
print('leverage:', leverage)
print('order_Size:', order_Size)
print('fee:', fee)
print("\nSymbol(s):", symbol, "fee:", fee)
print(f"{original_time_interval} OHLC Candle Sticks from {start} to {end}")
print("Account Balance:", account_balance)
print("% Gain on Account:", ((account_balance - originalBalance) * 100) / originalBalance)
print("Total Returns:", account_balance - originalBalance, "\n")

print(f"Annualized Volatility: {round(vol, 4)}%")
print(f"CAGR: {round(CAGR, 4)}%")
print("Sharpe Ratio:", round(Sharpe_ratio, 4))
print("Sortino Ratio:", round(sortino_ratio, 4))
print("Calmar Ratio:", round(calmar_ratio, 4))
print(f"Max Drawdown: {round(max_dd, 4)}%")

print(f"Average Win: {round(average * 100, 4)}%")
print("Trades Made: ", tradeNO)
print("Successful Trades:", len(winning_trades))
print("Accuracy: ", f"{(len(winning_trades) / tradeNO) * 100}%", "\n")
print(f"Winning Trades:\n {winning_trades}")
print(f"Losing Trades:\n {losing_trades}")
plt.plot(profitgraph)
plt.title(f"All coins: {original_time_interval} from {start} to {end}")
plt.ylabel('Account Balance')
plt.xlabel('Number of Trades')
plt.show()
