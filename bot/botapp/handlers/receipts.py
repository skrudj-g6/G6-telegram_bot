import io

from aiogram import F, Router
from aiogram.types import Message

from botapp import keyboards
from botapp.api import BackendClient

router = Router(name="receipts")

MAX_BYTES = 10 * 1024 * 1024
ALLOWED_DOCUMENT_TYPES = {"image/jpeg", "image/png", "application/pdf"}


@router.message(F.photo | F.document)
async def receipt(message: Message, api: BackendClient):
    """Чек (фото или PDF) прикрепляется к заявке, ожидающей чек. Диалоговое состояние не нужно:
    чек можно прислать в любой момент, пока заявка не закрылась по времени."""
    tg = message.from_user.id
    if message.photo:
        file = message.photo[-1]  # самый крупный размер, Telegram отдаёт JPEG
    else:
        file = message.document
        if file.mime_type not in ALLOWED_DOCUMENT_TYPES:
            await message.answer("Отправьте чек фото или файлом PDF (JPEG, PNG, PDF).")
            return
    if file.file_size and file.file_size > MAX_BYTES:
        await message.answer("Файл больше 10 МБ. Отправьте файл поменьше.")
        return

    awaiting = next(
        (d for d in await api.list_deposits(tg) if d["status"] == "awaiting_receipt"), None
    )
    if awaiting is None:
        await message.answer(
            "Сейчас нет заявки, ожидающей чек. Создайте заявку в разделе «💰 Пополнение».",
            reply_markup=keyboards.main_menu(),
        )
        return

    buffer = io.BytesIO()
    await message.bot.download(file, destination=buffer)
    await api.upload_receipt(tg, awaiting["id"], buffer.getvalue())
    await message.answer(
        f"📨 Чек получен. Заявка №{awaiting['id']} передана оператору. "
        "Статус смотрите в «📋 Мои заявки».",
        reply_markup=keyboards.main_menu(),
    )
