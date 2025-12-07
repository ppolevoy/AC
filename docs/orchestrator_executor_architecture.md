# Архитектура Orchestrator Executor

## 1. Архитектура компонентов

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              queue.py                                            │
│                         _process_update_task()                                   │
└─────────────────────────────────┬───────────────────────────────────────────────┘
                                  │
                                  │ 1. Загрузка контекста задачи
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                     UpdateTaskContextProvider                                    │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │  load(task_id) → UpdateTaskContext                                       │   │
│  │    • task, apps[], server, params                                        │   │
│  │    • is_batch, distr_url, mode, playbook_path                           │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────┬───────────────────────────────────────────────┘
                                  │
                                  │ 2. Создание контекста оркестратора
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                        OrchestratorContext                                       │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │  @dataclass (сессионный, создаётся для каждой задачи)                   │   │
│  │                                                                          │   │
│  │  Входные данные:          Вычисляемые поля:                             │   │
│  │  • task_id                • composite_names[]                           │   │
│  │  • apps[]                 • haproxy_backend                             │   │
│  │  • distr_url              • haproxy_api_url                             │   │
│  │  • orchestrator_playbook  • servers_apps_map{}                          │   │
│  │  • original_playbook_path                                               │   │
│  │  • drain_wait_time                                                      │   │
│  │  • required_params{}                                                    │   │
│  │  • optional_params{}                                                    │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────┬───────────────────────────────────────────────┘
                                  │
                                  │ 3. Выбор executor через Factory
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                    create_orchestrator_executor(context)                         │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │  Проверяет ApplicationMapping для apps:                                  │   │
│  │    • Есть HAProxy mapping? → HAProxyOrchestratorExecutor                │   │
│  │    • Нет mapping?          → SimpleOrchestratorExecutor                 │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
└──────────────────┬─────────────────────────────────┬────────────────────────────┘
                   │                                 │
                   ▼                                 ▼
┌──────────────────────────────────┐  ┌──────────────────────────────────┐
│  HAProxyOrchestratorExecutor     │  │  SimpleOrchestratorExecutor      │
│  ────────────────────────────    │  │  ────────────────────────────    │
│  • HAProxy drain/ready workflow  │  │  • Простой rolling update        │
│  • composite: srv::app::haproxy  │  │  • composite: srv::app           │
│  • Загружает backend, API URL    │  │  • Без внешних зависимостей      │
└──────────────────────────────────┘  └──────────────────────────────────┘
```

## 2. Template Method Pattern — executor.prepare()

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                    OrchestratorExecutor.prepare()                                │
│                         (Template Method)                                        │
└─────────────────────────────────────────────────────────────────────────────────┘
                                  │
        ┌─────────────────────────┼─────────────────────────┐
        │                         │                         │
        ▼                         ▼                         ▼
┌───────────────────┐  ┌───────────────────┐  ┌───────────────────┐
│ 1. _build_        │  │ 2. Parse custom   │  │ 3. _build_base_   │
│    composite_     │  │    params from    │  │    param_values() │
│    names()        │  │    playbook_path  │  │                   │
│   [ABSTRACT]      │  │                   │  │ • app_instances   │
│                   │  │ {server}          │  │ • drain_delay     │
│ HAProxy: 6 batch  │  │ {unpack=true}     │  │ • update_playbook │
│ Simple:  1 batch  │  │ {mode=deliver}    │  │ • distr_url       │
└───────────────────┘  └───────────────────┘  └───────────────────┘
        │                         │                         │
        └─────────────────────────┼─────────────────────────┘
                                  │
        ┌─────────────────────────┼─────────────────────────┐
        │                         │                         │
        ▼                         ▼                         ▼
┌───────────────────┐  ┌───────────────────┐  ┌───────────────────┐
│ 4. Merge custom   │  │ 5. _add_specific_ │  │ 6. Build final    │
│    params into    │  │    params()       │  │    outputs        │
│    param_values   │  │   [VIRTUAL]       │  │                   │
│                   │  │                   │  │ • playbook_path   │
│                   │  │ HAProxy adds:     │  │   with {params}   │
│                   │  │ • haproxy_backend │  │ • extra_params{}  │
│                   │  │ • haproxy_api_url │  │   for Ansible     │
└───────────────────┘  └───────────────────┘  └───────────────────┘
                                  │
                                  ▼
                    ┌───────────────────────────┐
                    │  Return:                  │
                    │  (playbook_path,          │
                    │   extra_params)           │
                    └───────────────────────────┘
```

## 3. Оптимизация N+1 — Batch Loading

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         ДО ОПТИМИЗАЦИИ (N+1)                                     │
│                    HAProxyOrchestratorExecutor                                   │
└─────────────────────────────────────────────────────────────────────────────────┘

  for app in apps (40 штук):                      SQL Запросы:
  ├── Server.query.get(app.server_id)         →   40 запросов
  ├── ApplicationMapping.query.filter_by()    →   40 запросов
  ├── HAProxyServer.query.get(mapping.id)     →   40 запросов
  ├── HAProxyBackend.query.get(server.id)     →   40 запросов
  └── HAProxyInstance.query.get(backend.id)   →   40 запросов
                                                  ──────────────
                                          ИТОГО:  ~200 запросов
                                                  ~1000ms при 5ms latency


