set KEY=29ac1db14d0842c65b6a0af7d4db2a4f
set B64SECRET=eGw/OKZeUIWKbrT4ehDN3gkPMFJqHavuEDT8D/QQ2Si/pXB/olKUcExnQ0SwhlSMVmA4JIxZZi2ScWEsX4NDXg==
set PASSPHRASE=afm8rcw81x
set REST_URL=https://api-public.sandbox.pro.coinbase.com
set WS_URL=wss://ws-feed-public.sandbox.pro.coinbase.com
set LOG_DRIVE=logs
@REM set PATH_TO_TICKS_CSV=C:\Users\patri\Desktop\trader_log_parser\out\tick.csv
@REM set PATH_TO_WALLET_CSV=C:\Users\patri\Desktop\coin_trader\wallet.csv

python .\src\main.py config.csv 
