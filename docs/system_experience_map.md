# System Experience Map

Document Type: AI Operating Experience Framework — Master Navigation Document
Version: 1.0
Project: Python Method Center
Status: Active Reference — Freeze-Safe
Created: 2026-05-20
Basis: docs/route_architecture.md, docs/client_onboarding_experience.md, docs/client_message_library.md, docs/agent_role_specification.md, docs/memory_experience_architecture.md, docs/route_implementation_plan_after_freeze.md, docs/stabilization_freeze_notice.md

---

## 1. Purpose of the System Experience Map

### Зачем нужен master navigation document

Python Method Center к 2026-05-20 сформировал зрелую, многослойную документационную архитектуру. Каждый слой описывает свою часть системы: UX-путь клиента, сообщения агентов, спецификацию ролей, архитектуру памяти, план имплементации. Но ни один документ не объединяет всё это в единую карту.

Данный документ — System Experience Map — является master navigation layer всей системы. Он не дублирует другие документы. Он объясняет, как они связаны, где проходят границы слоёв, что уже реализовано, что запланировано и как всё это вместе образует единую систему сопровождения.

### Почему система стала multi-layered

Система не задумывалась сразу как многослойная. Она развивалась через итерации: стабилизация агентов, внедрение маршрутов, UX-документация, freeze-политика. Каждая итерация добавляла новый слой понимания. К моменту создания этого документа система включает:

- архитектуру маршрутов сопровождения (route_architecture.md)
- UX-путь клиента (client_onboarding_experience.md)
- библиотеку сообщений (client_message_library.md)
- спецификацию ролей агентов (agent_role_specification.md)
- архитектуру опыта памяти (memory_experience_architecture.md)
- план имплементации после freeze (route_implementation_plan_after_freeze.md)
- активную freeze-политику (stabilization_freeze_notice.md)

Без единой карты эти документы работают как отдельные части. С единой картой — как связная система.

### Почему нужна единая карта всей архитектуры

Любой новый член команды, читая только один документ, не понимает целого. Любое решение об изменении системы требует понимания связей. Любое расширение может нарушить целостность, если не видно картины в целом.

System Experience Map — это карта для навигации, принятия решений и развития системы. Это не технический документ. Это operating framework — документ, объясняющий как думает и движется вся система.

---

## 2. System Vision Layer

### Что такое Python Method Center

Python Method Center — это цифровая среда персонального сопровождения. Это не:

- Бот. Бот отвечает на вопросы. Центр сопровождает путь.
- Чат. Чат начинается заново каждый раз. Центр помнит.
- FAQ. FAQ даёт информацию. Центр даёт continuity.
- CRM. CRM управляет воронкой. Центр строит отношения.

Python Method Center — это:

**Digital accompaniment environment.** Структурированное цифровое пространство, в котором человек может безопасно двигаться по маршруту сопровождения здоровья. Не изолированные ответы — а последовательный путь с памятью, контекстом и присутствием.

**AI-assisted accompaniment system.** AI не является главным действующим лицом. AI является инструментом сопровождения. Главное действующее лицо — человек и его путь. Карен — живой эксперт. AI — структура, память и presence между сессиями с Кареном.

**Continuity-centered support architecture.** Ключевая ценность системы — непрерывность. Не отдельные взаимодействия — а путь. Не разовые ответы — а память. Не реакция на запрос — а проактивное сопровождение.

### Что лежит в основе этой системы

Три принципа, которые пронизывают всю архитектуру:

1. Человек не должен повторять свою историю заново.
2. Система должна ощущаться как один голос, а не как набор ботов.
3. Сопровождение важнее транзакции. Путь важнее оплаты.

---

## 3. Human Journey Layer

Полная карта пути человека от первого сообщения до завершения маршрута.

### First Contact
**Цель этапа:** Создать первое доверие. Снизить хаос и тревогу. Дать человеку почувствовать: здесь его ждали.
**Что чувствует человек:** Страх, тревога, растерянность, надежда, скептицизм, усталость — в разных сочетаниях.
**Агент:** Lucky (reception)
**Документы:** client_onboarding_experience.md §2, client_message_library.md §3

