import os
import logging
import requests
import sys
import time
from http import HTTPStatus
from logging import StreamHandler
from dotenv import load_dotenv
import telegram
from exceptions import (ApiYandexUnavailableError,
                        ApiYandexOtherError, SendMessageError)

FORMAT: str = '%(asctime)s %(levelname)s %(message)s'

logging.basicConfig(level=logging.DEBUG,
                    filename='main.log',
                    filemode='a',
                    format=FORMAT,
                    encoding='UTF-8')

logger = logging.getLogger(__name__)
handler = StreamHandler(stream=sys.stdout)
formatter = logging.Formatter(FORMAT)
logger.addHandler(handler)
handler.setFormatter(formatter)

load_dotenv()
PRACTICUM_TOKEN: str = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN: str = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID: str = os.getenv('TELEGRAM_CHAT_ID')

RETRY_PERIOD: int = 600
ENDPOINT: str = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS: dict = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

HOMEWORK_VERDICTS: dict = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


def check_tokens() -> bool:
    """Проверка доступности переменных окружения."""
    return all([PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID])


def get_api_answer(timestamp) -> dict:
    """Запрос ответа API сервиса Практикум.Домашка."""
    try:
        homework_status = requests.get(**{
            'url': ENDPOINT,
            'headers': HEADERS,
            'params': {'from_date': timestamp}})
        if homework_status.status_code != HTTPStatus.OK:
            logging.error(f'Эндпоинт {ENDPOINT} не доступен')
            raise ApiYandexUnavailableError
        return homework_status.json()
    except requests.exceptions.RequestException:
        logging.error(f'Проблема при обращении к {ENDPOINT}')
        raise ApiYandexOtherError


def check_response(response) -> list:
    """Проверка ответа API сервиса Практикум.Домашка.
    Проверка соответствия документации
    """
    if isinstance(response, dict):
        if 'homeworks' not in response:
            logging.error('В ответе нет ключа homeworks')
            raise KeyError
        if not isinstance(response['homeworks'], list):
            logging.error('Ответ c домашними работами пришел не в виде списка')
            raise TypeError
        elif not response['homeworks']:
            logging.debug('Ответ не содержит список домашних работ')
        else:
            return response['homeworks'][0]
    else:
        logging.error('Получен некорреткный ответ от API')
        raise TypeError


def parse_status(homework) -> str:
    """
    Извлечение из ответа API статуса проверки работы.
    Формирование ответа для отправки в Telegram-чат студента
    """
    for key in ('homework_name', 'status'):
        if key not in homework:
            logger.error(f'Ключ {key} отсутсвует в ответе API')
            raise KeyError()

    homework_name = homework['homework_name']
    homework_status = homework['status']

    if homework_status not in HOMEWORK_VERDICTS:
        logger.error('Получен некорректный статус домашней работы')
        raise KeyError()

    verdict = HOMEWORK_VERDICTS[homework_status]
    return f'Изменился статус проверки работы "{homework_name}": {verdict}'


def send_message(bot, message) -> None:
    """Отправка сообщения ботом в Telegram-чат студента."""
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logger.debug('Удачная отправка любого сообщения в Telegram')
    except Exception:
        logger.error('Сбой при отправке сообщения в Telegram')
        raise SendMessageError


def main() -> None:
    """
    Основная логика работы бота.
    Порядок:
    1. Проверяем доступность токенов в env
    2. Запрашиваем ответ от API сервиса
    3. Проверяем ответ API
    (при отсутствии данных, повторяем запрос через 10 мин.)
    4. Извлекаем из ответа API статус проверки и подготавливем ответ
    5. Отправляем сообщение в чат
    """
    if not check_tokens():
        logger.critical('Отсутствует одна или несколько'
                        'из переменных окружения')
        sys.exit()

    old_message = ''
    old_error_message = ''
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())
    while True:
        try:
            response = get_api_answer(timestamp)
            homework = check_response(response)
            if homework:
                message = parse_status(homework)
                if old_message != message:
                    send_message(bot, message)
                    old_message = message
        except Exception as error:
            error_message = f'Сбой в работе программы: ' \
                            f'{error.__class__.__name__}'
            if old_error_message != error_message:
                send_message(bot, error_message)
                old_error_message = error_message
        time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
