# Миграция на PostgreSQL

## Обзор изменений

Реализована миграция с YDB/previous_response_id на PostgreSQL для хранения истории диалогов.

## Новая архитектура

### Таблицы PostgreSQL

1. **`public.conversations`** - хранит диалоги
   - `id` (UUID) - идентификатор диалога
   - `telegram_user_id` (BIGINT) - ID пользователя в Telegram
   - `created_at` (TIMESTAMPTZ) - время создания

2. **`public.messages`** - хранит сообщения
   - `id` (BIGSERIAL) - идентификатор сообщения
   - `conversation_id` (UUID) - FK на conversations
   - `role` (TEXT) - роль: 'user', 'assistant', 'tool', 'system'
   - `content` (TEXT) - содержимое сообщения
   - `metadata` (JSONB) - дополнительные метаданные (опционально)
   - `created_at` (TIMESTAMPTZ) - время создания

### Новые модули

- **`src/storage/pg_client.py`** - клиент для подключения к PostgreSQL
- **`src/storage/conversation_repo.py`** - репозиторий для работы с диалогами

### Изменённые файлы

- **`src/services/yandex_agent_service.py`**:
  - Добавлено сохранение входящих сообщений пользователя
  - Добавлена загрузка истории последних 30 сообщений
  - Добавлено сохранение ответов ассистента
  - Обновлена логика сброса контекста (`/new`)

- **`requirements.txt`**:
  - Добавлена зависимость `psycopg2-binary`

## Конфигурация

Необходимо добавить переменные окружения в `.env`:

```env
# PostgreSQL Configuration
PG_HOST=localhost
PG_PORT=5432
PG_DB=ai_db
PG_USER=postgres
PG_PASSWORD=your_password

# Альтернатива - можно использовать DATABASE_URL
# DATABASE_URL=postgresql://user:password@host:port/database
```

## Логика работы

### При получении сообщения:
1. Получаем `telegram_user_id` из `chat_id`
2. Получаем/создаём `conversation_id` через `get_or_create_conversation(telegram_user_id)`
3. Сохраняем входящее сообщение: `append_message(conversation_id, "user", text)`
4. Загружаем последние 30 сообщений: `load_last_messages(conversation_id, limit=30)`
5. Отправляем запрос в LLM (пока через `previous_response_id` для Responses API)
6. Сохраняем ответ: `append_message(conversation_id, "assistant", answer)`
7. Сохраняем информацию о tool-вызовах (если были)

### При команде /new:
1. Создаём новый диалог: `create_new_conversation(telegram_user_id)`
2. Старый диалог остаётся в базе (не удаляется)
3. Сбрасываем `previous_response_id` в YDB (для совместимости с Responses API)

### Сохранение tool-вызовов:
- Информация о tool-вызовах сохраняется как сообщение с `role='system'`
- Формат: `"Tools used: tool1, tool2, ..."`
- Metadata хранит список инструментов: `{"tools": ["tool1", "tool2"]}`

## Совместимость с Responses API

**Важно**: На данный момент Responses API всё ещё управляет своей внутренней историей через `previous_response_id`. 

PostgreSQL используется для:
- Прозрачного хранения всех сообщений
- Возможности анализа диалогов
- Будущей миграции на полное управление историей через messages-массив

## Проверка работы

Запустите тестовый скрипт:

```bash
python check_postgres.py
```

Скрипт проверяет:
- Создание/получение диалога
- Добавление сообщений разных типов (user/assistant/system)
- Загрузку последних N сообщений
- Создание нового диалога при /new
- Сохранение старых диалогов

## Удалённая функциональность YDB

### Что осталось (для совместимости):
- `ydb_client.get_last_response_id()` - для Responses API
- `ydb_client.save_response_id()` - для Responses API
- `ydb_client.reset_context()` - для Responses API

### Что можно удалить в будущем:
После полной миграции на управление историей через Postgres:
- Вся логика `previous_response_id`
- Таблица `chat_threads` в YDB
- Зависимость от YDB для хранения контекста

## План дальнейшей миграции

1. **Этап 1** (текущий): ✅ Дублирование истории в Postgres
2. **Этап 2**: Переключение на отправку истории через `messages` вместо `previous_response_id`
3. **Этап 3**: Полное удаление зависимости от YDB для управления контекстом
4. **Этап 4**: Оптимизация формирования контекста (summarization, выбор важных сообщений)

## Примечания

- История ограничена последними 30 сообщениями для предотвращения раздувания контекста
- Каждый `conversation_id` привязан к одному `telegram_user_id` (личные чаты)
- При `/new` старые диалоги не удаляются, а создаётся новый
- Tool результаты сохраняются кратко, без избыточной информации
