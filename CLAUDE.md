# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**AC (Application Control)** is a Flask-based application management platform that provides centralized control over distributed applications across multiple servers. It monitors application states, orchestrates updates, and manages deployment workflows through Ansible integration with HAProxy and Eureka service discovery support.

## Deployment Environment

The application runs in a containerized environment:

| Component | Container Name | External Port | Internal Port |
|-----------|----------------|---------------|---------------|
| Application | `fak-apps` | 17071 | 5000 |
| Database | `pg-fak` | - | 5432 |

### Container Commands
```bash
# View application logs
docker logs fak-apps

# Restart application
docker restart fak-apps

# Access application shell
docker exec -it fak-apps /bin/bash

# Access database
docker exec -it pg-fak psql -U <user> -d <database>
```

### Access URL
- Local: http://localhost:17071
- Network: http://<host-ip>:17071

## Running the Application

### Development (outside container)
```bash
# Run the Flask application
python main.py --config development --debug

# Initialize/reset database
python init-db.py --config development

# Initialize with demo data
python init-db.py --config development --demo
```

### Production (in container)
```bash
# Run without debug mode
python main.py --config production --host 0.0.0.0 --port 5000
```

## Database Management

The application uses PostgreSQL and Flask-Migrate (Alembic) for database management.

### Database Configuration
Database connection is configured via environment variables (see `app/config.py:get_database_url()`):
- `DATABASE_URL` - Full connection string (takes precedence)
- OR individual params: `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`

### Migrations
```bash
# Create a migration
flask db migrate -m "Description"

# Apply migrations
flask db upgrade

# Rollback
flask db downgrade
```

## Architecture

### Core Data Model Hierarchy

**Server** → **ApplicationInstance** → **ApplicationGroup** ← **ApplicationCatalog**

1. **Server** (`app/models/server.py`): Physical or virtual hosts running applications
   - Monitored via FAgent API for application discovery
   - Flags: `is_haproxy_node`, `is_eureka_node`
   - Relationships: instances, events, haproxy_instances, eureka_server

2. **ApplicationCatalog** (`app/models/application_catalog.py`): Centralized registry of application types
   - Stores defaults: `default_playbook_path`, `default_artifact_url`, `default_artifact_extension`
   - Referenced by ApplicationGroup for type-specific defaults

3. **ApplicationInstance** (`app/models/application_instance.py`): Actual app instances running on servers
   - Types: `docker`, `eureka`, `site`, `service`
   - Parsed name format: `{app_name}_{instance_number}` (e.g., `jurws_1`, `mobws_2`)
   - Status: `online`, `offline`, `unknown`, `starting`, `stopping`, `no_data`
   - Docker-specific: `container_id`, `container_name`, `compose_project_dir`, `image`, `tag`
   - Eureka-specific: `eureka_url`, `eureka_registered`
   - Custom overrides: `custom_playbook_path`, `custom_artifact_url`, `custom_artifact_extension`
   - Soft delete via `deleted_at`, tag support via `tags_cache`

4. **ApplicationGroup** (`app/models/application_group.py`): Logical grouping of app instances
   - Stores shared settings (artifact URLs, playbook paths, artifact extensions)
   - Batch grouping strategies: `by_group`, `by_server`, `by_instance_name`, `no_grouping`
   - Methods: `sync_playbook_to_instances()`, `get_effective_playbook_path()`
   - Tag support with `tags_cache`

5. **Event** (`app/models/event.py`): Action history
   - Foreign key: `instance_id` (references ApplicationInstance)
   - Types: `start`, `stop`, `restart`, `update`, `connect`, `disconnect`
   - Status: `success`, `failed`, `pending`

### Tagging System

Comprehensive tagging in `app/models/tag.py`:
- **Tag**: Entity with metadata (`display_name`, `description`, `icon`, `tag_type`, `css_class`, `border_color`, `text_color`)
- Many-to-many relationships with ApplicationInstance and ApplicationGroup
- **TagHistory**: Audit trail for all assignments/removals
- Auto-updating `tags_cache` on both entities for fast filtering
- SQLAlchemy event listeners for automatic cache updates

