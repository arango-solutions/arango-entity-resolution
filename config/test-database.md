# Test Database Configuration

**Purpose:** Persistent test database for arango-entity-resolution library
**Container:** `arango-entity-resolution-test`

---

## Quick Reference

| Setting | Value |
|---------|-------|
| **Container Name** | `arango-entity-resolution-test` |
| **Image** | `arangodb/arangodb:3.12` |
| **Port** | `8532` (mapped to internal 8529) |
| **Root Password** | `$ARANGO_TEST_PASSWORD` (set in your environment or `.env`) |
| **Default Database** | `entity_resolution` |
| **Web UI** | http://localhost:8532 |

The compose file reads the root password from the `ARANGO_TEST_PASSWORD`
environment variable and refuses to start without it. Pick any value and put it
in your shell profile or the project `.env` (which is gitignored):

```bash
export ARANGO_TEST_PASSWORD='choose-a-local-test-password'
```

---

## Usage

### Starting the Test Container

```bash
docker-compose -f docker-compose.test.yml up -d
```

### Stopping the Test Container

```bash
docker-compose -f docker-compose.test.yml down
```

### Accessing ArangoDB Web UI

Open: http://localhost:8532

- **Username:** `root`
- **Password:** value of `$ARANGO_TEST_PASSWORD`
- **Database:** `entity_resolution`

---

## Running Tests

```bash
ARANGO_ROOT_PASSWORD="$ARANGO_TEST_PASSWORD" ARANGO_HOST=localhost ARANGO_PORT=8532 \
  python3 -m pytest -m integration
```

### Create Test Database (if needed)

```python
import os
from arango import ArangoClient

client = ArangoClient(hosts='http://localhost:8532')
sys_db = client.db('_system', username='root', password=os.environ['ARANGO_TEST_PASSWORD'])

if not sys_db.has_database('entity_resolution'):
    sys_db.create_database('entity_resolution')
```

---

## Container Management

```bash
docker ps | grep arango-entity-resolution-test   # status
docker logs arango-entity-resolution-test        # logs
docker restart arango-entity-resolution-test     # restart
```

### Remove Container and Data (Clean Start)

```bash
docker-compose -f docker-compose.test.yml down -v
docker-compose -f docker-compose.test.yml up -d
```

---

## Why a Dedicated Test Container?

1. **No Port Conflicts:** Uses port 8532 (other containers use 8529, 8530, 8531)
2. **Known Credentials:** Always whatever you set `ARANGO_TEST_PASSWORD` to
3. **Isolated Data:** Won't interfere with other projects
4. **Persistent:** Data survives container restarts via Docker volumes
5. **Clean State:** Can easily reset by removing volumes

Note: `scripts/run_tests_with_temp_arango.sh` is the preferred way to run the
full suite; it starts a throwaway container on a free port with a generated
password and cleans up afterwards.

---

## Troubleshooting

### Container Won't Start

- `error ... ARANGO_TEST_PASSWORD` from docker-compose: export the variable (see Quick Reference).
- Port in use: `lsof -i :8532`, then stop the conflicting service or change the port mapping.

### Authentication Failed

The container keeps the password it was *first created* with (it is stored in the
Docker volume). If you changed `ARANGO_TEST_PASSWORD` after the first start,
either reset the volumes (`down -v && up -d`) or keep using the original value.

---

## Integration with CI/CD

```yaml
# Example GitHub Actions
services:
  arangodb:
    image: arangodb/arangodb:3.12
    env:
      ARANGO_ROOT_PASSWORD: ${{ secrets.ARANGO_TEST_PASSWORD }}
    ports:
      - 8532:8529

steps:
  - name: Run Tests
    run: python3 -m pytest -m integration
    env:
      ARANGO_ROOT_PASSWORD: ${{ secrets.ARANGO_TEST_PASSWORD }}
      ARANGO_HOST: localhost
      ARANGO_PORT: 8532
```

---

## Persistence

**Data Location:** Docker volumes
- `arango-entity-resolution_arango_test_data`
- `arango-entity-resolution_arango_test_apps`

```bash
docker volume ls | grep arango-entity-resolution
```
