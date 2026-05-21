import json, re, random, string, time
import websocket

def _tok(prefix):
    return prefix + "".join(random.choice(string.ascii_lowercase) for _ in range(12))

def _msg(func, args):
    m = json.dumps({"m": func, "p": args}, separators=(",", ":"))
    return f"~m~{len(m)}~m~{m}"

def pull_series(symbol, resolution="1W", bars=320, retries=5):
    """Return list of (epoch_seconds, close) for a TradingView symbol."""
    last_err = None
    for attempt in range(retries):
        try:
            ws = websocket.create_connection(
                "wss://data.tradingview.com/socket.io/websocket",
                header=["Origin: https://www.tradingview.com"],
                timeout=20,
            )
            cs = _tok("cs_")
            sid = "sds_sym_1"
            ws.send(_msg("set_auth_token", ["unauthorized_user_token"]))
            ws.send(_msg("chart_create_session", [cs, ""]))
            ws.send(_msg("resolve_symbol", [cs, sid, "=" + json.dumps({"symbol": symbol, "adjustment": "splits"})]))
            ws.send(_msg("create_series", [cs, "s1", "s1", sid, resolution, bars, ""]))

            data = {}
            deadline = time.time() + 20
            while time.time() < deadline:
                raw = ws.recv()
                for h in re.findall(r"~m~\d+~m~(~h~\d+)", raw):
                    ws.send(f"~m~{len(h)}~m~{h}")
                if '"timescale_update"' in raw or '"du"' in raw:
                    for m in re.findall(r'\{"i":\d+,"v":\[([^\]]+)\]\}', raw):
                        nums = [float(x) for x in m.split(",") if x.strip() not in ("", "null")]
                        if len(nums) >= 5:
                            data[int(nums[0])] = nums[4]  # close
                if '"series_completed"' in raw and data:
                    break
            ws.close()
            if data:
                return sorted(data.items())
            last_err = "no data parsed"
        except Exception as e:
            last_err = repr(e)
            time.sleep(1.0)
    raise RuntimeError(f"{symbol}: failed after {retries} tries: {last_err}")

if __name__ == "__main__":
    s = pull_series("ECONOMICS:CNM2", "1M", 80)
    print("CNM2 points:", len(s))
    for t, c in s[-4:]:
        print(time.strftime("%Y-%m-%d", time.gmtime(t)), c)
