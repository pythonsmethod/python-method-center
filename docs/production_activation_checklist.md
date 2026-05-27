# Production Activation Checklist

Document Type: Operational Readiness Framework — Master Activation Checklist
Version: 1.0
Project: Python Method Center
Status: Active Reference — Freeze-Safe
Created: 2026-05-20
Basis: docs/system_experience_map.md, docs/route_implementation_plan_after_freeze.md, docs/stabilization_freeze_notice.md, docs/route_architecture.md, docs/client_onboarding_experience.md, docs/memory_experience_architecture.md, docs/agent_role_specification.md

---

## 1. Purpose of Production Activation Checklist

### Зачем нужен activation discipline

Python Method Center прошёл через период активной нестабильности (ORCH FATAL серии, Phase 4 Stabilization Freeze). Система была намеренно заморожена — не из страха, а из дисциплины. Это был сознательный выбор: строить архитектуру правильно, а не торопиться ломать production ради функций.

Теперь, когда docs-архитектура сформирована полностью — маршруты, UX, агенты, память, сообщения, system map — система готова к activation. Но activation без discipline — это путь обратно к нестабильности.

Данный документ является master operational checklist. Он не описывает код. Он описывает дисциплину перехода: как проверять, что система готова; как убеждаться, что каждый шаг не нарушил то, что работало; как сохранить человеческое ощущение системы в процессе технической активации.

### Почему сложные AI-системы ломаются без operational readiness

Сложные AI-системы ломаются не только из-за технических ошибок. Они ломаются из-за:
- нарушения маршрутизации без проверки downstream effects
- изменения промптов без UX-верификации
- добавления новых слоёв без понимания interaction patterns
- скорости деплоя без верификации каждого шага
- отсутствия explicit rollback plan

Каждый из этих рисков присутствует в данной системе. Production Activation Checklist — это страховочная сетка против всех них.

### Почему docs-first architecture была выбрана сознательно

Docs-first strategy позволила системе пройти период заморозки без потери развития. Вместо того чтобы стоять и ждать — система строила архитектурный капитал:
- route_architecture.md (маршруты как системная спецификация)
- client_onboarding_experience.md (UX-архитектура пути)
- client_message_library.md (approved message patterns)
- agent_role_specification.md (официальные роли агентов)
- memory_experience_architecture.md (UX памяти)
- system_experience_map.md (master navigation)
- production_activation_checklist.md (данный документ)

Когда freeze снимается — система не начинает с нуля. Она активирует то, что уже полностью спроектировано.

---

## 2. Current System State Before Activation

### Что уже существует в production (2026-05-20)

**AI layer:** Claude + GPT через ai_router.py с fallback
**Agent routing:** orchestrator_core.py → agent_selector.py (Phase 3, ROUTE_AGENT_MAP)
**Route resolution:** route_resolver.py + auto_router.py + state_engine.py
**Memory engine:** memory_writer.py + central_ai_core.py + PostgreSQL (pm_sessions)
**Payment flow:** Stripe webhooks → main.py → on_payment_confirmed
**Emotional overlay:** emotional_overlay.py (независимый слой)
**Priority engine:** priority_engine.py (interrupt-система)
**Session state:** pm_sessions с JSONB-полями, включая payment_status
**Agents deployed:** Lucky, Hannah, Maya, Iris, Vera, Nadia, Gabriel, Sophia, Karen, Sarah

### Что существует только как docs architecture

- care_route, care_duration, support_level, karen_access, ai_support_level, onboarding_stage, rehab_stage, renewal_status — **не в production schema**
- Route-aware agent prompts — **не активированы**
- Companion layer ownership (Nadia) — **не имплементирован**
- Karen connection bridge sub-flow — **не формализован**
- Renewal flow trigger — **не активен**
- Registry sync (agents.py ↔ agent_selector.py) — **не выполнен**

### Что ещё не внедрено

- Phase A: DB migration (migrate_route_state.sql — spec готов, не применён)
- Phase B: care_route в context_package
- Phase C: route-aware agent prompts
- Phase D: Iris / Nadia prompt expansion
- Phase E: renewal flow trigger
- Phase F: full route-aware UX

### Freeze status

**ACTIVE** — Stabilization Freeze объявлен 2026-05-19, commit afe38578. Условия снятия: 7 подряд чистых дней без ORCH FATAL + total_webhooks_processed >= 50 + mean latency < 5000ms across 20+ webhooks.