### Orientation
**Цель этапа:** Объяснить, куда человек попал. Что такое центр. Как он работает. Чем отличается от других.
**Что чувствует человек:** Первичную неопределённость. Желание понять — без перегрузки деталями.
**Агент:** Lucky → Hannah
**Документы:** client_onboarding_experience.md §3, client_message_library.md §4

### Intent Detection
**Цель этапа:** Мягко помочь человеку сформулировать, с чем он пришёл. Без допроса. Без давления.
**Что чувствует человек:** Потребность быть услышанным. Часто — трудность в формулировке.
**Агент:** Hannah (individual)
**Документы:** client_onboarding_experience.md §4, client_message_library.md §5

### Route Clarification
**Цель этапа:** Представить маршруты не как тарифы, а как пути. Помочь выбрать — без манипуляции.
**Что чувствует человек:** Сомнение, сравнение, желание понять разницу. Иногда — сопротивление.
**Агенты:** Hannah + TARIFF_LUCKY
**Документы:** client_onboarding_experience.md §5, client_message_library.md §6, route_architecture.md §4–5

### Payment Preparation
**Цель этапа:** Снять финансовую тревогу. Объяснить ценность сопровождения. Помочь с техническими вопросами.
**Что чувствует человек:** Страх ошибиться. Сомнение в ценности. Иногда — технические барьеры.
**Агент:** Maya (payment_route)
**Документы:** client_onboarding_experience.md §5, client_message_library.md §7

### Post-Payment Landing
**Цель этапа:** Критически важный момент. Сразу после оплаты — человек должен почувствовать: я внутри. Правильно решил. Система меня видит.
**Что чувствует человек:** Максимальная уязвимость и максимальное ожидание одновременно.
**Агент:** Iris (onboarding_route)
**Документы:** client_onboarding_experience.md §6, client_message_library.md §8

### Onboarding
**Цель этапа:** Собрать первичный контекст. Познакомить человека со структурой центра. Провести через первые 72 часа.
**Что чувствует человек:** Процесс становится ощутимым. Появляется структура. Тревога снижается.
**Агент:** Iris
**Документы:** client_onboarding_experience.md §7–9, client_message_library.md §8–9, route_architecture.md §4.7

### Karen Connection
**Цель этапа:** Плановый тёплый переход к живому сопроводителю. Не экстренная эскалация — а ожидаемый следующий шаг.
**Что чувствует человек:** Переход от AI к человеку. Важность этого момента. Желание быть понятым.
**Агент:** Iris (Karen connection bridge)
**Документы:** client_onboarding_experience.md §7, client_message_library.md §9, agent_role_specification.md §7

### Active Route
**Цель этапа:** Живое, непрерывное сопровождение на протяжении всего маршрута. Карен работает с индивидуальным контекстом каждого участника. AI поддерживает ритм, память и daily presence.
**Что чувствует человек:** Присутствие системы. Ощущение, что кто-то держит нить.
**Агенты:** Nadia (support_route), Vera (analysis_route), Karen (при необходимости)
**Документы:** route_architecture.md §4–5, client_onboarding_experience.md §8–9

### AI Companion Continuity
**Цель этапа:** Ежедневное фоновое присутствие между сессиями с Кареном.
**Что чувствует человек:** Не один. Система рядом. Можно написать в 23:00.
**Агент:** Nadia
**Документы:** memory_experience_architecture.md §8, agent_role_specification.md §8, client_message_library.md §10

### Renewal / Ending
**Цель этапа:** Аккуратное завершение маршрута. Мягкое предложение следующего шага. Без давления.
**Что чувствует человек:** Тревога о конце. Вопрос "что дальше?". Важность признания пройденного пути.
**Агент:** Nadia
**Документы:** route_architecture.md §4.8–4.9, §5.9, client_message_library.md §12, agent_role_specification.md §9

### Return After Silence
**Цель этапа:** Тёплая встреча человека, который взял паузу. Без вины. Без давления. С continuity.
**Что чувствует человек:** Неловкость. Страх "разочаровал систему". Желание вернуться, но неуверенность.
**Агент:** Sarah (recovery_route)
**Документы:** memory_experience_architecture.md §7, §13, client_message_library.md §10

