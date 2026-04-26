import asyncio
from aiogram import Bot, Dispatcher

from handlers import deposit, registration, start, withdraw, profile

TOKEN = "8341289452:AAFwp03zCUUB_g_BsCfoBahsJoKQIwSoBjE"

bot = Bot(token=TOKEN)
dp = Dispatcher()

dp.include_router(start.router)
dp.include_router(registration.router)
dp.include_router(deposit.router)
dp.include_router(withdraw.router)
dp.include_router(profile.router)

async def main():
    print("Бот запущен")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())