┌─────────────────────────────────────────────────────────────────────────────────┐
│                        ПОСЛЕ ОПТИМИЗАЦИИ (Batch)                                 │
│                    HAProxyOrchestratorExecutor                                   │
└─────────────────────────────────────────────────────────────────────────────────┘

  ┌─────────────────────────────────────────────────────────────────────────────┐
  │  BATCH PRELOAD PHASE (6 SQL запросов)                                       │
  │                                                                              │
  │  1. Server.query.filter(id.in_(server_ids))          →  1 запрос           │
  │     servers_map = {id: server}                                              │
  │                                                                              │
  │  2. ApplicationMapping.query.filter(app_id.in_())    →  1 запрос           │
  │     mappings_map = {app_id: mapping}                                        │
  │                                                                              │
  │  3. HAProxyServer.query.filter(id.in_())             →  1 запрос           │
  │     haproxy_servers = {id: server}                                          │
  │                                                                              │
  │  4. HAProxyBackend.query.filter(id.in_())            →  1 запрос           │
  │     backends_map = {id: backend}                                            │
  │                                                                              │
  │  5. HAProxyInstance.query                            →  1 запрос           │
  │       .options(joinedload(server))  ←─ eager load                          │
  │       .filter(id.in_())                                                     │
  │     haproxy_instances_map = {id: instance}                                  │
  │                                                                              │
  │  6. (sort_instances_for_batches уже оптимизирован)   →  1 запрос           │
  └─────────────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
  ┌─────────────────────────────────────────────────────────────────────────────┐
  │  PROCESSING PHASE (0 SQL запросов — только чтение из maps)                  │
  │                                                                              │
  │  for app in sorted_apps:                                                    │
  │      server = servers_map[app.server_id]           ←─ O(1) lookup          │
  │      mapping = mappings_map[app.id]                ←─ O(1) lookup          │
  │      haproxy_server = haproxy_servers[mapping.id]  ←─ O(1) lookup          │
  │      backend = backends_map[server.backend_id]     ←─ O(1) lookup          │
  │      instance = haproxy_instances_map[backend.id]  ←─ O(1) lookup          │
  │                                                                              │
  │      composite_names.append(f"{srv}::{app}::{haproxy}")                     │
  └─────────────────────────────────────────────────────────────────────────────┘

                                          ИТОГО:  ~6-8 запросов
                                                  ~30-40ms при 5ms latency
                                                  ─────────────────────────
                                                  УСКОРЕНИЕ: ~25x
```

## 4. Полный Flow выполнения задачи обновления

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                              USER REQUEST                                     │
│                    "Обновить 40 приложений в группе"                         │
└──────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│  queue.py :: _process_update_task(task_id)                                   │
│                                                                               │
│  1. ─────────────────────────────────────────────────────────────────────────│
│     ctx = UpdateTaskContextProvider.load(task_id)                            │
│     • Загружает Task, Apps[], Server из БД                                   │
│     • Определяет is_batch, playbook_path, mode                               │
│                                                                               │
│  2. ─────────────────────────────────────────────────────────────────────────│
│     if should_use_orchestrator(ctx):                                         │
│         orchestrator_metadata = load_orchestrator_metadata()                 │
│                                                                               │
│  3. ─────────────────────────────────────────────────────────────────────────│
│         orch_context = OrchestratorContext(                                  │
│             task_id, apps, distr_url,                                        │
│             orchestrator_playbook,                                           │
│             original_playbook_path,                                          │
│             required_params, optional_params                                 │
│         )                                                                    │
│                                                                               │
│  4. ─────────────────────────────────────────────────────────────────────────│
│         executor = create_orchestrator_executor(orch_context)                │
│         │                                                                    │
│         ├── Check ApplicationMapping                                         │
│         │   └── HAProxy mapping found? → HAProxyOrchestratorExecutor        │
│         │   └── No mapping?            → SimpleOrchestratorExecutor         │
│                                                                               │
│  5. ─────────────────────────────────────────────────────────────────────────│
│         playbook_path, extra_params = executor.prepare()                     │
│         │                                                                    │
│         ├── _build_composite_names()     [6 batch SQL queries]              │
│         ├── Parse custom params          [no SQL]                           │
│         ├── _build_base_param_values()   [no SQL]                           │
│         ├── _add_specific_params()       [no SQL]                           │
│         └── Build playbook_path + extra_params                              │
│                                                                               │
│  6. ─────────────────────────────────────────────────────────────────────────│
│         ssh_service.update_application(                                      │
│             server_name, app_name, app_id,                                   │
│             distr_url, mode,                                                 │
│             playbook_path,    ← "orchestrator.yml {app_instances} {backend}" │
│             extra_params      ← {app_instances: "srv::app::haproxy,..."}    │
│         )                                                                    │
└──────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│  ssh_ansible_service.py :: update_application()                              │
│                                                                               │
│  1. _prepare_update_context()   → Подготовка Ansible команды                 │
│  2. _execute_ansible_command()  → SSH выполнение на control host             │
│  3. _finalize_update_result()   → Парсинг результата, обновление БД          │
└──────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                          ANSIBLE PLAYBOOK                                     │
│                      orchestrator-even-odd.yml                                │
│                                                                               │
│  Получает параметры:                                                         │
│  • app_instances: "fdmz01::jurws_1::srv1,fdmz02::jurws_1::srv2,..."         │
│  • haproxy_backend: "jurws_backend"                                          │
│  • haproxy_api_url: "http://10.0.0.1:5000/api/v1/haproxy/default"           │
│  • drain_delay: 300                                                          │
│  • distr_url: "http://nexus/app.zip"                                        │
│                                                                               │
│  Выполняет:                                                                  │
│  1. EVEN batch: drain → update → ready                                       │
│  2. ODD batch:  drain → update → ready                                       │
└──────────────────────────────────────────────────────────────────────────────┘
```

