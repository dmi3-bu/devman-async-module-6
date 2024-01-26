import asyncio
import logging
import time
from contextlib import contextmanager
from enum import Enum

import aiohttp
import pymorphy2
from anyio import create_task_group
from async_timeout import timeout

from adapters import ArticleNotFound
from adapters.inosmi_ru import sanitize
from text_tools import calculate_jaundice_rate, split_by_words

logging.basicConfig(level=logging.DEBUG)

TEST_ARTICLES = ['https://inosmi.ru/20240120/neyroseti-267505713.html',
                 'https://lenta.ru/brief/2021/08/26/afg_terror/',
                 'https://inosmi.ru/not/exist.html']
CONNECTION_TIMEOUT = 5
ANALYSIS_TIMEOUT = 3


class ProcessingStatus(Enum):
    OK = 'OK'
    FETCH_ERROR = 'FETCH_ERROR'
    PARSING_ERROR = 'PARSING_ERROR'
    TIMEOUT = 'TIMEOUT'

    def __str__(self):
        return str(self.value)

    def __repr__(self):
        return str(self.value)


@contextmanager
def timer():
    t1 = t2 = time.monotonic()
    yield lambda: round(t2 - t1, 6)
    t2 = time.monotonic()


async def fetch(session, url):
    async with session.get(url) as response:
        response.raise_for_status()
        return await response.text()


async def process_article(session, morph, charged_words, url, results):
    score = None
    words_count = None
    time_spent = None

    try:
        if 'inosmi.ru' not in url:
            raise ArticleNotFound

        async with timeout(CONNECTION_TIMEOUT):
            html = await fetch(session, url)
    except ArticleNotFound:
        status = ProcessingStatus.PARSING_ERROR
    except aiohttp.ClientError:
        status = ProcessingStatus.FETCH_ERROR
    except asyncio.exceptions.TimeoutError:
        status = ProcessingStatus.TIMEOUT
    else:
        status = ProcessingStatus.OK
        with timer() as time_spent:
            text = sanitize(html, plaintext=True)

            try:
                async with timeout(ANALYSIS_TIMEOUT):
                    words = await split_by_words(morph, text)
            except asyncio.exceptions.TimeoutError:
                status = ProcessingStatus.TIMEOUT
            else:
                words_count = len(words)
                score = calculate_jaundice_rate(words, charged_words)

    logging.debug(f'URL: {url}')
    logging.debug(f'Статус: {status}')
    logging.debug(f'Рейтинг: {score}')
    logging.debug(f'Слов в статье: {words_count}')
    if time_spent:
        logging.debug(f"Анализ закончен за {time_spent()} сек")
    result = {'status': status, 'url': url, 'score': score, 'words_count': words_count}
    results.append(result)


def load_charged_words():
    charged_words = []
    with open('charged_dict/positive_words.txt', 'r') as f:
        lines = f.read().splitlines()
        charged_words.extend(lines)

    with open('charged_dict/negative_words.txt', 'r') as f:
        lines = f.read().splitlines()
        charged_words.extend(lines)
    return charged_words


async def process_articles(urls, morph):
    charged_words = load_charged_words()
    results = []

    async with aiohttp.ClientSession() as session:
        async with create_task_group() as tg:
            for url in urls:
                tg.start_soon(process_article, session, morph, charged_words, url, results)

    return results


def test_process_article():
    morph = pymorphy2.MorphAnalyzer()
    results = asyncio.run(process_articles(TEST_ARTICLES, morph))
    assert results == [{'score': None, 'status': ProcessingStatus.PARSING_ERROR,
                        'url': 'https://lenta.ru/brief/2021/08/26/afg_terror/', 'words_count': None},
                       {'score': None, 'status': ProcessingStatus.FETCH_ERROR,
                        'url': 'https://inosmi.ru/not/exist.html', 'words_count': None},
                       {'score': 0.82, 'status': ProcessingStatus.OK,
                        'url': 'https://inosmi.ru/20240120/neyroseti-267505713.html', 'words_count': 612}]

    urls = ['https://inosmi.ru/20240120/neyroseti-267505713.html']
    global ANALYSIS_TIMEOUT
    ANALYSIS_TIMEOUT = 0.01
    results = asyncio.run(process_articles(urls, morph))
    assert results == [{'score': None, 'status': ProcessingStatus.TIMEOUT,
                        'url': 'https://inosmi.ru/20240120/neyroseti-267505713.html', 'words_count': None}]
