# Документация по стадиям LangGraph

## Общая архитектура

Проект использует двухуровневую архитектуру графов LangGraph:

1. **MainGraph** (`src/graph/main_graph.py`) - основной граф для маршрутизации между различными типами диалогов
2. **BookingGraph** (`src/graph/booking/graph.py`) - подграф для обработки процесса бронирования

---

## 1. Основной граф (MainGraph)

### Структура графа

```
START → detect_stage → [условный роутинг] → [обработчики стадий] → END
```

### Узлы MainGraph

#### 1.1. `detect_stage` (Определение стадии)
- **Тип**: Silent Node (не добавляет messages в историю)
- **Агент**: `StageDetectorAgent`
- **Функция**: Анализирует последнее сообщение пользователя и историю диалога, определяет, к какой стадии относится запрос
- **Особенности**:
  - Фильтрует историю: удаляет tool сообщения, ограничивает до 10 последних сообщений
  - Может вызвать CallManager (эскалация к менеджеру)
  - Если CallManager вызван, граф завершается с ответом менеджера

#### 1.2. Условный роутинг (`_route_after_detect`)
После определения стадии происходит маршрутизация на соответствующий обработчик:

- `booking` → `handle_booking`
- `cancellation_request` → `handle_cancellation_request`
- `reschedule` → `handle_reschedule`
- `view_my_booking` → `handle_view_my_booking`
- `about_salon` → `handle_about_salon`
- `end` → END (если CallManager был вызван)

---

## 2. Стадии диалога (DialogueStage)

Определены в `src/agents/dialogue_stages.py`:

### 2.1. `booking` - Бронирование услуги
- **Агент**: `BookingAgent`
- **Обработчик**: `handle_booking`
- **Особенности**: Использует подграф `BookingGraph` для многоэтапного процесса бронирования
- **Когда выбирается**: Основной агент, выбирается когда другие агенты не подходят, или когда клиент хочет забронировать услугу/узнать об услугах

### 2.2. `cancellation_request` - Запрос на отмену записи
- **Агент**: `CancelBookingAgent`
- **Обработчик**: `handle_cancellation_request`
- **Инструменты**: `CancelBooking`, `GetClientRecords`, `CallManager`
- **Когда выбирается**: Клиент просит отменить существующую запись
- **Логика**:
  1. Проверяет историю - если уже предлагали перенос, не предлагает снова
  2. Если клиент настаивает на отмене, находит запись через `GetClientRecords`
  3. Отменяет через `CancelBooking`
  4. Подтверждает отмену

### 2.3. `reschedule` - Перенос записи
- **Агент**: `RescheduleAgent`
- **Обработчик**: `handle_reschedule`
- **Инструменты**: `FindSlots`, `GetClientRecords`, `RescheduleBooking`, `CallManager`
- **Когда выбирается**: Клиент просит перенести запись на другое время/дату, говорит что опаздывает
- **Логика** (4 шага):
  1. Определяет запись для переноса (уточняет телефон, использует `GetClientRecords`)
  2. Уточняет новое время (если клиент не указал дату, спрашивает)
  3. Пытается перенести через `RescheduleBooking`
  4. Если мастер занят - использует `FindSlots` для предложения альтернативных слотов

### 2.4. `view_my_booking` - Просмотр своих записей
- **Агент**: `ViewMyBookingAgent`
- **Обработчик**: `handle_view_my_booking`
- **Инструменты**: `GetClientRecords`, `CallManager`
- **Когда выбирается**: Клиент хочет посмотреть свои записи ("на когда я записан?", "какие у меня записи?")
- **Логика**: Уточняет телефон (если не знает), использует `GetClientRecords`, показывает список записей

### 2.5. `about_salon` - Информация о салоне
- **Агент**: `AboutSalonAgent`
- **Обработчик**: `handle_about_salon`
- **Инструменты**: Нет (только текстовая информация)
- **Когда выбирается**: Клиент спрашивает про адреса, контакты, телефоны, соцсети салона ("расскажите про салон", "где вы находитесь", "как с вами связаться")
- **Важно**: НЕ про услуги, только про салон

---

## 3. Граф бронирования (BookingGraph)

### Структура графа

```
START → analyzer → [условный роутинг] → [узлы обработки] → END
```

### Состояние графа (BookingGraphState)

Состоит из двух частей:
- `booking`: `BookingSubState` - состояние бронирования
- `conversation`: `ConversationState` - состояние диалога (включая messages)

### Поля BookingSubState

- `service_id`: ID услуги (int)
- `service_name`: Название услуги (str)
- `master_id`: ID мастера (int)
- `master_name`: Имя мастера (str)
- `slot_time`: Время слота в формате "YYYY-MM-DD HH:MM" (str)
- `slot_time_verified`: Флаг проверки доступности времени (bool)
- `client_name`: Имя клиента (str)
- `client_phone`: Телефон клиента (str)
- `is_finalized`: Флаг завершения бронирования (bool)
- `service_details_needed`: Флаг необходимости ответа на вопрос об услуге (bool)

