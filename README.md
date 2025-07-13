# README.md для HappyFaceChat Bot

Telegram-бот для управления доступом к закрытой супергруппе, обработки подписок и платежей через ЮKassa. Дает пробный доступ на 5 дней, продлевает подписки и удаляет пользователей из группы при истечении подписки.

## Требования

* Python 3.9+ (для локального запуска).
* Аккаунт на PythonAnywhere (для сервера).
* Git Bash (для Windows, загрузка файлов).
* Токен бота от [BotFather](https://t.me/BotFather).
* ЮKassa: SHOP\_ID и SECRET\_KEY.
* SQLite база: data/subscriptions.db.
* Закрытая супергруппа Telegram с ботом-администратором.

## Структура проекта

text
СвернутьПеренос
Копировать
HappyFaceBot/
├──
│ ├── bot.py # Код бота
│ ├── database.py # Работа с базой
│ ├── .env # Настройки
│ ├── requirements.txt # Библиотеки
│ └── data/
│ └── subscriptions.db # База данных
<br>
## Запуск бота

### 1\. Локальный запуск \(для тестов\)

#### Шаг 1: Подготовка файлов

* Скопируйте bot.py, database.py, .env, requirements.txt, data/subscriptions.db в папку, например, \~/HappyFaceBot/TelegramBot.

#### Шаг 2: Настройка .env

* В .env укажите:
env
СвернутьПеренос
Копировать
<span class="colour" style="color: rgb(209, 154, 102);">YOOKASSA\_SHOP\_ID</span>=ваш\_идентификатор
<span class="colour" style="color: rgb(209, 154, 102);">YOOKASSA\_SECRET\_KEY</span>=ваш\_ключ
<span class="colour" style="color: rgb(209, 154, 102);">SUBSCRIPTION\_PRICE</span>=
<span class="colour" style="color: rgb(209, 154, 102);">TELEGRAM\_BOT\_TOKEN</span>=
<span class="colour" style="color: rgb(209, 154, 102);">CHANNEL\_ID</span>= <span class="colour" style="color: rgb(92, 99, 112);">*\# ID супергруппы \(@GetIDsBot\)*</span>
<span class="colour" style="color: rgb(209, 154, 102);">CHAT\_LINK</span>=
<span class="colour" style="color: rgb(209, 154, 102);">LINK\_CLOSED\_CHANNEL</span>=
<span class="colour" style="color: rgb(209, 154, 102);">TRIAL\_DAYS</span>=<span class="colour" style="color: rgb(209, 154, 102);">5</span>
<span class="colour" style="color: rgb(209, 154, 102);">ADMIN\_ID</span>= <span class="colour" style="color: rgb(92, 99, 112);">*\# ID супергруппы \(@userinfobot\)*</span>
<span class="colour" style="color: rgb(209, 154, 102);">FRIEND\_ID</span>= <span class="colour" style="color: rgb(92, 99, 112);">*\# ID супергруппы \(@userinfobot\)*</span>

#### Шаг 3: Установка библиотек

* В терминале (в папке ):
bash
СвернутьПереносИсполнить
Копировать
pip install -r requirements.txt
* В requirements.txt:
text
python-telegram-bot==20.7
python-dotenv==1.0.1
yookassa==3.2.0
pytz==2024.2

#### Шаг 4: Добавление бота в супергруппу

* Добавьте @HappyFaceChat\_bot в супергруппу как администратора:
    * Права: отправка сообщений, управление участниками, создание ссылок.
* Включите **"Скрыть историю для новых участников"**.

#### Шаг 5: Запуск

* Выполните:
bash
СвернутьПереносИсполнить
Копировать
python bot.py
* Логи в bot.log.
* Проверьте через /start в Telegram.

#### Шаг 6: Остановка

* Нажмите Ctrl+C.

### 2\. Запуск на сервере \(PythonAnywhere\)

#### Шаг 1: Загрузка файлов

* В Git Bash (из HappyFaceBot/):
bash
СвернутьПереносИсполнить
Копироватьscp bot.py [HappyFaceBot@ssh.pythonanywhere.com](mailto:HappyFaceBot@ssh.pythonanywhere.com):/home/HappyFaceBot/bot.py
scp .env [HappyFaceBot@ssh.pythonanywhere.com](mailto:HappyFaceBot@ssh.pythonanywhere.com):/home/HappyFaceBot/.env
scp requirements.txt [HappyFaceBot@ssh.pythonanywhere.com](mailto:HappyFaceBot@ssh.pythonanywhere.com):/home/HappyFaceBot/requirements.txt
scp database.py [HappyFaceBot@ssh.pythonanywhere.com](mailto:HappyFaceBot@ssh.pythonanywhere.com):/home/HappyFaceBot/database.py
scp -r data [HappyFaceBot@ssh.pythonanywhere.com](mailto:HappyFaceBot@ssh.pythonanywhere.com):/home/HappyFaceBot/

#### Шаг 2: Проверка файлов

* В PythonAnywhere → **Files** проверьте /home/HappyFaceBot/:
    * bot.py, .env, requirements.txt, database.py, data/subscriptions.db.
* Убедитесь, что .env корректен.

#### Шаг 3: Установка библиотек

* В Bash-консоли:
bash
СвернутьПереносИсполнить
Копировать
pip3 install --user -r /home/HappyFaceBot/requirements.txt
* Если есть виртуальное окружение:
bash
СвернутьПереносИсполнить
Копировать
<span class="colour" style="color: rgb(230, 192, 123);">source</span> /home/HappyFaceBot/.venv/bin/activate
pip install -r /home/HappyFaceBot/requirements.txt

#### Шаг 4: Настройка веб-приложения

* В PythonAnywhere → **Web**:
    * Создайте приложение: **Add a new web app** → **Manual configuration** → **Python 3.13**.
    * Настройки:
        * **Source code**: /home/HappyFaceBot/bot.py.
        * **Working directory**: /home/HappyFaceBot/TelegramBot.
        * **WSGI** (/var/www/happyfacebot\_pythonanywhere\_com\_wsgi.py):
        python
        СвернутьПереносИсполнить
        Копировать
        <span class="colour" style="color: rgb(198, 120, 221);">import</span> sys
        path = <span class="colour" style="color: rgb(152, 195, 121);">'/home/HappyFaceBot/TelegramBot'</span>
        <span class="colour" style="color: rgb(198, 120, 221);">if</span> path <span class="colour" style="color: rgb(198, 120, 221);">not</span> <span class="colour" style="color: rgb(198, 120, 221);">in</span> sys.path:
        sys.path.append(path)
        <span class="colour" style="color: rgb(198, 120, 221);">from</span> bot <span class="colour" style="color: rgb(198, 120, 221);">import</span> main
        main()
        * **Virtualenv** (если есть): /home/HappyFaceBot/.venv.

#### Шаг 5: Добавление бота в супергруппу

* Как в локальном запуске.

#### Шаг 6: Запуск

* В **Web** нажмите **Reload**.
* Проверьте bot.log:
text
СвернутьПеренос
Копировать
2025-07-13 HH:MM:SS - \_\_main\_\_ - INFO - Bot started and ready to accept payments

### 3\. Тестирование

#### Тесты

* Отправьте /start, /check, /rejoin, /check\_payment в Telegram.
* Для проверки исключения:
    * В базе:
    bash
    СвернутьПереносИсполнить
    Копировать
    sqlite3 /home/HappyFaceBot/data/subscriptions.db
    <br>
sql
    СвернутьПеренос
    Копировать
    UPDATE users <span class="colour" style="color: rgb(198, 120, 221);">SET</span> subscription\_end = <span class="colour" style="color: rgb(152, 195, 121);">'2025-07-10 00:00:00'</span> <span class="colour" style="color: rgb(198, 120, 221);">WHERE</span> user\_id = ВАШ\_ИД;
    .exit
    * В bot.py временно замените:
    python
    СвернутьПереносИсполнить
    Копировать
    application.job\_queue.run\_repeating(check\_subscriptions, interval=<span class="colour" style="color: rgb(209, 154, 102);">86400</span>, first=<span class="colour" style="color: rgb(209, 154, 102);">10</span>)
    <br>
на:
    python
    СвернутьПереносИсполнить
    Копировать
    application.job\_queue.run\_once(check\_subscriptions, when=<span class="colour" style="color: rgb(209, 154, 102);">10</span>)
    * Загрузите bot.py и перезапустите приложение.

#### Проблемы

* **"Conflict: terminated by other getUpdates request"**:
    * Не запускайте python bot.py вручную.
    * Проверьте процессы:
    bash
    СвернутьПереносИсполнить
    Копировать
    ps aux \| grep python
    <span class="colour" style="color: rgb(230, 192, 123);">kill</span> \<PID>
    * Перезапустите веб-приложение.
* **Ошибки ссылок**:
    * Проверьте CHANNEL\_ID и права бота.
* **Ошибки оплаты**:
    * Проверьте ЮKassa ключи в .env.

#### Логи

* Проверяйте bot.log для отладки.

## Примечания

* Делайте резервную копию subscriptions.db.