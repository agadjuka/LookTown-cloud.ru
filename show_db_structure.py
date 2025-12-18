"""Скрипт для получения структуры базы данных PostgreSQL"""
import os
import sys
from dotenv import load_dotenv
import psycopg2

# Загружаем переменные окружения
load_dotenv()

print("=" * 80)
print("СТРУКТУРА БАЗЫ ДАННЫХ PostgreSQL")
print("=" * 80)

database_url = os.getenv("DATABASE_URL")
if not database_url:
    print("\n❌ ОШИБКА: DATABASE_URL не найден в .env файле")
    sys.exit(1)

try:
    conn = psycopg2.connect(database_url)
    cursor = conn.cursor()
    
    # Получаем список всех таблиц
    cursor.execute("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public'
        ORDER BY table_name;
    """)
    tables = cursor.fetchall()
    
    print(f"\n📋 Найдено таблиц: {len(tables)}\n")
    
    for table in tables:
        table_name = table[0]
        print("=" * 80)
        print(f"📊 ТАБЛИЦА: {table_name}")
        print("=" * 80)
        
        # Получаем структуру таблицы
        cursor.execute("""
            SELECT 
                column_name,
                data_type,
                character_maximum_length,
                is_nullable,
                column_default
            FROM information_schema.columns
            WHERE table_schema = 'public' 
            AND table_name = %s
            ORDER BY ordinal_position;
        """, (table_name,))
        
        columns = cursor.fetchall()
        
        print(f"\n{'Колонка':<30} {'Тип':<20} {'Nullable':<10} {'Default':<30}")
        print("-" * 80)
        
        for col in columns:
            col_name = col[0]
            data_type = col[1]
            max_length = col[2]
            is_nullable = col[3]
            default = col[4] if col[4] else ""
            
            # Формируем строку типа с длиной
            if max_length:
                type_str = f"{data_type}({max_length})"
            else:
                type_str = data_type
            
            print(f"{col_name:<30} {type_str:<20} {is_nullable:<10} {default:<30}")
        
        # Получаем PRIMARY KEY
        cursor.execute("""
            SELECT a.attname
            FROM pg_index i
            JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
            WHERE i.indrelid = %s::regclass
            AND i.indisprimary;
        """, (f'public.{table_name}',))
        
        pk_cols = cursor.fetchall()
        if pk_cols:
            pk_names = [col[0] for col in pk_cols]
            print(f"\n🔑 PRIMARY KEY: {', '.join(pk_names)}")
        
        # Получаем FOREIGN KEYS
        cursor.execute("""
            SELECT
                kcu.column_name,
                ccu.table_name AS foreign_table_name,
                ccu.column_name AS foreign_column_name
            FROM information_schema.table_constraints AS tc
            JOIN information_schema.key_column_usage AS kcu
                ON tc.constraint_name = kcu.constraint_name
                AND tc.table_schema = kcu.table_schema
            JOIN information_schema.constraint_column_usage AS ccu
                ON ccu.constraint_name = tc.constraint_name
                AND ccu.table_schema = tc.table_schema
            WHERE tc.constraint_type = 'FOREIGN KEY'
            AND tc.table_name = %s;
        """, (table_name,))
        
        fk_cols = cursor.fetchall()
        if fk_cols:
            print(f"\n🔗 FOREIGN KEYS:")
            for fk in fk_cols:
                print(f"   {fk[0]} -> {fk[1]}.{fk[2]}")
        
        # Получаем количество записей
        cursor.execute(f"SELECT COUNT(*) FROM {table_name};")
        count = cursor.fetchone()[0]
        print(f"\n📊 Количество записей: {count}")
        
        # Если есть записи, покажем пример строки
        if count > 0:
            cursor.execute(f"SELECT * FROM {table_name} LIMIT 1;")
            sample = cursor.fetchone()
            col_names = [desc[0] for desc in cursor.description]
            
            print(f"\n📄 Пример записи:")
            for i, col_name in enumerate(col_names):
                value = sample[i]
                if value and len(str(value)) > 50:
                    value = str(value)[:50] + "..."
                print(f"   {col_name}: {value}")
        
        print("\n")
    
    cursor.close()
    conn.close()
    
    print("=" * 80)
    print("✅ СТРУКТУРА БАЗЫ ДАННЫХ ПОЛУЧЕНА")
    print("=" * 80)

except Exception as e:
    print(f"\n❌ ОШИБКА: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
