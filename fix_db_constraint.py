"""Миграция: Удаление UNIQUE constraint для telegram_user_id"""
import os
import sys
from dotenv import load_dotenv
import psycopg2

load_dotenv()

print("=" * 80)
print("ИСПРАВЛЕНИЕ БАЗЫ ДАННЫХ: Разрешение множества диалогов")
print("=" * 80)

database_url = os.getenv("DATABASE_URL")
if not database_url:
    print("\n❌ ОШИБКА: DATABASE_URL не найден")
    sys.exit(1)

try:
    conn = psycopg2.connect(database_url)
    cursor = conn.cursor()
    
    print("\n1️⃣ Удаление UNIQUE ограничения...")
    
    # Проверяем имя ограничения
    cursor.execute("""
        SELECT constraint_name 
        FROM information_schema.table_constraints 
        WHERE table_name = 'conversations' 
        AND constraint_type = 'UNIQUE'
        AND constraint_name = 'conversations_telegram_user_id_key';
    """)
    
    if cursor.fetchone():
        cursor.execute("""
            ALTER TABLE conversations 
            DROP CONSTRAINT conversations_telegram_user_id_key;
        """)
        print("✅ Ограничение UNIQUE удалено. Теперь можно создавать новые диалоги.")
    else:
        print("⚠️ Ограничение не найдено (возможно, уже удалено).")
    
    # Сохраняем изменения
    conn.commit()
    
    cursor.close()
    conn.close()
    
    print("\n" + "=" * 80)
    print("✅ ГОТОВО! Попробуйте команду /new снова.")
    print("=" * 80)

except Exception as e:
    print(f"\n❌ ОШИБКА: {e}")
    sys.exit(1)
