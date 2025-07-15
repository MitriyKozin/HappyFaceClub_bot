from math import ceil
from datetime import datetime, timedelta
from multiprocessing import context
import pytz
import telegram
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler, ChatMemberHandler
from telegram.error import TelegramError
from telegram.constants import ParseMode
from yookassa import Configuration, Payment
from dotenv import load_dotenv
from database import get_db_connection, init_db, add_user, check_user_access, update_subscription
import os
import logging
import asyncio
import sqlite3 # Python 3.9.13  Ok


# Настройка логирования с явной кодировкой UTF-8
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Загрузка переменных окружения
load_dotenv()
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
CHANNEL_ID = int(os.getenv('CHANNEL_ID'))
CHAT_LINK = os.getenv('CHAT_LINK')
LINK_CLOSED_CHANNEL = os.getenv('LINK_CLOSED_CHANNEL')
SUBSCRIPTION_PRICE = float(os.getenv('SUBSCRIPTION_PRICE', 1000))
TRIAL_DAYS = int(os.getenv('TRIAL_DAYS', 5))
ADMIN_ID = int(os.getenv('ADMIN_ID'))
FRIEND_ID = int(os.getenv('FRIEND_ID', 0))

# Проверка переменных окружения
if not all([TOKEN, CHANNEL_ID, CHAT_LINK, LINK_CLOSED_CHANNEL, SUBSCRIPTION_PRICE, TRIAL_DAYS, ADMIN_ID]):
    raise ValueError("Missing required environment variables in .env")

# Настройка ЮKassa
Configuration.account_id = os.getenv('YOOKASSA_SHOP_ID')
Configuration.secret_key = os.getenv('YOOKASSA_SECRET_KEY')

# Временная зона Москвы
MOSCOW_TZ = pytz.timezone('Europe/Moscow')

# Инициализация базы данных
init_db()

async def generate_invite_link(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> str:
    try:
        link = await context.bot.create_chat_invite_link(
            chat_id=CHANNEL_ID,
            member_limit=1,
            expire_date=int((datetime.now(MOSCOW_TZ) + timedelta(days=1)).timestamp())
        )
        return link.invite_link
    except Exception as e:
        logger.error(f"Error generating invite link for user {user_id}: {e}")
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"⚠️ Ошибка создания ссылки для пользователя {user_id}: {e}",
            parse_mode=ParseMode.HTML
        )
        if FRIEND_ID:
            await context.bot.send_message(
                chat_id=FRIEND_ID,
                text=f"⚠️ Ошибка создания ссылки для пользователя {user_id}: {e}",
                parse_mode=ParseMode.HTML
            )
        return ""