### Узлы BookingGraph

#### 3.1. `analyzer` (Анализатор)
- **Функция**: Извлекает сущности из текста пользователя
- **Извлекает**: service_id/service_name, master_id/master_name, slot_time, client_name, client_phone
- **Особенности**:
  - Использует LLM для извлечения данных в JSON формате
  - Обрабатывает смену темы (если клиент меняет услугу, сбрасывает service_id, master_id, slot_time в null)
  - Если время 00:00 - обрабатывает как дату без времени
  - Может установить `service_details_needed: true` если клиент хочет узнать детали об услуге

#### 3.2. `service_manager` (Менеджер услуг)
- **Когда запускается**:
  - Если `service_id` отсутствует (None)
  - Если `service_details_needed = True` (приоритет 1 - консультация)
- **Инструменты**: `GetCategories`, `FindService`, `ViewService`, `Masters`, `CallManager`
- **Функция**: Помогает клиенту выбрать услугу
- **Логика**:
  - Если клиент просто хочет забронировать - вызывает `GetCategories`
  - Если клиент указал услугу - использует `FindService`
  - Если клиент спрашивает про услугу - использует `ViewService`
  - Если клиент спрашивает про мастеров - использует `Masters`
  - Может вернуть JSON с `service_id` когда услуга выбрана
  - Сбрасывает `service_details_needed` после ответа

#### 3.3. `slot_manager` (Менеджер слотов)
- **Когда запускается**:
  - Если `slot_time` отсутствует (None) - ищет и предлагает слоты
  - Если `slot_time` указан, но `slot_time_verified = False` - проверяет доступность времени
- **Инструменты**: `FindSlots`, `CallManager`
- **Функция**: Ищет доступные временные слоты или проверяет доступность указанного времени
- **Логика**:
  - Если время указано, но не проверено - проверяет через `find_slots_by_period`
  - Если время доступно - устанавливает `slot_time_verified = True`
  - Если время недоступно - сбрасывает `slot_time` и сообщает клиенту
  - Если времени нет - ищет слоты через `FindSlots` с учетом пожеланий клиента
  - Может вернуть JSON с `slot_time` когда клиент выбрал слот

#### 3.4. `contact_collector` (Сборщик контактов)
- **Когда запускается**: Если `service_id` и `slot_time` есть, но отсутствует `client_name` или `client_phone`
- **Инструменты**: `CallManager`
- **Функция**: Собирает имя и телефон клиента
- **Логика**:
  - Просит клиента указать имя и телефон
  - Может извлечь данные из ответа через JSON парсинг
  - Если JSON найден - не отправляет сообщение клиенту (процесс продолжается автоматически)

#### 3.5. `finalizer` (Финализатор)
- **Когда запускается**: Когда все данные собраны (service_id, slot_time, client_name, client_phone)
- **Инструменты**: `CreateBooking`, `CallManager`
- **Функция**: Создает запись через `CreateBooking`
- **Логика**:
  - Проверяет наличие всех обязательных данных
  - Вызывает `CreateBooking` с собранными данными
  - Устанавливает `is_finalized = True` после успешного создания
  - Подтверждает бронирование клиенту

---

## 4. Логика роутинга в BookingGraph

### 4.1. Роутинг после `analyzer` (`route_booking`)

Проверки выполняются в строгом порядке:

1. **Если `is_finalized = True`** → END (процесс завершен)

2. **Если `answer` не пустой** → END (нужно отправить сообщение клиенту и ждать ответа)

3. **ПРИОРИТЕТ 1 (Консультация)**: Если `service_details_needed = True` → `service_manager` (всегда, независимо от других полей)

4. **ПРИОРИТЕТ 2 (Стандартная воронка)**: Если `service_id is None` → `service_manager`

5. **Если `slot_time is None`** → `slot_manager` (поиск слотов)

6. **Если `slot_time` есть, но `slot_time_verified is False/None`** → `slot_manager` (проверка доступности)

7. **Если нет контактов** (`client_name` или `client_phone`) → `contact_collector`

8. **Иначе** (все данные есть) → `finalizer`

### 4.2. Роутинг после `slot_manager` (`route_after_slot_manager`)

- **Если `slot_time_verified = True`**:
  - Если нет контактов → `contact_collector`
  - Если контакты есть → `finalizer`
- **Иначе** → END (предложили слоты или время недоступно - уже написали сообщение)

### 4.3. Роутинг после `service_manager` и `contact_collector`

Используется `route_booking`:
- Если `answer` пустой → продолжается по логике `route_booking`
- Если `answer` не пустой → END (отправляем сообщение клиенту)