## 5. Диаграмма классов (UML-style)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          <<abstract>>                                        │
│                      OrchestratorExecutor                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│ - context: OrchestratorContext                                               │
├─────────────────────────────────────────────────────────────────────────────┤
│ + prepare() : Tuple[str, Dict]              ← Template Method               │
│ + sort_instances_for_batches() : List[App]                                  │
│ # _build_composite_names() : void           ← Abstract                      │
│ # _add_specific_params(params) : void       ← Virtual (hook)                │
│ # _build_base_param_values() : Dict                                         │
│ # _calculate_drain_delay_seconds() : int                                    │
│ # _extract_update_playbook_name() : str                                     │
│ # _get_short_server_name(server) : str                                      │
└─────────────────────────────────────────────────────────────────────────────┘
                          △                    △
                          │                    │
           ┌──────────────┘                    └──────────────┐
           │                                                  │
┌──────────────────────────────┐            ┌──────────────────────────────┐
│ HAProxyOrchestratorExecutor  │            │ SimpleOrchestratorExecutor   │
├──────────────────────────────┤            ├──────────────────────────────┤
│ # _build_composite_names()   │            │ # _build_composite_names()   │
│   → srv::app::haproxy        │            │   → srv::app                 │
│   → 6 batch queries          │            │   → 1 batch query            │
│                              │            │                              │
│ # _add_specific_params()     │            │ (uses default - no-op)       │
│   → haproxy_backend          │            │                              │
│   → haproxy_api_url          │            │                              │
└──────────────────────────────┘            └──────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                       <<dataclass>>                                          │
│                    OrchestratorContext                                       │
├─────────────────────────────────────────────────────────────────────────────┤
│ + task_id: str                                                               │
│ + apps: List[ApplicationInstance]                                            │
│ + distr_url: str                                                             │
│ + orchestrator_playbook: str                                                 │
│ + original_playbook_path: str                                                │
│ + drain_wait_time: Optional[float]                                           │
│ + required_params: Dict[str, Any]                                            │
│ + optional_params: Dict[str, Any]                                            │
│ ─────────────────────────────────── computed ───────────────────────────────│
│ + composite_names: List[str]        ← filled by executor                    │
│ + haproxy_backend: Optional[str]    ← filled by HAProxy executor            │
│ + haproxy_api_url: Optional[str]    ← filled by HAProxy executor            │
│ + servers_apps_map: Dict            ← filled by executor                    │
├─────────────────────────────────────────────────────────────────────────────┤
│ + __post_init__()  → validation                                             │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                       <<function>>                                           │
│              create_orchestrator_executor(context)                           │
├─────────────────────────────────────────────────────────────────────────────┤
│ Factory: выбирает executor на основе ApplicationMapping                      │
│                                                                              │
│ if any app has HAProxy mapping:                                              │
│     return HAProxyOrchestratorExecutor(context)                             │
│ else:                                                                        │
│     return SimpleOrchestratorExecutor(context)                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## 6. Метрики производительности

| Сценарий | До оптимизации | После оптимизации | Ускорение |
|----------|----------------|-------------------|-----------|
| 10 apps batch | ~50 SQL / 250ms | ~8 SQL / 40ms | 6x |
| 40 apps batch | ~200 SQL / 1000ms | ~8 SQL / 40ms | 25x |
| 100 apps batch | ~500 SQL / 2500ms | ~8 SQL / 40ms | 62x |

## 7. Файлы модуля

| Файл | Описание |
|------|----------|
| `app/services/orchestrator_executor.py` | Основной модуль с executor'ами |
| `app/services/update_task_context.py` | Провайдер контекста задачи |
| `app/core/playbook_parameters.py` | Парсер параметров playbook |
| `app/config.py` | Константы (OrchestratorDefaults) |
| `tests/test_orchestrator_executor.py` | Unit-тесты (16 тестов) |
