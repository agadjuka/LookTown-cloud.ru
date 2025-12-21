import asyncio
import os
import sys
import json
from dotenv import load_dotenv
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg_pool import AsyncConnectionPool

# --- Настройка для Windows ---
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

load_dotenv()

# --- Твой ID ---
THREAD_ID = "261617302" 

# --- Подключение ---
DB_URI = os.getenv("DATABASE_URL")
if not DB_URI:
    host = os.getenv("PG_HOST", "localhost")
    user = os.getenv("PG_USER", "postgres")
    passw = os.getenv("PG_PASSWORD", "")
    db = os.getenv("PG_DB", "ai_db")
    port = os.getenv("PG_PORT", "5432")
    DB_URI = f"postgresql://{user}:{passw}@{host}:{port}/{db}"

class Colors:
    USER = '\033[94m'      # Синий
    AI = '\033[92m'        # Зеленый
    TOOL_CALL = '\033[93m' # Желтый
    TOOL_RES = '\033[96m'  # Голубой
    SYSTEM = '\033[90m'    # Серый
    RESET = '\033[0m'
    BOLD = '\033[1m'
    RED = '\033[91m'

async def print_history():
    print(f"🔌 Подключаюсь к базе данных для потока {Colors.BOLD}{THREAD_ID}{Colors.RESET}...")
    
    async with AsyncConnectionPool(conninfo=DB_URI) as pool:
        checkpointer = AsyncPostgresSaver(pool)
        
        # Получаем сырой чекпоинт (это словарь)
        config = {"configurable": {"thread_id": THREAD_ID}}
        checkpoint = await checkpointer.aget(config)
        
        if not checkpoint:
            print(f"{Colors.RED}❌ История пуста или thread_id неверен.{Colors.RESET}")
            return

        # ВАЖНО: Данные лежат в ключе 'channel_values'
        # Если его нет, пробуем искать в корне (зависит от версии), но обычно это channel_values
        values = checkpoint.get("channel_values", checkpoint)
        messages = values.get("messages", [])
        
        print(f"\n📚 {Colors.BOLD}ИСТОРИЯ СООБЩЕНИЙ ({len(messages)} шт):{Colors.RESET}")
        print("="*60)
        
        for i, msg in enumerate(messages):
            # Определяем тип сообщения. У LangChain объектов это .type, у словарей ['type']
            msg_type = getattr(msg, 'type', 'unknown')
            content = getattr(msg, 'content', '')
            
            # --- 1. USER ---
            if msg_type == "human":
                print(f"\n[{i}] {Colors.USER}👤 USER:{Colors.RESET}")
                print(f"    {content}")

            # --- 2. AI (Ответы + Вызовы) ---
            elif msg_type == "ai":
                print(f"\n[{i}] {Colors.AI}🤖 AI:{Colors.RESET}")
                if content:
                    print(f"    {content}")
                
                # Проверяем tool_calls
                tool_calls = getattr(msg, 'tool_calls', [])
                if tool_calls:
                    for tc in tool_calls:
                        print(f"    {Colors.TOOL_CALL}🔨 CALL TOOL: {tc.get('name')}{Colors.RESET}")
                        print(f"       Args: {json.dumps(tc.get('args'), ensure_ascii=False)}")
                        print(f"       ID: {tc.get('id')}")

            # --- 3. TOOL RESULT (Важно!) ---
            elif msg_type == "tool":
                print(f"\n[{i}] {Colors.TOOL_RES}⚙️ TOOL RESULT ({getattr(msg, 'name', 'unknown')}):{Colors.RESET}")
                print(f"    Linked to Call ID: {getattr(msg, 'tool_call_id', 'N/A')}")
                
                content_str = str(content)
                if len(content_str) > 300:
                    content_str = content_str[:300] + "..."
                print(f"    Data: {content_str}")

            # --- 4. SYSTEM ---
            elif msg_type == "system":
                print(f"\n[{i}] {Colors.SYSTEM}💻 SYSTEM:{Colors.RESET}")
                print(f"    {content[:100]}...")

            else:
                print(f"\n[{i}] ❓ UNKNOWN ({msg_type}): {content[:50]}...")

        print("\n" + "="*60)
        
        # Переменные состояния
        print(f"{Colors.BOLD}📦 ТЕКУЩЕЕ СОСТОЯНИЕ (STATE):{Colors.RESET}")
        for key, val in values.items():
            if key != "messages":
                val_str = str(val)
                if len(val_str) > 100: val_str = val_str[:100] + "..."
                print(f"   • {key}: {val_str}")

if __name__ == "__main__":
    try:
        asyncio.run(print_history())
    except Exception as e:
        print(f"❌ Критическая ошибка скрипта: {e}")
        import traceback
        traceback.print_exc()