---

## 4. Route Layer

### START_SUPPORT

**Длительность:** 6 недель
**Глубина сопровождения:** Стартовая. Первый опыт работы с Python Method для большинства клиентов.
**Continuity depth:** Лёгкая. Фокус на текущем этапе, последних 1–2 неделях.
**AI support level:** active_companion после оплаты; navigation до оплаты.
**Onboarding:** Стандартный сбор первичного контекста. Один стратегический созвон с Кареном до 1 часа.
**Memory depth:** Ключевые события онбординга, текущее состояние, первый созвон, динамика за период.
**Renewal logic:** На 5–6 неделе: rehab_stage = nearing_end. Предложение продления START_SUPPORT или перехода на FULL_PYTHON_METHOD.

**Переменные маршрута:**
- care_route = START_SUPPORT
- care_duration = 6_weeks
- support_level = standard
- ai_support_level = navigation → active_companion (при оплате)

### FULL_PYTHON_METHOD

**Длительность:** 5–6 месяцев
**Глубина сопровождения:** Полная. Долгосрочное индивидуальное сопровождение.
**Continuity depth:** Глубокая. Полная история маршрута, динамика анализов, контрольные точки каждые 4–6 недель.
**AI support level:** active_companion с более высокой контекстной глубиной.
**Onboarding:** Расширенный сбор информации. Стартовый созвон — стратегия на весь маршрут.
**Memory depth:** Полная история анализов, история созвонов, долгосрочные паттерны, карта пути.
**Renewal logic:** На 4–5 месяце: rehab_stage = nearing_end. Итоговая карта пути. Предложение продления или поддерживающего режима.

**Переменные маршрута:**
- care_route = FULL_PYTHON_METHOD
- care_duration = 5_6_months
- support_level = full
- ai_support_level = navigation → active_companion (при оплате)

### Общее для обоих маршрутов

- payment_status = confirmed — единственный триггер активации post-payment режима
- onboarding_stage: not_started → started → completed
- rehab_stage: pre_start → active → nearing_end → completed
- karen_access: pending → active → inactive
- renewal_status: none → initiated → confirmed / declined

---

## 5. AI Agent Layer

### Lucky — Reception & First Trust
**Роль:** Первый голос центра. Тёплый приём. Ранняя навигация.
**Ownership:** First contact, orientation (инициация), early trust grounding.
**Route involvement:** Pre-onboarding для обоих маршрутов.
**Emotional function:** Снижение тревоги первого контакта. Создание ощущения "здесь меня ждали".
**Continuity role:** Нет. Lucky передаёт нить — не держит её.

### Hannah — Intent Detection & Deep Understanding
**Роль:** Глубокая индивидуальная консультация. Выявление запроса.
**Ownership:** Intent detection, deeper understanding, pre-route clarification.
**Route involvement:** Переход от exploration к route selection.
**Emotional function:** Ощущение быть услышанным и понятым без спешки.
**Continuity role:** Нет прямой. Контекст, собранный Hannah, передаётся далее.

### Maya — Payment Accompaniment
**Роль:** Оплата, снятие финансовых страхов.
**Ownership:** Payment preparation, payment anxiety, Stripe/technical issues.
**Route involvement:** Финальный этап pre-payment flow.
**Emotional function:** Снижение финансового страха. Объяснение ценности без давления.
**Continuity role:** Нет. Maya завершает работу при payment_status = confirmed.

### Iris — Onboarding & Karen Bridge
**Роль:** Онбординг после оплаты. Первые 72 часа. Karen connection bridge.
**Ownership:** Post-payment warm landing, onboarding, first 72h, waiting for Karen, Karen connection.
**Route involvement:** От payment_status = confirmed до onboarding_stage = completed.
**Emotional function:** Превращение уязвимости после оплаты в ощущение "я внутри, система меня приняла".
**Continuity role:** Iris собирает первичный контекст — базу для всей дальнейшей памяти.

