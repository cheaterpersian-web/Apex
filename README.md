## VPN Protocol Status Telegram Bot (Python)

A Telegram bot that periodically tests connectivity for popular VPN/proxy protocols (OpenVPN, WireGuard, Shadowsocks, V2Ray, Reality, etc.), stores results, shows a simple dashboard in Telegram, and notifies subscribers when a protocol becomes available.

### Features
- Test connectivity for multiple protocols (extensible architecture)
- Telegram dashboard and on-change notifications
- JSON-based persistence for statuses and subscribers
- Add/remove/list protocols from Telegram
- Safe: only connectivity checks; no exploitation or illegal activity

### Requirements
- Python 3.10+
- Linux VPS recommended
- Telegram Bot Token (from `@BotFather`)
- Optional: system clients if you want deep/proxy testing
  - OpenVPN (`openvpn`), WireGuard tools (`wg`, `wg-quick`)
  - Shadowsocks (`ss-local` from shadowsocks-libev), V2Ray/Xray (`v2ray` or `xray`)

### Quick Start
1. Clone/copy the project to your VPS.
2. Create and fill `.env` with your Telegram token:
```
cp .env.example .env
# Edit .env and set TELEGRAM_BOT_TOKEN
```
3. (Optional) Adjust `config.example.yaml`, then copy to `config.yaml`:
```
cp config.example.yaml config.yaml
```
4. Create a virtual environment and install deps:
```
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```
5. Run the bot:
```
python -m app.main
```

### How Connectivity Checks Work
- By default, TCP/UDP reachability is attempted based on the protocol config.
- For proxy-capable protocols (Shadowsocks, V2Ray, Reality), you can provide a client start command that spins up a temporary local SOCKS proxy; the bot will run an HTTP GET (via the proxy) to a test URL to validate end-to-end connectivity, then terminate the client.
- OpenVPN and WireGuard default to port reachability (non-root). Full tunnel verification would require privileged networking; the bot does not alter system networking.

### Telegram Commands
- `/start` – Register and show help
- `/help` – Usage tips
- `/status` – Show dashboard of all protocols and their latest results
- `/refresh` – Trigger an immediate re-check
- `/subscribe` – Subscribe to notifications
- `/unsubscribe` – Unsubscribe from notifications
- `/list_protocols` – List configured protocols
- `/add_protocol <json>` – Add a protocol (see examples below)
- `/remove_protocol <id>` – Remove a protocol by ID

### Protocol Config Examples
You can add protocols from Telegram using JSON after the command. Minimal examples:

OpenVPN (TCP reachability):
```
/add_protocol {"id":"ovpn-1","name":"My OpenVPN","type":"openvpn","host":"1.2.3.4","port":443,"transport":"tcp"}
```

WireGuard (UDP reachability):
```
/add_protocol {"id":"wg-1","name":"My WireGuard","type":"wireguard","host":"1.2.3.4","port":51820,"transport":"udp"}
```

Shadowsocks with local client command (SOCKS proxy):
```
/add_protocol {
  "id":"ss-1",
  "name":"My Shadowsocks",
  "type":"shadowsocks",
  "host":"1.2.3.4",
  "port":8388,
  "transport":"tcp",
  "client":{
    "start_command":"ss-local -s 1.2.3.4 -p 8388 -l 1081 -k PASSWORD -m aes-256-gcm",
    "socks_port":1081,
    "ready_regex":"listening at 127.0.0.1:1081",
    "startup_timeout_sec":8
  }
}
```

V2Ray (SOCKS proxy via config):
```
/add_protocol {
  "id":"v2-1",
  "name":"My V2Ray",
  "type":"v2ray",
  "host":"example.com",
  "port":443,
  "transport":"tcp",
  "client":{
    "start_command":"v2ray run -c /path/to/config.json",
    "socks_port":1082,
    "ready_regex":"socks\\(server\\) listening",
    "startup_timeout_sec":10
  }
}
```

Reality (Xray) – also tested via local SOCKS:
```
/add_protocol {
  "id":"reality-1",
  "name":"My Reality",
  "type":"reality",
  "host":"example.com",
  "port":443,
  "transport":"tcp",
  "client":{
    "start_command":"xray run -c /path/to/reality.json",
    "socks_port":1083,
    "ready_regex":"socks\\(server\\) listening",
    "startup_timeout_sec":10
  }
}
```

### Data Persistence
- JSON files are stored in `data/` (created at runtime):
  - `protocols.json` – list of protocol configs
  - `status.json` – latest results per protocol
  - `subscribers.json` – Telegram user IDs subscribed to notifications

### Notes and Safety
- The bot only performs connectivity checks. It does not circumvent security controls or modify system routing.
- For UDP (e.g., WireGuard), port-level checks are best-effort and may produce false negatives/positives due to UDP semantics.
- If you provide a client command, ensure the binary exists on the VPS and is safe to run.

### Run as a Service (optional)
You can wrap the command into `tmux`, `screen`, or create a systemd unit to keep it running.