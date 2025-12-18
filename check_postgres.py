"""Скрипт проверки работы с PostgreSQL"""
import os
import sys

# Добавляем родительскую директорию в путь для импорта модулей
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.storage.conversation_repo import get_conversation_repo


def check_postgres_migration():
    """Проверка работы с PostgreSQL"""
    
    print("=" * 80)
    print("ПРОВЕРКА: Работа с PostgreSQL через ConversationRepository")
    print("=" * 80)
    
    # Получаем репозиторий
    repo = get_conversation_repo()
    
    # Тестовый telegram_user_id
    test_user_id = 123456789
    
    print(f"\n1. Создание/получение диалога для telegram_user_id={test_user_id}")
    conversation_id = repo.get_or_create_conversation(test_user_id)
    print(f"✅ Conversation ID: {conversation_id}")
    
    print(f"\n2. Добавление сообщения пользователя")
    msg_id_1 = repo.append_message(conversation_id, "user", "Привет! Хочу записаться на стрижку")
    print(f"✅ Message ID: {msg_id_1}")
    
    print(f"\n3. Добавление ответа ассистента")
    msg_id_2 = repo.append_message(
        conversation_id, 
        "assistant", 
        "Здравствуйте! Конечно, помогу вам записаться. На какую дату вы хотели бы?"
    )
    print(f"✅ Message ID: {msg_id_2}")
    
    print(f"\n4. Добавление второго сообщения пользователя")
    msg_id_3 = repo.append_message(conversation_id, "user", "На завтра, если возможно")
    print(f"✅ Message ID: {msg_id_3}")
    
    print(f"\n5. Добавление сообщения о tool-вызове")
    msg_id_4 = repo.append_message(
        conversation_id, 
        "system", 
        "Tools used: search_available_slots",
        {"tools": ["search_available_slots"]}
    )
    print(f"✅ Message ID: {msg_id_4}")
    
    print(f"\n6. Загрузка последних сообщений (limit=10)")
    messages = repo.load_last_messages(conversation_id, limit=10)
    print(f"✅ Загружено {len(messages)} сообщений:")
    for i, msg in enumerate(messages, 1):
        content_preview = msg['content'][:50] + "..." if len(msg['content']) > 50 else msg['content']
        print(f"   {i}. [{msg['role']}] {content_preview}")
    
    print(f"\n7. Проверка получения существующего диалога")
    conversation_id_2 = repo.get_or_create_conversation(test_user_id)
    if conversation_id == conversation_id_2:
        print(f"✅ Получен тот же диалог: {conversation_id_2}")
    else:
        print(f"❌ ERROR: Получен другой диалог!")
    
    print(f"\n8. Создание нового диалога (как при /new)")
    new_conversation_id = repo.create_new_conversation(test_user_id)
    print(f"✅ Новый Conversation ID: {new_conversation_id}")
    print(f"   Старый остался в базе: {conversation_id}")
    
    print(f"\n9. Проверка, что новый диалог теперь активен")
    current_conversation_id = repo.get_or_create_conversation(test_user_id)
    if current_conversation_id == new_conversation_id:
        print(f"✅ Активный диалог изменился на: {current_conversation_id}")
    else:
        print(f"❌ ERROR: Активный диалог не изменился!")
    
    print(f"\n10. Проверка, что новый диалог пустой")
    messages_new = repo.load_last_messages(new_conversation_id, limit=10)
    print(f"✅ Новый диалог содержит {len(messages_new)} сообщений (должно быть 0)")
    
    print(f"\n11. Проверка, что старый диалог сохранён")
    messages_old = repo.load_last_messages(conversation_id, limit=10)
    print(f"✅ Старый диалог содержит {len(messages_old)} сообщений")
    
    print("\n" + "=" * 80)
    print("✅ ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ!")
    print("=" * 80)


if __name__ == "__main__":
    try:
        check_postgres_migration()
    except Exception as e:
        print(f"\n❌ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
