import json

import pymorphy2
from aiohttp import web

from main import process_articles

URLS_LIMIT = 10


async def index(request):
    urls = request.query['urls'].split(',')
    if len(urls) > URLS_LIMIT:
        resp = f'{{"error": "too many urls in request, should be {URLS_LIMIT} or less"}}'
        return web.Response(text=resp, status=400, content_type='application/json')

    resp = await process_articles(urls, morph)
    resp = json.dumps(resp, default=str)
    return web.Response(text=resp, content_type='application/json')


if __name__ == '__main__':
    morph = pymorphy2.MorphAnalyzer()
    app = web.Application()
    app.add_routes([
        web.get('/', index),
    ])
    web.run_app(app)