### Additive-only implementation strategy

Все изменения только через ADD COLUMN IF NOT EXISTS. Никаких изменений существующей логики без явного audit. Никакого переписывания orchestrator, route_resolver, auto_router. Только additive expansion.

---

## 3. Preconditions Before Lift Freeze

Все пункты должны быть выполнены **до** снятия freeze и начала любого deployment.

### Стабильность production

- [ ] Stabilization freeze официально снят (governance commit с сообщением "governance: lift stabilization freeze — Phase 4 complete")
- [ ] 7+ подряд чистых дней без ORCH FATAL в Railway logs
- [ ] total_webhooks_processed >= 50
- [ ] Mean latency < 5000ms across 20+ webhooks
- [ ] Health endpoint отвечает стабильно: /health = 200 OK
- [ ] Нет активных traceback в логах
- [ ] Нет незакрытых критических ошибок

### Документационная готовность

- [ ] route_architecture.md — Active (commit 6a346e6) ✓
- [ ] migrate_route_state.sql — Pending (commit d8f6d87, не применён) ✓
- [ ] route_implementation_plan_after_freeze.md — Active (commit 849471c) ✓
- [ ] client_onboarding_experience.md — Active (commit 786e726) ✓
- [ ] client_message_library.md — Active (commit eb521d1) ✓
- [ ] agent_role_specification.md — Active (commit 98ad0b1) ✓
- [ ] memory_experience_architecture.md — Active (commit 25e5c2a) ✓
- [ ] system_experience_map.md — Active (commit a3cac16) ✓
- [ ] production_activation_checklist.md — Active (данный документ) ✓

### Операционная готовность

- [ ] DB backup выполнен перед любым изменением
- [ ] Rollback strategy для каждой phase зафиксирована
- [ ] Deployment discipline согласована командой
- [ ] Один человек отвечает за каждую phase deployment

---

## 4. Activation Principles

Следующие принципы применяются ко всем фазам активации без исключений.

**One phase = one deploy.** Не объединять несколько фаз в один деплой. Каждая фаза — отдельный commit, отдельный деплой, отдельный цикл верификации.

**One deploy = one verification cycle.** После каждого деплоя — проверка. Не продолжать к следующей фазе, пока не подтверждена стабильность текущей.

**Stop on error.** Любой traceback, unexpected routing, broken UX — немедленная остановка. Диагностика до следующего шага.

**Additive only.** Никаких изменений существующей логики. Только добавление. ADD COLUMN IF NOT EXISTS. Prompt expansion, не prompt rewrite.

**No broad refactor.** Не переписывать orchestrator_core.py, route_resolver.py, auto_router.py в процессе activation phases.

**Continuity over speed.** Лучше медленнее, но с сохранённым UX. Разрушенная continuity — это разрушённое доверие клиента.

**UX integrity over feature count.** Добавить меньше функций, но убедиться, что каждая работает правильно с точки зрения человеческого опыта.

---

## 5. Phase Activation Checklist

### Phase A — DB Route Fields

**Goal:** Добавить route-переменные в pm_sessions и pm_client_profiles через migrate_route_state.sql.

**Files affected:** PostgreSQL schema (pm_sessions, pm_client_profiles). Никакие Python файлы не изменяются.

**Pre-deploy checks:**
- [ ] DB backup выполнен
- [ ] migrate_route_state.sql просмотрен и подтверждён
- [ ] Все ALTER TABLE используют ADD COLUMN IF NOT EXISTS
- [ ] Нет DROP COLUMN, ALTER COLUMN, RENAME
- [ ] Test environment проверен (если доступен)

**Deploy:**
- [ ] Применить migrate_route_state.sql
- [ ] Проверить: все 7 новых колонок добавлены в pm_sessions
- [ ] Проверить: все 10 новых колонок добавлены в pm_client_profiles
- [ ] Проверить: 3 индекса созданы (idx_client_care_route, idx_client_rehab_stage, idx_client_care_expires)

**Post-deploy checks:**
- [ ] Существующие сессии не повреждены
- [ ] payment_status = confirmed сессии продолжают работать
- [ ] Новые колонки имеют правильные DEFAULT значения
- [ ] Логи чистые, нет DB ERROR