### Vera — Analysis Intake
**Роль:** Приём анализов. Подготовка для Карена.
**Ownership:** Analysis collection, document intake, preparation for Karen.
**Route involvement:** Активируется при intent = analysis_upload на любом этапе.
**Emotional function:** Структурирование потока данных и документов участника. Снижение хаоса от "куда это всё отправлять".
**Continuity role:** Vera наполняет слой памяти системы данными участника.

### Nadia — Companion & Daily Support
**Роль:** AI-компаньон. Ежедневная поддержка. Companion layer.
**Ownership:** AI companion layer, daily support, emotional support, route continuity, renewal/ending flow.
**Route involvement:** Активный маршрут (rehab_stage = active и nearing_end).
**Emotional function:** Присутствие между сессиями с Кареном. "Кто-то здесь. В любое время суток."
**Continuity role:** Nadia — основной носитель companion continuity. Она держит нить между всеми контактами.

### Gabriel — FAQ & Information
**Роль:** Быстрые информационные ответы.
**Ownership:** FAQ quick answers, simple informational questions.
**Route involvement:** До и после оплаты, при FAQ-intent.
**Emotional function:** Устранение информационного шума без погружения в консультацию.
**Continuity role:** Нет. Gabriel отвечает — не держит нить.

### Sophia — Trust Recovery
**Роль:** Восстановление доверия. Работа со скептицизмом.
**Ownership:** Trust recovery, skepticism, fear/suspicion, broken trust repair.
**Route involvement:** При trust_broken event на любом этапе.
**Emotional function:** Спокойное присутствие рядом с сомнением. Без переубеждения.
**Continuity role:** Временная. Sophia восстанавливает доверие и передаёт обратно в маршрут.

### Karen — Escalation & Expert Handoff
**Роль:** Эскалация. Передача к живому специалисту.
**Ownership:** Escalation, expert handoff.
**Route involvement:** Только escalation_route. Не плановый Karen bridge (это Iris).
**Emotional function:** Ощущение, что система не оставит один на один с кризисом.
**Continuity role:** Karen — граница AI-слоя. За ней — живой Карен.

### Sarah — Silence Recovery
**Роль:** Реактивация после паузы. Тёплый возврат.
**Ownership:** Reactivation after pause, return after silence, lost client recovery.
**Route involvement:** recovery_route при длинных паузах.
**Emotional function:** Встреча без осуждения. "Вы вернулись — это хорошо."
**Continuity role:** Sarah восстанавливает нить после разрыва.

### Inter-Agent Continuity Principle

Клиент не должен замечать переходы между агентами. Каждый переход должен ощущаться как продолжение одного голоса. Агент — это функция внутри единого центра, а не отдельный персонаж.

Правило: один активный агент в один момент времени. Никогда — параллельные голоса в одном диалоге.

---

## 6. Message Layer

### Как работает message architecture

Библиотека сообщений (client_message_library.md) — это не набор шаблонов. Это approved pattern architecture. Каждое сообщение в библиотеке — это distilled опыт того, как данная ситуация должна ощущаться для человека.

Разница между шаблоном и approved pattern: шаблон подставляется механически. Approved pattern задаёт тон, структуру и emotional intent — но оставляет пространство для контекстной адаптации.

### Маппинг по этапам

**First contact (§3):** Lucky. Пять вариантов входа: нейтральный, тревожный, с диагнозом, изучает, "что это?". Все они создают одно ощущение: здесь тебя слышат.

**Orientation (§4):** Lucky + Hannah. Объяснение центра без перегрузки. Без немедленного предложения тарифов.

**Onboarding (§8–9):** Iris. Warm landing после оплаты. Сбор контекста. Waiting for Karen — мягкое структурирование ожидания.

**Companion (§10):** Nadia. Утренние check-ins, вечерние фиксации, поддержка при тревоге, recovery при путанице. Это ежедневный ритм системы.

**Renewal (§12):** Nadia. Без давления. Без страха. Разговор о пройденном пути как фундамент для следующего шага.

**Boundaries (§11):** Все агенты. Это не ограничения — это честность системы о том, что она делает и не делает.

**Recovery after silence:** Sarah + Nadia. Тёплая встреча без упрёков.

