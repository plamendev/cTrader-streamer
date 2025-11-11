import asyncio
import json
import os
import uuid
import websockets
import time
import base64

# --- SETTINGS ---
ACCESS_TOKEN = os.getenv("CTRADER_ACCESS_TOKEN", "")
CLIENT_ID = os.getenv("CTRADER_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("CTRADER_CLIENT_SECRET", "")
SYMBOL = "EURUSD"  # e.g. "EURUSD", "XAUUSD", etc.
ENV = os.getenv("CTRADER_ENV", "live").lower()  # "demo" or "live"
ENDPOINT = "wss://live.ctraderapi.com:5036" if ENV == "live" else "wss://demo.ctraderapi.com:5036"

# --- MESSAGE HELPERS ---
def make_msg(payload_type: int, payload: dict, client_msg_id: str | None = None):
    return {
        "clientMsgId": client_msg_id or str(uuid.uuid4()),
        "payloadType": payload_type,
        "payload": payload,
    }

def application_auth_req(client_id: str, client_secret: str):
    # 2100: ProtoOAApplicationAuthReq
    return make_msg(2100, {"clientId": client_id, "clientSecret": client_secret})

def get_accounts_by_token_req(access_token: str):
    # 2149: ProtoOAGetAccountsByAccessTokenReq
    return make_msg(2149, {"accessToken": access_token})

def account_auth_req(ctid_trader_account_id: int, access_token: str):
    # 2102: ProtoOAAccountAuthReq (client request)
    return make_msg(2102, {"ctidTraderAccountId": ctid_trader_account_id, "accessToken": access_token})

def symbols_list_req(ctid_trader_account_id: int, include_archived: bool = False):
    # 2114: ProtoOASymbolsListReq
    return make_msg(2114, {"ctidTraderAccountId": ctid_trader_account_id, "includeArchivedSymbols": include_archived})

def subscribe_spots_req(ctid_trader_account_id: int, symbol_id: int):
    # 2127: ProtoOASubscribeSpotsReq
    return make_msg(2127, {"ctidTraderAccountId": ctid_trader_account_id, "symbolId": symbol_id})

# --- DIAGNOSTICS ---
def _b64url_to_bytes(segment: str) -> bytes:
    # Add padding for base64 url-safe decoding
    padding = '=' * (-len(segment) % 4)
    return base64.urlsafe_b64decode(segment + padding)

def inspect_token(token: str):
    try:
        parts = token.split('.')
        if len(parts) == 3:
            header = json.loads(_b64url_to_bytes(parts[0]).decode('utf-8'))
            payload = json.loads(_b64url_to_bytes(parts[1]).decode('utf-8'))
            print("Access token looks like JWT. Decoded claims:")
            print("- header:", header)
            # Avoid printing sensitive full token; only claims for debugging
            safe_payload = {k: payload.get(k) for k in (
                'aud', 'iss', 'scope', 'ctid', 'exp', 'iat', 'env'
            ) if k in payload}
            # Include broker/account hints if present
            for k in ('brokerId', 'accountIds'):
                if k in payload:
                    safe_payload[k] = payload[k]
            print("- payload:", safe_payload)
        else:
            print("Access token does not look like JWT; limited introspection available.")
    except Exception as e:
        print(f"Token inspection failed: {e}")

# --- MAIN LOOP ---
async def stream_prices():
    if not CLIENT_ID or not CLIENT_SECRET:
        print("Missing credentials: set CTRADER_CLIENT_ID and CTRADER_CLIENT_SECRET env vars.")
        return
    if not ACCESS_TOKEN:
        print(f"Missing access token: set CTRADER_ACCESS_TOKEN for {ENV} environment.")
        return

    async with websockets.connect(ENDPOINT) as ws:
        print(f"Connecting to cTrader Open API (JSON, {ENV}:5036)...")
        print(f"Endpoint: {ENDPOINT}")
        inspect_token(ACCESS_TOKEN)

        # Step 1: Application auth
        await ws.send(json.dumps(application_auth_req(CLIENT_ID, CLIENT_SECRET)))

        # Wait for ApplicationAuthRes (2101)
        msg = await ws.recv()
        data = json.loads(msg)
        if data.get("payloadType") != 2101:
            print("Unexpected response to application auth:", data)
            return
        print("Application auth OK.")

        # Step 2: Get accounts by access token
        await ws.send(json.dumps(get_accounts_by_token_req(ACCESS_TOKEN)))
        msg = await ws.recv()
        data = json.loads(msg)
        if data.get("payloadType") not in (2150,):
            print("Unexpected response to get accounts:", data)
            return
        payload = data.get("payload", {})
        accounts = payload.get("traderAccounts")
        # Fallback to 'ctidTraderAccount' which is used in JSON mapping
        if accounts is None:
            accounts = payload.get("ctidTraderAccount")
            if isinstance(accounts, dict):
                accounts = [accounts]
            elif accounts is None:
                accounts = []
        print(f"Accounts response: count={len(accounts)}; raw payload keys={list(payload.keys())}")
        if not accounts:
            print("No accounts returned for provided access token.")
            print("Tips:")
            print("- Ensure CTRADER_ENV matches your token (demo vs live are separate).")
            print("- Use a LIVE access token when ENV=live. Demo tokens won't work on live.")
            print("- Confirm your OAuth scopes include 'accounts' or 'trading'.")
            print("- Verify the token belongs to the cTID owning the target account.")
            print("- Some brokers may restrict Open API; confirm your broker enables it.")
            print("- Regenerate token via OAuth and re-test.")
            print("  Auth guide: https://help.ctrader.com/open-api/account-authentication/")
            print("  Endpoints: https://help.ctrader.com/open-api/proxies-endpoints/")
            return
        # Prefer explicit ctidTraderAccountId; some payloads may expose 'accountId'
        account_id = accounts[0].get("ctidTraderAccountId") or accounts[0].get("accountId")
        if account_id is None:
            print("Unable to extract account ID from accounts payload:", accounts[0])
            return
        print(f"Using account {account_id}.")

        # Step 3: Account auth
        await ws.send(json.dumps(account_auth_req(account_id, ACCESS_TOKEN)))
        msg = await ws.recv()
        data = json.loads(msg)
        if data.get("payloadType") != 2103:
            print("Unexpected response to account auth:", data)
            return
        print("Account auth OK.")

        # Step 4: Get symbols list and find target symbolId
        await ws.send(json.dumps(symbols_list_req(account_id)))
        msg = await ws.recv()
        data = json.loads(msg)
        if data.get("payloadType") not in (2115,):
            # Handle possible error response
            if data.get("payloadType") == 2142:
                err = data.get("payload", {})
                print("Symbols list error:", err)
            else:
                print("Unexpected response to symbols list:", data)
                return
        payload = data.get("payload", {})
        print(f"Symbols list payload keys={list(payload.keys())}")
        # The repeated symbols field can be named "symbols" or "symbol" depending on JSON mapping
        symbols = payload.get("symbols")
        if symbols is None:
            symbols = payload.get("symbol")
        if not symbols:
            print("No symbols returned for account.")
            print("Raw symbols payload:", payload)
            return
        # Try to find by exact symbolName match first, otherwise fallback to displayName
        target = None
        for s in symbols:
            name = s.get("symbolName") or s.get("name")
            disp = s.get("displayName")
            if name == SYMBOL or disp == SYMBOL:
                target = s
                break
        if not target:
            # Fallback: case-insensitive search
            for s in symbols:
                name = (s.get("symbolName") or s.get("name") or "").upper()
                disp = (s.get("displayName") or "").upper()
                if name == SYMBOL.upper() or disp == SYMBOL.upper():
                    target = s
                    break
        if not target:
            print(f"Symbol '{SYMBOL}' not found in symbols list.")
            print("Tip: ensure the symbol exists and is available for this account.")
            return
        symbol_id = target.get("symbolId")
        if symbol_id is None:
            print("Found symbol but missing symbolId:", target)
            return
        print(f"Found symbol {SYMBOL} with id {symbol_id}.")

        # Step 5: Subscribe to spot prices
        await ws.send(json.dumps(subscribe_spots_req(account_id, symbol_id)))
        print(f"Subscribe request sent for {SYMBOL} (symbolId={symbol_id}). Waiting for events...")

        # Step 6: Stream spot events
        while True:
            try:
                msg = await ws.recv()
                data = json.loads(msg)
                pt = data.get("payloadType")
                if pt == 2131:  # ProtoOASpotEvent
                    p = data.get("payload", {})
                    bid = p.get("bid")
                    ask = p.get("ask")
                    ts = p.get("timestamp") or p.get("time") or p.get("timestampInMs")
                    print(f"Spot {SYMBOL}: bid={bid} ask={ask} ts={ts}")
                elif pt == 2128:  # ProtoOASubscribeSpotsRes
                    print(f"Subscribe confirmed for {SYMBOL} (symbolId={symbol_id}).")
                elif pt == 2142:  # ProtoOAErrorRes
                    print("Error event:", data.get("payload", {}))
                else:
                    # You can add more handlers here as needed
                    pass
            except websockets.ConnectionClosed:
                print("Connection closed.")
                break

# --- RUN ---
if __name__ == "__main__":
    try:
        asyncio.run(stream_prices())
    except KeyboardInterrupt:
        print("\nDisconnected.")