**Rollback triggers:**
- DB ERROR при применении миграции
- Существующие сессии перестали загружаться
- payment flow сломан

**Success conditions:**
- Все новые поля присутствуют в schema
- Старая логика работает без изменений
- Нет traceback в логах

---

### Phase B — Session / State Model (care_route в context_package)

**Goal:** Добавить care_route и ai_support_level в context_package. Агенты начинают получать route-aware context.

**Files affected:** central_ai_core.py (build_context_package), agents.py или agent_selector.py (_build_prompt).

**Pre-deploy checks:**
- [ ] Phase A успешно завершена и верифицирована
- [ ] care_route поле существует в pm_sessions
- [ ] Понятно, откуда care_route читается (из session)
- [ ] Понятно, как DEFAULT значение (none/NULL) обрабатывается в промпте

**Deploy:**
- [ ] Добавить care_route в context_package (additive, не заменять существующие поля)
- [ ] Добавить ai_support_level в context_package
- [ ] Проверить, что _build_prompt получает и использует эти значения

**Post-deploy checks:**
- [ ] Сессии без care_route (NULL) продолжают работать нормально
- [ ] Сессии с care_route = START_SUPPORT получают корректный context
- [ ] Сессии с care_route = FULL_PYTHON_METHOD получают корректный context
- [ ] Routing логика не изменилась
- [ ] Логи показывают правильные agent selections

**Rollback triggers:**
- Агенты перестали выбираться корректно
- Context_package вызывает ошибки при формировании
- Существующие активные сессии сломаны

**Success conditions:**
- Агенты получают care_route в system prompt
- Behavior нейтральных сессий не изменился
- Логи чистые

---

### Phase C — Payment → Route Activation

**Goal:** При payment_status = confirmed автоматически устанавливать care_route, ai_support_level = active_companion, onboarding_stage = started.

**Files affected:** agents.py (on_payment_confirmed), возможно main.py.

**Pre-deploy checks:**
- [ ] Phase B успешно завершена
- [ ] Понятно, где происходит on_payment_confirmed
- [ ] Логика установки переменных написана additive (не заменяет существующий flow)
- [ ] TARIFF_1_LINK и TARIFF_2_LINK корректно маппятся на care_route

**Deploy:**
- [ ] При Stripe success: care_route устанавливается из тарифа
- [ ] ai_support_level = active_companion устанавливается
- [ ] onboarding_stage = started устанавливается
- [ ] Существующий payment notification flow не нарушен

**Post-deploy checks:**
- [ ] Тест Stripe: успешная оплата → care_route = START_SUPPORT (или FULL_PYTHON_METHOD)
- [ ] Тест Stripe: ai_support_level корректен
- [ ] Тест Stripe: onboarding запускается
- [ ] Karen notification отправляется (существующий flow)
- [ ] Нет двойных срабатываний

**Rollback triggers:**
- Payment flow нарушен
- Karen notification перестала отправляться
- care_route не устанавливается
- Двойные уведомления

**Success conditions:**
- Новая оплата → care_route установлен корректно
- Старые сессии не затронуты
- Весь payment notification flow работает

---

### Phase D — Post-Payment Onboarding (Iris + Nadia prompt expansion)

**Goal:** Расширить промпты Iris и Nadia. Iris: warm landing + first 72h + Karen connection bridge. Nadia: companion layer + daily support.

**Files affected:** agent_selector.py (_AGENT_PERSONAS для Iris и Nadia), или agents.py (IRIS_PROMPT, NADIA_PROMPT).

**Pre-deploy checks:**
- [ ] Phase C успешно завершена
- [ ] care_route передаётся в context (Phase B)
- [ ] Новые тексты промптов написаны согласно agent_role_specification.md
- [ ] Тональность проверена на соответствие client_message_library.md
- [ ] Изменения additive (расширение промпта, не замена)

**Deploy:**
- [ ] Обновить Iris persona: warm landing, first 72h awareness, Karen connection bridge
- [ ] Обновить Nadia persona: companion layer, daily check-in cadence, renewal flow awareness
- [ ] Убедиться, что другие агенты не затронуты

**Post-deploy checks:**
- [ ] Тест онбординга: первое сообщение Iris после оплаты — тёплое, не формальное
- [ ] Тест Iris: через 72h context соответствует ожиданиям
- [ ] Тест Nadia: companion check-in tone корректен
- [ ] Тест Nadia: не звучит как алгоритм
- [ ] Routing между агентами не нарушен

