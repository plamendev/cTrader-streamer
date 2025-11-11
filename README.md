A minimal Python script that connects to the cTrader Open API (JSON over WebSocket), authenticates your application and trading account, retrieves the symbol list, and subscribes to spot price updates for a selected symbol.

The script performs a complete auth + market data flow using official `ProtoOAPayloadType` IDs and prints live bid/ask updates to the console.

## Features

- WebSocket connection to cTrader Open API JSON endpoint (`demo` or `live`).
- Application authentication: `ProtoOAApplicationAuthReq` (`2100`) → `ProtoOAApplicationAuthRes` (`2101`).
- Accounts by access token: `ProtoOAGetAccountsByAccessTokenReq` (`2149`) → `ProtoOAGetAccountsByAccessTokenRes` (`2150`).
- Account authentication: `ProtoOAAccountAuthReq` (`2102`) → `ProtoOAAccountAuthRes` (`2103`).
- Symbols list: `ProtoOASymbolsListReq` (`2114`) → `ProtoOASymbolsListRes` (`2115`).
- Spots subscription: `ProtoOASubscribeSpotsReq` (`2127`) → `ProtoOASubscribeSpotsRes` (`2128`).
- Spot events stream: `ProtoOASpotEvent` (`2131`) with bid/ask printing.
- Helpful diagnostics: token inspection, payload keys logging, and error handling.

## Requirements

- Python `3.8+`.
- `websockets` library.

Install dependency:

```bash
pip install websockets
```

## Configuration

Set these environment variables (macOS/Linux shells):

```bash
export CTRADER_CLIENT_ID="<your app client id>"
export CTRADER_CLIENT_SECRET="<your app client secret>"
export CTRADER_ACCESS_TOKEN="<access token for demo/live>"
# Select environment: "live" or "demo"
export CTRADER_ENV="live"
# Target symbol (e.g., EURUSD, XAUUSD)
export SYMBOL="EURUSD"
```

Notes:

- `CTRADER_ENV` picks the endpoint automatically: `wss://live.ctraderapi.com:5036` or `wss://demo.ctraderapi.com:5036`.
- Ensure your access token matches the environment (live tokens won’t work on demo, and vice versa).
- Your token must have scopes that allow account lookup and market data (typically `accounts`/`trading`).

## Usage

Run the script:

```bash
python main.py
```

You should see logs like:

```
Connecting to cTrader Open API (JSON, live:5036)...
Application auth OK.
Accounts response: count=1; ...
Using account 45211659.
Account auth OK.
Symbols list payload keys=[...]
Found symbol EURUSD with id 1.
Subscribe request sent for EURUSD (symbolId=1). Waiting for events...
Spot EURUSD: bid=115920 ask=115920 ts=1762887809806
...
```

## How It Works

1. Connect to WebSocket endpoint based on `CTRADER_ENV`.
2. Send application auth (`2100`) and wait for (`2101`).
3. Request accounts by token (`2149`) and use account from (`2150`).
4. Send account auth (`2102`) and verify (`2103`).
5. Request symbols list (`2114`) and locate the target `symbolId` in (`2115`).
6. Subscribe to spots (`2127`) and stream `ProtoOASpotEvent` (`2131`). A `SubscribeSpotsRes` (`2128`) may arrive; spot events can come immediately.

## Price Formatting

- Spot prices in events are raw integers. To display decimal prices, scale using the symbol’s precision (`digits`).
- Example approach (not implemented in code yet): `formatted_price = raw / (10 ** digits)`.

## Troubleshooting

- No accounts returned:
  - Verify the token belongs to the correct cTID profile and broker.
  - Check token scopes and that Open API access is enabled by your broker.
  - Ensure environment (`CTRADER_ENV`) matches token type.
- No symbols returned or symbol not found:
  - Confirm the symbol is available for your account.
  - Try an exact `symbolName` (e.g., `EURUSD`) or check `displayName`.
- Immediate spot events before subscribe response:
  - This is expected; the script handles both `2131` (event) and `2128` (subscribe confirmation).
- Error messages (`ProtoOAErrorRes` `2142`):
  - The script prints the error payload; check permissions, account state, and input IDs.

## Project Structure

- `main.py` — entry point script that handles WebSocket connection, authentication, symbols lookup, spots subscription, and event streaming.

## References

- cTrader Open API 2.0 Docs: https://help.ctrader.com/open-api/
- Proxies & Endpoints: https://help.ctrader.com/open-api/proxies-endpoints/

## Disclaimer

This script subscribes to market data only. It does not place trades. Keep your credentials secure and avoid committing secrets to source control.