async def create_payment(user_id: int, bot_username: str):
    try:
        payment = Payment.create({
            "amount": {
                "value": f"{SUBSCRIPTION_PRICE:.2f}",
                "currency": "RUB"
            },
            "confirmation": {
                "type": "redirect",
                "return_url": f"https://t.me/{bot_username}?start=payment_{user_id}"
            },
            "capture": True,
            "description": "Подписка на HappyFaceClub",
            "metadata": {"user_id": str(user_id)}
        })
        logger.info(f"Created payment {payment.id} for user {user_id}")

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
        INSERT INTO payments (payment_id, user_id, amount, status)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(payment_id) DO NOTHING
        ''', (payment.id, user_id, SUBSCRIPTION_PRICE, 'pending'))
        conn.commit()
        conn.close()

        return payment.confirmation.confirmation_url, payment.id
    except Exception as e:
        logger.error(f"Payment creation error for user {user_id}: {e}")
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"⚠️ Ошибка создания платежа для пользователя {user_id}: {e}",
            parse_mode=ParseMode.HTML
        )
        if FRIEND_ID:
            await context.bot.send_message(
                chat_id=FRIEND_ID,
                text=f"⚠️ Ошибка создания платежа для пользователя {user_id}: {e}",
                parse_mode=ParseMode.HTML
            )
        return None, None

async def check_payment_status(payment_id: str, user_id: int, context: ContextTypes.DEFAULT_TYPE):
    try:
        payment = Payment.find_one(payment_id)
        if not payment:
            logger.error(f"Payment {payment_id} not found for user {user_id}")
            return False

        if payment.metadata.get('user_id') != str(user_id):
            logger.error(f"Payment {payment_id} does not belong to user {user_id}")
            return False

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute('''
        UPDATE payments SET status = ?, date = datetime('now')
        WHERE payment_id = ?
        ''', (payment.status, payment.id))

        if payment.status == 'succeeded':
            update_subscription(user_id, payment_id, SUBSCRIPTION_PRICE)

            cursor.execute('''
            SELECT subscription_end FROM users WHERE user_id = ?
            ''', (user_id,))
            result = cursor.fetchone()
            new_end_date = None
            if result and result[0]:
                new_end_date = datetime.strptime(result[0], '%Y-%m-%d %H:%M:%S').replace(tzinfo=MOSCOW_TZ)
            else:
                new_end_date = datetime.now(MOSCOW_TZ) + timedelta(days=30)
            conn.commit()
            conn.close()

            invite_link = await generate_invite_link(context, user_id)
            if not invite_link:
                logger.error(f"Failed to generate invite link for user {user_id}")
                await context.bot.send_message(
                    chat_id=user_id,
                    text="⚠️ Ошибка при создании ссылки на группу. Пожалуйста, свяжитесь с поддержкой.",
                    parse_mode=ParseMode.HTML
                )
                return True

            await context.bot.send_message(
                chat_id=user_id,
                text=f"✅ <b>Оплата подтверждена!</b>\n\n"
                     f"🔓 Ваша подписка продлена до {new_end_date.strftime('%d.%m.%Y')}\n"
                     f"🔗 Ссылка в группу: {invite_link}\n\n"
                     f"Спасибо за доверие! ❤️",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔐 Перейти в группу", url=invite_link)]
                ])
            )

            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"💳 <b>Новый платеж</b>\n"
                     f"👤 Пользователь: {user_id} (@{(await context.bot.get_chat(user_id)).username or 'без имени'})\n"
                     f"💰 Сумма: {SUBSCRIPTION_PRICE} RUB\n"
                     f"🆔 ID платежа: {payment.id}",
                parse_mode=ParseMode.HTML
            )
            if FRIEND_ID:
                await context.bot.send_message(
                    chat_id=FRIEND_ID,
                    text=f"💳 <b>Новый платеж</b>\n"
                         f"👤 Пользователь: {user_id} (@{(await context.bot.get_chat(user_id)).username or 'без имени'})\n"
                         f"💰 Сумма: {SUBSCRIPTION_PRICE} RUB\n"
                         f"🆔 ID платежа: {payment.id}",
                    parse_mode=ParseMode.HTML
                )
            logger.info(f"Payment {payment_id} succeeded for user {user_id}")
            return True
        else:
            conn.commit()
            conn.close()
            logger.info(f"Payment {payment_id} status: {payment.status}")
            return False
    except Exception as e:
        logger.error(f"Payment processing error for user {user_id}: {e}")
        if 'conn' in locals():
            conn.close()
        return False

async def handle_payment_return(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if update.message and update.message.text.startswith('/start payment_'):
            user_id = int(update.message.text.split('_')[1])
            if update.effective_user.id != user_id:
                await update.message.reply_text("⚠️ Эта ссылка не для вас", parse_mode=ParseMode.HTML)
                return

            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('''
            SELECT payment_id FROM payments
            WHERE user_id = ?
            ORDER BY date DESC LIMIT 1
            ''', (user_id,))
            payment = cursor.fetchone()
            conn.close()

            if payment:
                payment_id = payment[0]
                if await check_payment_status(payment_id, user_id, context):
                    return
                else:
                    await update.message.reply_text(
                        "⌛️ Платеж еще не обработан. Попробуйте через минуту или используйте /check_payment.",
                        parse_mode=ParseMode.HTML
                    )
            else:
                await update.message.reply_text(
                    "⚠️ Платеж не найден. Попробуйте начать процесс заново с /start.",
                    parse_mode=ParseMode.HTML
                )
    except Exception as e:
        logger.error(f"Payment return handler error: {e}")
        await update.message.reply_text(
            "⚠️ Произошла ошибка при обработке платежа",
            parse_mode=ParseMode.HTML
        )
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"⚠️ Ошибка в handle_payment_return для пользователя {update.effective_user.id}: {e}",
            parse_mode=ParseMode.HTML
        )
        if FRIEND_ID:
            await context.bot.send_message(
                chat_id=FRIEND_ID,
                text=f"⚠️ Ошибка в handle_payment_return для пользователя {update.effective_user.id}: {e}",
                parse_mode=ParseMode.HTML
            )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user = update.effective_user
        logger.info(f"User: {user.id} @{user.username}")

        add_user(user.id, user.username)

        if context.args and context.args[0].startswith('payment_'):
            await handle_payment_return(update, context)
            return

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
        SELECT subscription_end, trial_used, join_date, active FROM users WHERE user_id = ?
        ''', (user.id,))
        result = cursor.fetchone()
        conn.close()

        sub_type = 'none'
        days_left = 0
        end_date = None
        active = False

        now = datetime.now(MOSCOW_TZ)
        if result:
            subscription_end, trial_used, join_date, active = result
            if subscription_end:
                sub_end = datetime.strptime(subscription_end, '%Y-%m-%d %H:%M:%S').replace(tzinfo=MOSCOW_TZ)
                if sub_end > now and active:
                    sub_type = 'paid'
                    days_left = max(0, ceil((sub_end - now).total_seconds() / (24 * 3600)))
                    end_date = subscription_end
            if not trial_used:
                join = datetime.strptime(join_date, '%Y-%m-%d %H:%M:%S').replace(tzinfo=MOSCOW_TZ)
                trial_end = join + timedelta(days=TRIAL_DAYS)
                days_left = max(0, ceil((trial_end - now).total_seconds() / (24 * 3600)))
                if days_left >= 0:
                    sub_type = 'trial'
                    end_date = trial_end.strftime('%Y-%m-%d %H:%M:%S')
                    active = True

        payment_link, payment_id = await create_payment(user.id, context.bot.username)
        if not payment_link:
            await update.message.reply_text(
                "⚠️ Ошибка при создании платежа. Пожалуйста, попробуйте позже.",
                parse_mode=ParseMode.HTML
            )
            return

        welcome_text = (
            f"✨ <b>Добро пожаловать в Happy Face Club</b> ✨\n\n"
            f"🌿 Это место, где ты можешь быть собой.\n"
            f"Здесь вы найдёте простые, но мощные инструменты для улучшения самочувствия и красоты\n\n"
            f"💆‍♀️ Массаж и телесные практики\n"
            f"🥗 Вкусные и полезные рецепты\n"
            f"🫶 Поддержку комьюнити\n\n"
        )

        keyboard = [
            [InlineKeyboardButton("🔐 Перейти в группу", url=LINK_CLOSED_CHANNEL)],
            [InlineKeyboardButton("💬 Чат сообщества", url=CHAT_LINK)],
            [InlineKeyboardButton("💳 Оплатить/продлить подписку", url=payment_link)],
            [
                InlineKeyboardButton("🔍 Проверить подписку", callback_data="check"),
                InlineKeyboardButton("🔄 Вернуться в группу", callback_data="rejoin")
            ],
            [
                InlineKeyboardButton("💸 Статус платежа", callback_data="check_payment"),
                InlineKeyboardButton("❓ Помощь", callback_data="help")
            ]
        ]

        if sub_type in ['paid', 'trial']:
            invite_link = await generate_invite_link(context, user.id)
            if not invite_link:
                await update.message.reply_text("⚠️ Ошибка создания ссылки", parse_mode=ParseMode.HTML)
                return

            text = welcome_text
            if sub_type == 'paid':
                text += (
                    f"⭐️ <b>Ваша подписка активна</b>\n"
                    f"Тип: Платная\n"
                    f"Осталось дней: {days_left}\n"
                    f"Завершается: {datetime.strptime(end_date, '%Y-%m-%d %H:%M:%S').replace(tzinfo=MOSCOW_TZ).strftime('%d.%m.%Y')}\n\n"
                    f"Вы можете продлить подписку, оплатив еще один месяц.\n\n"
                )
            else:
                text += (
                    f"✨ <b>У тебя есть {days_left} дней бесплатного доступа</b> - почувствуй, как тебе здесь.\n\n"
                )

            text += (
                f"🔗 Ссылка в группу: {invite_link}\n"
                f"💬 Чат сообщества: {CHAT_LINK}\n\n"
                f"💳 {'Продлить подписку' if sub_type == 'paid' else 'Оплатить подписку'}: {SUBSCRIPTION_PRICE} руб/месяц"
            )

            keyboard[0][0] = InlineKeyboardButton("🔐 Перейти в группу", url=invite_link)

            await update.message.reply_text(
                text=text,
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(keyboard),
                disable_web_page_preview=True
            )
            return

        # Пользователь без активной подписки
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
        SELECT trial_used, join_date FROM users WHERE user_id = ?
        ''', (user.id,))
        result = cursor.fetchone()
        conn.close()

        if result and not result[0]:
            join = datetime.strptime(result[1], '%Y-%m-%d %H:%M:%S').replace(tzinfo=MOSCOW_TZ)
            trial_end = join + timedelta(days=TRIAL_DAYS)
            days_left = max(0, ceil((trial_end - now).total_seconds() / (24 * 3600)))
            if days_left >= 0:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute('''
                UPDATE users SET subscription_end = ?, active = 1
                WHERE user_id = ?
                ''', (trial_end.strftime('%Y-%m-%d %H:%M:%S'), user.id))
                conn.commit()
                conn.close()

                invite_link = await generate_invite_link(context, user.id)
                if not invite_link:
                    await update.message.reply_text("⚠️ Ошибка создания ссылки", parse_mode=ParseMode.HTML)
                    return

                text = welcome_text + (
                    f"✨ <b>У тебя есть {days_left} дней бесплатного доступа</b> - почувствуй, как тебе здесь.\n\n"
                    f"🔗 Ссылка в группу: {invite_link}\n"
                    f"💬 Чат сообщества: {CHAT_LINK}\n\n"
                    f"💳 После пробного периода: {SUBSCRIPTION_PRICE} руб/месяц"
                )

                keyboard[0][0] = InlineKeyboardButton("🔐 Перейти в группу", url=invite_link)

                await update.message.reply_text(
                    text=text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    disable_web_page_preview=True
                )
            else:
                text = welcome_text + (
                    f"🔒 Для доступа к материалам требуется подписка\n\n"
                    f"💳 Стоимость: {SUBSCRIPTION_PRICE} руб/месяц"
                )

                await update.message.reply_text(
                    text=text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    disable_web_page_preview=True
                )
        else:
            text = welcome_text + (
                f"🔒 Для доступа к материалам требуется подписка\n\n"
                f"💳 Стоимость: {SUBSCRIPTION_PRICE} руб/месяц"
            )

            await update.message.reply_text(
                text=text,
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(keyboard),
                disable_web_page_preview=True
            )

    except Exception as e:
        logger.error(f"Error in start for user {user.id}: {str(e)}")
        await update.message.reply_text(
            "⚠️ Произошла ошибка. Пожалуйста, попробуйте позже.",
            parse_mode=ParseMode.HTML
        )
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"⚠️ Ошибка в start для пользователя {user.id}: {e}",
            parse_mode=ParseMode.HTML
        )
        if FRIEND_ID:
            await context.bot.send_message(
                chat_id=FRIEND_ID,
                text=f"⚠️ Ошибка в start для пользователя {user.id}: {e}",
                parse_mode=ParseMode.HTML
            )

async def check_access(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        query = update.callback_query
        if query:
            user = query.from_user
            chat_id = query.message.chat_id
        else:
            user = update.effective_user
            chat_id = user.id

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
        SELECT subscription_end, trial_used, join_date, active FROM users WHERE user_id = ?
        ''', (user.id,))
        result = cursor.fetchone()
        conn.close()

        sub_type = 'none'
        days_left = 0
        end_date = None
        active = False

        now = datetime.now(MOSCOW_TZ)
        if result:
            subscription_end, trial_used, join_date, active = result
            if subscription_end:
                sub_end = datetime.strptime(subscription_end, '%Y-%m-%d %H:%M:%S').replace(tzinfo=MOSCOW_TZ)
                if sub_end > now and active:
                    sub_type = 'paid'
                    days_left = max(0, ceil((sub_end - now).total_seconds() / (24 * 3600)))
                    end_date = subscription_end
            if not trial_used:
                join = datetime.strptime(join_date, '%Y-%m-%d %H:%M:%S').replace(tzinfo=MOSCOW_TZ)
                trial_end = join + timedelta(days=TRIAL_DAYS)
                days_left = max(0, ceil((trial_end - now).total_seconds() / (24 * 3600)))
                if days_left >= 0:
                    sub_type = 'trial'
                    end_date = trial_end.strftime('%Y-%m-%d %H:%M:%S')
                    active = True

        if sub_type in ['paid', 'trial']:
            invite_link = await generate_invite_link(context, user.id)
            if not invite_link:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="⚠️ Ошибка создания ссылки",
                    parse_mode=ParseMode.HTML
                )
                return

            await context.bot.send_message(
                chat_id=chat_id,
                text=f"✅ <b>Ваша подписка активна</b>\n\n"
                     f"Тип: {'Платная' if sub_type == 'paid' else 'Пробный период'}\n"
                     f"Осталось дней: {days_left}\n"
                     f"Завершается: {datetime.strptime(end_date, '%Y-%m-%d %H:%M:%S').replace(tzinfo=MOSCOW_TZ).strftime('%d.%m.%Y')}\n\n"
                     f"🔗 Новая ссылка в группу: {invite_link}",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔐 Перейти в группу", url=invite_link)],
                    [
                        InlineKeyboardButton("💳 Продлить подписку", url=(await create_payment(user.id, context.bot.username))[0]),
                        InlineKeyboardButton("❓ Помощь", callback_data="help")
                    ]
                ])
            )
        else:
            payment_link, _ = await create_payment(user.id, context.bot.username)
            if payment_link:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"❌ <b>Ваша подписка истекла</b>\n\n"
                         f"Для продолжения доступа, пожалуйста, продлите подписку.\n"
                         f"💳 Стоимость: {SUBSCRIPTION_PRICE} руб/месяц",
                    parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("💳 Продлить подписку", url=payment_link)],
                        [InlineKeyboardButton("❓ Помощь", callback_data="help")]
                    ])
                )
            else:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="⚠️ Ошибка при создании платежа. Пожалуйста, попробуйте позже.",
                    parse_mode=ParseMode.HTML
                )
    except Exception as e:
        logger.error(f"Error in check_access for user {user.id}: {e}")
        await context.bot.send_message(
            chat_id=chat_id,
            text="⚠️ Произошла ошибка. Пожалуйста, попробуйте позже.",
            parse_mode=ParseMode.HTML
        )
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"⚠️ Ошибка в check_access для пользователя {user.id}: {e}",
            parse_mode=ParseMode.HTML
        )
        if FRIEND_ID:
            await context.bot.send_message(
                chat_id=FRIEND_ID,
                text=f"⚠️ Ошибка в check_access для пользователя {user.id}: {e}",
                parse_mode=ParseMode.HTML
            )