**Rollback triggers:**
- Iris отправляет формальное/холодное первое сообщение
- Nadia звучит как робот
- Routing между агентами нарушен

**Success conditions:**
- Post-payment experience соответствует client_onboarding_experience.md §6–9
- Companion layer работает органично
- UX-верификация пройдена (см. раздел 6)

---

### Phase E — AI Support Level Separation

**Goal:** ai_support_level корректно разделяет поведение агентов до и после оплаты. Навигационный режим vs active_companion режим.

**Files affected:** agent_selector.py или agents.py (логика на основе ai_support_level).

**Pre-deploy checks:**
- [ ] Phase D успешно завершена
- [ ] ai_support_level передаётся в context_package (Phase B)
- [ ] Поведение при navigation четко определено
- [ ] Поведение при active_companion чётко определено

**Deploy:**
- [ ] Pre-payment агенты (Lucky, Hannah, Maya) работают в navigation mode
- [ ] Post-payment агенты (Iris, Nadia, Vera) переключаются при ai_support_level = active_companion
- [ ] Граница строга: payment_status = confirmed → переключение

**Post-deploy checks:**
- [ ] До оплаты: AI не собирает детальную медицинскую информацию
- [ ] После оплаты: AI активирует onboarding контекст
- [ ] Граница не пропускается при любых edge cases
- [ ] Нет путаницы между режимами

**Rollback triggers:**
- AI собирает медицинскую информацию до оплаты
- Onboarding не активируется после оплаты
- Режимы смешиваются

**Success conditions:**
- Чёткая граница navigation / active_companion
- UX соответствует route_architecture.md §6

---

### Phase F — Renewal / Expiration Logic

**Goal:** Система корректно устанавливает rehab_stage = nearing_end при приближении к концу маршрута. Nadia активируется для renewal flow.

**Files affected:** Scheduler/reminder logic, priority_engine.py (additive rule), Nadia prompt (уже расширен в Phase D).

**Pre-deploy checks:**
- [ ] Phases A–E успешно завершены
- [ ] care_expires_at поле заполняется при активации маршрута
- [ ] Priority engine понимает nearing_end как Nadia-trigger

**Deploy:**
- [ ] При (care_expires_at - now) <= threshold → rehab_stage = nearing_end
- [ ] Nadia получает renewal context
- [ ] Renewal messages из §12 client_message_library.md активны

**Post-deploy checks:**
- [ ] Тест: маршрут approaching expiry → Nadia получает нужный context
- [ ] Renewal message — мягкое, без давления
- [ ] При renewal_status = confirmed — маршрут продлевается
- [ ] При renewal_status = declined — маршрут корректно завершается

**Rollback triggers:**
- Renewal message ощущается как давление или манипуляция
- Нарушение payment flow при продлении
- Неправильное завершение маршрута

**Success conditions:**
- Renewal flow соответствует route_architecture.md §4.9 / §5.9
- Опыт завершения аккуратный, не обрывистый

---

## 6. Human Experience Verification

### Самый важный раздел

Технические проверки необходимы, но недостаточны. Система может работать без traceback — и при этом ощущаться как холодный автомат. Этот раздел проверяет human experience.

### Проверки

**First contact feels warm**
Тест: написать в бот как новый пользователь. Первое сообщение Lucky.
Критерий: ощущение тепла и встречи, не "добро пожаловать в чат-бот".
Признак провала: "Здравствуйте! Чем могу помочь?" в холодном регистре.

**Onboarding feels structured**
Тест: пройти онбординг после тестовой оплаты.
Критерий: каждый шаг ощущается логичным и тёплым. Нет ощущения анкеты.
Признак провала: Iris задаёт вопросы как форма.

**Payment confirmation reduces anxiety**
Тест: первое сообщение Iris сразу после payment_status = confirmed.
Критерий: "ты внутри, система тебя видит, следующий шаг понятен".
Признак провала: "Ваша оплата подтверждена. Ожидайте."

**Karen connection feels human**
Тест: сообщение Iris о подключении Карена.
Критерий: тёплое, объясняющее, снижающее тревогу ожидания.
Признак провала: "Ваши данные переданы специалисту."

