import os
import logging
import requests
import sys
import time
from http import HTTPStatus
from logging import StreamHandler
from dotenv import load_dotenv
import telegram
from exceptions import TokenError, ApiYandexUnavailableError, \
    ApiYandexOtherError, ParseStatusError, SendMessageError

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
HOMEWORK_STATUS: str = ''
MESSAGE: str = ''


def check_tokens() -> bool:
    """Проверка доступности переменных окружения."""
    status = all([PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID])
    return status


def get_api_answer(timestamp) -> dict:
    """Запрос ответа API сервиса Практикум.Домашка."""
    try:
        homework_status = requests.get(
            ENDPOINT,
            headers=HEADERS,
            params={'from_date': timestamp}
        )
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
    if isinstance(response, dict) and tuple(
            response.keys()) == ('homeworks', 'current_date'):
        if not isinstance(response['homeworks'], list):
            logging.error('Ответ c домашними работами пришел не в виде списка')
            raise TypeError
        elif response['homeworks']:
            homework = response['homeworks'][0]
            return homework
        else:
            logging.debug('Ответ не содержит список домашних работ')
    else:
        logging.error('Получен некорреткный ответ от API')
        raise TypeError


def parse_status(homework) -> str:
    """
    Извлечение из ответа API статуса проверки работы.
    Формирование ответа для отправки в Telegram-чат студента
    """
    try:
        homework_name = homework['homework_name']
        homework_status = homework['status']
        verdict = HOMEWORK_VERDICTS[homework_status]
        logging.debug('Получен корректный статус работы в ответе API')
        return f'Изменился статус проверки работы "{homework_name}". {verdict}'
    except Exception:
        logging.error('Неожиданный статус домашней работы,'
                      ' обнаруженный в ответе API')
        raise ParseStatusError


def send_message(bot, message) -> None:
    """Отправка сообщения ботом в Telegram-чат студента."""
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logger.debug('Удачная отправка любого сообщения в Telegram')
    except Exception:
        logger.error('Сбой при отправке сообщения в Telegram')
        raise SendMessageError


# Комментарий для ревьювера: Очень много времени потратил
# на разработку алгоритма, когда повторный статус ошибки и статус
# проверки домашней работы отправляется в телегу только один раз
# не смог додуматься как решить внутри функции и через декоратор.
# В итоге решил через глобальные переменные, но чувствую, что через декоратор
# было бы самым правильным решением, дайте, пожалуйста, ОС
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
        raise TokenError

    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())
    while True:
        try:
            response = get_api_answer(timestamp)
            homework = check_response(response)
            global HOMEWORK_STATUS
            if homework and HOMEWORK_STATUS != homework['status']:
                HOMEWORK_STATUS = homework['status']
                message = parse_status(homework)
                send_message(bot, message)
        except Exception as error:
            if error.__class__.__name__ == TypeError:
                break
            global MESSAGE
            message = f'Сбой в работе программы: {error.__class__.__name__}'
            if MESSAGE != message:
                send_message(bot, message)
                MESSAGE = message
        time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
