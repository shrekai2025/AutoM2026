import yfinance as yf
ticker = yf.Ticker("MSTR")
info = ticker.info
print("Price", info.get("currentPrice"))
print("Shares", info.get("sharesOutstanding"))
print("Market Cap", info.get("marketCap"))