**AI continuity works**
Тест: написать через день после онбординга.
Критерий: система помнит контекст без полного повторения истории.
Признак провала: AI начинает заново как будто разговора не было.

**Return after silence works**
Тест: не писать 10+ дней, потом вернуться.
Критерий: тёплая встреча без вины, без давления.
Признак провала: "Вы давно не писали. Что случилось?"

**Memory recall feels natural**
Тест: AI упоминает что-то из предыдущего разговора.
Критерий: органично, уместно, по смыслу.
Признак провала: "Я помню, что 12 дней назад вы написали: '...'"

**No creepy memory behaviour**
Тест: разговор с упоминанием случайной детали.
Критерий: AI не воспроизводит случайные детали как доказательство памяти.
Признак провала: "Вы упоминали собаку на прогулке — как она?"

**No robotic loops**
Тест: задать один вопрос дважды.
Критерий: AI не копирует ответ механически.
Признак провала: одинаковый дословный ответ на оба раза.

**No agent confusion**
Тест: перейти от FAQ к консультации к онбордингу.
Критерий: переходы незаметны, тон единый.
Признак провала: ощущение "разных ботов" в одном чате.

---

## 7. Agent Behaviour Verification

### Lucky
- [ ] Первый ответ тёплый, не холодный
- [ ] Не называет стоимость первым
- [ ] Не давит на выбор маршрута
- [ ] Передаёт нить Hannah корректно при углублении запроса
- [ ] При кризисных сигналах — активирует escalation_route

### Hannah
- [ ] Выявляет запрос через мягкие вопросы (§5 message library)
- [ ] Не торопит с выбором маршрута
- [ ] Не делает медицинских выводов
- [ ] Корректно представляет оба маршрута (§6 message library)
- [ ] Передаёт к Maya при "готов выбрать"

### Maya
- [ ] Принимает человека с выбором без повторного убеждения
- [ ] Не создаёт искусственную срочность
- [ ] Объясняет альтернативы при технических проблемах Stripe
- [ ] Завершает работу при payment_status = confirmed
- [ ] Не работает после подтверждения оплаты

### Iris
- [ ] Первое post-payment сообщение — тёплое, не формальное
- [ ] Сбор контекста — органичный, не анкетный
- [ ] First 72h structure ощущается как поддержка, не протокол
- [ ] Karen connection bridge — тёплый, плановый, не экстренный
- [ ] Не исчезает до появления Карена

### Vera
- [ ] Принимает анализы структурировано
- [ ] Не интерпретирует показатели
- [ ] Не говорит "в норме / не в норме"
- [ ] Подтверждает получение и объясняет следующий шаг

### Nadia
- [ ] Companion check-ins — органичные, не алгоритмические
- [ ] Tone — тёплый и спокойный, не назойливый
- [ ] Не пишет повторно если нет ответа
- [ ] Renewal messages — мягкие, без давления
- [ ] Не становится психотерапевтом

### Gabriel
- [ ] Отвечает быстро и информативно
- [ ] Не втягивается в консультацию вместо FAQ
- [ ] При глубоком вопросе — перенаправляет правильно

### Sophia
- [ ] Не переубеждает агрессивно
- [ ] Присутствует рядом с сомнением, не борется с ним
- [ ] Не обещает "у нас иначе"

### Karen
- [ ] Активируется только при escalation_route, не при плановом onboarding
- [ ] Не имитирует живого Карена
- [ ] Корректно инициирует передачу без задержки

### Sarah
- [ ] Первое сообщение после паузы — без упрёков
- [ ] Не давит на быстрое возобновление
- [ ] Восстанавливает нить мягко

---

## 8. Route Verification

### START_SUPPORT

- [ ] После оплаты TARIFF_1: care_route = START_SUPPORT
- [ ] care_duration = 6_weeks
- [ ] support_level = standard
- [ ] Онбординг запускается: onboarding_stage = started
- [ ] Memory depth соответствует 6-недельному горизонту
- [ ] Renewal инициируется на 5–6 неделе (rehab_stage = nearing_end)
- [ ] Ending message — аккуратное завершение, не обрыв
- [ ] При renewal: предложение START_SUPPORT продления или FULL_PYTHON_METHOD перехода

### FULL_PYTHON_METHOD