async def rejoin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        query = update.callback_query
        if query:
            user = query.from_user
            chat_id = query.message.chat_id
        else:
            user = update.effective_user
            chat_id = user.id

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
        SELECT subscription_end, trial_used, join_date, active
        FROM users
        WHERE user_id = ?
        ''', (user.id,))
        result = cursor.fetchone()
        conn.close()

        sub_type = 'none'
        days_left = 0
        end_date = None
        active = False

        now = datetime.now(MOSCOW_TZ)
        if result:
            subscription_end, trial_used, join_date, active = result
            if subscription_end:
                sub_end = datetime.strptime(subscription_end, '%Y-%m-%d %H:%M:%S').replace(tzinfo=MOSCOW_TZ)
                if sub_end > now and active:
                    sub_type = 'paid'
                    days_left = max(0, ceil((sub_end - now).total_seconds() / (24 * 3600)))
                    end_date = subscription_end
            if not trial_used:
                join = datetime.strptime(join_date, '%Y-%m-%d %H:%M:%S').replace(tzinfo=MOSCOW_TZ)
                trial_end = join + timedelta(days=TRIAL_DAYS)
                days_left = max(0, ceil((trial_end - now).total_seconds() / (24 * 3600)))
                if days_left >= 0:
                    sub_type = 'trial'
                    end_date = trial_end.strftime('%Y-%m-%d %H:%M:%S')
                    active = True

        if sub_type in ['paid', 'trial']:
            try:
                chat_member = await context.bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user.id)
                if chat_member.status in ['member', 'administrator', 'creator']:
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text="✅ Вы уже состоите в группе. Новая ссылка не требуется.",
                        parse_mode=ParseMode.HTML
                    )
                    return
            except Exception:
                pass

            invite_link = await generate_invite_link(context, user.id)
            if not invite_link:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="⚠️ Ошибка создания ссылки",
                    parse_mode=ParseMode.HTML
                )
                return

            await context.bot.send_message(
                chat_id=chat_id,
                text=f"✅ <b>Ваша подписка активна</b>\n\n"
                     f"Тип: {'Платная' if sub_type == 'paid' else 'Пробный период'}\n"
                     f"Осталось дней: {days_left}\n"
                     f"Завершается: {datetime.strptime(end_date, '%Y-%m-%d %H:%M:%S').replace(tzinfo=MOSCOW_TZ).strftime('%d.%m.%Y')}\n\n"
                     f"🔗 Новая ссылка в группу: {invite_link}",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔐 Перейти в группу", url=invite_link)],
                    [
                        InlineKeyboardButton("💳 Продлить подписку", url=(await create_payment(user.id, context.bot.username))[0]),
                        InlineKeyboardButton("❓ Помощь", callback_data="help")
                    ]
                ])
            )
        else:
            payment_link, _ = await create_payment(user.id, context.bot.username)
            if payment_link:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"❌ <b>Ваша подписка истекла</b>\n\n"
                         f"Для возвращения в группу, пожалуйста, продлите подписку.\n"
                         f"💳 Стоимость: {SUBSCRIPTION_PRICE} руб/месяц",
                    parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("💳 Продлить подписку", url=payment_link)],
                        [InlineKeyboardButton("❓ Помощь", callback_data="help")]
                    ])
                )
            else:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="⚠️ Ошибка при создании платежа. Пожалуйста, попробуйте позже.",
                    parse_mode=ParseMode.HTML
                )
    except Exception as e:
        logger.error(f"Error in rejoin for user {user.id}: {e}")
        await context.bot.send_message(
            chat_id=chat_id,
            text="⚠️ Произошла ошибка. Пожалуйста, попробуйте позже.",
            parse_mode=ParseMode.HTML
        )
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"⚠️ Ошибка в rejoin для пользователя {user.id}: {e}",
            parse_mode=ParseMode.HTML
        )
        if FRIEND_ID:
            await context.bot.send_message(
                chat_id=FRIEND_ID,
                text=f"⚠️ Ошибка в rejoin для пользователя {user.id}: {e}",
                parse_mode=ParseMode.HTML
            )

async def check_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        query = update.callback_query
        if query:
            user = query.from_user
            chat_id = query.message.chat_id
        else:
            user = update.effective_user
            chat_id = user.id

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
        SELECT payment_id, status FROM payments
        WHERE user_id = ?
        ORDER BY date DESC LIMIT 1
        ''', (user.id,))
        payment = cursor.fetchone()

        if payment:
            payment_id, status = payment
            if status == 'pending':
                await check_payment_status(payment_id, user.id, context)
                cursor.execute('''
                SELECT status FROM payments
                WHERE payment_id = ?
                ''', (payment_id,))
                status = cursor.fetchone()[0]

        conn.close()

        if payment:
            payment_id, _ = payment
            if status == 'succeeded':
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="✅ Ваш последний платеж успешно обработан. Используйте /check для получения новой ссылки в группу.",
                    parse_mode=ParseMode.HTML
                )
            elif status == 'pending':
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="⌛️ Ваш последний платеж еще не обработан. Пожалуйста, подождите или проверьте позже.",
                    parse_mode=ParseMode.HTML
                )
            else:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"❌ Ваш последний платеж имеет статус: {status}. Пожалуйста, свяжитесь с поддержкой.",
                    parse_mode=ParseMode.HTML
                )
        else:
            await context.bot.send_message(
                chat_id=chat_id,
                text="⚠️ Платежи не найдены. Начните процесс оплаты заново с /start.",
                parse_mode=ParseMode.HTML
            )
    except Exception as e:
        logger.error(f"Error in check_payment for user {user.id}: {e}")
        await context.bot.send_message(
            chat_id=chat_id,
            text="⚠️ Произошла ошибка. Пожалуйста, попробуйте позже.",
            parse_mode=ParseMode.HTML
        )
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"⚠️ Ошибка в check_payment для пользователя {user.id}: {e}",
            parse_mode=ParseMode.HTML
        )
        if FRIEND_ID:
            await context.bot.send_message(
                chat_id=FRIEND_ID,
                text=f"⚠️ Ошибка в check_payment для пользователя {user.id}: {e}",
                parse_mode=ParseMode.HTML
            )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        query = update.callback_query
        if query:
            chat_id = query.message.chat_id
        else:
            chat_id = update.effective_user.id

        text = (
            "📚 <b>Команды бота HappyFaceClub</b>\n\n"
            "ℹ️ Используйте команды ниже для управления подпиской и доступом к группе:\n"
            "/start - Начать работу и получить доступ к группе\n"
            "/check - Проверить статус подписки\n"
            "/rejoin - Получить новую ссылку в группу, если вы вышли\n"
            "/check_payment - Проверить статус последнего платежа\n"
            "/help - Показать это сообщение с командами\n"
        )
        if update.effective_user.id in [ADMIN_ID, FRIEND_ID]:
            text += (
                "/admin - Открыть меню администратора для управления ботом\n"
                "   ℹ️ В меню админа используйте кнопки для действий, например, просмотр активных пользователей.\n"
            )

        await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logger.error(f"Error in help_command: {e}")
        await context.bot.send_message(
            chat_id=chat_id,
            text="⚠️ Произошла ошибка. Пожалуйста, попробуйте позже.",
            parse_mode=ParseMode.HTML
        )
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"⚠️ Ошибка в help_command: {e}",
            parse_mode=ParseMode.HTML
        )
        if FRIEND_ID:
            await context.bot.send_message(
                chat_id=FRIEND_ID,
                text=f"⚠️ Ошибка в help_command: {e}",
                parse_mode=ParseMode.HTML
            )