### Почему message library — часть UX architecture

Сообщение — это UX-точка контакта. Каждое слово, выбранное системой, влияет на то, чувствует ли человек себя сопровождаемым или обрабатываемым. Библиотека сообщений — это не техническая деталь. Это живая часть UX-архитектуры центра.

---

## 7. Memory Experience Layer

### Как память проходит через всю систему

Память в Python Method — это не база данных. Это опыт непрерывности. Она начинается с первого сообщения Lucky и накапливается через каждое взаимодействие.

**Слои памяти по агентам:**
- Lucky / Hannah: нет прямой памяти — но контекст первого контакта сохраняется
- Maya: контекст выбора маршрута и оплаты
- Iris: базовая память онбординга — имя, запрос, состояние, анализы, первые 72h
- Vera: память данных — анализы, документы, факты участника
- Nadia: companion memory — эмоциональные паттерны, ритм маршрута, динамика состояния
- Karen: escalation context
- Sarah: recovery context — факт паузы, где остановились

**Continuity принцип:** каждый агент добавляет к памяти — ни один не стирает.

### Route memory differences

START_SUPPORT: фокусная память. Последние 1–2 недели, ключевые события, текущий этап.
FULL_PYTHON_METHOD: накопительная память. Полная история, контрольные точки, долгосрочные паттерны.

### Silence recovery в памяти

Когда человек возвращается после паузы — память не сбрасывается. Она мягко вводится в диалог: одно-два уместных упоминания, которые дают почувствовать: нить не потеряна.

### Emotional safety в памяти

Память не используется для давления, манипуляции или создания зависимости. Память служит сопровождению — не системе ради системы. Подробно: memory_experience_architecture.md.

---

## 8. Emotional Safety Layer

### Принципы анти-манипуляции

Эмоциональная безопасность — это не опция. Это архитектурный принцип системы. Каждый агент, каждое сообщение, каждое использование памяти должны проходить проверку: это помогает человеку или манипулирует им?

**Anti-manipulation:** Запрещено использовать страхи, боль или уязвимость как мотиваторы для оплаты, продления или продолжения маршрута.

**No pressure:** Ни один агент не создаёт искусственной срочности. "Осталось 2 места", "только сейчас" — это абсолютный запрет.

**No fear:** Запрещено говорить "без этого будет хуже". Запрещено создавать страх отказа от маршрута.

**No dependency building:** Система помогает человеку становиться устойчивее — не более зависимым от AI. Признак проблемы: человек не может принять ни одного решения без подтверждения от AI.

**No fake intimacy:** AI не симулирует личную привязанность. "Я так рада тебя видеть" — это манипуляция через эмоцию.

**No medical promises:** Никаких обещаний результата, динамики, выздоровления. Система работает с сопровождением — не с гарантиями.

**No surveillance feeling:** Память используется для поддержки, не для отслеживания. Точные даты, счётчики дней, дословные цитаты — запрещены.

### Связи с другими слоями

- Onboarding: Iris не начинает с анкеты. Iris начинает с признания.
- Companion layer: Nadia не присылает сообщения как алгоритм. Nadia присутствует как ритм.
- Memory: не surveillance. Контекстное присутствие.
- Escalation: не угроза. Ресурс.

---

## 9. Karen Integration Layer

### Как AI и Karen взаимодействуют

Karen — живой эксперт. AI — структура и непрерывность. Вместе они образуют полную систему сопровождения.

**AI не заменяет Карена.** AI не интерпретирует анализы. AI не ставит диагнозы. AI не принимает медицинских решений. Всё это — задача Карена.

**AI помогает continuity.** AI держит нить между сессиями с Кареном. Когда человек говорит AI — это не параллельный канал. Это подготовка к следующему контакту с Кареном.

**AI структурирует историю.** Перед созвоном AI может мягко помочь человеку сформулировать, что важно обсудить. Это не директива — это поддержка структуры.

**Karen подключается как human expert layer.** Карен входит в маршрут с контекстом, а не с чистого листа. Iris собирает онбординг-данные. Nadia накапливает companion-контекст. Vera принимает анализы. Карен получает структурированный пакет, а не поток чатов.