- [ ] После оплаты TARIFF_2: care_route = FULL_PYTHON_METHOD
- [ ] care_duration = 5_6_months
- [ ] support_level = full
- [ ] Онбординг расширенный, включает более глубокий сбор контекста
- [ ] Memory depth — полная накопительная история
- [ ] Контрольные точки каждые 4–6 недель (rehab_stage обновляется)
- [ ] Renewal инициируется на 4–5 месяце
- [ ] Итоговая карта пути при завершении

### Общее для обоих маршрутов

- [ ] Никакой маршрут не активируется без payment_status = confirmed
- [ ] onboarding_stage переходит: not_started → started → completed
- [ ] rehab_stage переходит: pre_start → active → nearing_end → completed
- [ ] karen_access: pending → active → inactive
- [ ] renewal_status: none → initiated → confirmed/declined

---

## 9. Memory Verification

### Continuity checks

- [ ] После онбординга: следующий разговор начинается с контекстом, не с нуля
- [ ] Имя и основной запрос помнятся без повторного запроса
- [ ] Этап маршрута используется в тоне ответов

### Return after silence checks

- [ ] После 3–7 дней молчания: тёплая встреча, не "вы давно не писали"
- [ ] После 2–4 недель: мягкое восстановление нити без перечисления истории
- [ ] После 1+ месяца: открытый вопрос, не попытка восстановить весь архив сразу

### Anti-surveillance checks

- [ ] AI не воспроизводит точные цитаты
- [ ] AI не упоминает точные даты ("17 дней назад")
- [ ] AI не перечисляет историю как лог
- [ ] AI не делает психологических выводов из истории

### Emotional safety checks

- [ ] Память не используется для создания давления
- [ ] Память не используется для удержания через страх
- [ ] Contextual recall — уместный, не театральный

---

## 10. Karen Integration Verification

- [ ] Karen connection — тёплый, плановый (Iris), не экстренный (Karen-агент)
- [ ] При Karen connection: человеку объясняется что, когда и как
- [ ] AI собирает контекст для Карена: имя, запрос, состояние, анализы
- [ ] Карен получает структурированный контекст, не поток чатов
- [ ] AI не интерпретирует анализы вместо Карена
- [ ] При эскалации: Karen-агент активируется, не Iris
- [ ] Человек не повторяет всё заново при подключении Карена
- [ ] AI не имитирует экспертизу Карена

---

## 11. Payment & Route Activation Verification

### Stripe success flow

- [ ] Webhook получен корректно
- [ ] payment_status = confirmed установлен
- [ ] care_route установлен из тарифа
- [ ] ai_support_level = active_companion
- [ ] onboarding_stage = started
- [ ] Karen notification отправлена
- [ ] Первое сообщение Iris отправлено

### Stripe failure flow

- [ ] Webhook failure обработан без traceback
- [ ] Клиент получает сообщение от Maya с альтернативами
- [ ] care_route НЕ устанавливается при failure
- [ ] Попытка повторной оплаты доступна

### Alternative payment handling

- [ ] При non-Stripe оплате: manual confirmation flow корректен
- [ ] care_route устанавливается при manual confirmation

### Edge cases

- [ ] Двойной webhook: не создаёт дублирующей активации
- [ ] Refund: корректная обработка care_route

---

## 12. Failure Conditions

Rollout нужно немедленно остановить при любом из следующих условий:

**Критические (немедленный rollback):**
- Traceback в production logs
- Payment flow нарушен (Stripe webhooks не обрабатываются)
- Существующие активные сессии потеряли данные
- Неправильное назначение care_route при оплате
- Onboarding не запускается после подтверждения оплаты

**Значительные (остановка, диагностика, решение перед продолжением):**
- Дублирующее поведение агентов (два голоса в одном диалоге)
- Creepy memory behaviour (точные цитаты, даты, surveillance-тон)
- Холодное первое сообщение после оплаты
- Karen connection через escalation_route вместо Iris bridge
- Нарушение routing (неправильный агент выбирается по route)
- Agent tone collapse (Nadia звучит как робот, Lucky — формально)

**Требуют проверки (не останавливают rollout, но требуют verification ticket):**
- Небольшие тональные отклонения в сообщениях
- Медленный response time (но < 5000ms threshold)
- Логи с WARNING (не ERROR)

---

## 13. Rollback Principles

### Rollback без паники

Rollback — это не провал. Это дисциплина. Лучше откатить и понять, чем продолжать с нарушением.

