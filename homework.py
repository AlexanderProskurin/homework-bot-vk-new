import logging
import os
import sys
import time
from http import HTTPStatus

import requests
from dotenv import load_dotenv
from exceptions import UnexpectedAPIStatusError

import vk_api

load_dotenv()

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
VK_TOKEN = os.getenv('VK_TOKEN')
VK_USER_ID = os.getenv('VK_USER_ID')

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}

logging.basicConfig(
    level=logging.DEBUG,
    format=(
        '%(asctime)s [%(levelname)s] '
        '%(funcName)s:%(lineno)d - %(message)s'
    ),
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(
            __file__ + '.log',
            encoding='utf-8'
        )
    ]
)


def check_tokens():
    """Проверить наличие обязательных переменных окружения."""
    tokens = (
        ('PRACTICUM_TOKEN', PRACTICUM_TOKEN),
        ('VK_TOKEN', VK_TOKEN),
        ('VK_USER_ID', VK_USER_ID)
    )

    missing_tokens = []

    for name, value in tokens:
        if not value:
            missing_tokens.append(name)

    if missing_tokens:
        message = (
            'Отсутствуют обязательные переменные окружения: '
            + ', '.join(missing_tokens)
        )
        logging.critical(message)
        raise RuntimeError(message)


def send_message(vk, message):
    """Отправить сообщение в VK и вернуть результат отправки."""
    try:
        vk.messages.send(
            user_id=VK_USER_ID,
            message=message,
            random_id=0
        )
    except Exception as error:
        logging.error(
            'Ошибка отправки сообщения в VK: %s',
            error
        )
        return False

    logging.debug('Сообщение успешно отправлено в VK.')
    return True


def get_api_answer(timestamp):
    """Получить ответ от API Практикума."""
    request_params = {
        'url': ENDPOINT,
        'headers': HEADERS,
        'params': {'from_date': timestamp},
        'timeout': 10
    }

    request_info = (
        'Запрос к API: {url}, '
        'from_date={params[from_date]}'
    ).format(**request_params)

    logging.debug(request_info)

    try:
        response = requests.get(**request_params)
    except requests.RequestException as error:
        raise ConnectionError(
            (
                'Ошибка запроса к {url}, '
                'from_date={params[from_date]}: {error}'
            ).format(**request_params, error=error)
        ) from error

    if response.status_code != HTTPStatus.OK:
        raise UnexpectedAPIStatusError(
            f'Эндпоинт {ENDPOINT} недоступен. '
            f'Код: {response.status_code}. '
            f'Причина: {response.reason}. '
            f'Ответ: {response.text}'
        )

    return response.json()


def check_response(response):
    """Проверить формат ответа API Практикума."""
    if not isinstance(response, dict):
        raise TypeError('Ответ API должен быть словарём.')

    if 'homeworks' not in response:
        raise KeyError('В ответе API отсутствует ключ homeworks.')

    homeworks = response['homeworks']

    if not isinstance(homeworks, list):
        raise TypeError('Значение homeworks должно быть списком.')

    return homeworks


def parse_status(homework):
    """Определить статус домашней работы и подготовить сообщение."""
    if 'homework_name' not in homework:
        raise KeyError('Отсутствует ключ homework_name.')

    if 'status' not in homework:
        raise KeyError('Отсутствует ключ status.')

    homework_name = homework['homework_name']
    status = homework['status']

    if status not in HOMEWORK_VERDICTS:
        raise ValueError(f'Неожиданный статус домашней работы: {status}')

    verdict = HOMEWORK_VERDICTS[status]

    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Управлять работой бота и проверкой статусов домашних работ."""
    check_tokens()

    logging.info('Бот запущен.')

    vk_session = vk_api.VkApi(token=VK_TOKEN)
    vk = vk_session.get_api()

    timestamp = int(time.time())
    last_message = ''

    while True:
        try:
            response = get_api_answer(timestamp)
            homeworks = check_response(response)

            if not homeworks:
                logging.debug('Новых статусов домашних работ нет.')
                timestamp = response.get('current_date', timestamp)
                continue

            message = parse_status(homeworks[0])

            if message != last_message and send_message(vk, message):
                last_message = message
                timestamp = response.get('current_date', timestamp)

        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            logging.exception(message)

            if message != last_message and send_message(vk, message):
                last_message = message

        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