### HAProxy Integration

Fully implemented in `app/models/haproxy.py`:

- **HAProxyInstance**: HAProxy instances accessible via FAgent
- **HAProxyBackend**: Backend pools with polling configuration
- **HAProxyServer**: Individual servers in backends
  - Fields: `status`, `weight`, `check_status`, `addr`
  - Metrics: `last_check_duration`, `downtime`, `sessions` (scur, smax)
  - Soft delete support
- **HAProxyServerStatusHistory**: Audit trail for status changes
- **HAProxyMappingHistory**: Audit trail for application mappings

Features:
- Periodic synchronization of backend server states
- Circuit breaker pattern for reliability
- Server state management: `drain`, `maint`, `ready`
- Automatic application-to-backend-server mapping

### Eureka Integration

Fully implemented in `app/models/eureka.py`:

- **EurekaServer**: Eureka registry servers with monitoring
- **EurekaApplication**: Apps registered in Eureka with statistics
- **EurekaInstance**: Individual service instances
  - Fields: `instance_id`, `ip_address`, `port`, `service_name`, `status`
  - Metadata, health_check_url, home_page_url, status_page_url
  - Soft delete and restoration support
- **EurekaInstanceStatusHistory**: Status change audit trail
- **EurekaInstanceAction**: Action journal (health_check, pause, shutdown, log_level_change)

### Application Mapping

Unified mapping in `app/models/application_mapping.py`:
- **ApplicationMapping**: Maps apps to external services (HAProxy, Eureka)
- Entity types: `HAPROXY_SERVER`, `EUREKA_INSTANCE` (extensible)
- Metadata: `is_manual`, `mapped_by`, `mapped_at`, `notes`, `is_active`
- **ApplicationMappingHistory**: Full audit trail with `old_values` and `new_values` (JSONB)

### Task Queue System

Located in `app/tasks/queue.py`, provides asynchronous task execution:

- **Task types**: `start`, `stop`, `restart`, `update`
- **Task states**: `pending`, `processing`, `completed`, `failed`
- Runs in a dedicated thread with persistent task storage
- Tasks stored in memory dict and events persisted to DB
- On startup, marks interrupted tasks as failed
- Supports batch operations for grouped applications

### Ansible Integration

Two modes of operation (controlled by `USE_SSH_ANSIBLE` config):

1. **SSH Mode** (default, `app/services/ssh_ansible_service.py`):
   - Executes Ansible playbooks via SSH on remote Ansible control host
   - Parameter substitution: `{server}`, `{app}`, `{distr_url}`, `{hostname}`, etc.
   - Custom parameters: `{param_name=value}`
   - Extra parameters passed as `--extra-vars` JSON

2. **Local Mode** (`app/services/ansible_service.py`):
   - Direct subprocess execution (deprecated)

### Orchestrator Playbooks

Special playbooks for zero-downtime updates with HAProxy integration:

- **Discovery**: Scanned from `ANSIBLE_PATH` using `ORCHESTRATOR_SCAN_PATTERN` (default: `*orchestrator*.yml`)
- **Parser** (`app/services/orchestrator_parser.py`): Extracts metadata from YAML comments
- **Model** (`app/models/orchestrator_playbook.py`): Stores parsed metadata (name, version, required/optional params)
- **Scanner** (`app/services/orchestrator_scanner.py`): Runs on startup to populate database

**Orchestrator workflow**:
1. Drain servers from HAProxy (`drain` command)
2. Wait for connections to close (`drain_delay`)
3. Execute update playbook on drained servers
4. Wait for app startup (`wait_after_update`)
5. Return servers to HAProxy pool (`ready`)
6. Repeat for next batch

**Parameter format**: Orchestrator playbooks receive composite names `{hostname}::{app_name}` (e.g., `fdmz01::jurws_1,fdmz02::jurws_2`)

