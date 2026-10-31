import asyncio
import os

from aiogram import Bot, Dispatcher

from handlers import deposit, registration, start, withdraw, profile

# Токен только из окружения. Прежний токен был в git-истории и считается скомпрометированным.
TOKEN = os.environ["BOT_TOKEN"]

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