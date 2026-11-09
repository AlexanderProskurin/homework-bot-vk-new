import logging
import os
import sys
import time

import requests
from dotenv import load_dotenv

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
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)


def check_tokens():
    """Проверить наличие обязательных переменных окружения."""
    tokens = (PRACTICUM_TOKEN, VK_TOKEN, VK_USER_ID)
    return all(tokens)


def send_message(vk, message):
    """Отправить сообщение пользователю VK."""
    vk.messages.send(
        user_id=VK_USER_ID,
        message=message,
        random_id=0
    )
    logging.debug('Сообщение успешно отправлено в VK.')


def get_api_answer(timestamp):
    """Получить ответ от API Практикума."""
    try:
        response = requests.get(
            ENDPOINT,
            headers=HEADERS,
            params={'from_date': timestamp},
            timeout=10
        )
    except requests.RequestException as error:
        raise ConnectionError(
            f'Ошибка при запросе к API Практикума: {error}'
        ) from error

    if response.status_code != 200:
        raise RuntimeError(
            f'Эндпоинт {ENDPOINT} недоступен. '
            f'Код ответа API: {response.status_code}'
        )

    return response.json()


def check_response(response):
    """Проверить формат ответа API Практикума."""
    if not isinstance(response, dict):
        raise TypeError('Ответ API должен быть словарём.')

    if 'homeworks' not in response:
        raise KeyError('В ответе API отсутствует ключ homeworks.')

    if 'current_date' not in response:
        raise KeyError('В ответе API отсутствует ключ current_date.')

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
        raise ValueError(f'Неизвестный статус домашней работы: {status}')

    verdict = HOMEWORK_VERDICTS[status]

    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def safe_send_message(vk, message):
    """Отправить сообщение в VK с обработкой ошибок."""
    try:
        send_message(vk, message)
    except Exception as error:
        logging.error(
            'Не удалось отправить сообщение в VK: %s',
            error
        )
        return False
    return True


def main():
    """Управлять работой бота и проверкой статусов домашних работ."""
    if not check_tokens():
        logging.critical(
            'Отсутствует обязательная переменная окружения. '
            'Программа остановлена.'
        )
        return

    logging.info('Бот запущен.')

    vk_session = vk_api.VkApi(token=VK_TOKEN)
    vk = vk_session.get_api()

    timestamp = int(time.time())
    last_status_message = None
    last_error_message = None

    while True:
        try:
            response = get_api_answer(timestamp)
            homeworks = check_response(response)

            if homeworks:
                message = parse_status(homeworks[0])

                if message != last_status_message:
                    if safe_send_message(vk, message):
                        last_status_message = message
            else:
                logging.debug('Новых статусов домашних работ нет.')

            timestamp = response['current_date']
            last_error_message = None

        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            logging.error(message)

            if message != last_error_message:
                if safe_send_message(vk, message):
                    last_error_message = message

        time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