### Services Layer

Located in `app/services/`:

| Service | Description |
|---------|-------------|
| `agent_service.py` | FAgent communication, async with aiohttp |
| `ssh_ansible_service.py` | SSH-based Ansible execution (primary) |
| `ansible_service.py` | Local Ansible execution (deprecated) |
| `application_group_service.py` | Group operations and batch processing |
| `orchestrator_scanner.py` | Playbook discovery and DB sync |
| `orchestrator_parser.py` | YAML metadata extraction |
| `eureka_service.py` | Eureka server integration |
| `eureka_mapper.py` | Automatic Eureka instance mapping |
| `haproxy_service.py` | HAProxy backend management |
| `haproxy_mapper.py` | Automatic HAProxy server mapping |
| `mapping_service.py` | Unified mapping operations |
| `nexus_artifact_service.py` | Maven artifact repository |
| `nexus_docker_service.py` | Docker image registry |

### API Structure

Located in `app/api/`:

| Route File | Description |
|------------|-------------|
| `servers_routes.py` | Server CRUD and monitoring |
| `applications_routes.py` | Application instance management |
| `app_groups_routes.py` | Application group operations |
| `tasks_routes.py` | Task queue monitoring |
| `orchestrator_routes.py` | Orchestrator playbook discovery |
| `ansible_routes.py` | Ansible variable validation |
| `artifacts_routes.py` | Artifact listing and management |
| `nexus_routes.py` | Nexus integration |
| `haproxy_routes.py` | HAProxy backend monitoring and control |
| `eureka_routes.py` | Eureka service discovery |
| `mappings_routes.py` | Application-to-service mappings |
| `tags_routes.py` | Tag management with full CRUD |
| `ssh_routes.py` | SSH/Ansible settings |
| `web.py` | Server-sent events (SSE) for real-time updates |

### Monitoring

Background monitoring tasks in `app/tasks/monitoring.py`:

- Periodic server polling via FAgent API
- Application state updates
- Event logging for status changes

## Key Configuration Variables

From `app/config.py`:

### Database
- `DATABASE_URL`: Full PostgreSQL connection string
- `POSTGRES_*`: Individual connection params

### Polling Intervals
- `POLLING_INTERVAL`: Server monitoring (default: 60s)
- `HAPROXY_POLLING_INTERVAL`: HAProxy sync (default: 60s)
- `EUREKA_POLLING_INTERVAL`: Eureka sync (default: 60s)

### HAProxy
- `HAPROXY_ENABLED`: Enable HAProxy integration (default: true)
- `HAPROXY_CACHE_TTL`: Cache duration (default: 30s)
- `HAPROXY_HISTORY_RETENTION_DAYS`: History cleanup (default: 30)
- `HAPROXY_REQUEST_TIMEOUT`: Request timeout (default: 10s)
- `HAPROXY_MAX_RETRIES`: Max retry attempts (default: 3)

### Eureka
- `EUREKA_ENABLED`: Enable Eureka integration (default: true)
- `EUREKA_CACHE_TTL`: Cache duration (default: 30s)
- `EUREKA_CACHE_MAX_SIZE`: Max cache entries (default: 1000)
- `EUREKA_HEALTH_CHECK_INTERVAL`: Health check interval (default: 30s)
- `EUREKA_HISTORY_RETENTION_DAYS`: History cleanup (default: 30)
- `EUREKA_MAX_HISTORY_RECORDS`: Max history records (default: 10000)

### Ansible
- `USE_SSH_ANSIBLE`: Enable SSH-based execution (default: true)
- `SSH_HOST`, `SSH_USER`, `SSH_PORT`, `SSH_KEY_FILE`: SSH connection params
- `ANSIBLE_PATH`: Base directory (default: `/etc/ansible`)
- `DEFAULT_UPDATE_PLAYBOOK`: Fallback playbook path
- `ORCHESTRATOR_SCAN_PATTERN`: Discovery pattern (default: `*orchestrator*.yml`)