**Preserve production stability.** Первый приоритет — стабильность существующего production. Если Phase B ломает что-то из Phase A — откатить Phase B, не трогать Phase A.

**Revert smallest possible scope.** Не откатывать всё подряд. Откатить только изменённый слой. Если сломан промпт Iris — откатить только промпт Iris.

**No emergency refactors.** Паника — плохой архитектор. Не пытаться "быстро починить" через широкие изменения. Диагностика сначала.

**Logs first, assumptions second.** Перед любым rollback action — читать логи. Что именно сломалось. Где. Когда. Только потом — решение.

**Document the rollback.** Что откатили, почему, что обнаружили — зафиксировать как commit message или в отдельном docs-файле.

### Rollback по фазам

- Phase A rollback: невозможен (ADD COLUMN IF NOT EXISTS безопасен, данные не ломаются). Проблемы Phase A — в логике, не в schema.
- Phase B rollback: убрать care_route из context_package, вернуть к предыдущей версии _build_prompt.
- Phase C rollback: убрать care_route assignment из on_payment_confirmed. Существующий payment flow не нарушен.
- Phase D rollback: откатить промпты Iris/Nadia к предыдущим версиям.
- Phase E rollback: убрать ai_support_level switching logic.
- Phase F rollback: убрать renewal trigger rule из priority_engine.

---

## 14. Success Criteria

Система считается успешно активированной, если выполнены все следующие условия:

**Технические:**
- [ ] Phases A–F задеплоены и верифицированы
- [ ] Production logs чистые (нет ERROR, нет traceback)
- [ ] Payment flow стабилен
- [ ] DB schema корректна

**UX-качество:**
- [ ] AI feels like one center — не набор ботов
- [ ] Continuity preserved — человек не повторяет историю заново
- [ ] Onboarding stable — тёплый, структурный, не анкетный
- [ ] Memory natural — органичная, не surveillance

**Агентное качество:**
- [ ] No cold bot feeling — ни один агент не ощущается как автомат
- [ ] No manipulative feeling — ни один момент не создаёт давления или страха
- [ ] No agent confusion — переходы незаметны для клиента
- [ ] No chaos between agents — один голос, один центр

**Интеграционное качество:**
- [ ] Companion layer stable — Nadia работает органично в daily support
- [ ] Karen integration smooth — planed bridge ≠ escalation
- [ ] Route assignment correct — START_SUPPORT vs FULL_PYTHON_METHOD корректны

**Итоговый тест:**
Написать в центр как новый клиент. Пройти путь от first contact до post-payment onboarding. Ответить на вопрос: "Это ощущается как центр сопровождения — или как бот?"

Если ответ — центр: активация успешна.

---

## 15. Final Activation Formula

Python Method Center должен активироваться:

**Постепенно.** Не all-at-once. Каждая фаза — отдельный шаг, отдельная верификация. Tempo активации определяется стабильностью системы, не желанием закончить быстро.

**Безопасно.** Каждое изменение — additive. Каждый шаг — с rollback plan. Каждый деплой — с verification cycle. Production stability — не жертва ради скорости.

**Через continuity.** Главный критерий каждой фазы — не "работает ли код", а "сохраняется ли ощущение непрерывности для клиента". Технические метрики важны, но UX-метрики важнее.

**Без разрушения existing stability.** Всё, что работает сейчас — продолжает работать. Активация новых слоёв не ломает старые. Additive only.

**Без потери человеческого ощущения системы.** Python Method — это не система управления маршрутами. Это система сопровождения людей. Каждое техническое изменение должно проходить проверку: делает ли это систему более человечной, или менее?

Если ответ "менее" — остановиться и пересмотреть.

Если ответ "более" — продолжать.

Именно так Python Method Center переходит из архитектуры в жизнь.

---

Document Type: Operational Readiness Framework — Master Activation Checklist
Version: 1.0
Status: Freeze-Safe — Documentation Only
Based on: system_experience_map.md (a3cac16), route_implementation_plan_after_freeze.md (849471c), stabilization_freeze_notice.md, route_architecture.md (6a346e6), client_onboarding_experience.md (786e726), memory_experience_architecture.md (25e5c2a), agent_role_specification.md (98ad0b1)
Next action: Execute after governance: lift stabilization freeze commit
