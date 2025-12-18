"""Скрипт проверки подключения к PostgreSQL"""
import os
import sys
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

print("=" * 80)
print("ПРОВЕРКА ПОДКЛЮЧЕНИЯ К PostgreSQL")
print("=" * 80)

# Проверяем наличие DATABASE_URL
database_url = os.getenv("DATABASE_URL")
if not database_url:
    print("\n❌ ОШИБКА: DATABASE_URL не найден в .env файле")
    sys.exit(1)

print(f"\n✅ DATABASE_URL найден: {database_url[:30]}...{database_url[-10:]}")

# Проверяем установку psycopg2
try:
    import psycopg2
    print("✅ psycopg2 установлен")
except ImportError:
    print("\n❌ ОШИБКА: psycopg2 не установлен")
    print("   Установите: python -m pip install psycopg2-binary")
    sys.exit(1)

# Пытаемся подключиться
print("\n⏳ Попытка подключения к базе данных...")

try:
    conn = psycopg2.connect(database_url)
    print("✅ Подключение успешно!")
    
    # Пытаемся выполнить простой запрос
    cursor = conn.cursor()
    cursor.execute("SELECT version();")
    db_version = cursor.fetchone()
    print(f"\n📊 Версия PostgreSQL: {db_version[0][:50]}...")
    
    # Проверяем наличие таблиц
    cursor.execute("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public'
        ORDER BY table_name;
    """)
    tables = cursor.fetchall()
    
    print(f"\n📋 Найдено таблиц в схеме public: {len(tables)}")
    for table in tables:
        print(f"   - {table[0]}")
    
    # Проверяем таблицы conversations и messages
    required_tables = ['conversations', 'messages']
    found_tables = [t[0] for t in tables]
    
    print(f"\n🔍 Проверка необходимых таблиц:")
    for table in required_tables:
        if table in found_tables:
            # Получаем количество записей
            cursor.execute(f"SELECT COUNT(*) FROM {table};")
            count = cursor.fetchone()[0]
            print(f"   ✅ {table}: {count} записей")
        else:
            print(f"   ❌ {table}: ОТСУТСТВУЕТ")
    
    # Закрываем соединение
    cursor.close()
    conn.close()
    
    print("\n" + "=" * 80)
    print("✅ ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ! База данных готова к работе.")
    print("=" * 80)

except psycopg2.OperationalError as e:
    print(f"\n❌ ОШИБКА ПОДКЛЮЧЕНИЯ: {e}")
    print("\nВозможные причины:")
    print("   1. Неверные учётные данные (user/password)")
    print("   2. Неверный хост или порт")
    print("   3. База данных не запущена")
    print("   4. Файрвол блокирует подключение")
    sys.exit(1)

except psycopg2.Error as e:
    print(f"\n❌ ОШИБКА БД: {e}")
    sys.exit(1)

except Exception as e:
    print(f"\n❌ НЕОЖИДАННАЯ ОШИБКА: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