### Docker
- `DOCKER_UPDATE_PLAYBOOK`: Docker update playbook path
- `DOCKER_REGISTRY_URL`: Docker registry URL
- `MAX_DOCKER_IMAGES_DISPLAY`: Max images to display (default: 30)

## Playbook Path Resolution

Priority order (highest to lowest):
1. `ApplicationInstance.custom_playbook_path`
2. `ApplicationGroup.update_playbook_path`
3. `ApplicationCatalog.default_playbook_path`
4. `Config.DEFAULT_UPDATE_PLAYBOOK`

## Batch Update Strategies

Defined in `app/models/application_group.py:BATCH_GROUPING_STRATEGIES`:

- **`by_group`**: Group by (server, playbook, group_id) - separate tasks per group
- **`by_server`**: Group by (server, playbook) - ignore group boundaries
- **`by_instance_name`**: Group by (server, playbook, original_name) - by instance name
- **`no_grouping`**: Each application instance gets its own task

## Architectural Patterns

- **Blueprint-based modular API**: Each feature has its own routes module
- **Service layer abstraction**: Business logic separated from routes
- **Audit trail pattern**: History tables for all critical state changes
- **Soft delete pattern**: Logical deletion with `deleted_at`/`removed_at` timestamps
- **Cache optimization**: `tags_cache` for fast filtering
- **Event listener pattern**: SQLAlchemy event hooks for automatic updates
- **Configuration-driven behavior**: Extensive environment variable configuration
- **Async-ready design**: Uses aiohttp for agent communication

## Working with the Codebase

### Adding a New Application Type

1. Add type constant to `ApplicationInstance.app_type` validation in `app/models/application_instance.py`
2. Update FAgent protocol in `app/services/agent_service.py`
3. Add type-specific logic in `app/tasks/queue.py:_process_*_task()` methods

### Adding a New API Endpoint

1. Choose appropriate blueprint in `app/api/`
2. Add route handler
3. Use `db.session` for database operations
4. Return JSON responses with appropriate status codes
5. Blueprint auto-registered in `app/api/__init__.py`

### Database Schema Changes

1. Modify model in `app/models/`
2. Generate migration: `flask db migrate -m "Description"`
3. Review generated migration in `migrations/versions/`
4. Apply: `flask db upgrade`
5. For complex changes, edit migration file manually before applying

### Adding Orchestrator Metadata Fields

1. Update parser in `app/services/orchestrator_parser.py`
2. Add fields to `OrchestratorPlaybook` model
3. Create database migration
4. Update `to_dict()` method for API exposure

### Adding a New External Service Integration

1. Create models in `app/models/` with appropriate history tables
2. Add entity type to `ApplicationMapping.entity_type`
3. Create service in `app/services/` for API communication
4. Create mapper service for automatic mapping
5. Add routes in `app/api/` for management endpoints
6. Update configuration in `app/config.py`

## Frontend Structure

### JavaScript Modules

Located in `app/static/js/`:

- `applications/` - Main app management UI
  - `applications.js`, `app-groups-management.js`
  - Core: `api-service.js`, `state-manager.js`, `dom-utils.js`, `config.js`, `security-utils.js`
  - Modals: `tags-modal.js`, `update-modal.js`, `info-modal.js`
  - `artifacts-manager.js`

- `haproxy/` - HAProxy management
  - `manager.js`, `ui.js`, `filters.js`, `api.js`

- `eureka/` - Eureka service discovery UI

- `servers/` - Server management
  - `servers.js`, `server-details.js`

- `common/` - Shared utilities

### HTML Templates

Located in `app/templates/`:
- `base.html` - Base layout
- `servers.html`, `server_details.html` - Server views
- `applications.html` - Application management
- `eureka.html` - Eureka dashboard
- `haproxy.html` - HAProxy dashboard
- `settings.html` - Extensive configuration UI
- `ssh_settings.html` - SSH/Ansible settings
- `tasks.html` - Task queue view
