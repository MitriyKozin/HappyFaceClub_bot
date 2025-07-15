# HappyFaceBot README

This is a Telegram bot for managing subscriptions and access to a private channel. The bot handles user subscriptions, payments via YooKassa, and sends welcome messages upon joining the channel. Below are instructions for setting up and running the bot locally or on a server.

<br>
Below is the proposed project structure for the HappyFaceBot Telegram bot project, based on the context provided and typical practices for a Python-based Telegram bot with database and configuration management. This structure ensures modularity, maintainability, and ease of deployment both locally and on a server like PythonAnywhere.

- - -

# HappyFaceBot Project Structure

text
СвернутьПеренос
Копировать
HappyFaceBot/
├── # Main project directory
│ ├── bot.py # Main bot script with handlers and logic
│ ├── database.py # Database connection and query functions
│ ├── .env # Environment variables (e.g., TOKEN, CHANNEL\_ID)
│ ├── data/ # Directory for persistent data
│ │ ├── subscriptions.db # SQLite database file
│ ├── bot.log # Log file for debugging
│ ├── requirements.txt # List of Python dependencies
│ └── README.md # Project documentation (this file)
├── .gitignore # Git ignore file to exclude sensitive files

## Prerequisites

* **Python**: Version 3.9 or higher
* **Dependencies**:
    * python-telegram-bot==20.7
    * yookassa==3.2.0
    * python-dotenv==1.0.1
