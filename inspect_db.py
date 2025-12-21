import asyncio
import os
import sys
from dotenv import load_dotenv
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg_pool import AsyncConnectionPool

# Фикс для Windows
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

load_dotenv()

# Твой ID из логов
THREAD_ID = "261617302" 

DB_URI = os.getenv("DATABASE_URL")
if not DB_URI:
    # Сборка URI если нет одной строки
    host = os.getenv("PG_HOST", "localhost")
    user = os.getenv("PG_USER", "postgres")
    passw = os.getenv("PG_PASSWORD", "")
    db = os.getenv("PG_DB", "ai_db")
    port = os.getenv("PG_PORT", "5432")
    DB_URI = f"postgresql://{user}:{passw}@{host}:{port}/{db}"

async def inspect_memory():
    print(f"🔌 Подключаюсь к БД для проверки потока {THREAD_ID}...")
    
    async with AsyncConnectionPool(conninfo=DB_URI) as pool:
        checkpointer = AsyncPostgresSaver(pool)
        
        # Загружаем последнее состояние
        config = {"configurable": {"thread_id": THREAD_ID}}
        state_snapshot = await checkpointer.aget(config)
        
        if not state_snapshot:
            print("❌ Состояние не найдено! (Возможно, неверный thread_id или база пуста)")
            return

        print("\n📂 --- СОДЕРЖИМОЕ ПАМЯТИ (SNAPSHOT) ---")
        if isinstance(state_snapshot, dict):
            print(f"Created At: {state_snapshot.get('created_at', 'N/A')}")
            values = state_snapshot.get("values", {})
        else:
            print(f"Created At: {state_snapshot.created_at}")
            values = state_snapshot.values
        messages = values.get("messages", [])
        
        print(f"\n📨 Сообщения в истории (всего {len(messages)}):")
        print("-" * 50)
        
        found_tool = False
        found_ai = False
        
        for i, msg in enumerate(messages):
            m_type = msg.type
            content = str(msg.content)[:100].replace('\n', ' ')
            
            print(f"[{i}] {m_type.upper()}: {content}...")
            
            if m_type == "tool": found_tool = True
            if m_type == "ai": found_ai = True
            
        print("-" * 50)
        
        if not found_tool:
            print("\n⚠️ ВНИМАНИЕ: В памяти НЕТ сообщений от инструментов (ToolMessage)!")
            print("   Это подтверждает, что результаты инструментов теряются.")
            
        if not found_ai:
            print("\n⚠️ ВНИМАНИЕ: В памяти НЕТ ответов ассистента (AIMessage)!")
            print("   Это подтверждает, что бот помнит только вопросы юзера, но не свои ответы.")

        print(f"\n📦 Другие переменные состояния: {list(values.keys())}")
        if "service_id" in values:
            print(f"   service_id: {values['service_id']}")

if __name__ == "__main__":
    asyncio.run(inspect_memory())