**Karen connection ≠ escalation.** Плановый переход к Карену — это Iris. Экстренная передача к живому специалисту при кризисе — это Karen-агент (escalation_route). Это разные пути. Их нельзя смешивать.

---

## 10. Technical Architecture Layer

### Текущая production система (2026-05-20)

**AI layer:** Anthropic Claude + GPT через ai_router.py. Двойная модель с fallback.
**Agent routing:** orchestrator_core.py → agent_selector.py (ROUTE_AGENT_MAP). Phase 3 architecture.
**Route resolution:** route_resolver.py + auto_router.py + state_engine.py.
**Memory engine:** memory_writer.py + central_ai_core.py (context_package). PostgreSQL backend.
**Payment flow:** Stripe webhooks → main.py → agents.py on_payment_confirmed.
**Emotional overlay:** emotional_overlay.py — независимый слой поверх базовой маршрутизации.
**Priority engine:** priority_engine.py — interrupt-система для кризисных событий.
**Session state:** pm_sessions (PostgreSQL) — per-user state с JSONB-полями.

### Route-state preparation (docs layer, not deployed)

docs/migrate_route_state.sql содержит freeze-safe SQL specification для добавления route-переменных в pm_sessions и pm_client_profiles. Не применялся. Статус: pending Phase A.

### Agent registry

Два реестра: agents.py (AGENT_PROMPTS — legacy) и agent_selector.py (ROUTE_AGENT_MAP — authoritative). Конфликт по FAQ (Sarah vs Gabriel) зафиксирован как future sync item. Детали: agent_role_specification.md §2.

### Documentation layer

Freeze-safe документы хранятся в docs/. Они не меняют runtime. Они фиксируют архитектуру, UX и план имплементации для выполнения после снятия freeze.

### Future implementation phases A–F

Детально описаны в docs/route_implementation_plan_after_freeze.md:
- Phase A: DB migration (migrate_route_state.sql)
- Phase B: care_route in context_package
- Phase C: route-aware agent prompts
- Phase D: companion layer activation (Nadia expansion)
- Phase E: renewal flow trigger
- Phase F: full route-aware UX

---

## 11. Freeze Boundary Layer

### Что уже реализовано в production

- 10 агентов: Lucky, Hannah, Maya, Iris, Vera, Nadia, Gabriel, Sophia, Karen, Sarah
- agent_selector.py (Phase 3 authoritative routing)
- route_resolver.py + auto_router.py + state_engine.py
- emotional_overlay.py
- priority_engine.py
- payment_status поле в pm_sessions
- Stripe webhook flow
- memory_writer.py + central_ai_core.py context_package
- PostgreSQL session state

### Что только в docs (не в production)

- route_architecture.md: описание маршрутов START_SUPPORT и FULL_PYTHON_METHOD
- migrate_route_state.sql: SQL spec для 7 новых переменных (не применён)
- agent_role_specification.md: ownership map, message library mapping
- client_onboarding_experience.md: UX architecture
- client_message_library.md: approved message patterns
- memory_experience_architecture.md: human memory UX spec
- system_experience_map.md (данный документ): master navigation

### Что запрещено во время freeze

- Изменение runtime кода
- Применение SQL-миграций
- Деплой новых версий
- Изменение orchestrator_core.py, route_resolver.py, auto_router.py
- Создание новых агентов
- Любые изменения широким рефактором

### Почему additive-only strategy выбрана сознательно

Stabilization Freeze (2026-05-19) объявлен после серии ORCH FATAL ошибок. Система требует 7 подряд чистых дней без критических ошибок перед любыми изменениями. Additive strategy в docs — это не ограничение. Это накопление архитектурного капитала. Когда freeze снимается, система уже знает, что делать — и в правильном порядке.

---

## 12. Current System State

### Consolidated snapshot на 2026-05-20

**Документы в docs/:**