### 4.4. Роутинг после `finalizer`

Всегда → END (только finalizer завершает граф)

---

## 5. Особенности работы с состоянием

### 5.1. Сохранение состояния

- **MainGraph**: Использует `checkpointer` для сохранения `ConversationState` в PostgreSQL
- **BookingGraph**: Использует тот же `checkpointer` для сохранения `BookingGraphState` (booking + conversation)
- **Thread ID**: Используется `chat_id` (telegram_user_id) как `thread_id` для изоляции состояний разных пользователей

### 5.2. Обновление состояния

- **Критические поля** (`service_id`, `slot_time`, `master_id`, `master_name`, `slot_time_verified`): Обновляются только если значение явно указано (даже если None - для сброса)
- **Некритические поля**: Обновляются только если значение не None и не пустое
- **Смена темы**: Если клиент меняет услугу/мастера, критические поля сбрасываются в None

### 5.3. Адаптеры состояний

Используются адаптеры (`_create_booking_state_adapter`) для преобразования между:
- `BookingSubState` ↔ `ConversationState`
- Это позволяет узлам работать с `ConversationState`, а графу - с `BookingSubState`

---

## 6. Обработка ошибок и эскалация

### 6.1. CallManager

Все узлы и агенты могут вызвать `CallManager` для эскалации к менеджеру в случаях:
- Системная ошибка
- Неизвестный ответ на вопрос
- Недовольство клиента
- Технические ошибки API (например, 429 - слишком много запросов)

### 6.2. Поведение при вызове CallManager

- Если CallManager вызван в `detect_stage` → граф завершается с ответом менеджера
- Если CallManager вызван в других узлах → возвращается ответ с `manager_alert` и граф завершается

---

## 7. Потоки данных

### 7.1. Основной поток (MainGraph)

```
Пользователь → detect_stage → определение стадии → обработчик стадии → ответ пользователю
```

### 7.2. Поток бронирования (BookingGraph)

```
Пользователь → analyzer → извлечение данных → 
  → service_manager (если нет service_id) → выбор услуги →
  → slot_manager (если нет slot_time) → выбор времени →
  → contact_collector (если нет контактов) → сбор контактов →
  → finalizer → создание записи → завершение
```

### 7.3. Возможные циклы

- **service_manager ↔ slot_manager**: Если клиент меняет услугу после выбора времени
- **slot_manager → contact_collector/finalizer**: После проверки времени
- **contact_collector → finalizer**: После сбора контактов

---

## 8. Важные замечания

### 8.1. Silent Nodes

- `detect_stage` - не добавляет промежуточные сообщения в историю (только для маршрутизации)
- `analyzer` - не добавляет сообщения в историю (только обновляет состояние)

### 8.2. JSON в ответах

Некоторые узлы могут возвращать JSON для обновления состояния:
- `service_manager`: `{"service_id": 12345678}`
- `slot_manager`: `{"slot_time": "YYYY-MM-DD HH:MM"}`
- `contact_collector`: `{"client_name": "...", "client_phone": "..."}`

Если JSON найден - сообщение клиенту не отправляется, процесс продолжается автоматически.

### 8.3. Обработка времени 00:00

Если `slot_time` имеет время 00:00 - это обрабатывается как дата без времени:
- В `analyzer` - не устанавливается `slot_time`
- В `slot_manager` - ищутся слоты на эту дату

### 8.4. Приоритеты роутинга

1. **Консультация** (`service_details_needed = True`) - всегда в `service_manager`
2. **Стандартная воронка** - по наличию данных (service_id → slot_time → контакты → finalizer)

---

## 9. Файлы и их назначение

- `src/graph/main_graph.py` - основной граф и маршрутизация между стадиями
- `src/graph/booking/graph.py` - граф бронирования и его роутинг
- `src/graph/booking/analyzer.py` - узел анализатора
- `src/graph/booking/nodes/service_manager.py` - узел выбора услуги
- `src/graph/booking/nodes/slot_manager.py` - узел работы со слотами
- `src/graph/booking/nodes/contact_collector.py` - узел сбора контактов
- `src/graph/booking/nodes/finalizer.py` - узел финализации
- `src/graph/booking/state.py` - определение BookingSubState
- `src/graph/conversation_state.py` - определение ConversationState
- `src/agents/dialogue_stages.py` - определение стадий диалога
- `src/agents/stage_detector_agent.py` - агент определения стадии
- `src/agents/booking_agent.py` - агент бронирования
- `src/agents/cancel_booking_agent.py` - агент отмены
- `src/agents/reschedule_agent.py` - агент переноса
- `src/agents/view_my_booking_agent.py` - агент просмотра записей
- `src/agents/about_salon_agent.py` - агент информации о салоне



