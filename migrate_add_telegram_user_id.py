"""Миграция: добавление telegram_user_id в таблицу conversations"""
import os
import sys
from dotenv import load_dotenv
import psycopg2

load_dotenv()

print("=" * 80)
print("МИГРАЦИЯ: Добавление telegram_user_id в conversations")
print("=" * 80)

database_url = os.getenv("DATABASE_URL")
if not database_url:
    print("\n❌ ОШИБКА: DATABASE_URL не найден")
    sys.exit(1)

try:
    conn = psycopg2.connect(database_url)
    cursor = conn.cursor()
    
    print("\n1️⃣ Проверка наличия колонки telegram_user_id...")
    cursor.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = 'conversations' 
        AND column_name = 'telegram_user_id';
    """)
    
    if cursor.fetchone():
        print("✅ Колонка telegram_user_id уже существует")
    else:
        print("⏳ Добавление колонки telegram_user_id...")
        
        # Добавляем колонку
        cursor.execute("""
            ALTER TABLE conversations 
            ADD COLUMN telegram_user_id BIGINT;
        """)
        
        print("✅ Колонка telegram_user_id добавлена")
    
    print("\n2️⃣ Проверка UNIQUE constraint на telegram_user_id...")
    cursor.execute("""
        SELECT constraint_name 
        FROM information_schema.table_constraints 
        WHERE table_name = 'conversations' 
        AND constraint_type = 'UNIQUE'
        AND constraint_name LIKE '%telegram_user_id%';
    """)
    
    if cursor.fetchone():
        print("✅ UNIQUE constraint уже существует")
    else:
        print("⏳ Добавление UNIQUE constraint...")
        
        cursor.execute("""
            ALTER TABLE conversations 
            ADD CONSTRAINT conversations_telegram_user_id_key 
            UNIQUE (telegram_user_id);
        """)
        
        print("✅ UNIQUE constraint добавлен")
    
    print("\n3️⃣ Создание индекса для быстрого поиска...")
    cursor.execute("""
        SELECT indexname 
        FROM pg_indexes 
        WHERE tablename = 'conversations' 
        AND indexname = 'idx_conversations_telegram_user_id';
    """)
    
    if cursor.fetchone():
        print("✅ Индекс уже существует")
    else:
        cursor.execute("""
            CREATE INDEX idx_conversations_telegram_user_id 
            ON conversations(telegram_user_id);
        """)
        
        print("✅ Индекс создан")
    
    # Сохраняем изменения
    conn.commit()
    
    print("\n4️⃣ Проверка финальной структуры таблицы conversations:")
    cursor.execute("""
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_name = 'conversations'
        ORDER BY ordinal_position;
    """)
    
    columns = cursor.fetchall()
    print(f"\n{'Колонка':<30} {'Тип':<20} {'Nullable':<10}")
    print("-" * 60)
    for col in columns:
        print(f"{col[0]:<30} {col[1]:<20} {col[2]:<10}")
    
    cursor.close()
    conn.close()
    
    print("\n" + "=" * 80)
    print("✅ МИГРАЦИЯ ЗАВЕРШЕНА УСПЕШНО!")
    print("=" * 80)

except Exception as e:
    print(f"\n❌ ОШИБКА: {e}")
    import traceback
    traceback.print_exc()
    if conn:
        conn.rollback()
    sys.exit(1)