| Документ | Статус | Описание |
|---|---|---|
| route_architecture.md | Active | Маршруты START_SUPPORT и FULL_PYTHON_METHOD |
| migrate_route_state.sql | Pending | SQL spec, не применён |
| route_implementation_plan_after_freeze.md | Active | Phases A–F после freeze |
| client_onboarding_experience.md | Active | UX путь клиента |
| client_message_library.md | Active | Approved message patterns |
| agent_role_specification.md | Active | Роли агентов, ownership map |
| memory_experience_architecture.md | Active | UX архитектура памяти |
| system_experience_map.md | Active | Master navigation (данный документ) |

**Слои зафиксированы:**
- Route layer: полностью документирован
- Human journey layer: полностью документирован
- Agent layer: полностью документирован
- Message layer: полностью документирован
- Memory layer: полностью документирован
- Technical layer: задокументирован высокоуровнево
- Freeze boundary: чётко определена

**Implementation readiness:**
- Phase A (DB migration): SQL spec готов в migrate_route_state.sql
- Phase B (context_package): требует Phase A
- Phase C–F: требуют Phase A+B

### Next implementation step after freeze

1. Официальное снятие freeze (governance commit)
2. Health check: 7 чистых дней без ORCH FATAL
3. DB backup
4. Phase A: применить migrate_route_state.sql
5. Verify и продолжить по плану

---

## 13. Future Evolution Principles

### Не плодить агентов

10 существующих агентов покрывают все функциональные потребности системы. Каждый новый агент — это новый реестр, новый промпт, новое место конфликта. Прежде чем добавлять агента — исчерпать возможности расширения существующих промптов.

### Не превращать систему в хаос

Сложность не равна возможностям. Чем больше агентов, маршрутов, правил — тем выше риск несогласованности, которую человек почувствует как хаос. Простая система, работающая последовательно, лучше сложной системы с дырами.

### Continuity over complexity

Любое изменение системы должно сначала проверяться: усиливает ли оно ощущение непрерывности или разрушает его? Если новая функция добавляет возможность, но нарушает continuity — это плохой trade-off.

### Expansion only through architectural alignment

Перед расширением — сначала архитектурный документ. Сначала спецификация в docs/. Потом реализация. Никогда не наоборот. Это урок текущего цикла: docs-first strategy создаёт устойчивость.

### AI should feel like one center

Вне зависимости от количества агентов, маршрутов и технических слоёв — человек должен чувствовать один голос. Один центр. Одно присутствие. Это не технологическая задача. Это архитектурная дисциплина.

---

## 14. Final System Formula

Python Method Center должен ощущаться:

**Как единая система сопровождения.** Не как сборка несвязанных модулей, которые "вроде работают вместе". Как живая, связная структура, где каждый элемент знает своё место.

**Не как набор ботов.** Клиент не должен замечать Lucky, Hannah, Maya или Nadia. Клиент должен чувствовать: центр. Один голос. Одно присутствие.

**Не как медицинская машина.** Система работает с людьми в уязвимых состояниях. Клинический холод, формальные подтверждения, обезличенные ответы — это разрушает доверие быстрее, чем любая техническая ошибка.

**Не как воронка продаж.** Оплата — это вход в сопровождение, не финальная цель системы. Если система ощущается как воронка — она перестаёт быть центром.

**А как структурированное цифровое пространство continuity, navigation и accompaniment.**

Continuity: система помнит. Путь не начинается заново.
Navigation: система помогает человеку понять, где он и куда движется.
Accompaniment: система рядом. Не только в момент запроса — но как фоновое присутствие, которое держит нить.

Именно это отличает Python Method Center от чата, бота, FAQ и CRM.

---

Document Type: AI Operating Experience Framework — Master Navigation Document
Version: 1.0
Status: Freeze-Safe — Documentation Only
Layer coverage: Human Journey, Route, Agent, Message, Memory, Emotional Safety, Karen Integration, Technical, Freeze Boundary, Current State
Based on: route_architecture.md (6a346e6), client_onboarding_experience.md (786e726), client_message_library.md (eb521d1), agent_role_specification.md (98ad0b1), memory_experience_architecture.md (25e5c2a), route_implementation_plan_after_freeze.md (849471c), stabilization_freeze_notice.md
Next review: after stabilization freeze lift