* **Telegram Bot Token**: Obtain from [BotFather](https://t.me/BotFather)
* **YooKassa Account**: For payment processing
* **SQLite**: For database management
* **Server**: PythonAnywhere or similar (for server deployment)

## Setup Instructions

### 1\. Clone the Repository

bash
СвернутьПереносИсполнить
Копироватьgit <span class="colour" style="color: rgb(230, 192, 123);">clone</span> [https://github.com/](https://github.com/)\<your-username>/HappyFaceBot.git
<span class="colour" style="color: rgb(230, 192, 123);">cd</span> HappyFaceBot/TelegramBot

<br>
### 2\. Install Dependencies

Create and activate a virtual environment, then install dependencies:

bash
СвернутьПереносИсполнить
Копировать
python -m venv venv
<span class="colour" style="color: rgb(230, 192, 123);">source</span> venv/bin/activate <span class="colour" style="color: rgb(92, 99, 112);">*\# On Windows: venv\Scripts\activate*</span>
pip install python-telegram-bot==20.7 yookassa==3.2.0 python-dotenv==1.0.1

<br>
### 3\. Configure Environment Variables

Create a .env file in the TelegramBot directory with the following content:

bash
СвернутьПереносИсполнить
Копировать
TOKEN=<your\_bot\_token>
CHANNEL\_ID=<your\_channel\_id>
CHAT\_LINK=<your\_chat\_link>
ADMIN\_ID=<your\_admin\_id>
FRIEND\_ID=<friend\_id\_if\_any>
YOOKASSA\_SHOP\_ID=<yookassa\_shop\_id>
YOOKASSA\_SECRET\_KEY=<yookassa\_secret\_key>

<br>
### 4\. Set Up the Database

The bot uses an SQLite database (subscriptions.db) to store user data.

* Ensure the data directory exists: mkdir -p data
* The database is automatically created when the bot runs for the first time.

### 5\. Running Locally

Run the bot in polling mode:

bash
СвернутьПереносИсполнить
Копировать
python bot.py

<br>
The bot will start and log to bot.log. Ensure no other instances are running to avoid telegram.error.Conflict errors.

### 6\. Running on a Server \(PythonAnywhere\)

1. **Upload Files**:
    * Upload the TelegramBot directory to /home/\<your-username>/TelegramBot on PythonAnywhere.
2. **Set Up Virtual Environment**:
bash
СвернутьПереносИсполнить
Копировать
mkvirtualenv --python=/usr/bin/python3.9 your\_env
pip install python-telegram-bot==20.7 yookassa==3.2.0 python-dotenv==1.0.1
3. **Configure Task** (for polling mode):
    * In PythonAnywhere, go to **Tasks** and create a task:
        * Command: python /home/\<your-username>/bot.py
        * Virtualenv: /home/\<your-username>/.virtualenvs/your\_env
4. **Configure Webhook** (recommended):
    * Update bot.py to use application.run\_webhook:
    python
    СвернутьПереносИсполнить
    Копировать
    application.run\_webhook(
    listen=<span class="colour" style="color: rgb(152, 195, 121);">"0.0.0.0"</span>,
    port=<span class="colour" style="color: rgb(209, 154, 102);">8443</span>,
    url\_path=<span class="colour" style="color: rgb(152, 195, 121);">"/webhook"</span>,
    webhook\_url=<span class="colour" style="color: rgb(152, 195, 121);">"https://\<your-username>.[pythonanywhere.com/webhook](http://pythonanywhere.com/webhook)"</span>
    )
    * Set up a web app in PythonAnywhere:
        * Source code: /home/\<your-username>/TelegramBot
        * WSGI file (/var/www/\<your-username>\_pythonanywhere\_com\_wsgi.py):
        python
        СвернутьПереносИсполнить
        Копировать
        <span class="colour" style="color: rgb(198, 120, 221);">import</span> sys
        path = <span class="colour" style="color: rgb(152, 195, 121);">'/home/\<your-username>/TelegramBot'</span>
        <span class="colour" style="color: rgb(198, 120, 221);">if</span> path <span class="colour" style="color: rgb(198, 120, 221);">not</span> <span class="colour" style="color: rgb(198, 120, 221);">in</span> sys.path:
        sys.path.append(path)
        <span class="colour" style="color: rgb(198, 120, 221);">from</span> bot <span class="colour" style="color: rgb(198, 120, 221);">import</span> application
    * Set Webhook:
    bash
    СвернутьПереносИсполнить
    Копироватьcurl -X POST [https://api.telegram.org/bot](https://api.telegram.org/bot)<your\_bot\_token>/setWebhook?url=https://\<your-username>.[pythonanywhere.com/webhook](http://pythonanywhere.com/webhook)
    * Reload the web app in PythonAnywhere.

### 7\. Bot Permissions

* Add the bot as an admin to the private channel (CHANNEL\_ID) with "Manage Members" permission.
* In BotFather, run /setprivacy and set to Disabled to receive chat\_member updates.

## Known Issues

* **Welcome Message Not Sent After Joining Private Channel**:
    * **Problem**: The bot fails to send welcome messages to users upon joining the private channel.
    * **Cause**: Likely due to missing chat\_member updates, incorrect bot permissions, or issues with the database (e.g., invalid subscription status).
    * **Solution**:
        1. Ensure the bot has admin rights in the channel with "Manage Members" permission.
        2. Verify /setprivacy is set to Disabled in BotFather.
        3. Check the database (data/subscriptions.db) to confirm user subscriptions:
        bash
        СвернутьПереносИсполнить
        Копировать
        sqlite3 data/subscriptions.db
        SELECT user\_id, username, subscription\_end, trial\_used, join\_date, active FROM users;
        <br>
Ensureactive = 1 and subscription\_end is in the future.
        4. Check logs (bot.log) for errors in handle\_chat\_member\_update.
        5. Avoid running multiple bot instances to prevent telegram.error.Conflict errors.

## Logs

* Logs are saved to /home/\<your-username>/bot.log (or locally to bot.log).
* Check logs for errors like telegram.error.Conflict or database issues.

## Testing

1. Start the bot locally or on the server.
2. Join the private channel with a test user (ensure the user has an active subscription in the database).
3. Verify that the welcome message is sent and check bot.log for details.

If you encounter issues, provide:

* Logs from bot.log.
* Output of curl [https://api.telegram.org/bot](https://api.telegram.org/bot)<your\_bot\_token>/getWebhookInfo.
* Database query results: SELECT \* FROM users;.