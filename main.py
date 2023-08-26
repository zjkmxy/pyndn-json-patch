import json
from fastapi import FastAPI, Body, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
import asyncio as aio
import logging
from ndn import appv2
from ndn import encoding as enc
from ndn import types, utils
from ndn import security as sec
from ndn.app_support import svs as svs
import random
from pyndn_json_patch.objdb import ObjDb


HTML_TEMPLATE = r'''
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Title</title>
  <script src="/static/aframe.js"></script>
  <script src="/static/aincraft.js"></script>
</head>
<body>
{0}
</body>
</html>
'''

logging.basicConfig(format='[{asctime}]{levelname}:{message}',
                    datefmt='%Y-%m-%d %H:%M:%S',
                    level=logging.INFO,
                    style='{')


fetched_dict = {}
fetch_signal = aio.Event()
running = False
group_prefix = enc.Name.from_str('/example/testJsonPatch')


def on_missing_data(_svs_inst: svs.SvsInst):
    # This function must be non-blocking
    fetch_signal.set()


app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
obj_db = ObjDb()
obj_db.initial_default()

ndn_app = appv2.NDNApp()
keychain = ndn_app.default_keychain()
text_node_id = f'node-{random.randbytes(4).hex()}'
name_node_id = enc.Name.from_str(text_node_id)
node_name = name_node_id + group_prefix
svs_inst = svs.SvsInst(
    group_prefix, name_node_id,
    on_missing_data,
    sec.DigestSha256Signer(),
    appv2.pass_all,
    sync_interval=10,
)
packet_cache = {}


@ndn_app.route(node_name)
def data_pkt_handler(name, _app_param, reply, _context):
    name_bytes = enc.Name.to_bytes(name)
    ret = packet_cache.get(name_bytes, None)
    if ret:
        reply(ret)


async def fetch_missing_data():
    while running:
        await fetch_signal.wait()
        if not running:
            return
        local_sv = svs_inst.local_sv.copy()
        fetch_signal.clear()
        local_sv.pop(enc.Name.to_bytes(name_node_id), None)
        for node_id, seq in local_sv.items():
            fetched_seq = fetched_dict.get(node_id, -1)
            node_name = enc.Name.from_bytes(node_id) + group_prefix
            if fetched_seq < seq:
                fetched_dict[node_id] = seq
                for i in range(fetched_seq+1, seq+1):
                    pkt_name = node_name + [enc.Component.from_sequence_num(i)]
                    try:
                        _, data, _ = await ndn_app.express(pkt_name, appv2.pass_all)
                        patch = bytes(data).decode()
                        logging.info(f'Fetched {enc.Name.to_str(pkt_name)}: {patch}')
                        try:
                            # Patch json
                            obj_db.patch_item(json.loads(patch))
                            # Shoot to websocket
                            for _, peer in peer_ws.items():
                                await peer.send_json(json.loads(patch))
                        except (ValueError, KeyError) as e:
                            logging.error(f'[{enc.Name.to_str(pkt_name)}] Invalid patch {e}')
                    except types.InterestNack as e:
                        logging.info(f'[{enc.Name.to_str(pkt_name)}] Nacked with reason={e.reason}')
                    except types.InterestTimeout:
                        logging.info(f'[{enc.Name.to_str(pkt_name)}] Timeout')
                    except types.InterestCanceled:
                        logging.info(f'[{enc.Name.to_str(pkt_name)}] Canceled')
                    except types.ValidationFailure:
                        logging.info(f'[[{enc.Name.to_str(pkt_name)}] Data failed to validate')
                    except (ValueError, KeyError) as e:
                        logging.error(f'[{enc.Name.to_str(pkt_name)}]: {e}')


def generate_svs_data(data: bytes):
    seq = svs_inst.new_data()
    name = node_name + [enc.Component.from_sequence_num(seq)]
    data_pkt = ndn_app.make_data(name, data, sec.DigestSha256Signer(), freshness_period=5000)
    packet_cache[enc.Name.to_bytes(name)] = data_pkt


@app.get("/", response_class=HTMLResponse)
async def root():
    return HTML_TEMPLATE.format(obj_db.resolve_html('/root'))


@app.get('/objects/{obj_path:path}')
async def objects_json(obj_path: str):
    return obj_db.resolve_json('/' + obj_path)


@app.post('/patches/{obj_path:path}')
async def patches_json(obj_path: str, patch: dict = Body(...)):
    name = '/' + obj_path
    if patch.get('op', '') != 'new':
        old_item = obj_db.get_item(name)
        if not old_item:
            return {'status': 'error', 'reason': 'specified object does not exist'}
        patch['@prev'] = old_item['@version']
    patch['@name'] = name
    patch['@version'] = utils.timestamp()
    # First try to patch locally
    try:
        obj_db.patch_item(patch)
    except (ValueError, KeyError) as e:
        return {'status': 'error', 'reason': str(e)}
    # Then generate data
    generate_svs_data(json.dumps(patch).encode('utf-8'))
    return {'status': 'success', 'version': patch['@version']}


class BackgroundRunner:
    def __init__(self):
        pass

    async def run_main(self):
        # logging.error(obj_db.resolve_html('/'))
        global running
        running = True
        fetch_missing_task = aio.create_task(fetch_missing_data())
        logging.info(f'Run as {text_node_id} ...')

        async def after_start():
            svs_inst.start(ndn_app)
            await ndn_app.register(group_prefix)

        try:
            await ndn_app.main_loop(after_start())
        except KeyboardInterrupt:
            logging.info('Receiving Ctrl+C, exit')

        # await app.unregister(group_prefix)
        svs_inst.stop()
        running = False
        fetch_signal.set()
        await fetch_missing_task
        # await app.shutdown()


runner = BackgroundRunner()
peer_ws = {}
pid_max = 0


@app.on_event('startup')
async def app_startup():
    aio.create_task(runner.run_main())


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    global pid_max
    await websocket.accept()
    pid = pid_max
    pid_max += 1
    peer_ws[pid] = websocket
    try:
        while True:
            data = await websocket.receive_json()
            logging.info(f'Received: {data}')
            try:
                # Local update
                obj_db.patch_item(data)
                # Generate sync packet
                generate_svs_data(json.dumps(data).encode('utf-8'))

                # Shoot to other local websocket (in case there are many)
                for wsid, peer in peer_ws.items():
                    if wsid != pid:
                        await peer.send_json(data)
            except (ValueError, KeyError) as e:
                logging.error(f'Invalid patch from ws: {e}')
    except WebSocketDisconnect:
        del peer_ws[pid]