async def admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.effective_user.id
        if user_id not in [ADMIN_ID, FRIEND_ID]:
            await update.message.reply_text("⚠️ Доступ запрещён!", parse_mode=ParseMode.HTML)
            return

        keyboard = [
            [InlineKeyboardButton("📋 Список зарегистрированных пользователей", callback_data="remove_inactive")]
        ]
        await update.message.reply_text(
            "🔧 <b>Меню администратора</b>\n\n"
            "ℹ️ Используйте кнопки ниже для управления ботом. Для проверки статуса задач или логов обратитесь к серверу.\n\n"
            "Выберите действие:",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except Exception as e:
        logger.error(f"Error in admin_menu for user {user_id}: {e}")
        await update.message.reply_text(
            "⚠️ Произошла ошибка. Пожалуйста, попробуйте позже.",
            parse_mode=ParseMode.HTML
        )
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"⚠️ Ошибка в admin_menu для пользователя {user_id}: {e}",
            parse_mode=ParseMode.HTML
        )
        if FRIEND_ID:
            await context.bot.send_message(
                chat_id=FRIEND_ID,
                text=f"⚠️ Ошибка в admin_menu для пользователя {user_id}: {e}",
                parse_mode=ParseMode.HTML
            )

async def remove_inactive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.effective_user.id
        if user_id not in [ADMIN_ID, FRIEND_ID]:
            await update.message.reply_text("⚠️ Доступ запрещён!", parse_mode=ParseMode.HTML)
            return

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
        SELECT user_id, username FROM users WHERE active = 1
        ''')
        active_users = cursor.fetchall()
        conn.close()

        if not active_users:
            await update.message.reply_text(
                "ℹ️ Нет активных пользователей в базе данных.",
                parse_mode=ParseMode.HTML
            )
            return

        user_list = "\n".join(
            f"👤 ID: {user[0]}, Username: @{user[1] or 'без имени'}"
            for user in active_users
        )
        await update.message.reply_text(
            f"📋 <b>Активные пользователи ({len(active_users)}):</b>\n\n"
            f"{user_list}\n\n"
            f"ℹ️ Telegram не позволяет ботам видеть участников приватной группы. "
            f"Пожалуйста, проверьте участников группы вручную в настройках Telegram и сравните с этим списком.",
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logger.error(f"Error in remove_inactive: {e}")
        await update.message.reply_text(
            "⚠️ Произошла ошибка. Пожалуйста, попробуйте позже.",
            parse_mode=ParseMode.HTML
        )
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"⚠️ Ошибка в remove_inactive: {e}",
            parse_mode=ParseMode.HTML
        )
        if FRIEND_ID:
            await context.bot.send_message(
                chat_id=FRIEND_ID,
                text=f"⚠️ Ошибка в remove_inactive: {e}",
                parse_mode=ParseMode.HTML
            )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        query = update.callback_query
        await query.answer()

        if query.data == "check":
            await check_access(update, context)
        elif query.data == "rejoin":
            await rejoin(update, context)
        elif query.data == "check_payment":
            await check_payment(update, context)
        elif query.data == "help":
            await help_command(update, context)
        elif query.data == "remove_inactive":
            user_id = query.from_user.id
            if user_id not in [ADMIN_ID, FRIEND_ID]:
                await query.message.reply_text("⚠️ Доступ запрещён!", parse_mode=ParseMode.HTML)
                return

            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('''
            SELECT user_id, username FROM users WHERE active = 1
            ''')
            active_users = cursor.fetchall()
            conn.close()

            if not active_users:
                await query.message.reply_text(
                    "ℹ️ Нет активных пользователей в базе данных.",
                    parse_mode=ParseMode.HTML
                )
                return

            user_list = "\n".join(
                f"👤 ID: {user[0]}, Username: @{user[1] or 'без имени'}"
                for user in active_users
            )
            await query.message.reply_text(
                f"📋 <b>Активные пользователи ({len(active_users)}):</b>\n\n"
                f"{user_list}\n\n"
                f"ℹ️ Telegram не позволяет ботам видеть участников приватной группы. "
                f"Пожалуйста, проверьте участников группы вручную в настройках Telegram и сравните с этим списком.",
                parse_mode=ParseMode.HTML
            )
        else:
            await query.message.reply_text(
                "⚠️ Неизвестная команда. Пожалуйста, используйте кнопки из меню.",
                parse_mode=ParseMode.HTML
            )
    except Exception as e:
        logger.error(f"Error in button_callback: {e}")
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="⚠️ Произошла ошибка при обработке кнопки. Пожалуйста, попробуйте позже.",
            parse_mode=ParseMode.HTML
        )
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"⚠️ Ошибка в button_callback для пользователя {query.from_user.id}: {e}",
            parse_mode=ParseMode.HTML
        )
        if FRIEND_ID:
            await context.bot.send_message(
                chat_id=FRIEND_ID,
                text=f"⚠️ Ошибка в button_callback для пользователя {query.from_user.id}: {e}",
                parse_mode=ParseMode.HTML
            )

async def check_subscriptions(context: ContextTypes.DEFAULT_TYPE):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT user_id, username, subscription_end, trial_used, join_date, active FROM users WHERE active = 1')
        users = cursor.fetchall()

        now = datetime.now(MOSCOW_TZ)
        for user_id, username, subscription_end, trial_used, join_date, active in users:
            end_date = None
            days_left = None
            if subscription_end:
                end_date = datetime.strptime(subscription_end, '%Y-%m-%d %H:%M:%S').replace(tzinfo=MOSCOW_TZ)
                days_left = max(0, ceil((end_date - now).total_seconds() / (24 * 3600)))
            elif not trial_used:
                join = datetime.strptime(join_date, '%Y-%m-%d %H:%M:%S').replace(tzinfo=MOSCOW_TZ)
                trial_end = join + timedelta(days=TRIAL_DAYS)
                days_left = max(0, ceil((trial_end - now).total_seconds() / (24 * 3600)))
                end_date = trial_end

            if days_left is not None and days_left >= 0:
                if days_left in [1, 3]:
                    payment_link, _ = await create_payment(user_id, context.bot.username)
                    if payment_link:
                        try:
                            await context.bot.send_message(
                                chat_id=user_id,
                                text=f"⚠️ <b>Ваша подписка заканчивается через {days_left} день(дня)!</b>\n\n"
                                     f"Пожалуйста, продлите подписку, чтобы продолжить доступ в группе.\n"
                                     f"💳 Стоимость: {SUBSCRIPTION_PRICE} руб/месяц",
                                parse_mode=ParseMode.HTML,
                                reply_markup=InlineKeyboardMarkup([
                                    [InlineKeyboardButton("💳 Продлить подписку", url=payment_link)]
                                ])
                            )
                        except TelegramError as e:
                            if "chat not found" in str(e).lower():
                                logger.info(f"Skipping subscription reminder for user {user_id}: Chat not found")
                            else:
                                logger.error(f"Error sending subscription reminder to user {user_id}: {e}")
                                await context.bot.send_message(
                                    chat_id=ADMIN_ID,
                                    text=f"⚠️ Ошибка отправки напоминания пользователю {user_id}: {e}",
                                    parse_mode=ParseMode.HTML
                                )
                                if FRIEND_ID:
                                    await context.bot.send_message(
                                        chat_id=FRIEND_ID,
                                        text=f"⚠️ Ошибка отправки напоминания пользователю {user_id}: {e}",
                                        parse_mode=ParseMode.HTML
                                    )
            if end_date and end_date < now and active:
                # Обновляем статус в базе перед попыткой исключения
                cursor.execute('UPDATE users SET active = 0 WHERE user_id = ?', (user_id,))
                conn.commit()
                logger.info(f"User {user_id} (@{username or 'без имени'}) marked as inactive in database")

                try:
                    await context.bot.ban_chat_member(
                        chat_id=CHANNEL_ID,
                        user_id=user_id
                    )
                    logger.info(f"User {user_id} (@{username or 'без имени'}) removed from group due to expired subscription")
                    await context.bot.send_message(
                        chat_id=ADMIN_ID,
                        text=f"✅ Пользователь {user_id} (@{username or 'без имени'}) удалён из группы из-за истёкшей подписки",
                        parse_mode=ParseMode.HTML
                    )
                    if FRIEND_ID:
                        await context.bot.send_message(
                            chat_id=FRIEND_ID,
                            text=f"✅ Пользователь {user_id} (@{username or 'без имени'}) удалён из группы из-за истёкшей подписки",
                            parse_mode=ParseMode.HTML
                        )
                except TelegramError as e:
                    if "participant_id_invalid" in str(e).lower():
                        logger.info(f"User {user_id} (@{username or 'без имени'}) not in group, skipping ban")
                    else:
                        logger.error(f"Error banning user {user_id}: {e}")
                        await context.bot.send_message(
                            chat_id=ADMIN_ID,
                            text=f"⚠️ Ошибка при удалении пользователя {user_id} (@{username or 'без имени'}): {e}",
                            parse_mode=ParseMode.HTML
                        )
                        if FRIEND_ID:
                            await context.bot.send_message(
                                chat_id=FRIEND_ID,
                                text=f"⚠️ Ошибка при удалении пользователя {user_id} (@{username or 'без имени'}): {e}",
                                parse_mode=ParseMode.HTML
                            )

                payment_link, _ = await create_payment(user_id, context.bot.username)
                if payment_link:
                    try:
                        await context.bot.send_message(
                            chat_id=user_id,
                            text=f"❌ <b>Ваша подписка истекла</b>\n\n"
                                 f"Вы были исключены из группы HappyFaceClub.\n"
                                 f"Для продолжения доступа, пожалуйста, продлите подписку.\n"
                                 f"💳 Стоимость: {SUBSCRIPTION_PRICE} руб/месяц",
                            parse_mode=ParseMode.HTML,
                            reply_markup=InlineKeyboardMarkup([
                                [InlineKeyboardButton("💳 Продлить подписку", url=payment_link)]
                            ])
                        )
                    except TelegramError as e:
                        if "chat not found" in str(e).lower():
                            logger.info(f"Skipping expiration notification for user {user_id} (@{username or 'без имени'}): Chat not found")
                        else:
                            logger.error(f"Error notifying user {user_id} about expiration: {e}")
                            await context.bot.send_message(
                                chat_id=ADMIN_ID,
                                text=f"⚠️ Ошибка уведомления пользователя {user_id} (@{username or 'без имени'}) об истечении подписки: {e}",
                                parse_mode=ParseMode.HTML
                            )
                            if FRIEND_ID:
                                await context.bot.send_message(
                                    chat_id=FRIEND_ID,
                                    text=f"⚠️ Ошибка уведомления пользователя {user_id} (@{username or 'без имени'}) об истечении подписки: {e}",
                                    parse_mode=ParseMode.HTML
                                )
        conn.close()
    except Exception as e:
        logger.error(f"Error in check_subscriptions: {e}")
        if 'conn' in locals():
            conn.close()
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"⚠️ Ошибка в check_subscriptions: {e}",
            parse_mode=ParseMode.HTML
        )
        if FRIEND_ID:
            await context.bot.send_message(
                chat_id=FRIEND_ID,
                text=f"⚠️ Ошибка в check_subscriptions: {e}",
                parse_mode=ParseMode.HTML
            )

async def handle_chat_member_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        chat_member_update = update.chat_member
        if not chat_member_update:
            return

        user = chat_member_update.from_user
        chat = chat_member_update.chat
        new_status = chat_member_update.new_chat_member.status
        old_status = chat_member_update.old_chat_member.status

        # Проверяем, что пользователь только что вступил в канал
        if new_status in ['member', 'administrator', 'creator'] and old_status in ['left', 'kicked']:
            # Проверяем, что событие произошло в нужном канале
            if str(chat.id) != str(CHANNEL_ID):
                logger.info(f"User {user.id} joined chat {chat.id}, but it's not the target channel {CHANNEL_ID}")
                return

            # Проверяем статус подписки
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('''
            SELECT subscription_end, trial_used, join_date, active FROM users WHERE user_id = ?
            ''', (user.id,))
            result = cursor.fetchone()
            conn.close()

            sub_type = 'none'
            days_left = 0
            end_date = None
            active = False
            now = datetime.now(MOSCOW_TZ)

            if result:
                subscription_end, trial_used, join_date, active = result
                if subscription_end:
                    sub_end = datetime.strptime(subscription_end, '%Y-%m-%d %H:%M:%S').replace(tzinfo=MOSCOW_TZ)
                    if sub_end > now and active:
                        sub_type = 'paid'
                        days_left = max(0, ceil((sub_end - now).total_seconds() / (24 * 3600)))
                        end_date = subscription_end
                if not trial_used:
                    join = datetime.strptime(join_date, '%Y-%m-%d %H:%M:%S').replace(tzinfo=MOSCOW_TZ)
                    trial_end = join + timedelta(days=TRIAL_DAYS)
                    days_left = max(0, ceil((trial_end - now).total_seconds() / (24 * 3600)))
                    if days_left >= 0:
                        sub_type = 'trial'
                        end_date = trial_end.strftime('%Y-%m-%d %H:%M:%S')
                        active = True

            if sub_type not in ['paid', 'trial']:
                logger.info(f"User {user.id} (@{user.username or 'без имени'}) attempted to join without active subscription")
                try:
                    await context.bot.ban_chat_member(chat_id=chat.id, user_id=user.id)
                    await context.bot.send_message(
                        chat_id=user.id,
                        text="❌ У вас нет активной подписки. Пожалуйста, оформите подписку с помощью /start.",
                        parse_mode=ParseMode.HTML
                    )
                except TelegramError as e:
                    logger.error(f"Error banning or notifying user {user.id}: {e}")
                return

            # Отправляем приветственное сообщение
            welcome_text = (
                "Добро пожаловать в Happy Face Club! 🌿\n\n"
                "Рада знать, что ты хочешь позаботиться о своём теле и душе✨\n"
                "Ты присоединилась только что, и поэтому пока не видишь контента — это нормально!\n"
                "Контент в клубе виден только с момента твоего вступления, всё, что было раньше — остаётся закрытым.\n\n"
                "Но не переживай: каждый день мы добавляем новые практики, и ты скоро всё увидишь и почувствуешь!\n\n"
                f"Тип подписки: {'Платная' if sub_type == 'paid' else 'Пробный период'}\n"
                f"Осталось дней: {days_left}\n"
                f"Завершается: {datetime.strptime(end_date, '%Y-%m-%d %H:%M:%S').replace(tzinfo=MOSCOW_TZ).strftime('%d.%m.%Y')}\n\n"
                f"Если возникнут вопросы, ты можешь задать их в нашем чате: {CHAT_LINK}\n\n"
                "С любовью ДАША HAPPY FACE ❤️"
            )
            try:
                await context.bot.send_message(
                    chat_id=user.id,
                    text=welcome_text,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True
                )
                logger.info(f"Sent welcome message to user {user.id} (@{user.username or 'без имени'}) upon joining channel {CHANNEL_ID}")
            except TelegramError as e:
                logger.error(f"Error sending welcome message to user {user.id}: {e}")
                await context.bot.send_message(
                    chat_id=ADMIN_ID,
                    text=f"⚠️ Ошибка при отправке приветственного сообщения пользователю {user.id} (@{user.username or 'без имени'}): {e}",
                    parse_mode=ParseMode.HTML
                )
                if FRIEND_ID:
                    await context.bot.send_message(
                        chat_id=FRIEND_ID,
                        text=f"⚠️ Ошибка при отправке приветственного сообщения пользователю {user.id} (@{user.username or 'без имени'}): {e}",
                        parse_mode=ParseMode.HTML
                    )

    except Exception as e:
        logger.error(f"Error in handle_chat_member_update for user {user.id}: {e}")
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"⚠️ Ошибка в handle_chat_member_update для пользователя {user.id}: {e}",
            parse_mode=ParseMode.HTML
        )
        if FRIEND_ID:
            await context.bot.send_message(
                chat_id=FRIEND_ID,
                text=f"⚠️ Ошибка в handle_chat_member_update для пользователя {user.id}: {e}",
                parse_mode=ParseMode.HTML
            )      

# Закомментированная функция notify_users на случай, если она понадобится в будущем
"""
async def notify_users(context: ContextTypes.DEFAULT_TYPE):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT user_id FROM users')
        users = cursor.fetchall()
        conn.close()
        sent_count = 0
        for user_id in users:
            try:
                await context.bot.get_chat(chat_id=user_id[0])
                await context.bot.send_message(
                    chat_id=user_id[0],
                    text="🎉 Бот @HappyFaceChat_bot запущен! Напишите /start, чтобы получить 5 дней пробного доступа!",
                    parse_mode=ParseMode.HTML
                )
                logger.info(f"Notification sent to user {user_id[0]}")
                sent_count += 1
                await asyncio.sleep(0.1)
            except TelegramError as e:
                if "chat not found" in str(e).lower():
                    logger.info(f"Skipping notification for user {user_id[0]}: Chat not found")
                else:
                    logger.error(f"Error notifying user {user_id[0]}: {e}")
                    await context.bot.send_message(
                        chat_id=ADMIN_ID,
                        text=f"⚠️ Ошибка уведомления пользователю {user_id[0]}: {e}",
                        parse_mode=ParseMode.HTML
                    )
                    if FRIEND_ID:
                        await context.bot.send_message(
                            chat_id=FRIEND_ID,
                            text=f"⚠️ Ошибка уведомления пользователю {user_id[0]}: {e}",
                            parse_mode=ParseMode.HTML
                        )
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"✅ Уведомления отправлены {sent_count} пользователям!",
            parse_mode=ParseMode.HTML
        )
        if FRIEND_ID:
            await context.bot.send_message(
                chat_id=FRIEND_ID,
                text=f"✅ Уведомления отправлены {sent_count} пользователям!",
                parse_mode=ParseMode.HTML
            )
    except Exception as e:
        logger.error(f"Error in notify_users: {e}")
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"⚠️ Ошибка в notify_users: {e}",
            parse_mode=ParseMode.HTML
        )
        if FRIEND_ID:
            await context.bot.send_message(
                chat_id=FRIEND_ID,
                text=f"⚠️ Ошибка в notify_users: {e}",
                parse_mode=ParseMode.HTML
            )
"""


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error: {context.error}")
    if isinstance(context.error, telegram.error.Conflict):
        logger.error("Conflict error: Another instance of the bot is running. Stopping this instance.")
        try:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text="⚠️ Обнаружен конфликт: другой экземпляр бота уже запущен. Останавливаю текущий экземпляр.",
                parse_mode=ParseMode.HTML
            )
            if FRIEND_ID:
                await context.bot.send_message(
                    chat_id=FRIEND_ID,
                    text="⚠️ Обнаружен конфликт: другой экземпляр бота уже запущен. Останавливаю текущий экземпляр.",
                    parse_mode=ParseMode.HTML
                )
        except TelegramError as e:
            logger.error(f"Failed to send conflict notification: {e}")
        raise SystemExit("Stopping bot due to Conflict error")

def main():
    try:
        application = Application.builder().token(TOKEN).build()
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("check", check_access))
        application.add_handler(CommandHandler("rejoin", rejoin))
        application.add_handler(CommandHandler("check_payment", check_payment))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("admin", admin_menu))
        application.add_handler(CommandHandler("remove_inactive", remove_inactive))
        application.add_handler(CallbackQueryHandler(button_callback))
        application.add_handler(ChatMemberHandler(handle_chat_member_update, ChatMemberHandler.MY_CHAT_MEMBER))
        application.add_error_handler(error_handler)

        application.job_queue.run_repeating(check_subscriptions, interval=86400, first=10)

        logger.info("Bot started and ready to accept payments")
        # Настройка Webhook
        application.run_webhook(
            listen="0.0.0.0",
            port=8443,
            url_path="/webhook",
            webhook_url="https://HappyFaceBot.pythonanywhere.com/webhook"
        )
    except Exception as e:
        logger.error(f"Error starting bot: {e}")
        try:
            bot = telegram.Bot(token=TOKEN)
            bot.send_message(
                chat_id=ADMIN_ID,
                text=f"⚠️ Ошибка запуска бота: {str(e)}",
                parse_mode=ParseMode.HTML
            )
            if FRIEND_ID:
                bot.send_message(
                    chat_id=FRIEND_ID,
                    text=f"⚠️ Ошибка запуска бота: {str(e)}",
                    parse_mode=ParseMode.HTML
                )
        except Exception as send_error:
            logger.error(f"Failed to send error message: {send_error}")

if __name__ == "__main__":
    main()