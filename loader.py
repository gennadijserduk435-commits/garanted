from aiogram import Bot, Dispatcher, types
from config import API_TOKEN

bot = Bot(token=API_TOKEN)
dp = Dispatcher()
user_data = {} 

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