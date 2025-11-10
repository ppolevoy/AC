# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**AC (Application Control)** is a Flask-based application management platform that provides centralized control over distributed applications across multiple servers. It monitors application states, orchestrates updates, and manages deployment workflows through Ansible integration.

## Running the Application

### Development
```bash
# Run the Flask application
python main.py --config development --debug

# Initialize/reset database
python init-db.py --config development

# Initialize with demo data
python init-db.py --config development --demo
```

### Production
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

### Core Concepts

**Servers** → **Applications** → **Application Groups** → **Application Instances**

1. **Servers** (`app/models/server.py`): Physical or virtual hosts running applications
   - Monitored via FAgent API for application discovery
   - Can be designated as HAProxy nodes

2. **Applications** (`app/models/application.py`): Individual app installations
   - Types: `docker`, `eureka`, `site`, `service`
   - Parsed name format: `{app_name}_{instance_number}` (e.g., `jurws_1`, `mobws_2`)
   - Linked to Application Groups for batch operations

3. **Application Groups** (`app/models/application_group.py`): Logical grouping of app instances
   - Stores shared settings (artifact URLs, playbook paths, artifact extensions)
   - Supports batch grouping strategies: `by_group`, `by_server`, `by_instance_name`, `no_grouping`

4. **Application Instances** (`app/models/application_group.py:ApplicationInstance`): Junction table
   - Links Applications to Groups
   - Allows per-instance overrides of group settings
   - Stores `original_name`, `instance_number`, custom playbook/artifact URLs

### Task Queue System

Located in `app/tasks/queue.py`, provides asynchronous task execution:

- **Task types**: `start`, `stop`, `restart`, `update`
- Runs in a dedicated thread with persistent task storage
- Tasks stored in memory dict and events persisted to DB
- On startup, marks interrupted tasks as failed
- Supports batch operations for grouped applications

### Ansible Integration

Two modes of operation (controlled by `USE_SSH_ANSIBLE` config):

1. **SSH Mode** (default, `app/services/ssh_ansible_service.py`):
   - Executes Ansible playbooks via SSH on remote Ansible control host
   - Supports parameter substitution: `{server}`, `{app}`, `{distr_url}`, etc.
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

### HAProxy Management Module

Architecture documented in `haproxy_module_architecture.md`. Key features:

- Periodic synchronization of HAProxy backend server states
- Circuit breaker pattern for reliability
- Server state management: `drain`, `maint`, `ready`
- Automatic application-to-backend-server mapping
- Audit trail for all operations

**Models** (when implemented):
- `haproxy_instances`: HAProxy server instances
- `haproxy_backends`: Backend pools
- `haproxy_servers`: Individual servers in backends
- `haproxy_actions`: Command audit log
- `haproxy_server_status_history`: Status change history

### API Structure

Located in `app/api/`:

- **`__init__.py`**: Registers all API blueprints under `/api` prefix
- **`routes.py`**: Core application/server CRUD and batch update operations
- **`app_groups_routes.py`**: Application group management
- **`orchestrator_routes.py`**: Orchestrator playbook discovery and metadata
- **`nexus_routes.py`**: Nexus artifact repository integration
- **`web.py`**: Server-sent events (SSE) for real-time updates

### Monitoring

Background monitoring tasks in `app/tasks/monitoring.py`:

- Periodic server polling via FAgent API
- Application state updates
- Event logging for status changes

## Key Configuration Variables

From `app/config.py`:

- `ANSIBLE_DIR` / `ANSIBLE_PATH`: Base directory for Ansible playbooks
- `DEFAULT_UPDATE_PLAYBOOK`: Fallback playbook path
- `USE_SSH_ANSIBLE`: Enable SSH-based Ansible execution
- `SSH_*`: SSH connection parameters for remote Ansible host
- `POLLING_INTERVAL`: Server monitoring frequency (default: 60s)
- `ORCHESTRATOR_SCAN_PATTERN`: Pattern for discovering orchestrator playbooks

## Playbook Path Resolution

Priority order (highest to lowest):
1. `ApplicationInstance.custom_playbook_path`
2. `Application.update_playbook_path`
3. `ApplicationGroup.update_playbook_path`
4. `Config.DEFAULT_UPDATE_PLAYBOOK`

## Batch Update Strategies

Defined in `app/models/application_group.py:BATCH_GROUPING_STRATEGIES`:

- **`by_group`**: Group by (server, playbook, group_id) - separate tasks per group
- **`by_server`**: Group by (server, playbook) - ignore group boundaries
- **`by_instance_name`**: Group by (server, playbook, original_name) - by instance name
- **`no_grouping`**: Each application instance gets its own task

Batch tasks in `app/api/routes.py:batch_update_applications()` create Task objects with `app_ids` list parameter, processed in `app/tasks/queue.py:_process_update_task()`.

## Working with the Codebase

### Adding a New Application Type

1. Add type constant to `Application.app_type` validation
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
