import os
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ParseMode
from telegram.error import TimedOut
from service_factory import get_agent_service
from src.services.logger_service import logger
from src.services.date_normalizer import normalize_dates_in_text
from src.services.time_normalizer import normalize_times_in_text
from src.services.link_converter import convert_yclients_links_in_text
from src.services.text_formatter import convert_bold_markdown_to_html
from src.services.retry_service import RetryService
from src.services.call_manager_service import CallManagerException
from src.services.escalation_service import EscalationService
from src.handlers.voice_utils import extract_message_text

load_dotenv()

TELEGRAM_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

async def send_to_agent(message_text, chat_id):
    """Отправка сообщения агенту через LangGraph с retry на нижнем уровне"""
    async def _execute_agent_request():
        """Внутренняя функция для выполнения запроса к агенту"""
        logger.agent("Обработка сообщения", chat_id)
        agent_service = get_agent_service()
        response = await agent_service.send_to_agent(chat_id, message_text)
        logger.agent("Ответ получен", chat_id)
        return response
    
    try:
        # Используем RetryService для retry на нижнем уровне (async версия)
        response = await RetryService.execute_with_retry_async(
            operation=_execute_agent_request,
            max_retries=3,
            operation_name="отправка сообщения агенту",
            context_info={
                "chat_id": chat_id,
                "message": message_text
            }
        )
        return response
    except CallManagerException as e:
        # Обрабатываем вызов CallManager - возвращаем результат эскалации
        logger.info("CallManager был вызван из-за критической ошибки")
        return e.escalation_result
    except Exception as e:
        logger.error("Ошибка при обращении к агенту", str(e))
        return {"user_message": f"Ошибка при обращении к агенту: {str(e)}"}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    chat_id = str(update.effective_chat.id)
    logger.telegram("Команда /start", chat_id)
    await update.message.reply_text('Добрый день!\nНа связи менеджер LOOKTOWN 🌻\n\nЧем я могу вам помочь?')

async def new_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /new - сброс контекста"""
    chat_id = str(update.effective_chat.id)
    logger.telegram("Команда /new", chat_id)
    try:
        agent_service = get_agent_service()
        await agent_service.reset_context(chat_id)
        logger.success("Контекст сброшен", chat_id)
        await update.message.reply_text('Контекст сброшен. Начинаем новый диалог!')
    except Exception as e:
        logger.error("Ошибка при сбросе контекста", str(e))
        await update.message.reply_text(f'Ошибка при сбросе контекста: {str(e)}')

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых и голосовых сообщений"""
    chat_id = str(update.effective_chat.id)
    user_id = update.effective_user.id
    
    # Извлекаем текст из сообщения (текстового или голосового)
    user_message, error_message, is_voice = await extract_message_text(
        update=update,
        bot=context.bot,
        chat_id=chat_id
    )
    
    # Если была ошибка при обработке голосового сообщения
    if error_message:
        await update.message.reply_text(error_message)
        return
    
    # Проверка, что у нас есть текст для обработки
    if not user_message:
        logger.warning("Получено сообщение без текста", chat_id)
        return
    
    # Пытаемся показать индикатор печати, но не критично, если не получится
    try:
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    except TimedOut:
        logger.warning("Таймаут при отправке send_chat_action, продолжаем обработку", chat_id)
    except Exception as e:
        logger.warning(f"Ошибка при отправке send_chat_action: {e}, продолжаем обработку", chat_id)
    
    agent_response = await send_to_agent(user_message, chat_id)
    # Ожидаем словарь: {"user_message": str, "manager_alert": Optional[str]}
    user_message_text = agent_response.get("user_message") if isinstance(agent_response, dict) else str(agent_response)
    
    # Проверяем на эскалацию [CALL_MANAGER] перед отправкой в Telegram
    if user_message_text and user_message_text.strip().startswith('[CALL_MANAGER]'):
        escalation_service = EscalationService()
        escalation_result = escalation_service.handle(user_message_text, chat_id)
        user_message_text = escalation_result.get("user_message", user_message_text)
        # Обновляем agent_response с результатом эскалации
        agent_response = {
            "user_message": user_message_text,
            "manager_alert": escalation_result.get("manager_alert")
        }
    
    # Нормализуем даты и время в ответе
    user_message_text = normalize_dates_in_text(user_message_text)
    user_message_text = normalize_times_in_text(user_message_text)
    # Преобразуем ссылки yclients.com в HTML-гиперссылки
    user_message_text = convert_yclients_links_in_text(user_message_text)
    # Заменяем Markdown жирный текст (**текст**) на HTML теги (<b>текст</b>)
    user_message_text = convert_bold_markdown_to_html(user_message_text)
    await update.message.reply_text(user_message_text, parse_mode=ParseMode.HTML)

    # Обработка уведомления CallManager
    if isinstance(agent_response, dict) and agent_response.get("manager_alert"):
        manager_alert = normalize_dates_in_text(agent_response["manager_alert"])
        manager_alert = normalize_times_in_text(manager_alert)
        manager_alert = convert_yclients_links_in_text(manager_alert)
        manager_alert = convert_bold_markdown_to_html(manager_alert)
        
        # Если админ-панель не настроена, используем старый метод
        try:
            await update.message.reply_text(manager_alert, parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.warning(f"Ошибка при отправке manager_alert с HTML: {e}, отправляю без форматирования")
            await update.message.reply_text(manager_alert, parse_mode=None)
    
    logger.telegram("Ответ отправлен", chat_id)

async def set_bot_commands(bot) -> None:
    """Устанавливает команды бота для разных групп пользователей."""
    try:
        from telegram import BotCommand
        try:
            from telegram import BotCommandScopeChat, BotCommandScopeDefault
        except ImportError:
            try:
                from telegram.constants import BotCommandScopeChat, BotCommandScopeDefault
            except ImportError:
                from telegram.helpers import BotCommandScopeChat, BotCommandScopeDefault
        
        default_commands = [BotCommand("new", "Сбросить историю переписки")]
        await bot.set_my_commands(commands=default_commands, scope=BotCommandScopeDefault())
        
    except Exception as e:
        logger.error("Ошибка при установке команд бота: %s", str(e), exc_info=True)

def main():
    """Основная функция запуска бота"""
    logger.info("🚀 Запуск бота с LangGraph")
    
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("new", new_chat))
    
    application.add_handler(MessageHandler((filters.TEXT | filters.VOICE) & ~filters.COMMAND, handle_message))
    
    # Устанавливаем команды бота после инициализации
    async def post_init(app: Application) -> None:
        await set_bot_commands(app.bot)
    
    application.post_init = post_init
    
    logger.success("✅ Бот запущен и готов к работе")
    application.run_polling()

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем")